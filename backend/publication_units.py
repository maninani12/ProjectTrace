"""Private file-local evidence and structural graph drafts, versioned and resumable."""
import hashlib
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from analyzers.engine import redact
from backend.analysis_checkpoints import scope
from backend.db import AnalysisInput, PublicationUnit, now

SCHEMA = "projecttrace-publication-unit-v3"
MAX_UNIT_BYTES = 4_000_000


def key(signature, stage, path=""):
    return hashlib.sha256(json.dumps([SCHEMA, signature, stage, path]).encode()).hexdigest()


def file_graph(path, digest, sections, functions):
    nodes = [{"key": "artifact", "class": "ARTIFACT", "title": path, "metadata": {"path": path, "hash": digest}}]
    edges = [{"source": "SNAPSHOT", "target": "artifact", "relationship": "CONTAINS"},
             {"source": "COMPONENT", "target": "artifact", "relationship": "CONTAINS"},
             {"source": "artifact", "target": "EVIDENCE", "relationship": "HAS_FILE_EVIDENCE"}]
    for i, section in enumerate(sections):
        identifier = "section:" + str(i)
        nodes.append({"key": identifier, "class": "DOCUMENTATION_SECTION", "title": section["title"],
                      "metadata": {"path": path, "line": section["line"]}})
        edges.append({"source": identifier, "target": "EVIDENCE", "relationship": "DOCUMENTED_BY"})
    for i, function in enumerate(functions):
        identifier = "function:" + str(i)
        nodes.append({"key": identifier, "class": "FUNCTION", "title": function["value"],
                      "metadata": {"path": path, "line": function["line"], "end_line": function.get("end_line")}})
        edges.append({"source": identifier, "target": "EVIDENCE", "relationship": "IMPLEMENTED_IN"})
    return {"nodes": nodes, "edges": edges, "sections": sections}


def validate_graph(plan, path):
    keys = {node["key"] for node in plan["nodes"]}
    if len(keys) != len(plan["nodes"]):
        raise ValueError("Graph draft contains duplicate local node identities.")
    for node in plan["nodes"]:
        if node["class"] not in {"ARTIFACT", "FUNCTION", "DOCUMENTATION_SECTION"} or node["metadata"]["path"] != path:
            raise ValueError("Graph draft node scope is invalid.")
    allowed = keys | {"SNAPSHOT", "COMPONENT", "EVIDENCE"}
    for edge in plan["edges"]:
        if edge["source"] not in allowed or edge["target"] not in allowed or edge["relationship"] not in {
            "CONTAINS", "HAS_FILE_EVIDENCE", "DOCUMENTED_BY", "IMPLEMENTED_IN"
        }:
            raise ValueError("Graph draft relationship is invalid.")


class Drafts:
    def __init__(self, db, job_id, organization_id, repository_id, signature, checkpoint):
        self.db, self.job_id = db, job_id
        self.organization_id, self.repository_id = organization_id, repository_id
        self.signature, self.checkpoint = signature, checkpoint
        scope(db, job_id, organization_id, repository_id)
        self.hits, self.completed = 0, 0
        self.created, self.reused = set(), set()

    def load(self, stage, path=""):
        from backend.queue import cipher
        identifier = key(self.signature, stage, path)
        row = self.db.get(PublicationUnit, (self.job_id, identifier))
        if row is None or row.expires_at <= now():
            return None
        if (row.organization_id, row.repository_id, row.signature, row.stage) != (
            self.organization_id, self.repository_id, self.signature, stage):
            raise ValueError("Publication unit scope is invalid.")
        raw = cipher().decrypt(row.ciphertext.encode())
        if hashlib.sha256(raw).hexdigest() != row.result_digest:
            raise ValueError("Publication unit digest is invalid.")
        value = json.loads(raw)
        expected = [SCHEMA, self.job_id, self.organization_id, self.repository_id, self.signature, stage, path]
        if value.get("identity") != expected:
            raise ValueError("Publication unit identity is invalid.")
        if stage == "FILE_GRAPH":
            validate_graph(value["data"], path)
        self.hits += 1
        if identifier not in self.created:
            self.reused.add(identifier)
        return value["data"]

    def save(self, stage, path, data, dependency=None):
        from backend.queue import cipher
        raw = json.dumps({"identity": [SCHEMA, self.job_id, self.organization_id, self.repository_id,
                                      self.signature, stage, path], "data": data}, sort_keys=True).encode()
        if len(raw) > MAX_UNIT_BYTES:
            raise ValueError("Publication unit exceeds its bounded byte budget.")
        self.checkpoint()  # Own the fenced claim until this unit is committed.
        if dependency and self.load(*dependency) is None:
            raise ValueError("Publication unit dependency is incomplete.")
        retained = self.db.get(AnalysisInput, self.job_id)
        identifier = key(self.signature, stage, path)
        row = self.db.get(PublicationUnit, (self.job_id, identifier))
        if row is None:
            row = PublicationUnit(job_id=self.job_id, unit_key=identifier,
                                  organization_id=self.organization_id, repository_id=self.repository_id)
            self.db.add(row)
        row.signature, row.stage = self.signature, stage
        row.dependency_key = key(self.signature, *dependency) if dependency else None
        row.ciphertext = cipher().encrypt(raw).decode()
        row.result_digest = hashlib.sha256(raw).hexdigest()
        row.expires_at = min(retained.expires_at if retained else "9999",
                             (datetime.now(timezone.utc) + timedelta(hours=72)).isoformat())
        self.db.commit()
        self.completed += 1
        self.created.add(identifier)

    def require(self, stage, path=""):
        value = self.load(stage, path)
        if value is None:
            raise ValueError("Required publication unit is unavailable.")
        return value


def prepare(db, job_id, files, signature, result, checkpoint):
    drafts = Drafts(db, job_id, files.organization_id, files.repository_id, signature, checkpoint)
    paths = list(result["files"])
    path_digest = hashlib.sha256()
    for path in paths:
        path_digest.update(json.dumps(path).encode() + b"\n")
    manifest = {"file_count": len(paths), "paths_digest": path_digest.hexdigest(), "inventory_id": files.inventory_id}
    if drafts.load("MANIFEST") is None:
        drafts.save("MANIFEST", "", manifest)
    elif drafts.require("MANIFEST") != manifest:
        raise ValueError("Publication manifest changed within the same generation.")
    functions = {}
    for signal in result["signals"]:
        if signal["type"] == "function":
            functions.setdefault(signal["path"], []).append(signal)
    for path in paths:
        checkpoint()
        db.commit()  # End the short renewal before bounded source/object reads.
        if drafts.load("EVIDENCE", path) is None:
            source = files[path]
            redacted = redact(source)
            digest = files.hash_for(path)
            if hashlib.sha256(redacted.encode()).hexdigest() != digest:
                digest = files.store.put(db, files.organization_id, redacted.encode())[0]
            drafts.save("EVIDENCE", path, {"source_blob_digest": digest,
                        "line_count": len(redacted.splitlines())}, ("MANIFEST", ""))
        if drafts.load("FILE_GRAPH", path) is None:
            sections = []
            if path.endswith(".md"):
                sections = [{"title": redact(line.lstrip("# ")), "line": n}
                            for n, line in enumerate(files[path].splitlines(), 1) if line.startswith("#")]
            plan = file_graph(path, files.hash_for(path), sections, functions.get(path, []))
            drafts.save("FILE_GRAPH", path, plan, ("EVIDENCE", path))
    readiness = {"required_units": 1 + 2 * len(paths), "manifest_digest": hashlib.sha256(
        json.dumps(manifest, sort_keys=True).encode()).hexdigest(), "validation": "COMPLETE"}
    existing = drafts.load("READY")
    if existing is None:
        drafts.save("READY", "", readiness, ("MANIFEST", ""))
    elif existing != readiness:
        raise ValueError("Publication preparation readiness is inconsistent.")
    performance = getattr(checkpoint, "performance", None)
    if performance:
        performance.count("publication_units_reused", len(drafts.reused))
        performance.count("publication_units_completed", drafts.completed)
    return drafts


def purge_expired(db):
    for unit in db.scalars(select(PublicationUnit).where(PublicationUnit.expires_at <= now()).limit(1000)):
        db.delete(unit)
