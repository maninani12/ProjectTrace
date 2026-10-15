"""Additive ownership ledger. Legacy Records remain byte-for-byte unchanged."""
from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.db import Audit, Base, now


class AnalysisGeneration(Base):
    __tablename__ = "analysis_generations"
    __table_args__ = (
        UniqueConstraint("id", "organization_id", "repository_id"),
        UniqueConstraint("job_id", "signature"),
        ForeignKeyConstraint(["job_id", "organization_id", "repository_id"],
                             ["records.id", "records.organization_id", "records.repository_id"]),
        ForeignKeyConstraint(["snapshot_id", "organization_id", "repository_id"],
                             ["records.id", "records.organization_id", "records.repository_id"]),
        ForeignKeyConstraint(["inventory_id", "organization_id", "repository_id"],
                             ["source_inventories.id", "source_inventories.organization_id", "source_inventories.repository_id"]),
        CheckConstraint("state IN ('STAGING','VALIDATED','PUBLISHED','ABANDONED')", name="ck_generation_state"),
        Index("ix_generations_recovery", "state", "expires_at"),
    )
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    repository_id: Mapped[str] = mapped_column(ForeignKey("repositories.id"))
    job_id: Mapped[str] = mapped_column(String(80))
    signature: Mapped[str] = mapped_column(String(64))
    content_key: Mapped[str] = mapped_column(String(64))
    inventory_id: Mapped[str] = mapped_column(String(80))
    branch: Mapped[str] = mapped_column(String(200))
    expected_pointer_revision: Mapped[int]
    state: Mapped[str] = mapped_column(String(30), default="STAGING")
    snapshot_id: Mapped[str | None] = mapped_column(ForeignKey("records.id"), nullable=True)
    created_at: Mapped[str] = mapped_column(String(50), default=now)
    expires_at: Mapped[str] = mapped_column(String(50))
    published_at: Mapped[str | None] = mapped_column(String(50), nullable=True)
    validation_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    validation_records: Mapped[int | None] = mapped_column(nullable=True)


class GenerationRecord(Base):
    __tablename__ = "generation_records"
    __table_args__ = (
        ForeignKeyConstraint(["generation_id", "organization_id", "repository_id"],
                             ["analysis_generations.id", "analysis_generations.organization_id", "analysis_generations.repository_id"]),
        ForeignKeyConstraint(["record_id", "organization_id", "repository_id"],
                             ["records.id", "records.organization_id", "records.repository_id"]),
        Index("ix_generation_records_stage", "generation_id", "stage", "ordinal"),
        UniqueConstraint("generation_id", "stage", "ordinal"),
    )
    record_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    generation_id: Mapped[str] = mapped_column(String(80))
    organization_id: Mapped[str] = mapped_column(String(80))
    repository_id: Mapped[str] = mapped_column(String(80))
    stage: Mapped[str] = mapped_column(String(40))
    ordinal: Mapped[int]


class GenerationReceipt(Base):
    __tablename__ = "generation_receipts"
    __table_args__ = (
        ForeignKeyConstraint(["generation_id", "organization_id", "repository_id"],
                             ["analysis_generations.id", "analysis_generations.organization_id", "analysis_generations.repository_id"]),
    )
    generation_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    stage: Mapped[str] = mapped_column(String(40), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(80))
    repository_id: Mapped[str] = mapped_column(String(80))
    dependency_digest: Mapped[str] = mapped_column(String(64))
    digest: Mapped[str] = mapped_column(String(64))
    chunk_count: Mapped[int]
    record_count: Mapped[int]
    completed_at: Mapped[str] = mapped_column(String(50), default=now)


class GenerationChunk(Base):
    __tablename__ = "generation_chunks"
    __table_args__ = (
        ForeignKeyConstraint(["generation_id", "organization_id", "repository_id"],
                             ["analysis_generations.id", "analysis_generations.organization_id", "analysis_generations.repository_id"]),
    )
    generation_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    stage: Mapped[str] = mapped_column(String(40), primary_key=True)
    ordinal: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(80))
    repository_id: Mapped[str] = mapped_column(String(80))
    ciphertext: Mapped[str] = mapped_column(Text)
    digest: Mapped[str] = mapped_column(String(64))


class GenerationAudit(Base):
    __tablename__ = "generation_audits"
    __table_args__ = (
        ForeignKeyConstraint(["generation_id", "organization_id", "repository_id"],
                             ["analysis_generations.id", "analysis_generations.organization_id", "analysis_generations.repository_id"]),
        ForeignKeyConstraint(["event_id", "organization_id", "repository_id"],
                             ["audit_events.id", "audit_events.organization_id", "audit_events.repository_id"]),
        ForeignKeyConstraint(["activity_id", "organization_id", "repository_id"],
                             ["application_activity.id", "application_activity.organization_id", "application_activity.repository_id"]),
    )
    event_id: Mapped[str] = mapped_column(ForeignKey("audit_events.id"), primary_key=True)
    activity_id: Mapped[str] = mapped_column(ForeignKey("application_activity.id"), unique=True)
    generation_id: Mapped[str] = mapped_column(String(80), index=True)
    organization_id: Mapped[str] = mapped_column(String(80))
    repository_id: Mapped[str] = mapped_column(String(80))


class PublishedGeneration(Base):
    __tablename__ = "published_generations"
    __table_args__ = (
        ForeignKeyConstraint(["generation_id", "organization_id", "repository_id"],
                             ["analysis_generations.id", "analysis_generations.organization_id", "analysis_generations.repository_id"]),
    )
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), primary_key=True)
    repository_id: Mapped[str] = mapped_column(ForeignKey("repositories.id"), primary_key=True)
    branch: Mapped[str] = mapped_column(String(200), primary_key=True)
    generation_id: Mapped[str] = mapped_column(String(80))
    revision: Mapped[int] = mapped_column(default=1)


Index("uq_audits_generation_scope", Audit.id, Audit.organization_id, Audit.repository_id, unique=True)
