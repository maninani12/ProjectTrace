"""Real API learning journeys, assessments and security boundaries in owned DBs."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from backend import main
from backend.admin_models import FeaturePolicy, OrganizationMembership, Team, TeamMembership
from backend.db import Audit, Grant, Repository, User
from backend.domain import persist_analysis
from backend.onboarding_models import LearningAssessment, LearningJourney, LearningObjective, LearningReview
from backend.security import passwords


@pytest.fixture
def learners(signed, monkeypatch):
    monkeypatch.setenv("ANALYSIS_INPUT_KEY", Fernet.generate_key().decode())
    with main.Session() as db:
        manager = db.get(User, "demo-engineer")
        manager.role = "ORG_OWNER"
        db.add(OrganizationMembership(organization_id="northstar", user_id=manager.id, role="ORG_OWNER", state="ACTIVE"))
        for identity in ("learning-participant", "learning-mentor"):
            user = User(id=identity, organization_id="northstar", email=identity + "@example.test",
                password_hash=passwords.hash("Learning-qualification-123!"), role="ENGINEER")
            db.add(user)
            db.flush()
            db.add(OrganizationMembership(organization_id="northstar", user_id=identity, role="ENGINEER", state="ACTIVE"))
            db.add_all([Grant(user_id=identity, repository_id=repo) for repo in ("clean", "identity")])
        db.commit()
    clients = []
    for name in ("learning-participant", "learning-mentor"):
        client = TestClient(main.app)
        client.headers["origin"] = "http://127.0.0.1:5173"
        response = client.post("/api/auth/login", json={"email": name + "@example.test", "password": "Learning-qualification-123!"})
        assert response.status_code == 200
        client.headers["x-csrf-token"] = response.json()["csrf"]
        clients.append(client)
    yield signed, *clients
    for client in clients:
        client.close()


def assignment(mode="NEW_HIRE", **changes):
    return {"repository_id": "clean", "source_repository_id": "identity" if mode == "INTERNAL_TRANSFER" else None,
        "mode": mode, "role": "BACKEND", "participant_id": "learning-participant", "mentor_id": "learning-mentor",
        "manager_id": "demo-engineer", "skills": ["Python"], "retention_days": 30,
        "request_key": str(uuid.uuid4()), **changes}


def start(manager, **changes):
    response = manager.post("/api/learning/journeys", json=assignment(**changes))
    assert response.status_code == 200, response.text
    return response.json()


def approve_all(journey, participant, mentor):
    for item in journey["objectives"]:
        submitted = participant.post(f"/api/learning/journeys/{journey['id']}/objectives/{item['id']}/submit", json={
            "version": item["version"], "answer": "The captured project knowledge supports a static engineering explanation. Its linked scope does not establish runtime behavior.",
            "evidence_ids": [item["record_id"]]})
        assert submitted.status_code == 200, submitted.text
        updated = next(row for row in submitted.json()["objectives"] if row["id"] == item["id"])
        reviewed = mentor.post(f"/api/learning/journeys/{journey['id']}/objectives/{item['id']}/review", json={
            "version": updated["version"], "score": 4, "notes": "Controlled mentor review confirms the response cites the captured project and states its supported static scope."})
        assert reviewed.status_code == 200, reviewed.text
    return reviewed.json()


@pytest.mark.parametrize("mode", ["NEW_HIRE", "INTERNAL_TRANSFER"])
def test_both_learning_modes_complete_with_evidence_mentor_and_manager_reviews(learners, mode):
    manager, participant, mentor = learners
    body = assignment(mode)
    created = manager.post("/api/learning/journeys", json=body)
    assert created.status_code == 200, created.text
    journey = created.json()
    duplicate = manager.post("/api/learning/journeys", json=body)
    assert duplicate.status_code == 200 and duplicate.json()["id"] == journey["id"]
    assert journey["objectives"] and journey["snapshot_id"]
    assert journey["mode"] == mode
    assert bool(journey["comparison"]) == (mode == "INTERNAL_TRANSFER")
    declared = participant.post(f"/api/learning/journeys/{journey['id']}/skills", json={"version": journey["version"], "skills": ["Python", "API"]})
    assert declared.status_code == 200
    assert all(item["state"] == "ASSIGNED" for item in declared.json()["objectives"])
    premature = manager.post(f"/api/learning/journeys/{journey['id']}/complete", json={"version": declared.json()["version"], "notes": "Attempt before objective reviews."})
    assert premature.status_code == 409
    current = approve_all(declared.json(), participant, mentor)
    completed = manager.post(f"/api/learning/journeys/{journey['id']}/complete", json={"version": current["version"], "notes": "Controlled manager review approves all independently assessed learning objectives."})
    assert completed.status_code == 200, completed.text
    result = completed.json()
    assert result["state"] == "COMPLETED" and result["progress"]["approved"] == result["progress"]["total"]
    assert result["completion_records"][0]["snapshot_id"] == result["snapshot_id"]
    with main.Session() as db:
        assert db.scalar(select(func.count()).select_from(LearningJourney)) == 1
        assessments = list(db.scalars(select(LearningAssessment)))
        assert len(assessments) == result["progress"]["total"]
        assert all("captured project knowledge" not in row.ciphertext for row in assessments)
        assert db.scalar(select(func.count()).select_from(LearningReview)) == len(assessments) + 1
        actions = set(db.scalars(select(Audit.action)))
        assert {"LEARNING_ASSIGNED", "LEARNING_SKILLS_DECLARED", "LEARNING_COMPLETED", "LEARNING_MENTOR_REVIEW"} <= actions


def test_learning_authority_citations_and_optimistic_versions_fail_closed(learners):
    manager, participant, mentor = learners
    journey = start(manager)
    item = journey["objectives"][0]
    path = f"/api/learning/journeys/{journey['id']}/objectives/{item['id']}"
    response = participant.post(path + "/review", json={"version": item["version"], "score": 4, "notes": "Self review must be rejected."})
    assert response.status_code == 403
    response = manager.post(path + "/submit", json={"version": item["version"], "answer": "A manager cannot impersonate a participant in this learning assessment.", "evidence_ids": [item["record_id"]]})
    assert response.status_code == 403
    response = participant.post(path + "/submit", json={"version": item["version"], "answer": "Citations outside the captured project cannot establish an evidence-backed explanation.", "evidence_ids": ["outside-reference"]})
    assert response.status_code == 422
    valid = {"version": item["version"], "answer": "Captured evidence supports this statement within the project snapshot and static scope.", "evidence_ids": [item["record_id"]]}
    assert participant.post(path + "/submit", json=valid).status_code == 200
    assert participant.post(path + "/submit", json=valid).status_code == 409
    latest = participant.get(f"/api/learning/journeys/{journey['id']}").json()
    current = next(row for row in latest["objectives"] if row["id"] == item["id"])
    rejected = mentor.post(path + "/review", json={"version": current["version"], "score": 2, "notes": "Explain the limitations of the captured evidence more carefully."})
    assert rejected.status_code == 200
    assert next(row for row in rejected.json()["objectives"] if row["id"] == item["id"])["state"] == "CHANGES_REQUESTED"
    with main.Session() as db:
        assert db.scalar(select(func.count()).select_from(LearningAssessment)) == 1


def test_transfer_rechecks_both_project_grants_and_feature_denials(learners):
    manager, participant, _ = learners
    journey = start(manager, mode="INTERNAL_TRANSFER")
    with main.Session() as db:
        db.delete(db.get(Grant, ("learning-participant", "identity")))
        db.commit()
    assert participant.get(f"/api/learning/journeys/{journey['id']}").status_code == 404
    assert participant.get("/api/learning/journeys").json()["items"] == []
    with main.Session() as db:
        db.add(Grant(user_id="learning-participant", repository_id="identity"))
        db.add(FeaturePolicy(id="learning-denial", organization_id="northstar", scope_key="northstar:USER:learning-participant",
            scope_type="USER", target_id="learning-participant", feature="onboarding", decision="DENY", mandatory=False,
            reason="Qualification deny", changed_by="demo-engineer"))
        db.commit()
    assert participant.get(f"/api/learning/journeys/{journey['id']}").status_code == 403
    assert participant.get("/api/learning/knowledge/clean").status_code == 403


def test_source_refresh_preserves_completed_history_and_requires_new_assessments(learners):
    manager, participant, mentor = learners
    journey = start(manager)
    reviewed = approve_all(journey, participant, mentor)
    completed = manager.post(f"/api/learning/journeys/{journey['id']}/complete", json={"version": reviewed["version"], "notes": "The initial captured learning revision is complete."}).json()
    old_snapshot = completed["snapshot_id"]
    with main.Session() as db:
        actor, repo = db.get(User, "demo-engineer"), db.get(Repository, "clean")
        snapshot = persist_analysis(db, actor, repo, {"README.md": "# API\nBackend uses FastAPI.\n", "app.py": "from fastapi import FastAPI\napp=FastAPI()\n"}, base_id=old_snapshot)
        new_snapshot = snapshot.id
        db.commit()
    changed = participant.get(f"/api/learning/journeys/{journey['id']}").json()
    assert changed["refresh_required"] and changed["state"] == "COMPLETED"
    refreshed = manager.post(f"/api/learning/journeys/{journey['id']}/refresh", json={"version": changed["version"]})
    assert refreshed.status_code == 200, refreshed.text
    current = refreshed.json()
    assert current["revision"] == 2 and current["snapshot_id"] == new_snapshot
    assert current["progress"]["approved"] == 0
    assert current["completion_records"] == completed["completion_records"]
    with main.Session() as db:
        old = list(db.scalars(select(LearningObjective).where(LearningObjective.revision == 1)))
        assert old and all(row.state == "APPROVED" and row.snapshot_id == old_snapshot for row in old)


def test_retention_withholds_private_responses_and_blocks_mutations(learners):
    manager, participant, _ = learners
    journey = start(manager)
    item = journey["objectives"][0]
    response = participant.post(f"/api/learning/journeys/{journey['id']}/objectives/{item['id']}/submit", json={"version": item["version"],
        "answer": "A private controlled learning explanation with captured source references and stated limitations.", "evidence_ids": [item["record_id"]]})
    assert response.status_code == 200
    with main.Session() as db:
        db.get(LearningJourney, journey["id"]).expires_at = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        db.commit()
    hidden = participant.get(f"/api/learning/journeys/{journey['id']}").json()
    assert hidden["retention_expired"]
    assert all(row["assessment"] is None for row in hidden["objectives"])
    assert "private controlled learning explanation" not in str(hidden)
    assert manager.post(f"/api/learning/journeys/{journey['id']}/refresh", json={"version": hidden["version"]}).status_code == 409


def test_database_scope_and_unassigned_user_cannot_read_learning(learners):
    manager, _, _ = learners
    journey = start(manager)
    with main.Session() as db:
        with pytest.raises(IntegrityError):
            db.execute(LearningObjective.__table__.update().where(LearningObjective.journey_id == journey["id"]).values(organization_id="other"))
        db.rollback()
    viewer = TestClient(main.app)
    viewer.headers["origin"] = "http://127.0.0.1:5173"
    response = viewer.post("/api/auth/login", json={"email": "viewer@example.com", "password": "Strong-test-password-123!"})
    assert response.status_code == 200
    assert viewer.get(f"/api/learning/journeys/{journey['id']}").status_code == 404
    assert viewer.get("/api/learning/journeys").json()["items"] == []
    viewer.close()


def test_learning_member_directory_supports_bounded_search_beyond_first_page(learners):
    manager, _, _ = learners
    with main.Session() as db:
        for index in range(55):
            identity = f"aa-directory-{index:03}"
            db.add(User(id=identity, organization_id="northstar", email=identity + "@example.test", password_hash="unused-no-login", role="VIEWER"))
            db.flush()
            db.add(OrganizationMembership(organization_id="northstar", user_id=identity, role="VIEWER", state="ACTIVE"))
        db.commit()
    first = manager.get("/api/learning/members?repository_id=clean").json()
    assert len(first["items"]) == 50 and first["has_more"]
    assert "learning-participant" not in {row["id"] for row in first["items"]}
    found = manager.get("/api/learning/members?repository_id=clean&search=learning-").json()
    assert {row["id"] for row in found["items"]} == {"learning-participant", "learning-mentor"}
    assert not found["has_more"]


def test_team_manager_assignment_requires_current_team_membership(learners):
    manager, _, mentor = learners
    with main.Session() as db:
        db.add(Team(id="learning-team", organization_id="northstar", name="Learning Team", owner_id="demo-engineer"))
        db.flush()
        for identity in ("demo-engineer", "learning-participant", "learning-mentor"):
            db.add(TeamMembership(team_id="learning-team", user_id=identity, organization_id="northstar",
                role="ADMIN" if identity == "demo-engineer" else "MEMBER"))
        db.get(User, "demo-engineer").role = "TEAM_ADMIN"
        db.get(OrganizationMembership, ("northstar", "demo-engineer")).role = "TEAM_ADMIN"
        db.commit()
    assert manager.get("/api/learning/members?repository_id=clean").status_code == 403
    directory = manager.get("/api/learning/members?repository_id=clean&team_id=learning-team")
    assert directory.status_code == 200
    journey = start(manager, team_id="learning-team")
    assert journey["can_complete"]
    with main.Session() as db:
        db.delete(db.get(TeamMembership, ("learning-team", "learning-mentor")))
        db.commit()
    assert mentor.get(f"/api/learning/journeys/{journey['id']}").status_code == 404


def test_revoked_manager_permission_does_not_allow_completion(learners):
    manager, _, _ = learners
    journey = start(manager)
    with main.Session() as db:
        db.get(User, "demo-engineer").role = "VIEWER"
        db.get(OrganizationMembership, ("northstar", "demo-engineer")).role = "VIEWER"
        db.commit()
    response = manager.get(f"/api/learning/journeys/{journey['id']}")
    assert response.status_code == 200 and not response.json()["can_complete"]
    denied = manager.post(f"/api/learning/journeys/{journey['id']}/complete", json={"version": response.json()["version"], "notes": "A former manager permission cannot complete the path."})
    assert denied.status_code == 403
