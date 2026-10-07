"""Operator-owned secret-file injection; imported repository configuration never reaches this loader."""

import os
import re
from pathlib import Path

SECRET_NAMES = {
    "ANALYSIS_PREVIOUS_KEYS",
    "DATABASE_URL",
    "REDIS_URL",
    "ANALYSIS_INPUT_KEY",
    "AUDIT_CHECKPOINT_KEY",
    "OIDC_CLIENT_SECRET",
    "GITHUB_PRIVATE_KEY",
    "GITHUB_WEBHOOK_SECRET",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
}


def load_secrets():
    for name, path in list(os.environ.items()):
        if not name.endswith("_FILE") or not path:
            continue
        key = name[:-5]
        if key not in SECRET_NAMES and not re.fullmatch(r"SCM_[A-Z0-9_]{1,80}", key):
            continue
        try:
            with Path(path).open("rb") as stream:
                raw = stream.read(32769)
            if not raw or len(raw) > 32768:
                raise ValueError()
            value = raw.decode().strip()
            if not value or (os.getenv(key) and os.environ[key] != value):
                raise ValueError()
        except (OSError, UnicodeError, ValueError):
            raise RuntimeError(
                f"Operator secret file for {key} is unavailable, oversized or conflicts with its environment value."
            ) from None
        os.environ[key] = value


def validate_production():
    if os.getenv("APP_ENV") != "production":
        return
    from urllib.parse import parse_qs, urlsplit

    from cryptography.fernet import Fernet
    from sqlalchemy.engine import make_url
    from sqlalchemy.exc import ArgumentError

    try:
        database = make_url(os.getenv("DATABASE_URL", ""))
        redis = urlsplit(os.getenv("REDIS_URL", ""))
        if not database.drivername.startswith("postgresql") or database.query.get("sslmode") != "verify-full":
            raise ValueError()
        if (
            redis.scheme != "rediss"
            or not redis.hostname
            or parse_qs(redis.query).get("ssl_cert_reqs", ["required"])[0].lower() != "required"
        ):
            raise ValueError()
        Fernet(os.environ["ANALYSIS_INPUT_KEY"].encode())
        origins = os.getenv("CORS_ORIGINS", "").split(",")
        if not origins or any(
            urlsplit(origin).scheme != "https" or not urlsplit(origin).hostname or "*" in origin for origin in origins
        ):
            raise ValueError()
        if os.getenv("JOB_MODE") != "celery":
            raise ValueError()
    except (ValueError, KeyError, TypeError, ArgumentError):
        raise RuntimeError(
            "Production requires verified PostgreSQL/Redis TLS, explicit HTTPS origins, Celery and a valid operator encryption key."
        ) from None
