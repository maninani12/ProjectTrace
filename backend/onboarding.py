"""Evidence-backed new-hire and internal-transfer learning, with human review."""
import hashlib
import json
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select

from analyzers.engine import redact
from backend.admin_models import OrganizationMembership, Team, TeamMembership
from backend.db import Record, Repository, User, now
from backend.domain import audit
from backend.governance import future, permitted, repository_condition, require_feature, resolve_principal
from backend.onboarding_models import (
    LearningAssessment,
    LearningJourney,
    LearningObjective,
    LearningReview,
)
from backend.queue import cipher
from backend.security import authenticate, require_repo

router = APIRouter(prefix="/api/learning", tags=["Onboarding and Knowledge Transfer"])
ROLE_TOPICS = {
    "BACKEND": {"API", "DATABASE", "ARCHITECTURE", "TECHNOLOGY", "FRAMEWORK", "FUNCTION", "API_ENDPOINT"},
    "FRONTEND": {"API", "ARCHITECTURE", "TECHNOLOGY", "FRAMEWORK", "API_ENDPOINT", "FUNCTION"},
    "SECURITY": {"AUTHENTICATION", "SECURITY", "SAST", "SECRET", "IAC", "POLICY", "CONSISTENCY"},
    "PLATFORM": {"INFRASTRUCTURE", "CI", "DATABASE", "CONFIGURATION", "CI_WORKFLOW", "CLOUD_RESOURCE", "CONTAINER_WORKLOAD"},
    "GENERAL": set(),
}


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Start(Input):
    repository_id: str = Field(max_length=80)
    source_repository_id: str | None = Field(default=None, max_length=80)
    participant_id: str = Field(max_length=80)
    mentor_id: str = Field(max_length=80)
    manager_id: str = Field(max_length=80)
    team_id: str | None = Field(default=None, max_length=80)
    mode: Literal["NEW_HIRE", "INTERNAL_TRANSFER"]
    role: Literal["BACKEND", "FRONTEND", "SECURITY", "PLATFORM", "GENERAL"]
    skills: list[str] = Field(default_factory=list, max_length=30)
    request_key: str = Field(min_length=8, max_length=80)
    retention_days: int = Field(default=90, ge=7, le=180)


class Version(Input):
    version: int = Field(ge=1)


class Submission(Version):
    answer: str = Field(min_length=30, max_length=8000)
    evidence_ids: list[str] = Field(min_length=1, max_length=10)


class MentorReview(Version):
    score: int = Field(ge=0, le=4)
    notes: str = Field(min_length=10, max_length=2000)


class Completion(Version):
    notes: str = Field(min_length=10, max_length=2000)


class Skills(Version):
    skills: list[str] = Field(max_length=30)


@contextmanager
def session():
    from sqlalchemy.exc import IntegrityError
    from sqlalchemy.orm.exc import StaleDataError

    from backend.main import Session
    with Session() as db:
        try:
            yield db
        except (IntegrityError, StaleDataError):
            db.rollback()
            raise HTTPException(409, "The learning record changed or its scoped relationships are unavailable. Reload before retrying.") from None


def identity(db, request, mutation=False):
    actor, _ = authenticate(db, request, mutation, edit=False)
    require_feature(db, actor, "onboarding")
    return actor


def member(db, org, user_id):
    row = db.get(User, user_id)
    membership = db.get(OrganizationMembership, (org, user_id))
    if not row or not row.enabled or not membership or membership.state != "ACTIVE" or not future(membership.expires_at):
        raise HTTPException(404, "An active organization member is required.")
    actor = resolve_principal(db, row, org)
    if not actor.enabled:
        raise HTTPException(404, "An active organization member is required.")
    return actor


def latest(db, actor, repository_id, branch=None):
    require_repo(db, actor, repository_id)
    query = select(Record).where(Record.organization_id == actor.organization_id,
        Record.repository_id == repository_id, Record.kind == "snapshot")
    if branch:
        query = query.where(Record.data["branch"].as_string() == branch)
    row = snapshot_metadata(db, query.order_by(Record.created_at.desc(), Record.id.desc()).limit(1))
    if not row:
        raise HTTPException(409, "Publish a source snapshot before creating a learning path.")
    return row


def snapshot_metadata(db, query):
    row = db.execute(query.with_only_columns(Record.id, Record.kind, Record.organization_id, Record.repository_id,
        Record.data["branch"].as_string().label("branch"), Record.data["status"].as_string().label("status"),
        Record.data["analysis_coverage"]["summary"].label("coverage"))).first()
    if row is None:
        return None
    return SimpleNamespace(id=row.id, kind=row.kind, organization_id=row.organization_id,
                           repository_id=row.repository_id, data={"branch": row.branch, "status": row.status,
                           "analysis_coverage": {"summary": row.coverage or {}}})


def knowledge(db, actor, repository_id, snapshot=None):
    require_repo(db, actor, repository_id)
    snapshot = snapshot or latest(db, actor, repository_id)
    if (snapshot.kind, snapshot.organization_id, snapshot.repository_id) != ("snapshot", actor.organization_id, repository_id):
        raise HTTPException(404, "Learning snapshot is unavailable in this project.")
    rows, totals = [], {}
    for kind in ("claim", "graph_node", "finding"):
        query = select(Record).where(Record.organization_id == actor.organization_id,
            Record.repository_id == repository_id, Record.kind == kind,
            Record.data["scope"]["snapshot_id"].as_string() == snapshot.id)
        totals[kind] = db.scalar(select(func.count()).select_from(query.subquery()))
        rows.extend(db.scalars(query.order_by(Record.id).limit(100)))
    resources = []
    for row in rows:
        item = row.data
        category = item.get("category", item.get("class", "ENGINEERING"))
        if category in {"FUNCTION", "ARTIFACT", "OWNER", "DOCUMENTATION_SECTION"}:
            continue
        evidence_ids = list(dict.fromkeys(item.get("evidence_ids", [])))[:9]
        resources.append({"id": row.id, "kind": row.kind, "topic": category,
            "title": item.get("text", item.get("title", item.get("name", category))),
            "explanation": item.get("reason", item.get("explanation", "Captured static graph declaration; inspect its linked source.")),
            "status": item.get("status", item.get("authority", "STATIC")), "confidence": item.get("confidence", "UNSPECIFIED"),
            "path": item.get("path"), "line": item.get("line"), "evidence_ids": evidence_ids,
            "technology": item.get("expected") if isinstance(item.get("expected"), str) else None,
            "identity_id": item.get("identity_id", row.id)})
    return {"snapshot_id": snapshot.id, "branch": snapshot.data["branch"], "status": snapshot.data["status"],
        "coverage": snapshot.data.get("analysis_coverage", {}).get("summary", {}), "totals": totals,
        "resources": resources, "bounded_preview": True, "maximum_records_per_kind": 100,
        "limitations": ["Static source knowledge is scoped to a published snapshot.",
                         "Observed technologies and declared skills do not demonstrate employee competence."]}


def scope(db, actor, journey):
    if journey.organization_id != actor.organization_id or actor.id not in {
            journey.participant_id, journey.mentor_id, journey.manager_id}:
        raise HTTPException(404, "Learning path is not available in your authorized scope.")
    require_repo(db, actor, journey.repository_id)
    if journey.source_repository_id:
        require_repo(db, actor, journey.source_repository_id)
    if journey.team_id:
        team = db.get(Team, journey.team_id)
        if not team or team.archived or team.organization_id != actor.organization_id:
            raise HTTPException(404, "Learning team is unavailable.")
        if actor.id != journey.manager_id and not db.get(TeamMembership, (journey.team_id, actor.id)):
            raise HTTPException(404, "Learning team membership is unavailable.")
    return journey


def journey_for(db, actor, journey_id):
    row = db.get(LearningJourney, journey_id)
    if not row:
        raise HTTPException(404, "Learning path is not available in your authorized scope.")
    return scope(db, actor, row)


def current_objectives(db, journey):
    return list(db.scalars(select(LearningObjective).where(LearningObjective.journey_id == journey.id,
        LearningObjective.organization_id == journey.organization_id, LearningObjective.repository_id == journey.repository_id,
        LearningObjective.revision == journey.data["revision"]).order_by(LearningObjective.id)))


def check_version(row, version):
    if row.version != version:
        raise HTTPException(409, "The learning record changed. Reload before submitting.")


def writable(journey):
    if not future(journey.expires_at):
        raise HTTPException(409, "Learning retention window expired; private responses are withheld.")
    if journey.state == "COMPLETED":
        raise HTTPException(409, "This revision is completed; refresh it for a new source snapshot.")


def pin(db, actor, journey):
    row = snapshot_metadata(db, select(Record).where(Record.id == journey.snapshot_id))
    if not row or (row.kind, row.organization_id, row.repository_id) != (
            "snapshot", actor.organization_id, journey.repository_id):
        raise HTTPException(409, "Published learning snapshot is unavailable.")
    return row


def team_and_reviewers(db, actor, journey):
    reviewers = [member(db, actor.organization_id, value) for value in
                 (journey.participant_id, journey.mentor_id, journey.manager_id)]
    for reviewer in reviewers:
        require_repo(db, reviewer, journey.repository_id)
        if journey.source_repository_id:
            require_repo(db, reviewer, journey.source_repository_id)
    if not permitted(db, reviewers[2], "learning.manage", team_id=journey.team_id):
        raise HTTPException(403, "The assigned manager cannot manage learning in this scope.")
    for reviewer in reviewers:
        scope(db, reviewer, journey)


def plan(db, actor, journey, captured):
    skills = {s.casefold() for s in journey.data["skills"]}
    resources = captured["resources"]
    selected = [r for r in resources if not ROLE_TOPICS[journey.role] or r["topic"] in ROLE_TOPICS[journey.role]]
    selected = selected or resources
    selected = sorted(selected, key=lambda r: ((r.get("technology") or r["topic"]).casefold() in skills, r["id"]))[:16]
    if not selected:
        raise HTTPException(409, "The captured snapshot contains no supported learning knowledge.")
    for resource in selected:
        declared = (resource.get("technology") or resource["topic"]).casefold() in skills
        db.add(LearningObjective(id=str(uuid.uuid4()), organization_id=actor.organization_id,
            repository_id=journey.repository_id, journey_id=journey.id, snapshot_id=captured["snapshot_id"],
            record_id=resource["id"], revision=journey.data["revision"], data={**{k: v for k, v in resource.items() if k != "id"},
                "gap_basis": "DECLARED_FAMILIARITY_UNASSESSED" if declared else "LEARNING_OBJECTIVE",
                "question": f"Explain {resource['title']} using captured evidence, describe its supported scope and limitations, and identify one engineering implication.",
                "competence": "NOT_ASSESSED", "required_score": 3, "maximum_score": 4}))


def packed(db, actor, journey):
    snapshot = pin(db, actor, journey)
    newest = latest(db, actor, journey.repository_id, snapshot.data["branch"])
    objectives = current_objectives(db, journey)
    retained = future(journey.expires_at)
    items = []
    for objective in objectives:
        assessment = db.scalar(select(LearningAssessment).where(LearningAssessment.objective_id == objective.id)
            .order_by(LearningAssessment.created_at.desc(), LearningAssessment.id.desc()).limit(1))
        items.append({"id": objective.id, "record_id": objective.record_id, "snapshot_id": objective.snapshot_id,
            "state": objective.state, "version": objective.version, **objective.data,
            "assessment": ({"id": assessment.id, "evidence_ids": assessment.evidence_ids,
                "answer": cipher().decrypt(assessment.ciphertext.encode()).decode(), "submitted_at": assessment.created_at}
                if assessment and retained else None)})
    reviews = list(db.scalars(select(LearningReview).where(LearningReview.journey_id == journey.id)
        .order_by(LearningReview.created_at.desc(), LearningReview.id).limit(50)))
    return {"id": journey.id, "version": journey.version, "mode": journey.mode, "role": journey.role,
        "repository_id": journey.repository_id, "source_repository_id": journey.source_repository_id,
        "snapshot_id": journey.snapshot_id, "participant_id": journey.participant_id, "mentor_id": journey.mentor_id,
        "manager_id": journey.manager_id, "team_id": journey.team_id, "state": journey.state,
        "revision": journey.data["revision"], "skills": journey.data["skills"],
        "can_complete": actor.id == journey.manager_id and permitted(db, actor, "learning.manage", team_id=journey.team_id),
        "comparison": journey.data.get("comparison"), "completion_records": journey.data.get("completion_records", []),
        "refresh_required": newest.id != journey.snapshot_id, "latest_snapshot_id": newest.id,
        "retention_expired": not retained, "expires_at": journey.expires_at,
        "progress": {"approved": sum(i.state == "APPROVED" for i in objectives), "total": len(objectives)},
        "reviews": [{"id": r.id, "kind": r.kind, "decision": r.decision, "reviewer_id": r.reviewer_id,
                     "objective_id": r.objective_id, "at": r.created_at,
                     "notes": cipher().decrypt(r.ciphertext.encode()).decode() if retained else None} for r in reviews],
        "review_history_limit": 50,
        "objectives": items, "viewer": "PARTICIPANT" if actor.id == journey.participant_id else
            "MENTOR" if actor.id == journey.mentor_id else "MANAGER"}


@router.get("/knowledge/{repository_id}")
def dashboard(repository_id: str, request: Request):
    with session() as db:
        actor = identity(db, request)
        return knowledge(db, actor, repository_id)


@router.get("/members")
def learning_members(request: Request, repository_id: str, team_id: str | None = None,
                     search: str = Query("", max_length=100), offset: int = Query(0, ge=0),
                     limit: int = Query(50, ge=1, le=100)):
    with session() as db:
        actor = identity(db, request)
        require_repo(db, actor, repository_id)
        if not permitted(db, actor, "learning.manage", team_id=team_id):
            raise HTTPException(403, "Learning member assignment requires manager permission.")
        query = select(User.id, User.email, OrganizationMembership.role).join(OrganizationMembership,
            OrganizationMembership.user_id == User.id).where(OrganizationMembership.organization_id == actor.organization_id,
            OrganizationMembership.state == "ACTIVE", User.enabled.is_(True))
        if team_id:
            team = db.get(Team, team_id)
            if not team or team.archived or team.organization_id != actor.organization_id:
                raise HTTPException(404, "Learning team is unavailable.")
            query = query.join(TeamMembership, TeamMembership.user_id == User.id).where(
                TeamMembership.team_id == team_id, TeamMembership.organization_id == actor.organization_id)
        if search.strip():
            pattern = "%" + search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            query = query.where(or_(User.email.ilike(pattern, escape="\\"), User.id.ilike(pattern, escape="\\")))
        rows = db.execute(query.order_by(User.id).offset(offset).limit(limit + 1)).all()
        return {"items": [dict(row._mapping) for row in rows[:limit]], "limit": limit,
                "offset": offset, "has_more": len(rows) > limit, "bounded": True}


@router.get("/journeys")
def journeys(request: Request, offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=50)):
    with session() as db:
        actor = identity(db, request)
        query = select(LearningJourney).where(LearningJourney.organization_id == actor.organization_id,
            or_(LearningJourney.participant_id == actor.id, LearningJourney.mentor_id == actor.id, LearningJourney.manager_id == actor.id))
        authorized_repositories = select(Repository.id).where(repository_condition(actor))
        valid_teams = select(Team.id).where(Team.organization_id == actor.organization_id, Team.archived.is_(False))
        memberships = select(TeamMembership.team_id).where(TeamMembership.organization_id == actor.organization_id,
                                                         TeamMembership.user_id == actor.id)
        query = query.where(LearningJourney.repository_id.in_(authorized_repositories),
            or_(LearningJourney.source_repository_id.is_(None), LearningJourney.source_repository_id.in_(authorized_repositories)),
            or_(LearningJourney.team_id.is_(None), LearningJourney.team_id.in_(valid_teams) &
                or_(LearningJourney.manager_id == actor.id, LearningJourney.team_id.in_(memberships))))
        rows = list(db.scalars(query.order_by(LearningJourney.created_at.desc(), LearningJourney.id).offset(offset).limit(limit + 1)))
        items = []
        for row in rows:
            try:
                scope(db, actor, row)
                items.append({"id": row.id, "mode": row.mode, "role": row.role, "state": row.state,
                    "repository_id": row.repository_id, "participant_id": row.participant_id})
            except HTTPException:
                continue
        return {"items": items[:limit], "has_more": len(rows) > limit, "offset": offset, "limit": limit}


@router.post("/journeys")
def start(request: Request, body: Start):
    with session() as db:
        actor = identity(db, request, True)
        if not permitted(db, actor, "learning.manage", team_id=body.team_id):
            raise HTTPException(403, "Learning assignments require scoped manager permission.")
        if actor.id != body.manager_id:
            raise HTTPException(403, "Create an assignment as its accountable manager.")
        if len(set((body.participant_id, body.mentor_id, body.manager_id))) != 3:
            raise HTTPException(422, "Participant, mentor and manager must be three distinct members.")
        if (body.mode == "NEW_HIRE" and body.source_repository_id) or (body.mode == "INTERNAL_TRANSFER" and
                (not body.source_repository_id or body.source_repository_id == body.repository_id)):
            raise HTTPException(422, "Internal transfer requires a distinct authorized source project.")
        if any(not 1 <= len(skill.strip()) <= 120 for skill in body.skills):
            raise HTTPException(422, "Skill declarations must contain 1 to 120 characters each.")
        fingerprint = hashlib.sha256(json.dumps(body.model_dump(), sort_keys=True).encode()).hexdigest()
        existing = db.scalar(select(LearningJourney).where(LearningJourney.organization_id == actor.organization_id,
            LearningJourney.participant_id == body.participant_id, LearningJourney.request_key == body.request_key))
        if existing:
            scope(db, actor, existing)
            if existing.data["request_digest"] != fingerprint:
                raise HTTPException(409, "The request key was used for a different learning assignment.")
            return packed(db, actor, existing)
        captured = knowledge(db, actor, body.repository_id)
        comparison = None
        if body.source_repository_id:
            prior = knowledge(db, actor, body.source_repository_id)
            target_tags = {r["technology"] for r in captured["resources"] if r["technology"]}
            prior_tags = {r["technology"] for r in prior["resources"] if r["technology"]}
            comparison = {"source_snapshot_id": prior["snapshot_id"], "target_snapshot_id": captured["snapshot_id"],
                "shared_observed_technologies": sorted(target_tags & prior_tags),
                "target_observed_technologies": sorted(target_tags - prior_tags), "competence_basis": "NOT_INFERRED_FROM_PROJECT_TECHNOLOGY"}
        row = LearningJourney(id=str(uuid.uuid4()), organization_id=actor.organization_id,
            repository_id=body.repository_id, source_repository_id=body.source_repository_id,
            snapshot_id=captured["snapshot_id"], team_id=body.team_id, participant_id=body.participant_id,
            mentor_id=body.mentor_id, manager_id=body.manager_id, mode=body.mode, role=body.role,
            request_key=body.request_key, expires_at=(datetime.now(timezone.utc) + timedelta(days=body.retention_days)).isoformat(),
            data={"skills": [redact(s.strip()) for s in body.skills], "skills_declared_by": actor.id,
                  "revision": 1, "request_digest": fingerprint,
                  "comparison": comparison, "completion_records": []})
        team_and_reviewers(db, actor, row)
        require_feature(db, member(db, actor.organization_id, row.participant_id), "onboarding")
        db.add(row)
        db.flush()
        plan(db, actor, row, captured)
        audit(db, actor, "LEARNING_ASSIGNED", row.id, {"mode": row.mode, "snapshot_id": row.snapshot_id}, row.repository_id)
        db.commit()
        return packed(db, actor, row)


@router.get("/journeys/{journey_id}")
def detail(journey_id: str, request: Request):
    with session() as db:
        actor = identity(db, request)
        return packed(db, actor, journey_for(db, actor, journey_id))


@router.post("/journeys/{journey_id}/objectives/{objective_id}/submit")
def submit(journey_id: str, objective_id: str, body: Submission, request: Request):
    with session() as db:
        actor = identity(db, request, True)
        journey = journey_for(db, actor, journey_id)
        writable(journey)
        if actor.id != journey.participant_id:
            raise HTTPException(403, "Only the assigned participant can submit an assessment.")
        objective = db.get(LearningObjective, objective_id, with_for_update=True)
        if not objective or (objective.journey_id, objective.revision) != (journey.id, journey.data["revision"]):
            raise HTTPException(404, "Current learning objective is unavailable.")
        check_version(objective, body.version)
        allowed = {objective.record_id, *objective.data["evidence_ids"]}
        if not set(body.evidence_ids) <= allowed:
            raise HTTPException(422, "Assessment citations must reference this objective's captured knowledge.")
        for reference in body.evidence_ids:
            record = db.get(Record, reference)
            if not record or (record.organization_id, record.repository_id, record.data.get("scope", {}).get("snapshot_id")) != (
                    actor.organization_id, journey.repository_id, journey.snapshot_id):
                raise HTTPException(422, "Assessment citation is unavailable in the captured project scope.")
        if objective.state == "APPROVED":
            raise HTTPException(409, "Approved assessment is retained; refresh creates a new revision.")
        count = db.scalar(select(func.count()).select_from(LearningAssessment).where(LearningAssessment.objective_id == objective.id))
        if count >= 5:
            raise HTTPException(409, "Assessment attempt limit reached; review the learning assignment.")
        assessment_id = str(uuid.uuid4())
        db.add(LearningAssessment(id=assessment_id, organization_id=actor.organization_id,
            repository_id=journey.repository_id, objective_id=objective.id, participant_id=actor.id,
            ciphertext=cipher().encrypt(redact(body.answer).encode()).decode(), evidence_ids=list(dict.fromkeys(body.evidence_ids))))
        objective.state = "SUBMITTED"
        objective.data = {**objective.data, "assessment_sequence": count + 1, "latest_assessment_id": assessment_id}
        audit(db, actor, "LEARNING_ASSESSMENT_SUBMITTED", objective.id, {"journey_id": journey.id}, journey.repository_id)
        db.commit()
        return packed(db, actor, journey)


@router.post("/journeys/{journey_id}/skills")
def declare_skills(journey_id: str, body: Skills, request: Request):
    with session() as db:
        actor = identity(db, request, True)
        journey = journey_for(db, actor, journey_id)
        writable(journey)
        check_version(journey, body.version)
        if actor.id != journey.participant_id:
            raise HTTPException(403, "Only the participant can attest their skill declaration.")
        if any(not 1 <= len(value.strip()) <= 120 for value in body.skills):
            raise HTTPException(422, "Skill declarations must contain 1 to 120 characters each.")
        values = [redact(value.strip()) for value in body.skills]
        journey.data = {**journey.data, "skills": values, "skills_declared_by": actor.id, "skills_declared_at": now()}
        for objective in current_objectives(db, journey):
            declared = (objective.data.get("technology") or objective.data["topic"]).casefold() in {v.casefold() for v in values}
            objective.data = {**objective.data, "gap_basis": "DECLARED_FAMILIARITY_UNASSESSED" if declared else "LEARNING_OBJECTIVE"}
        audit(db, actor, "LEARNING_SKILLS_DECLARED", journey.id, {"declaration_count": len(values)}, journey.repository_id)
        db.commit()
        return packed(db, actor, journey)


@router.post("/journeys/{journey_id}/objectives/{objective_id}/review")
def review(journey_id: str, objective_id: str, body: MentorReview, request: Request):
    with session() as db:
        actor = identity(db, request, True)
        journey = journey_for(db, actor, journey_id)
        writable(journey)
        team_and_reviewers(db, actor, journey)
        if actor.id != journey.mentor_id:
            raise HTTPException(403, "Only the assigned mentor can assess this response.")
        objective = db.get(LearningObjective, objective_id)
        if not objective or (objective.journey_id, objective.revision) != (journey.id, journey.data["revision"]):
            raise HTTPException(404, "Current learning objective is unavailable.")
        check_version(objective, body.version)
        if objective.state != "SUBMITTED":
            raise HTTPException(409, "Submit an assessment before mentor review.")
        objective.state = "APPROVED" if body.score >= 3 else "CHANGES_REQUESTED"
        objective.data = {**objective.data, "score": body.score, "competence": "MENTOR_ASSESSED",
                          "reviewed_at": now(), "reviewer_id": actor.id}
        db.add(LearningReview(id=str(uuid.uuid4()), organization_id=actor.organization_id,
            repository_id=journey.repository_id, journey_id=journey.id, objective_id=objective.id,
            reviewer_id=actor.id, kind="MENTOR", decision=objective.state,
            ciphertext=cipher().encrypt(redact(body.notes).encode()).decode()))
        audit(db, actor, "LEARNING_MENTOR_REVIEW", objective.id, {"decision": objective.state, "score": body.score}, journey.repository_id)
        db.commit()
        return packed(db, actor, journey)


@router.post("/journeys/{journey_id}/complete")
def complete(journey_id: str, body: Completion, request: Request):
    with session() as db:
        actor = identity(db, request, True)
        journey = journey_for(db, actor, journey_id)
        writable(journey)
        check_version(journey, body.version)
        team_and_reviewers(db, actor, journey)
        if actor.id != journey.manager_id:
            raise HTTPException(403, "Only the assigned manager can complete this learning revision.")
        captured = pin(db, actor, journey)
        if latest(db, actor, journey.repository_id, captured.data["branch"]).id != journey.snapshot_id:
            raise HTTPException(409, "Source changed; refresh learning before completion.")
        objectives = current_objectives(db, journey)
        if not objectives or any(row.state != "APPROVED" for row in objectives):
            raise HTTPException(409, "Every current objective requires mentor approval before completion.")
        journey.state = "COMPLETED"
        completion = {"revision": journey.data["revision"], "snapshot_id": journey.snapshot_id,
                      "manager_id": actor.id, "at": now(), "objective_ids": [row.id for row in objectives],
                      "basis": "MENTOR_ASSESSMENTS_AND_MANAGER_REVIEW"}
        journey.data = {**journey.data, "completion_records": [*journey.data["completion_records"], completion]}
        db.add(LearningReview(id=str(uuid.uuid4()), organization_id=actor.organization_id,
            repository_id=journey.repository_id, journey_id=journey.id, reviewer_id=actor.id,
            kind="MANAGER", decision="COMPLETED", ciphertext=cipher().encrypt(redact(body.notes).encode()).decode()))
        audit(db, actor, "LEARNING_COMPLETED", journey.id, {"snapshot_id": journey.snapshot_id, "revision": journey.data["revision"]}, journey.repository_id)
        db.commit()
        return packed(db, actor, journey)


@router.post("/journeys/{journey_id}/refresh")
def refresh(journey_id: str, body: Version, request: Request):
    with session() as db:
        actor = identity(db, request, True)
        journey = journey_for(db, actor, journey_id)
        if not future(journey.expires_at):
            raise HTTPException(409, "Learning retention window expired.")
        check_version(journey, body.version)
        team_and_reviewers(db, actor, journey)
        if actor.id != journey.manager_id:
            raise HTTPException(403, "The assigned manager must approve a source refresh.")
        previous = pin(db, actor, journey)
        captured = knowledge(db, actor, journey.repository_id, latest(db, actor, journey.repository_id, previous.data["branch"]))
        if captured["snapshot_id"] == journey.snapshot_id:
            return packed(db, actor, journey)
        if journey.data["revision"] >= 32:
            raise HTTPException(409, "Learning revision limit reached; retain history and create a new assignment.")
        journey.snapshot_id, journey.state = captured["snapshot_id"], "REFRESH_REQUIRED"
        comparison = journey.data.get("comparison")
        if comparison:
            prior_snapshot = snapshot_metadata(db, select(Record).where(Record.id == comparison["source_snapshot_id"]))
            if not prior_snapshot:
                raise HTTPException(409, "Published transfer baseline is unavailable.")
            prior = knowledge(db, actor, journey.source_repository_id, prior_snapshot)
            target_tags = {r["technology"] for r in captured["resources"] if r["technology"]}
            prior_tags = {r["technology"] for r in prior["resources"] if r["technology"]}
            comparison = {**comparison, "target_snapshot_id": captured["snapshot_id"],
                "shared_observed_technologies": sorted(target_tags & prior_tags),
                "target_observed_technologies": sorted(target_tags - prior_tags)}
        journey.data = {**journey.data, "revision": journey.data["revision"] + 1, "comparison": comparison}
        db.flush()
        plan(db, actor, journey, captured)
        audit(db, actor, "LEARNING_REFRESHED", journey.id, {"snapshot_id": journey.snapshot_id, "revision": journey.data["revision"]}, journey.repository_id)
        db.commit()
        return packed(db, actor, journey)
