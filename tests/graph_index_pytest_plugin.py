"""Opt-in test-only installation, restricted by exact disposable ownership."""

import os

import pytest


@pytest.fixture(autouse=True)
def isolated_graph_index_candidate(request):
    from tests.graph_index_prototype import install, listen_for_guards, mark

    mode = os.getenv("SCALE001_INDEX_TEST_MODE", "baseline")
    if "storage" in request.fixturenames:
        db, _, _ = request.getfixturevalue("storage")
        engine = db.get_bind()
    elif "client" in request.fixturenames:
        request.getfixturevalue("client")
        from backend import main

        with main.Session() as db:
            engine = db.get_bind()
    else:
        yield
        return
    with engine.connect() as connection:
        raw = connection.connection.driver_connection
        mark(raw.execute("PRAGMA database_list").fetchone()[2])
        schema = install(raw, mode)
        assert len(schema["after"]) == 4
    release = listen_for_guards(engine) if mode == "validated_partial" else lambda: None
    try:
        yield
    finally:
        release()
