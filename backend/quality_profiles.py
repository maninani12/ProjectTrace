"""Recommended -> organization -> team -> repository inheritance without copies."""

import copy
import re

from sqlalchemy import select

from analyzers.code_quality.rules import config
from backend.db import NativeProfile


def merge(base, patch):
    result = copy.deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def scope_key(repository_id=None, team_id=None):
    if repository_id and team_id:
        raise ValueError("Select repository or team profile scope.")
    if team_id:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,60}", team_id):
            raise ValueError("Invalid team profile ID.")
        return "team:" + team_id
    return repository_id or "organization"


def effective(db, organization_id, repository_id=None, team_id=None):
    selected = scope_key(repository_id, team_id)

    def row(key):
        return db.scalar(
            select(NativeProfile).where(
                NativeProfile.organization_id == organization_id, NativeProfile.scope_key == key
            )
        )

    local = row(selected)
    organization = row("organization")
    assigned = team_id or (local.data.get("quality_team") if local and repository_id else None)
    team = row(scope_key(team_id=assigned)) if assigned else None
    chain = []
    for item in (organization, team, local):
        if item and item.id not in {r.id for r in chain}:
            chain.append(item)
    result, provenance = {}, []
    for item in chain:
        result = merge(result, {k: v for k, v in item.data.items() if k != "quality_team"})
        provenance.append({"id": item.id, "scope": item.scope_key, "version": item.version})
    result["quality"] = config(result.get("quality"))
    result["version"] = local.version if local else 0
    result["profile_lineage"] = provenance
    return result, local
