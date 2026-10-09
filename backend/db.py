"""Portable local adapter; PostgreSQL is the deployed database."""

import os
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
    inspect,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.orm import Session as ORMSession

from backend.settings import load_secrets, validate_production

load_secrets()
validate_production()


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
    enabled: Mapped[bool] = mapped_column(default=True)
    local_login_allowed: Mapped[bool] = mapped_column(default=True)


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
    provider_id: Mapped[str | None] = mapped_column(String(600), nullable=True)


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
    oidc_subject_id: Mapped[str | None] = mapped_column(ForeignKey("oidc_subjects.id"), nullable=True)


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


# Match the API's portable JSON expressions; payloads remain authoritative Records.
Index(
    "ix_records_graph_snapshot",
    Record.organization_id,
    Record.repository_id,
    Record.kind,
    Record.data["scope"]["snapshot_id"].as_string(),
)
for _endpoint in ("source", "target"):
    Index(
        "ix_records_graph_" + _endpoint,
        Record.organization_id,
        Record.repository_id,
        Record.kind,
        Record.data["snapshot_id"].as_string(),
        Record.data[_endpoint].as_string(),
    )

Index(
    "ix_records_graph_class",
    Record.organization_id, Record.repository_id, Record.kind,
    Record.data["scope"]["snapshot_id"].as_string(), Record.data["class"].as_string(), Record.id,
)
Index(
    "ix_records_snapshot_identity",
    Record.organization_id, Record.repository_id, Record.created_at, Record.id, Record.version,
    sqlite_where=Record.kind == "snapshot", postgresql_where=Record.kind == "snapshot",
)
for _kind, _fields in (("claim", ("status",)), ("finding", ("severity", "review_status"))):
    Index(
        "ix_records_" + _kind + "_summary",
        Record.organization_id, Record.repository_id, Record.data["scope"]["snapshot_id"].as_string(),
        *(Record.data[field].as_string() for field in _fields),
        sqlite_where=Record.kind == _kind, postgresql_where=Record.kind == _kind,
    )


class SnapshotView(Base):
    """Small version-checked read projection; published with its source snapshot."""

    __tablename__ = "snapshot_views"
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("records.id", ondelete="CASCADE"), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    repository_id: Mapped[str] = mapped_column(ForeignKey("repositories.id"), index=True)
    source_version: Mapped[int]
    data: Mapped[dict] = mapped_column(JSON)


class QueueCursor(Base):
    __tablename__ = "queue_cursor"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    last_tenant: Mapped[str] = mapped_column(String(80), default="")
    revision: Mapped[int] = mapped_column(default=0)


class QueueEntry(Base):
    __tablename__ = "queue_entries"
    __table_args__ = (
        Index("ix_queue_ready", "state", "created_at", "organization_id", "repository_id"),
        Index("ix_queue_running_scope", "organization_id", "repository_id", "state", "lease_expires_at"),
        Index("ix_queue_pr", "organization_id", "repository_id", "pr_key", "state"),
    )
    job_id: Mapped[str] = mapped_column(ForeignKey("records.id"), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    repository_id: Mapped[str] = mapped_column(ForeignKey("repositories.id"))
    state: Mapped[str] = mapped_column(String(40), default="QUEUED")
    created_at: Mapped[str] = mapped_column(String(50), default=now)
    lease_expires_at: Mapped[str | None] = mapped_column(String(50), nullable=True)
    worker_token: Mapped[str | None] = mapped_column(String(80), nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(default=False)
    pr_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    head_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)


class PRHead(Base):
    __tablename__ = "queue_pr_heads"
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), primary_key=True)
    repository_id: Mapped[str] = mapped_column(ForeignKey("repositories.id"), primary_key=True)
    pr_key: Mapped[str] = mapped_column(String(200), primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("records.id"))
    head_sha: Mapped[str] = mapped_column(String(40))


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


class QualityAnalysis(Base):
    """Immutable quality projection; source and findings stay in the Evidence Graph."""

    __tablename__ = "quality_analyses"
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("records.id", ondelete="CASCADE"), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    repository_id: Mapped[str] = mapped_column(ForeignKey("repositories.id"), index=True)
    branch: Mapped[str] = mapped_column(String(200), index=True)
    analyzer_version: Mapped[str] = mapped_column(String(40))
    profile_hash: Mapped[str] = mapped_column(String(64))
    data: Mapped[dict] = mapped_column(JSON)


class QualityOccurrence(Base):
    """Indexed occurrence pointing to the authoritative, reviewable finding record."""

    __tablename__ = "quality_occurrences"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "fingerprint"),
        Index("ix_quality_scoped_rule", "organization_id", "repository_id", "snapshot_id", "rule"),
    )
    finding_id: Mapped[str] = mapped_column(ForeignKey("records.id", ondelete="CASCADE"), primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("records.id", ondelete="CASCADE"), index=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    repository_id: Mapped[str] = mapped_column(ForeignKey("repositories.id"), index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    rule: Mapped[str] = mapped_column(String(50), index=True)
    path: Mapped[str] = mapped_column(String(240), index=True)
    symbol: Mapped[str] = mapped_column(String(500))
    language: Mapped[str] = mapped_column(String(40), index=True)
    dimension: Mapped[str] = mapped_column(String(40), index=True)
    severity: Mapped[str] = mapped_column(String(20), index=True)
    delta: Mapped[str] = mapped_column(String(30), index=True)


class TenantPolicy(Base):
    __tablename__ = "tenant_policies"
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), primary_key=True)
    data: Mapped[dict] = mapped_column(JSON)
    version: Mapped[int] = mapped_column(default=1)
    __mapper_args__ = {"version_id_col": version}


class FindingIdentity(Base):
    """Concept projection; immutable occurrence records remain authoritative."""

    __tablename__ = "finding_identities"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    repository_id: Mapped[str] = mapped_column(ForeignKey("repositories.id"), index=True)
    introduced_snapshot_id: Mapped[str] = mapped_column(ForeignKey("records.id"))
    rule: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[str] = mapped_column(String(50), default=now)


class FindingOccurrence(Base):
    __tablename__ = "finding_occurrences"
    __table_args__ = (
        Index("ix_finding_history_scope", "organization_id", "repository_id", "identity_id", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    repository_id: Mapped[str] = mapped_column(ForeignKey("repositories.id"), index=True)
    identity_id: Mapped[str] = mapped_column(ForeignKey("finding_identities.id"), index=True)
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("records.id", ondelete="CASCADE"), index=True)
    finding_id: Mapped[str | None] = mapped_column(
        ForeignKey("records.id", ondelete="CASCADE"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(40))
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(50), default=now)


class AuditHead(Base):
    __tablename__ = "audit_heads"
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), primary_key=True)
    sequence: Mapped[int]
    digest: Mapped[str] = mapped_column(String(64))


class AuditLink(Base):
    __tablename__ = "audit_links"
    __table_args__ = (UniqueConstraint("organization_id", "sequence"),)
    event_id: Mapped[str] = mapped_column(ForeignKey("audit_events.id"), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    sequence: Mapped[int]
    previous_digest: Mapped[str] = mapped_column(String(64))
    digest: Mapped[str] = mapped_column(String(64))


class SourceBlob(Base):
    __tablename__ = "source_blobs"
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), primary_key=True)
    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    bytes: Mapped[int]


class SourceInventory(Base):
    __tablename__ = "source_inventories"
    __table_args__ = (UniqueConstraint("id", "organization_id", "repository_id"),)
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    repository_id: Mapped[str] = mapped_column(ForeignKey("repositories.id"), index=True)
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(50), default=now)


class SourceInventoryFile(Base):
    __tablename__ = "source_inventory_files"
    __table_args__ = (
        ForeignKeyConstraint(
            ["inventory_id", "organization_id", "repository_id"],
            ["source_inventories.id", "source_inventories.organization_id", "source_inventories.repository_id"],
        ),
        ForeignKeyConstraint(["organization_id", "digest"], ["source_blobs.organization_id", "source_blobs.digest"]),
        Index("ix_source_files_scoped_component", "organization_id", "repository_id", "inventory_id", "component"),
    )
    inventory_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    path: Mapped[str] = mapped_column(String(240), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(80))
    repository_id: Mapped[str] = mapped_column(String(80))
    digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    component: Mapped[str] = mapped_column(String(200))
    data: Mapped[dict] = mapped_column(JSON)


class SnapshotInventory(Base):
    __tablename__ = "snapshot_inventories"
    __table_args__ = (
        ForeignKeyConstraint(
            ["inventory_id", "organization_id", "repository_id"],
            ["source_inventories.id", "source_inventories.organization_id", "source_inventories.repository_id"],
        ),
    )
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("records.id"), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    repository_id: Mapped[str] = mapped_column(ForeignKey("repositories.id"))
    inventory_id: Mapped[str] = mapped_column(String(80))


class ParserArtifact(Base):
    __tablename__ = "parser_artifacts"
    __table_args__ = (
        Index("ix_parser_artifact_scope", "organization_id", "content_hash", "parser_version"),
        Index("ix_parser_artifact_lookup", "organization_id", "id"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    content_hash: Mapped[str] = mapped_column(String(64))
    language: Mapped[str] = mapped_column(String(80))
    parser_version: Mapped[str] = mapped_column(String(64))
    rule_version: Mapped[str] = mapped_column(String(40))
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(50), default=now)


class OIDCSubject(Base):
    __tablename__ = "oidc_subjects"
    __table_args__ = (UniqueConstraint("issuer", "subject"),)
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    issuer: Mapped[str] = mapped_column(String(500))
    subject: Mapped[str] = mapped_column(String(250))
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    enabled: Mapped[bool] = mapped_column(default=True)


class OIDCAttempt(Base):
    __tablename__ = "oidc_attempts"
    state_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    browser_hash: Mapped[str] = mapped_column(String(64))
    nonce_hash: Mapped[str] = mapped_column(String(64))
    verifier_ciphertext: Mapped[str] = mapped_column(Text)
    expires: Mapped[float]
    organization_id: Mapped[str | None] = mapped_column(ForeignKey("organizations.id"), nullable=True)
    configuration_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)


def make_engine(url):
    engine = create_engine(
        url, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {}, pool_pre_ping=True
    )
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def enable_foreign_keys(connection, _):
            # Local API and Celery share this file. Rollback journals let a large
            # inventory writer block even account lookups; WAL keeps readers live.
            # SQLite's bounded busy timeout still applies to competing writers.
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA foreign_keys=ON")
            # Set a 32 MiB page-cache target for each local adapter connection.
            # The default 2 MiB cache churns on large immutable graph indexes.
            # This changes neither durability nor the repository/job limits.
            connection.execute("PRAGMA cache_size=-32768")

    return engine


engine = make_engine(os.getenv("DATABASE_URL", "sqlite:///./data/projecttrace.db"))
Session = sessionmaker(engine, expire_on_commit=False)


@event.listens_for(ORMSession, "before_flush")
def enforce_tenant_references(db, _context, _instances):
    """Reject cross-tenant ORM writes; direct SQL still requires DB-level controls."""
    pending = list(db.new)
    dirty = set(db.dirty)
    pending_by_identity = {(type(row), getattr(row, "id", None)): row for row in pending}
    references = dict(pending_by_identity)

    def lookup(model, identity):
        key = (model, identity)
        if key not in references:
            references[key] = db.get(model, identity)
        return references[key]

    for row in pending + list(dirty):
        org = getattr(row, "organization_id", None)
        repo_id = getattr(row, "repository_id", None)
        if org and row in dirty and inspect(row).attrs.organization_id.history.has_changes():
            raise ValueError("Tenant scope is immutable; cross-tenant reassignment rejected.")
        if org and repo_id:
            repo = lookup(Repository, repo_id)
            if not repo or repo.organization_id != org:
                raise ValueError("Cross-tenant repository reference rejected.")
        if isinstance(row, Grant):
            user, repo = lookup(User, row.user_id), lookup(Repository, row.repository_id)
            if not user or not repo or user.organization_id != repo.organization_id:
                raise ValueError("Cross-tenant repository grant rejected.")
        if isinstance(row, OIDCSubject):
            user = lookup(User, row.user_id)
            if not user or user.organization_id != row.organization_id:
                raise ValueError("Cross-tenant identity membership rejected.")
        if isinstance(row, FindingOccurrence):
            target = lookup(FindingIdentity, row.identity_id)
            if not target or (target.organization_id, target.repository_id) != (org, repo_id):
                raise ValueError("Cross-tenant finding identity reference rejected.")
        for field in ("snapshot_id", "introduced_snapshot_id", "finding_id", "job_id"):
            identity = getattr(row, field, None)
            if org and identity:
                target = lookup(Record, identity)
                if not target or target.organization_id != org or (repo_id and target.repository_id != repo_id):
                    raise ValueError("Cross-tenant analysis reference rejected.")
