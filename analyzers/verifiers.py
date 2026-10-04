"""Small deterministic verifiers. Static evidence never implies observed runtime.

The cache fingerprints each verifier's complete input subset, including absence.
Repository text remains data: no imported code, tools or provider calls occur here.
"""

import hashlib
import json
import re

TECHNOLOGIES = {
    "fastapi": ("FastAPI", "TECHNOLOGY", {"fastapi"}),
    "flask": ("Flask", "TECHNOLOGY", {"flask"}),
    "django": ("Django", "TECHNOLOGY", {"django"}),
    "react": ("React", "TECHNOLOGY", {"react", "react-dom"}),
    "express": ("Express", "TECHNOLOGY", {"express"}),
    "sqlalchemy": ("SQLAlchemy", "TECHNOLOGY", {"sqlalchemy"}),
    "postgresql": ("PostgreSQL", "TECHNOLOGY", {"psycopg", "psycopg2", "asyncpg", "postgres", "pg"}),
    "mysql": ("MySQL", "TECHNOLOGY", {"pymysql", "mysql", "mysqlclient", "mysql2"}),
    "sqlite": ("SQLite", "TECHNOLOGY", {"sqlite3", "aiosqlite", "sqlite"}),
    "mongodb": ("MongoDB", "TECHNOLOGY", {"pymongo", "motor", "mongoose", "mongodb"}),
    "redis": ("Redis", "TECHNOLOGY", {"redis", "ioredis"}),
    "kafka": ("Kafka", "ARCHITECTURE", {"kafka", "kafka-python", "confluent_kafka"}),
    "jwt": ("JWT", "AUTHENTICATION", {"jwt", "pyjwt", "jsonwebtoken"}),
    "session": ("sessions", "AUTHENTICATION", {"express-session"}),
    "oauth": ("OAuth", "AUTHENTICATION", {"authlib", "oauthlib"}),
    "rbac": ("RBAC", "AUTHORIZATION", set()),
    "pytest": ("pytest", "TESTING", {"pytest"}),
    "jest": ("Jest", "TESTING", {"jest"}),
    "vitest": ("Vitest", "TESTING", {"vitest"}),
    "github actions": ("GitHub Actions", "CI", set()),
    "docker": ("Docker", "INFRASTRUCTURE", set()),
    "kubernetes": ("Kubernetes", "INFRASTRUCTURE", {"kubernetes"}),
    "terraform": ("Terraform", "INFRASTRUCTURE", set()),
    "aws": ("AWS", "INFRASTRUCTURE", {"boto3"}),
    "azurerm": ("Azure", "INFRASTRUCTURE", set()),
    "google": ("Google Cloud", "INFRASTRUCTURE", set()),
    "tls": ("TLS", "SECURITY_CONTROL", set()),
}
TOKEN_ALIASES = {
    "postgres": "postgresql",
    "postgresql": "postgresql",
    "sessions": "session",
    "session-based": "session",
    "cookie sessions": "session",
    "oauth2": "oauth",
    "json web tokens": "jwt",
    "json web token": "jwt",
    "k8s": "kubernetes",
    "azure": "azurerm",
    "gcp": "google",
    "google cloud": "google",
    **{value: value for value in TECHNOLOGIES},
}
TOKEN = re.compile(
    r"(?<![\w-])(" + "|".join(re.escape(t) for t in sorted(TOKEN_ALIASES, key=len, reverse=True)) + r")(?![\w-])", re.I
)
DECLARATION = re.compile(
    r"\b(?:backend|frontend|database|authentication|authorization|auth|testing|tests?|"
    r"ci|continuous integration|deployment|infrastructure|encryption|the api|api|"
    r"(?:our |the )?(?:application|app|service|server|project|system|platform))\s+"
    r"(?:uses?|runs? on|is built (?:with|on)|is powered by|is implemented (?:with|using)|"
    r"relies on|is based on|supports?|implements?|is secured (?:by|with)|"
    r"is authenticated (?:using|with)|is deployed (?:with|on)|runs? (?:with|using))\s+([^.;]+)",
    re.I,
)


def claim_key(claim):
    """Identity survives equivalent wording and document line movement."""
    fields = [
        claim.get("category"),
        claim.get("expected"),
        claim.get("origin", "DOCUMENTATION"),
        claim.get("path"),
        claim.get("assertion_family", "declaration"),
    ]
    return hashlib.sha256(json.dumps(fields, ensure_ascii=True).encode()).hexdigest()


def extract_documentation(files):
    claims, seen = [], set()
    for path, text in files.items():
        if not path.endswith(".md"):
            continue
        fenced = False
        for line_no, line in enumerate(text.splitlines(), 1):
            if line.lstrip().startswith(("```", "~~~")):
                fenced = not fenced
                continue
            if fenced:
                continue
            candidates = []
            for declaration in DECLARATION.finditer(line):
                content = declaration.group(1)
                for match in TOKEN.finditer(content):
                    preceding = re.split(r",|\band\b|\bbut\b", content[: match.start()], flags=re.I)[-1]
                    if re.search(r"\b(?:not|no|without|never|avoid|might|may|planned|future)\b", preceding, re.I):
                        continue
                    expected = TOKEN_ALIASES[match.group(1).lower()]
                    label, category, _ = TECHNOLOGIES[expected]
                    subject = {
                        "AUTHENTICATION": "Authentication",
                        "AUTHORIZATION": "Authorization",
                        "TESTING": "Testing",
                        "CI": "CI",
                        "INFRASTRUCTURE": "Infrastructure",
                        "SECURITY_CONTROL": "Encryption",
                        "ARCHITECTURE": "Architecture",
                    }.get(
                        category, "Database" if expected in {"postgresql", "mysql", "sqlite", "mongodb"} else "Backend"
                    )
                    candidates.append((category, expected, f"{subject} uses {label}."))
            for match in re.finditer(
                r"\b(?:the )?API\s+(?:exposes|provides|serves)\s+(?:(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+)?(/[\w/{}/.-]+)",
                line,
                re.I,
            ):
                method, route = match.groups()
                candidates.append(
                    ("API", (method or "GET").upper() + " " + route.rstrip("."), match.group(0).rstrip(".") + ".")
                )
            for match in re.finditer(r"\bOrders publishes events through (Kafka|Redis)\b", line, re.I):
                candidates.append(("ARCHITECTURE", match.group(1).lower(), match.group(0) + "."))
            for category, expected, statement in candidates:
                identity = (path, category, expected)
                if identity in seen:
                    continue
                seen.add(identity)
                claims.append(
                    dict(
                        text=statement,
                        category=category,
                        expected=expected,
                        path=path,
                        line=line_no,
                        assertion_family="declaration",
                    )
                )
    return claims


class Verifier:
    name = "TechnologyVerifier"
    signal_types = {"technology", "database", "import"}

    def inputs(self, claim, signals, dependencies):
        expected = claim["expected"].lower()
        aliases = TECHNOLOGIES.get(expected, (expected, "", {expected}))[2] | {expected}
        selected = [
            s
            for s in signals
            if s["type"] in self.signal_types
            and (
                s["value"].lower() == expected or s["type"] == "import" and s["value"].split(".")[0].lower() in aliases
            )
        ]
        deps = [d for d in dependencies if d["name"].lower() in aliases]
        return selected, deps

    def evaluate(self, claim, signals, dependencies):
        explicit = [s for s in signals if s["type"] != "import"]
        if explicit:
            return (
                "VERIFIED",
                "Current static syntax/configuration supports this declaration; runtime is unobserved.",
                explicit,
            )
        if signals:
            return "INFERRED", "Related modules are imported; an import alone does not establish runtime use.", signals
        if dependencies:
            return "INFERRED", "A manifest declares this dependency; availability does not establish runtime use.", []
        return (
            "UNVERIFIED",
            "No conclusive supported static evidence was found. Absence does not prove a contradiction.",
            [],
        )


class DatabaseVerifier(Verifier):
    name = "DatabaseVerifier"


class AuthenticationVerifier(Verifier):
    name = "AuthenticationVerifier"
    signal_types = {"auth", "auth_hint", "import"}

    def inputs(self, claim, signals, dependencies):
        selected, deps = super().inputs(claim, signals, dependencies)
        if claim["expected"] == "session":
            selected.extend(
                s for s in signals if s["type"] == "auth_hint" and "session" in s["value"].lower() and s not in selected
            )
        # All affirmative configured modes are inputs to an exclusivity comparison.
        return [s for s in signals if s["type"] == "auth"] + [s for s in selected if s["type"] != "auth"], deps

    def evaluate(self, claim, signals, dependencies):
        modes = {s["value"] for s in signals if s["type"] == "auth"}
        supporting = [s for s in signals if s["type"] == "auth" and s["value"] == claim["expected"]]
        if supporting:
            return (
                "VERIFIED",
                "Executable syntax configures the declared authentication mechanism; runtime is unobserved.",
                supporting,
            )
        if modes and claim["expected"] in {"jwt", "session"} and modes <= {"jwt", "session"}:
            return (
                "CONTRADICTED",
                "The scanned static configuration selects "
                + ", ".join(sorted(modes))
                + "; additional unscanned services remain outside this scope.",
                [s for s in signals if s["type"] == "auth"],
            )
        inferred = [s for s in signals if s["type"] != "auth"]
        if inferred or dependencies:
            return (
                "INFERRED",
                "Authentication-related imports or hints exist; the configured mechanism is unproven.",
                inferred,
            )
        return super().evaluate(claim, [], [])


class APIVerifier(Verifier):
    name = "APIVerifier"
    signal_types = {"route"}


class AuthorizationVerifier(Verifier):
    name = "AuthorizationVerifier"
    signal_types = {"authorization"}


class InfrastructureVerifier(Verifier):
    name = "InfrastructureVerifier"
    signal_types = {"infrastructure"}


class TestingVerifier(Verifier):
    name = "TestingVerifier"
    signal_types = {"testing", "import", "technology"}


class CIWorkflowVerifier(Verifier):
    name = "CIWorkflowVerifier"
    signal_types = {"ci"}


class ArchitectureVerifier(Verifier):
    name = "ArchitectureVerifier"


class SecurityControlVerifier(Verifier):
    name = "SecurityControlVerifier"
    signal_types = {"security_control"}


class ConfigurationVerifier(Verifier):
    name = "ConfigurationVerifier"
    signal_types = {"configuration"}


class DependencyVerifier(Verifier):
    name = "DependencyVerifier"
    signal_types = set()


class DeploymentVerifier(InfrastructureVerifier):
    name = "DeploymentVerifier"


VERIFIERS = {
    "AUTHENTICATION": AuthenticationVerifier(),
    "AUTHORIZATION": AuthorizationVerifier(),
    "API": APIVerifier(),
    "INFRASTRUCTURE": InfrastructureVerifier(),
    "TESTING": TestingVerifier(),
    "CI": CIWorkflowVerifier(),
    "ARCHITECTURE": ArchitectureVerifier(),
    "CONFIGURATION": ConfigurationVerifier(),
    "DEPENDENCY": DependencyVerifier(),
    "DEPLOYMENT": DeploymentVerifier(),
    "SECURITY_CONTROL": SecurityControlVerifier(),
}


def verifier_for(claim):
    if claim["category"] == "TECHNOLOGY" and claim["expected"] in {"postgresql", "mysql", "sqlite", "mongodb"}:
        return DatabaseVerifier()
    return VERIFIERS.get(claim["category"], Verifier())


def verify_claim(claim, signals, dependencies, previous=None):
    verifier = verifier_for(claim)
    selected, deps = verifier.inputs(claim, signals, dependencies)
    payload = [
        verifier.name,
        claim["category"],
        claim["expected"],
        sorted((s["type"], s["value"], s["path"], s["line"]) for s in selected),
        sorted((d["ecosystem"], d["name"], d["version"], d["path"]) for d in deps),
    ]
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    if previous and previous.get("fingerprint") == fingerprint:
        return {**previous, "verifier": verifier.name}, True
    status, reason, evidence = verifier.evaluate(claim, selected, deps)
    return dict(fingerprint=fingerprint, status=status, reason=reason, signals=evidence, verifier=verifier.name), False
