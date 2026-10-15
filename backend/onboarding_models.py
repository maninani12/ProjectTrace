"""Learning records pin published knowledge; observed technology is not competence."""
from sqlalchemy import (
    JSON,
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.db import Base, now


class LearningJourney(Base):
    __tablename__ = "learning_journeys"
    __table_args__ = (
        UniqueConstraint("id", "organization_id", "repository_id"),
        UniqueConstraint("organization_id", "participant_id", "request_key"),
        ForeignKeyConstraint(["repository_id", "organization_id"], ["repositories.id", "repositories.organization_id"]),
        ForeignKeyConstraint(["source_repository_id", "organization_id"], ["repositories.id", "repositories.organization_id"]),
        ForeignKeyConstraint(["snapshot_id", "organization_id", "repository_id"], ["records.id", "records.organization_id", "records.repository_id"]),
        ForeignKeyConstraint(["organization_id", "team_id"], ["teams.organization_id", "teams.id"]),
        *(ForeignKeyConstraint(["organization_id", field], ["organization_memberships.organization_id", "organization_memberships.user_id"])
          for field in ("participant_id", "mentor_id", "manager_id")),
        CheckConstraint("mode IN ('NEW_HIRE','INTERNAL_TRANSFER')", name="ck_learning_mode"),
        CheckConstraint("state IN ('ACTIVE','COMPLETED','REFRESH_REQUIRED')", name="ck_learning_state"),
        CheckConstraint("participant_id<>mentor_id AND participant_id<>manager_id AND mentor_id<>manager_id", name="ck_learning_independent_review"),
        CheckConstraint("(mode='NEW_HIRE' AND source_repository_id IS NULL) OR (mode='INTERNAL_TRANSFER' AND source_repository_id IS NOT NULL AND source_repository_id<>repository_id)", name="ck_learning_source_mode"),
        Index("ix_learning_participants", "organization_id", "participant_id", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(80))
    repository_id: Mapped[str] = mapped_column(String(80))
    source_repository_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    snapshot_id: Mapped[str] = mapped_column(String(80))
    team_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    participant_id: Mapped[str] = mapped_column(String(80))
    mentor_id: Mapped[str] = mapped_column(String(80))
    manager_id: Mapped[str] = mapped_column(String(80))
    request_key: Mapped[str] = mapped_column(String(80))
    mode: Mapped[str] = mapped_column(String(30))
    role: Mapped[str] = mapped_column(String(30))
    state: Mapped[str] = mapped_column(String(30), default="ACTIVE")
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(50), default=now)
    expires_at: Mapped[str] = mapped_column(String(50))
    version: Mapped[int] = mapped_column(default=1)
    __mapper_args__ = {"version_id_col": version}


class LearningObjective(Base):
    __tablename__ = "learning_objectives"
    __table_args__ = (
        UniqueConstraint("id", "organization_id", "repository_id"),
        UniqueConstraint("journey_id", "revision", "record_id"),
        ForeignKeyConstraint(["journey_id", "organization_id", "repository_id"], ["learning_journeys.id", "learning_journeys.organization_id", "learning_journeys.repository_id"]),
        ForeignKeyConstraint(["record_id", "organization_id", "repository_id"], ["records.id", "records.organization_id", "records.repository_id"]),
        ForeignKeyConstraint(["snapshot_id", "organization_id", "repository_id"], ["records.id", "records.organization_id", "records.repository_id"]),
        CheckConstraint("state IN ('ASSIGNED','SUBMITTED','APPROVED','CHANGES_REQUESTED')", name="ck_learning_objective_state"),
        Index("ix_learning_objective_revision", "journey_id", "revision", "state"),
    )
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(80))
    repository_id: Mapped[str] = mapped_column(String(80))
    journey_id: Mapped[str] = mapped_column(String(80))
    snapshot_id: Mapped[str] = mapped_column(String(80))
    record_id: Mapped[str] = mapped_column(String(80))
    revision: Mapped[int]
    state: Mapped[str] = mapped_column(String(30), default="ASSIGNED")
    data: Mapped[dict] = mapped_column(JSON)
    version: Mapped[int] = mapped_column(default=1)
    __mapper_args__ = {"version_id_col": version}


class LearningAssessment(Base):
    __tablename__ = "learning_assessments"
    __table_args__ = (
        ForeignKeyConstraint(["objective_id", "organization_id", "repository_id"], ["learning_objectives.id", "learning_objectives.organization_id", "learning_objectives.repository_id"]),
        ForeignKeyConstraint(["organization_id", "participant_id"], ["organization_memberships.organization_id", "organization_memberships.user_id"]),
        Index("ix_learning_assessment_objective", "objective_id", "created_at", "id"),
    )
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(80))
    repository_id: Mapped[str] = mapped_column(String(80))
    objective_id: Mapped[str] = mapped_column(String(80))
    participant_id: Mapped[str] = mapped_column(String(80))
    ciphertext: Mapped[str] = mapped_column(Text)
    evidence_ids: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(50), default=now)


class LearningReview(Base):
    __tablename__ = "learning_reviews"
    __table_args__ = (
        ForeignKeyConstraint(["journey_id", "organization_id", "repository_id"], ["learning_journeys.id", "learning_journeys.organization_id", "learning_journeys.repository_id"]),
        ForeignKeyConstraint(["objective_id", "organization_id", "repository_id"], ["learning_objectives.id", "learning_objectives.organization_id", "learning_objectives.repository_id"]),
        ForeignKeyConstraint(["organization_id", "reviewer_id"], ["organization_memberships.organization_id", "organization_memberships.user_id"]),
        CheckConstraint("kind IN ('MENTOR','MANAGER')", name="ck_learning_review_kind"),
    )
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(80))
    repository_id: Mapped[str] = mapped_column(String(80))
    journey_id: Mapped[str] = mapped_column(String(80))
    objective_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    reviewer_id: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(20))
    decision: Mapped[str] = mapped_column(String(30))
    ciphertext: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(50), default=now)
