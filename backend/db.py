"""Portable local adapter; PostgreSQL is the deployed database."""

import os
from datetime import datetime, timezone

from sqlalchemy import JSON, ForeignKey, Index, String, Text, UniqueConstraint, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


def now():
    return datetime.now(timezone.utc).isoformat()


class Base(DeclarativeBase):
    pass


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    email: Mapped[str] = mapped_column(String(200), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(40))


class Repository(Base):
    __tablename__ = "repositories"
    __table_args__ = (UniqueConstraint("provider", "provider_id"),)
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    system: Mapped[str] = mapped_column(String(200))
    component: Mapped[str] = mapped_column(String(200))
    owner: Mapped[str] = mapped_column(String(200))
    provider: Mapped[str] = mapped_column(String(40), default="LOCAL")
    provider_id: Mapped[str | None] = mapped_column(String(100), nullable=True)


class Grant(Base):
    __tablename__ = "repository_grants"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    repository_id: Mapped[str] = mapped_column(ForeignKey("repositories.id"), primary_key=True)


class SessionToken(Base):
    __tablename__ = "sessions"
    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    csrf: Mapped[str] = mapped_column(String(100))
    expires: Mapped[float]


class Record(Base):
    """Versioned domain documents with explicit tenant/repository scope.

    Kinds: snapshot, artifact, evidence, edge, claim, finding, drift, pr,
    dependency, policy, review, exception, job, integration, usage.
    """

    __tablename__ = "records"
    __table_args__ = (
        UniqueConstraint("organization_id", "kind", "natural_key"),
        Index("ix_records_scoped_current", "organization_id", "repository_id", "kind", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    repository_id: Mapped[str | None] = mapped_column(ForeignKey("repositories.id"), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    natural_key: Mapped[str] = mapped_column(String(250))
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(50), default=now)
    version: Mapped[int] = mapped_column(default=1)
    __mapper_args__ = {"version_id_col": version}


class Audit(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    repository_id: Mapped[str | None] = mapped_column(ForeignKey("repositories.id"), nullable=True, index=True)
    actor: Mapped[str] = mapped_column(String(200))
    action: Mapped[str] = mapped_column(String(80))
    target: Mapped[str] = mapped_column(String(100))
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(50), default=now)


class AnalysisInput(Base):
    """Encrypted, expiring worker input; never returned by record APIs."""

    __tablename__ = "analysis_inputs"
    job_id: Mapped[str] = mapped_column(ForeignKey("records.id", ondelete="CASCADE"), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    repository_id: Mapped[str] = mapped_column(ForeignKey("repositories.id"), index=True)
    ciphertext: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[str] = mapped_column(String(50))


class Delivery(Base):
    __tablename__ = "webhook_deliveries"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    event: Mapped[str] = mapped_column(String(80))
    received_at: Mapped[str] = mapped_column(String(50), default=now)


class NativeProfile(Base):
    __tablename__ = "native_profiles"
    __table_args__ = (UniqueConstraint("organization_id", "scope_key"),)
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    repository_id: Mapped[str | None] = mapped_column(ForeignKey("repositories.id"), nullable=True, index=True)
    scope_key: Mapped[str] = mapped_column(String(80))
    data: Mapped[dict] = mapped_column(JSON)
    version: Mapped[int] = mapped_column(default=1)
    __mapper_args__ = {"version_id_col": version}


class CloudAsset(Base):
    """Typed inventory projection; the evidence record and immutable snapshots remain authoritative."""

    __tablename__ = "cloud_assets"
    id: Mapped[str] = mapped_column(ForeignKey("records.id", ondelete="CASCADE"), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    repository_id: Mapped[str] = mapped_column(ForeignKey("repositories.id"), index=True)
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("records.id"), index=True)
    provider: Mapped[str] = mapped_column(String(40))
    resource_id: Mapped[str] = mapped_column(String(500))
    asset_kind: Mapped[str] = mapped_column(String(120))
    exposure: Mapped[str] = mapped_column(String(60))
    encryption: Mapped[str] = mapped_column(String(60))
    observed_at: Mapped[str] = mapped_column(String(50))


def make_engine(url):
    engine = create_engine(
        url, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {}, pool_pre_ping=True
    )
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def enable_foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

    return engine


engine = make_engine(os.getenv("DATABASE_URL", "sqlite:///./data/projecttrace.db"))
Session = sessionmaker(engine, expire_on_commit=False)
