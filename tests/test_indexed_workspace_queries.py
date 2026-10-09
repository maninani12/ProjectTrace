"""Exercise query plans and cached constant paths, including self-edge deduplication."""
import pytest
from sqlalchemy import event, func, select, text

from backend import main
from backend.db import Record, User
from backend.domain import add
from backend.json_query import indexed_text
from backend.workspace_read import scoped_current
from tests.test_workspace_pagination import current_scope


def test_summary_reads_use_small_covering_indexes(signed):
    repo, _ = current_scope(signed)
    with main.Session() as db:
        user = db.scalar(select(User).where(User.email == 'demo@projecttrace.local'))
        repositories = main.allowed_repositories(db, user)
        repositories = [item for item in repositories if item.id == repo['id']]
        snapshots = main.workspace_snapshots(db, user, repositories)
        for kind, field in (('claim', 'status'), ('finding', 'severity')):
            value = indexed_text(Record.data, field)
            query = scoped_current(user, repositories, snapshots, [kind]).with_only_columns(value, func.count()).group_by(value)
            sql = str(query.compile(db.bind, compile_kwargs={'literal_binds': True}))
            plan = db.execute(text('EXPLAIN QUERY PLAN ' + sql)).all()
            assert any('ix_records_' + kind + '_summary' in row[-1] for row in plan), plan


def test_constant_json_paths_have_distinct_cache_keys_and_values(signed):
    with main.Session() as db:
        row = add(db, 'northstar', 'identity', 'query_fixture', {'left': 'A', 'right': 'B'})
        left = select(indexed_text(Record.data, 'left')).where(Record.id == row.id)
        right = select(indexed_text(Record.data, 'right')).where(Record.id == row.id)
        assert left._generate_cache_key() != right._generate_cache_key()
        assert db.scalar(left) == 'A' and db.scalar(right) == 'B' and db.scalar(left) == 'A'
    with pytest.raises(ValueError):
        indexed_text(Record.data, "caller' SQL")


def test_neighborhood_union_deduplicates_self_edges_and_keeps_relationship_filter(signed):
    repo, _ = current_scope(signed)
    with main.Session() as db:
        node = db.scalar(select(Record).where(Record.repository_id == repo['id'], Record.kind == 'graph_node',
            indexed_text(Record.data, 'scope', 'snapshot_id') == repo['snapshot']['id']))
        edge = add(db, 'northstar', repo['id'], 'edge', {'source':node.id,'target':node.id,
            'relationship':'SELF_FIXTURE','snapshot_id':repo['snapshot']['id']})
        db.commit()
    result = signed.get('/api/graph/neighborhood', params={'node_id':node.id,'relationship':'SELF_FIXTURE'}).json()
    assert result['total'] == 1 and [item['id'] for item in result['edges']] == [edge.id]
    assert len(result['nodes']) == 1


def test_infrastructure_read_seeks_snapshot_and_class_indexes(signed):
    from tests.test_code_quality import import_repo
    repo, sid = import_repo(signed, {"main.tf":'resource "aws_s3_bucket" "fixture" { acl = "public-read" }'})
    queries = []
    with main.Session() as db:
        engine = db.bind
    def capture(conn, cursor, statement, parameters, context, many):
        if "SELECT cloud_assets.id" in statement:
            queries.append((statement, parameters))
    event.listen(engine, "before_cursor_execute", capture)
    try:
        response = signed.get("/api/trust/infrastructure", params={"repository_id":repo,"snapshot_id":sid,"limit":1})
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert response.status_code == 200 and response.json()["resources"] and response.json()["findings"]
    assert len(queries) == 1
    with engine.connect() as conn:
        plan = conn.exec_driver_sql("EXPLAIN QUERY PLAN " + queries[0][0], queries[0][1]).all()
    assert any("ix_records_graph_class" in row[-1] and "<expr>" in row[-1] for row in plan), plan
