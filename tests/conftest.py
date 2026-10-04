import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from backend import main
from backend.db import Base, Grant, Organization, Repository, User, make_engine
from backend.security import passwords
from backend.seed import seed


@pytest.fixture
def client(tmp_path, monkeypatch):
    engine = make_engine(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(engine)  # Isolated test DB only; deployed schema uses Alembic.
    factory = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(main, "Session", factory)
    main.rate_windows.clear()
    with factory() as db:
        seed(db)
        db.add(Organization(id="other", name="Other tenant"))
        db.flush()
        db.add(
            User(
                id="outsider",
                organization_id="other",
                email="outside@example.com",
                password_hash=passwords.hash("Strong-test-password-123!"),
                role="ORG_OWNER",
            )
        )
        db.add(
            User(
                id="viewer",
                organization_id="northstar",
                email="viewer@example.com",
                password_hash=passwords.hash("Strong-test-password-123!"),
                role="VIEWER",
            )
        )
        db.flush()
        db.add(Grant(user_id="viewer", repository_id="clean"))
        db.add(
            Repository(
                id="private",
                organization_id="northstar",
                name="private-secret-repository",
                component="private",
                system="private",
                owner="Private Team",
                provider="LOCAL",
            )
        )
        db.commit()
    with TestClient(main.app) as test:
        test.headers["origin"] = "http://127.0.0.1:5173"
        yield test
    engine.dispose()


@pytest.fixture
def signed(client):
    response = client.post("/api/auth/demo", json={})
    assert response.status_code == 200
    client.headers["x-csrf-token"] = response.json()["csrf"]
    return client
