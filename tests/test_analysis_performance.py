import ast
import json
import threading

import pytest
from sqlalchemy import func, select

from analyzers.engine import finding, native_observations
from analyzers.finding_identity import annotate
from analyzers.performance import Performance
from backend.db import ParserArtifact, Record
from backend.jobs import execute_analysis
from backend.partitioned_analysis import analyze_inventory
from tests.test_repository_store import captured
from tests.test_repository_store import storage as storage


def test_structural_identity_hashes_a_file_once_without_changing_identity(monkeypatch):
    source = "def inspect(value):\n" + "    eval(value)\n" * 80
    findings = [finding("PT-SAST-005", "app.py", line) for line in range(2, 82)]
    original = ast.dump
    module_dumps = []
    def counted(node, *a, **kw):
        if isinstance(node, ast.Module):
            module_dumps.append(node)
        return original(node, *a, **kw)
    monkeypatch.setattr(ast, "dump", counted)
    annotate({"app.py": source}, findings, [])
    assert len(module_dumps) == 1
    assert all(row["identity_method"] == "PYTHON_AST" for row in findings)
    assert len({row["structural_context_hash"] for row in findings}) == 1
    assert len({row["file_structure_hash"] for row in findings}) == 1


def test_partition_source_cache_is_bounded_scoped_and_revalidates_next_partition(storage):
    sources = {f"part{i}.txt": "x" * 480_000 for i in range(5)}
    files = captured(storage, sources)
    part = files.view(cache_sources=True)
    for path in sources:
        assert part[path] == sources[path]
        assert part._source_cache_bytes <= 2_000_000
    assert part._source_reads == 5
    assert part["part4.txt"] == sources["part4.txt"] and part._source_hits == 1
    target = files.store.path(files.organization_id, files.hash_for("part4.txt"))
    target.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="integrity"):
        files.view(cache_sources=True)["part4.txt"]


def test_only_two_independent_helpers_run_concurrently_and_keep_results(monkeypatch):
    from analyzers import engine
    sources = {"app.ts": "export function inspect(v: string) { return eval(v); }", "Dockerfile": "FROM ubuntu:latest\nUSER root\n"}
    expected = native_observations(sources)
    syntax, iac = engine.analyze_languages, engine.structured_iac_batch
    barrier = threading.Barrier(2)
    running, maximum, lock = 0, 0, threading.Lock()
    def wrapper(function):
        def call(*a, **kw):
            nonlocal running, maximum
            with lock:
                running += 1
                maximum = max(maximum, running)
            try:
                barrier.wait(timeout=5)
                return function(*a, **kw)
            finally:
                with lock:
                    running -= 1
        return call
    monkeypatch.setattr(engine, "analyze_languages", wrapper(syntax))
    monkeypatch.setattr(engine, "structured_iac_batch", wrapper(iac))
    assert native_observations(sources) == expected
    assert maximum == 2


def test_incremental_analysis_reuses_unchanged_observations_and_reparses_changed_file(storage):
    db, _, _ = storage
    first = captured(storage, {"a.py": "def inspect(v):\n    return eval(v)\n", "b.py": "VALUE = 1\n"})
    initial = analyze_inventory(db, first)
    db.commit()
    unchanged = analyze_inventory(db, first)
    assert unchanged["source_storage"]["parser_cache_hits"] == 2
    assert unchanged["findings"] == initial["findings"]
    changed = captured(storage, {"a.py": "def inspect(v):\n    return eval(v)\n", "b.py": "VALUE = 2\n"})
    final = analyze_inventory(db, changed)
    assert final["source_storage"]["parser_cache_hits"] == 1
    assert final["source_storage"]["parser_cache_misses"] == 1


def test_completed_partitions_and_performance_survive_later_timeout(storage, monkeypatch):
    from backend import partitioned_analysis
    db, user, repo = storage
    files = captured(storage, {f"app{i:03d}.py": "VALUE = 1\n" for i in range(101)})
    original, calls = partitioned_analysis.native_observations, 0
    def interrupted(*a, **kw):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise TimeoutError("Synthetic bounded interruption")
        return original(*a, **kw)
    monkeypatch.setattr(partitioned_analysis, "native_observations", interrupted)
    with pytest.raises(TimeoutError):
        execute_analysis(db, user, repo, files)
    assert db.scalar(select(func.count()).select_from(ParserArtifact)) == 100
    job = db.scalar(select(Record).where(Record.kind == "job"))
    assert job.data["performance"]["counters"]["parser_cache_misses"] == 100
    assert db.scalar(select(func.count()).select_from(Record).where(Record.kind == "snapshot")) == 0


def test_performance_metadata_is_bounded_and_contains_no_source():
    timing = Performance()
    for i in range(1000):
        timing.record("PYTHON_NATIVE", i / 1000, f"app{i}.py")
    receipt = timing.snapshot()
    assert len(receipt["slowest_file_operations"]) == 40
    assert receipt["components"]["PYTHON_NATIVE"]["count"] == 1000
    assert "source" not in json.dumps(receipt["slowest_file_operations"])


def test_compact_tokens_preserve_full_duplication_results():
    from analyzers.code_quality.duplication import detect
    from analyzers.compact_tokens import CompactTokens
    tokens = [{"value": f"name:{i % 17}", "line": i // 5 + 1} for i in range(200)]
    rows = [{"path": path, "language": "Python", "name": "inspect", "duplicate_tokens": tokens}
            for path in ("a.py", "b.py")]
    compact = [{**r, "duplicate_tokens": CompactTokens(r["duplicate_tokens"])} for r in rows]
    assert list(compact[0]["duplicate_tokens"]) == tokens
    assert detect(compact) == detect(rows)


def test_parser_diagnostics_survive_without_fake_completed_results(storage):
    db, user, repo = storage
    files = captured(storage, {"bad.py": "def invalid(:\n", "template.yaml": "{{ .Values.notExecuted }}"})
    snapshot, job = execute_analysis(db, user, repo, files)
    rows = list(db.scalars(select(Record).where(Record.kind == "parser_diagnostic")))
    assert snapshot.data["status"] == "PARTIAL" and rows
    assert all(r.data["job_id"] == job.id and r.data["inventory_id"] == files.inventory_id for r in rows)
    assert all(r.data["result_scope"] == "FILE_LOCAL_DIAGNOSTIC_ONLY" for r in rows)


def test_operator_retry_preserves_original_inventory_history_and_authorization(storage, monkeypatch):
    from backend.db import Grant
    from backend.queue import enqueue_analysis
    from scripts.retry_retained_analysis import retry
    db, user, repo = storage
    db.add(Grant(user_id=user.id, repository_id=repo.id))
    db.commit()
    files = captured(storage, {"app.py": "VALUE = 1\n"})
    monkeypatch.setenv("JOB_MODE", "local")
    job = enqueue_analysis(db, user, repo, files, source="INVENTORY")
    job.data = {**job.data, "state": "FAILED", "duration_ms": 901000, "error_code": "ANALYSIS_TIME_BUDGET"}
    db.commit()
    user.enabled = False
    db.commit()
    with pytest.raises(ValueError, match="authorization"):
        retry(db, job.id)
    user.enabled = True
    db.commit()
    receipt = retry(db, job.id)
    assert receipt["inventory_id"] == files.inventory_id and receipt["retry_count"] == 1
    assert job.data["attempt_history"][-1]["duration_ms"] == 901000
    assert job.data["duration_ms"] is None and job.data["source"] == "INVENTORY"
    job.data = {**job.data, "state": "FAILED", "retry_count": 2}
    db.commit()
    with pytest.raises(ValueError, match="bounded"):
        retry(db, job.id)


def test_helper_timeout_retains_completed_file_and_diagnoses_remaining(monkeypatch):
    import subprocess

    from analyzers.languages import analyze_languages
    packet = {"schema": "projecttrace-parser-packet-v1", "path": "finished.ts", "result": [[], [], []],
              "seconds": 0.12, "state": "COMPLETED"}
    prefix = json.dumps(packet).encode() + b"\n" + b'{"incomplete":'
    def stopped(*a, **kw):
        raise subprocess.TimeoutExpired(a[0], 30, output=prefix)
    monkeypatch.setattr("analyzers.languages.subprocess.run", stopped)
    observed = analyze_languages({"finished.ts": "export const x = 1;", "pending.ts": "export const y = 2;"})
    assert observed["finished.ts"] == [[], [], []]
    assert observed["pending.ts"]["code"] == "HELPER_TIMEOUT"


def test_packet_scope_duplicates_and_corruption_are_rejected():
    from analyzers.parser_protocol import completed_packets
    packet = {"schema": "projecttrace-parser-packet-v1", "path": "owned.ts", "result": [[], [], []],
              "seconds": 0.1, "state": "COMPLETED"}
    encoded = json.dumps(packet).encode() + b"\n"
    with pytest.raises(ValueError, match="scope"):
        completed_packets(encoded, {"other.ts": ""}, 10000)
    with pytest.raises(ValueError, match="duplicate"):
        completed_packets(encoded * 2, {"owned.ts": ""}, 10000)
    with pytest.raises(ValueError, match="malformed"):
        completed_packets(b"broken\n" + encoded, {"owned.ts": ""}, 10000)


def test_quality_owner_lookup_sorts_each_file_once_and_keeps_narrowest_stable_match(monkeypatch):
    from builtins import sorted as builtin_sorted

    from analyzers.code_quality import core
    sources = {f"app{i}.py": "VALUE = 1\n" for i in range(50)}
    metrics, signals = [], []
    for path in sources:
        for index in range(100):
            metrics.append({"path": path, "language": "Python", "name": str(index),
                            "qualified_name": str(index), "line": 1, "end_line": 10 if index < 2 else 100,
                            "body_hash": str(index), "cyclomatic": 1, "nesting": 0, "parameters": 0,
                            "length": 1, "cognitive_approximation": 0})
        signals.append({"type": "quality_file", "path": path,
                        "observations": [{"rule": "PT-QUALITY-005", "line": 2,
                                          "anchor": str(i), "detail": "Fixture observation"} for i in range(5)]})
    sizes = []
    def bounded_sorted(items, *args, **kwargs):
        if kwargs.get('key'):
            sizes.append(len(items))
            assert len(items) <= 100
        return builtin_sorted(items, *args, **kwargs)
    monkeypatch.setattr(core, 'sorted', bounded_sorted, raising=False)
    findings, _ = core.build(sources, metrics, signals, [], [])
    assert sizes == [100] * 50
    assert len(findings) == 250
    assert all(row['symbol'] == '0' and row['end_line'] == 10 for row in findings)


def test_publication_checks_deadline_before_unbounded_output_and_rolls_back(storage, monkeypatch):
    from backend import jobs
    from backend.domain import add
    db, user, repo = storage
    files = captured(storage, {'app.py': 'VALUE = 1\n'})
    elapsed, created = [0], []
    def publication(db, user, repo, files, *, progress, **options):
        progress('BUILDING_EVIDENCE')
        for index in range(600):
            elapsed[0] += 4
            add(db, user.organization_id, repo.id, 'evidence', {'index': index}, defer_flush=True)
            created.append(index)
        raise AssertionError('Publication did not enforce its deadline')
    monkeypatch.setattr(jobs, 'persist_analysis', publication)
    with pytest.raises(TimeoutError):
        jobs.execute_analysis(db, user, repo, files, _elapsed_clock=lambda: elapsed[0])
    job = db.scalar(select(Record).where(Record.kind == 'job'))
    assert job.data['error_code'] == 'ANALYSIS_TIME_BUDGET'
    assert job.data['error_detail']['maximum'] == 900
    assert len(created) == 249
    assert db.scalar(select(func.count()).select_from(Record).where(Record.kind == 'evidence')) == 0
    assert 'analysis_output_checkpoint' not in db.info


def test_publication_writes_bounded_batches_and_preserves_all_rows(storage, monkeypatch):
    from sqlalchemy import event

    from backend import jobs
    from backend.domain import add
    db, user, repo = storage
    files = captured(storage, {'app.py': 'VALUE = 1\n'})
    flush_sizes = []
    event.listen(db, 'before_flush', lambda session, context, instances: flush_sizes.append(
        sum(isinstance(row, Record) and row.kind == 'evidence' for row in session.new)))
    def publication(db, user, repo, files, *, progress, **options):
        progress('BUILDING_EVIDENCE')
        for index in range(600):
            add(db, user.organization_id, repo.id, 'evidence', {'index': index})
        return add(db, user.organization_id, repo.id, 'snapshot', {'status': 'COMPLETED', 'warnings': []})
    monkeypatch.setattr(jobs, 'persist_analysis', publication)
    _, job = jobs.execute_analysis(db, user, repo, files)
    assert job.data['state'] == 'COMPLETED'
    assert db.scalar(select(func.count()).select_from(Record).where(Record.kind == 'evidence')) == 600
    assert max(flush_sizes) <= 250
    assert sum(flush_sizes) == 600
    assert len([size for size in flush_sizes if size]) <= 5
    assert 'analysis_output_checkpoint' not in db.info


def test_compiled_ownership_keeps_glob_order_and_does_not_cache_fallback():
    from analyzers.code_quality.classification import matches, ownership, ownership_rules
    class Inventory(dict):
        inventory_id = 'owned-test-inventory'
    lines = ['* @global', '/src/ @source', '**/tests/** @tests', '!src/** @ignored',
             'src/a.py @first @second # comment', '*.py @python'] + ['# comment'] * 4994 + ['* @beyond-budget']
    files = Inventory({'CODEOWNERS': '\n'.join(lines)})
    compiled = ownership_rules(files)
    assert ownership_rules(files) is compiled
    def reference(path, fallback):
        selected, provenance = fallback, 'ProjectTrace repository assignment'
        for line in lines[:5000]:
            parts = line.split('#', 1)[0].split()
            if len(parts) < 2 or parts[0].startswith(('!', '#')):
                continue
            pattern = parts[0].lstrip('/')
            if pattern.endswith('/'):
                pattern += '**'
            if matches(path, [pattern, '**/' + pattern]):
                selected = ' '.join(parts[1:])[:200]
                provenance = 'CODEOWNERS supported glob (last match)'
        return {'owner': selected, 'owner_source': provenance}
    for path in ('src/a.py', 'repo/src/b.py', 'src/tests/a.ts', 'README.md', 'repo/other/main.py'):
        assert ownership(path, files, 'Owner', rules=compiled) == reference(path, 'Owner')
    empty = Inventory({})
    assert ownership('a.py', empty, 'First')['owner'] == 'First'
    assert ownership('a.py', empty, 'Second')['owner'] == 'Second'


def test_function_graph_links_only_enclosing_quality_findings_in_the_same_file(storage):
    db, user, repo = storage
    source = 'def complex(value):\n' + ''.join(f'    if value == {i}: value += 1\n' for i in range(15)) + '    return value\n'
    files = captured(storage, {'a.py': source, 'b.py': source.replace('complex', 'other')})
    snapshot, _ = execute_analysis(db, user, repo, files)
    nodes = {r.id: r.data for r in db.scalars(select(Record).where(Record.kind == 'graph_node'))}
    findings = {r.id: r.data for r in db.scalars(select(Record).where(Record.kind == 'finding'))}
    edges = [r.data for r in db.scalars(select(Record).where(Record.kind == 'edge'))
             if r.data.get('relationship') == 'AFFECTS_FUNCTION']
    assert snapshot.data['status'] in {'COMPLETED', 'PARTIAL'} and edges
    for edge in edges:
        finding, function = findings[edge['source']], nodes[edge['target']]
        assert finding['category'] == 'QUALITY' and finding['path'] == function['path']
        assert function['line'] <= finding['line'] <= function['end_line']
    assert {nodes[edge['target']]['path'] for edge in edges} == {'a.py', 'b.py'}


def test_computation_without_record_additions_still_checks_deadline(storage, monkeypatch):
    from backend import jobs
    from backend.analysis_budget import checkpoint
    db, user, repo = storage
    files = captured(storage, {'app.py': 'VALUE = 1\n'})
    elapsed, completed = [0], []
    def computation(db, user, repo, files, *, progress, **options):
        progress('BUILDING_EVIDENCE')
        progress('CORRELATING')
        for index in range(600):
            elapsed[0] += 4
            checkpoint(db)
            completed.append(index)
        raise AssertionError('Computation did not enforce its deadline')
    monkeypatch.setattr(jobs, 'persist_analysis', computation)
    with pytest.raises(TimeoutError):
        jobs.execute_analysis(db, user, repo, files, _elapsed_clock=lambda: elapsed[0])
    job = db.scalar(select(Record).where(Record.kind == 'job'))
    assert job.data['stage'] == 'CORRELATING' and len(completed) == 249
    assert job.data['error_detail']['maximum'] == 900
    assert not any(key.startswith('analysis_output_') for key in db.info)


def test_completed_analysis_coverage_survives_publication_failure_without_snapshot(storage, monkeypatch):
    from backend import finding_history
    db, user, repo = storage
    files = captured(storage, {'good.py': 'VALUE = 1\n', 'broken.py': 'def invalid(:\n'})
    def interrupted(*args, **kwargs):
        raise TimeoutError('Synthetic bounded publication interruption')
    monkeypatch.setattr(finding_history, 'reconcile', interrupted)
    with pytest.raises(TimeoutError):
        execute_analysis(db, user, repo, files)
    db.expire_all()
    job = db.scalar(select(Record).where(Record.kind == 'job'))
    summary = job.data['completed_analysis']
    assert summary['publication_state'] == 'UNPUBLISHED'
    assert summary['source_inventory_id'] == files.inventory_id
    coverage = summary['coverage']['summary']
    assert coverage['files_discovered'] == 2
    assert coverage['source_files'] == 2 and coverage['source_files_parsed'] == 1
    assert coverage['states']['PARSE_FAILED'] == 1
    assert db.scalar(select(func.count()).select_from(Record).where(Record.kind == 'snapshot')) == 0
    assert db.scalar(select(func.count()).select_from(Record).where(Record.kind == 'parser_diagnostic')) == 1
    assert db.scalar(select(func.count()).select_from(ParserArtifact)) == 1


def test_correlation_reuses_created_records_and_keeps_update_batches_bounded(storage, monkeypatch):
    from sqlalchemy import event
    db, user, repo = storage
    files = captured(storage, {f'app{i}.py': 'def inspect(value):\n' + '    eval(value)\n' * 40 for i in range(8)})
    selected, updates = [], []
    def record_select(connection, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith('SELECT') and 'FROM records' in statement:
            selected.extend(value for value in parameters if isinstance(value, str))
    event.listen(db.get_bind(), 'before_cursor_execute', record_select)
    event.listen(db, 'before_flush', lambda session, context, instances: updates.append(
        sum(isinstance(row, Record) and row.kind == 'finding' for row in session.dirty)))
    snapshot, job = execute_analysis(db, user, repo, files)
    current_ids = {row['id'] for row in snapshot.data['findings']}
    assert len(current_ids) >= 320
    # ORM tenant/FK guards still call get(); the strong references satisfy those
    # checks without individual finding SELECTs or premature autoflushes.
    assert not current_ids.intersection(selected)
    assert max(updates) <= 250
    assert job.data['completed_analysis']['publication_state'] == 'PUBLISHED'
    assert job.data['completed_analysis']['snapshot_id'] == snapshot.id
