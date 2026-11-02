"""Diagnostic owned final-snapshot profiling. No production code/limits change.

The optional metric scale repeats a real owned metric's shape in encrypted rows;
it is a synthetic observation-volume fixture, not source/parser qualification.
"""
import argparse
import gc
import hashlib
import json
import os
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path


class Recorder:
    def __init__(self, allocation=False):
        from scripts.benchmark_repository_analysis import process_stats
        from tests.sqlite_memory_probe import SQLiteMemory
        self.stats = process_stats
        self.sqlite = SQLiteMemory()
        self.events, self.stack, self.intervals, self.sql, self.fetches = [], [], [], {}, {}
        self.phase, self.await_commit = "setup", False
        self.stop = threading.Event()
        self.allocation = allocation
        self.thread = threading.Thread(target=self.sample, daemon=True)
        self.thread.start()

    def sample(self):
        while not self.stop.wait(.005):
            rss = self.stats()["rss_bytes"]
            for item in (*tuple(self.stack), *tuple(self.intervals)):
                item["sampled_peak_rss_bytes"] = max(item["sampled_peak_rss_bytes"], rss)

    def final_begin(self):
        if self.allocation:
            import tracemalloc
            if not tracemalloc.is_tracing():
                tracemalloc.start(8)
        start = self.stats()
        self.intervals.append({'name': 'COMPLETE_FINAL_SNAPSHOT_PATH', 'phase': self.phase,
            'before': start, 'sampled_peak_rss_bytes': start['rss_bytes'], '_started': time.perf_counter(),
            'attributes': {}})

    def final_end(self, error=None):
        if self.intervals:
            item = self.intervals.pop()
            item['after'], item['seconds'] = self.stats(), time.perf_counter() - item.pop('_started')
            item['sampled_peak_rss_bytes'] = max(item['sampled_peak_rss_bytes'], item['after']['rss_bytes'])
            item['outcome'] = 'ERROR' if error else 'OK'
            if error:
                item['error'] = type(error).__name__ + ': ' + str(error)
            self.events.append(item)

    @contextmanager
    def span(self, name, **attributes):
        start = self.stats()
        item = {"name": name, "phase": self.phase, "before": start, "attributes": attributes,
                "sampled_peak_rss_bytes": start["rss_bytes"],
                "parent": self.stack[-1]['name'] if self.stack else None}
        trace_before = None
        if self.allocation and name in {"FINAL_SANITIZE", "SQL_ENCODE_SNAPSHOT", "CANONICAL_SNAPSHOT_STRING",
                                       "SQL_DECODE_LARGE", "DB_EXECUTE_SNAPSHOT_WRITE"}:
            import tracemalloc
            if tracemalloc.is_tracing():
                trace_before = tracemalloc.take_snapshot()
        begun = time.perf_counter()
        self.stack.append(item)
        try:
            yield item
            item["outcome"] = "OK"
        except BaseException as error:
            item["outcome"], item["error"] = "ERROR", type(error).__name__ + ": " + str(error)
            raise
        finally:
            item["seconds"] = time.perf_counter() - begun
            item["after"] = self.stats()
            item["sampled_peak_rss_bytes"] = max(item["sampled_peak_rss_bytes"], item["after"]["rss_bytes"])
            self.stack.pop()
            if trace_before is not None:
                import tracemalloc
                after = tracemalloc.take_snapshot()
                item["python_retained_delta_bytes"] = sum(s.size_diff for s in after.compare_to(trace_before, "lineno"))
                item["python_allocation_top"] = [{"location": str(s.traceback), "bytes": s.size_diff, "count": s.count_diff}
                    for s in after.compare_to(trace_before, "lineno")[:8]]
                item["python_traced_current_peak"] = tracemalloc.get_traced_memory()
            self.events.append(item)

    def close(self):
        self.stop.set()
        self.thread.join()


def sources(changed=False):
    files = {'README.md': b'The backend uses Flask.\nThe database uses PostgreSQL.\nAuthentication uses JWT.\n',
        'api.json': b'{"openapi":"3.0.0","paths":{"/health":{"get":{}}}}',
        'app.py': b"from flask import Flask\napp=Flask(__name__)\n@app.route('/health')\ndef health(): return True\n",
        'schema.json': b'{"owned":"unrelated data"}',
        'pod.yaml': b'apiVersion: v1\nkind: Pod\nmetadata:\n  name: owned\nspec:\n  containers:\n    - name: owned\n      image: owned:v1\n      securityContext:\n        privileged: true\n'}
    for number in range(12):
        parts = []
        for index in range(12):
            parts.append(f'def owned_{number}_{index}(value):\n')
            for condition in range(17):
                parts.append(f'    if value == {condition}:\n        value += {condition + 1}\n')
            parts.append(f'    return value + {number + index + (1 if changed and number == index == 0 else 0)}\n\n')
        files[f'owned/module_{number}.py'] = ''.join(parts).encode()
    files['owned/Owner.java'] = b'class Owner { int inspect(int value) { return value + 1; } }\n'
    files['owned/client.ts'] = b'export function inspect(value: string) { return eval(value); }\n'
    return files


def install(recorder, metrics):
    """Reversible process-local instrumentation of real production operations."""
    import uuid

    from sqlalchemy import event
    from sqlalchemy.engine import CursorResult
    from sqlalchemy.orm import Session as ORMSession

    from backend import db as model
    from backend import domain, generations, partitioned_analysis, quality_domain, workspace_read
    from backend.generation_context import Reader
    from backend.json_export import dumps

    @event.listens_for(model.engine, 'before_cursor_execute')
    def before_sql(connection, cursor, statement, parameters, context, many):
        context.owned_start = time.perf_counter()
        if recorder.intervals and statement.startswith('UPDATE records SET') and not many and any(
                type(p) is str and p == getattr(recorder, 'snapshot_id', None) for p in parameters):
            context.owned_span = recorder.span('DB_EXECUTE_SNAPSHOT_WRITE', sql=statement)
            context.owned_event = context.owned_span.__enter__()
            context.sqlite_before = recorder.sqlite.begin()

    @event.listens_for(model.engine, 'after_cursor_execute')
    def after_sql(connection, cursor, statement, parameters, context, many):
        if hasattr(context, 'owned_span'):
            context.owned_event['sqlite_malloc'] = recorder.sqlite.end(context.sqlite_before)
            context.owned_span.__exit__(None, None, None)
        stage = recorder.stack[-1]['name'] if recorder.stack else 'OTHER'
        key = recorder.phase + ':' + stage + ':' + statement.lstrip().split(None, 1)[0].upper()
        item = recorder.sql.setdefault(key, {'calls': 0, 'seconds': 0, 'executemany_calls': 0})
        item['calls'] += 1
        item['seconds'] += time.perf_counter() - context.owned_start
        item['executemany_calls'] += int(many)

    @event.listens_for(model.engine, 'handle_error')
    def failed_sql(context):
        if hasattr(context.execution_context, 'owned_span'):
            error = context.original_exception
            context.execution_context.owned_span.__exit__(type(error), error, error.__traceback__)

    fetch = CursorResult._fetchall_impl
    def fetchall(self):
        validation = recorder.intervals and any(item['name'] == 'VALIDATE_GENERATION' for item in recorder.stack)
        detailed = validation and 'records.data, generation_records.stage' in self.context.statement
        if detailed:
            with recorder.span('DB_FETCH_VALIDATION_BATCH') as event:
                result = fetch(self)
                event['attributes']['rows'] = len(result)
                return result
        if validation:
            # Metadata/ID-only queries have no snapshot payload. Retain aggregate
            # evidence, without one Python event object per tiny receipt lookup.
            start = time.perf_counter()
            result = fetch(self)
            counts = recorder.fetches.setdefault(recorder.phase, {'calls': 0, 'rows': 0, 'seconds': 0})
            counts['calls'] += 1
            counts['rows'] += len(result)
            counts['seconds'] += time.perf_counter() - start
            return result
        return fetch(self)
    CursorResult._fetchall_impl = fetchall

    commit = ORMSession.commit
    def measured_commit(self):
        if not recorder.intervals:
            return commit(self)
        label = 'ATOMIC_PUBLICATION_COMMIT' if recorder.await_commit else 'DB_COMMIT'
        with recorder.span(label, identity_map=len(self.identity_map), dirty=len(self.dirty), new=len(self.new)):
            result = commit(self)
        if recorder.await_commit:
            recorder.await_commit = False
            recorder.final_end()
        return result
    ORMSession.commit = measured_commit

    identifiers, owners = {}, []
    def owned_uuid4():
        caller = sys._getframe(1)
        key = (Path(caller.f_code.co_filename).name, caller.f_code.co_name)
        identifiers[key] = identifiers.get(key, 0) + 1
        return uuid.uuid5(uuid.NAMESPACE_URL, repr((key, identifiers[key])))
    uuid.uuid4 = owned_uuid4
    def record_uid():
        key = ('owned-record-storage', 'record_uid')
        identifiers[key] = identifiers.get(key, 0) + 1
        return str(uuid.uuid5(uuid.NAMESPACE_URL, repr((key, identifiers[key]))))
    domain.record_uid = record_uid
    model.generation_models.AnalysisGeneration.__table__.c.created_at.default.arg = lambda context: '2026-10-25T00:00:00+00:00'

    original_analyze = partitioned_analysis.analyze_inventory
    def analyze(*args, **kwargs):
        result = original_analyze(*args, **kwargs)
        if metrics is not None:
            from analyzers.observation_store import MetricRows
            with recorder.span("OWNED_METRIC_FIXTURE_BUILD", count=metrics):
                original = result['quality_metrics']
                seed = original[0]
                rows = MetricRows(('owned-eq', 'owned-eq', 'synthetic-metric-volume'))
                for number in range(metrics):
                    rows.append(original[number] if number < len(original) else
                        {**seed, 'name': f'owned_scaled_{number}', 'qualified_name': f'owned_scaled_{number}'})
                if getattr(kwargs.get('progress'), 'close_on_failure', None):
                    kwargs['progress'].close_on_failure(rows)
                owners.extend([original, rows])
                recorder.metric_spill = {'rows': len(rows), 'ciphertext_bytes': rows.bytes,
                    'cache_size': rows.connection.execute('PRAGMA cache_size').fetchone()[0]}
                result['quality_metrics'] = rows
                result['code_quality']['metrics'] = rows
                result['warnings'].append({'analyzer': 'OWNED_PROFILING', 'state': 'PARTIAL',
                    'message': 'Owned synthetic metric-volume profiling; not repository qualification.'})
        return result
    partitioned_analysis.analyze_inventory = analyze

    sanitize = domain.sanitize_metadata
    def metadata(value, **kwargs):
        caller = sys._getframe(1)
        if caller.f_code is domain.persist_analysis.__code__ and 'quality_metrics' in value and 'finding_delta' in value:
            with recorder.span("FINAL_SANITIZE", source_line=caller.f_lineno,
                metrics=len(value['quality_metrics']), findings=len(value['findings'])):
                return sanitize(value, **kwargs)
        return sanitize(value, **kwargs)
    domain.sanitize_metadata = metadata

    def serialize(value):
        kind = 'SNAPSHOT' if isinstance(value, dict) and 'quality_metrics' in value and 'finding_delta' in value else (
            'QUALITY' if isinstance(value, dict) and 'metrics' in value and 'profile_hash' in value else None)
        if kind:
            with recorder.span('SQL_ENCODE_' + kind) as event:
                result = dumps(value)
                event['attributes']['characters'] = len(result)
                return result
        return dumps(value)
    def deserialize(raw):
        if len(raw) > 16000:
            with recorder.span('SQL_DECODE_LARGE', characters=len(raw)) as event:
                value = json.loads(raw)
                event['attributes']['kind'] = 'snapshot' if isinstance(value, dict) and 'quality_metrics' in value else (
                    'quality' if isinstance(value, dict) and 'metrics' in value else 'other')
                return value
        return json.loads(raw)
    model.engine.dialect._json_serializer = serialize
    model.engine.dialect._json_deserializer = deserialize

    def wrap(obj, name, label, predicate=lambda *args, **kwargs: True):
        original = getattr(obj, name)
        def measured(*args, **kwargs):
            if predicate(*args, **kwargs):
                with recorder.span(label):
                    return original(*args, **kwargs)
            return original(*args, **kwargs)
        setattr(obj, name, measured)

    original_load = generations.Generation.load
    def load(self, stage):
        if stage != 'FINAL_OUTPUT':
            return original_load(self, stage)
        with recorder.span('FINAL_RECEIPT_LOOKUP'):
            result = original_load(self, stage)
        if result is None:
            recorder.snapshot_id = self.row.snapshot_id
            recorder.final_begin()
        return result
    generations.Generation.load = load
    wrap(generations.Generation, 'save', 'FINAL_RECEIPT_WRITE', lambda self, stage, state: stage == 'FINAL_OUTPUT')
    wrap(generations.Generation, 'validate', 'VALIDATE_GENERATION')
    promote = generations.Generation.promote
    def promotion(self, snapshot):
        with recorder.span('PROMOTE_GENERATION'):
            result = promote(self, snapshot)
        recorder.await_commit = True
        return result
    generations.Generation.promote = promotion
    wrap(quality_domain, 'persist', 'QUALITY_PERSIST')
    wrap(quality_domain, 'apply_comparison', 'QUALITY_COMPARISON')
    wrap(workspace_read, 'project_snapshot', 'PROJECT_SNAPSHOT')
    wrap(quality_domain, 'current_findings', 'CURRENT_FINDINGS_PRODUCER')
    wrap(Reader, 'record', 'TYPED_RECORD_HYDRATE', lambda self, identity, materialize=False: materialize)

    original_collect = gc.collect
    def collect(*args):
        caller = sys._getframe(1)
        if caller.f_code is domain.persist_analysis.__code__:
            with recorder.span('FINAL_GC'):
                return original_collect(*args)
        return original_collect(*args)
    gc.collect = collect

    class Json:
        def __getattr__(self, name):
            return getattr(json, name)

        def dumps(self, value, *args, **kwargs):
            if isinstance(value, list) and len(value) == 3 and value[1] == 'snapshot':
                with recorder.span('CANONICAL_SNAPSHOT_STRING') as event:
                    result = json.dumps(value, *args, **kwargs)
                    event['attributes']['characters'] = len(result)
                recorder.byte_span = recorder.span('CANONICAL_SNAPSHOT_UTF8_AND_HASH')
                recorder.byte_event = recorder.byte_span.__enter__()
                return result
            return json.dumps(value, *args, **kwargs)
    generations.json = Json()

    class Digest:
        def __init__(self, original):
            self.original = original

        def __getattr__(self, name):
            return getattr(self.original, name)

        def update(self, raw):
            if getattr(recorder, 'byte_span', None):
                try:
                    recorder.byte_event['attributes']['bytes'] = len(raw)
                    return self.original.update(raw)
                finally:
                    recorder.byte_span.__exit__(None, None, None)
                    recorder.byte_span = None
            return self.original.update(raw)

    class Hashes:
        def sha256(self, *args, **kwargs):
            return Digest(hashlib.sha256(*args, **kwargs))
    generations.hashlib = Hashes()
    return owners


def run(root, metrics=None, *, phases=('cold',), allocation=False):
    root.mkdir()
    os.environ.update(APP_ENV='demo', PROJECTTRACE_PARSER_ISOLATION='development', JOB_MODE='sync',
        DATABASE_URL='sqlite:///' + str(root/'benchmark.db'), SOURCE_BLOB_DIR=str(root/'blobs'),
        SOURCE_UPLOAD_DIR=str(root/'uploads'), ANALYSIS_KEY_FILE=str(root/'private.key'))
    from sqlalchemy import func, select

    from backend.db import Base, Grant, Organization, QualityAnalysis, Record, Repository, Session, User, engine
    from backend.generation_models import AnalysisGeneration, PublishedGeneration
    from backend.jobs import execute_analysis, inventory_time_budget
    from backend.quality_domain import current_findings
    from backend.repository_store import RepositoryFiles, capture
    from scripts.benchmark_repository_scale import verify_database

    recorder = Recorder(allocation)
    owners = install(recorder, metrics)
    Base.metadata.create_all(engine)
    states = []
    cold_id = None
    try:
        with Session() as db:
            db.add(Organization(id='owned-eq', name='Owned fixture'))
            db.flush()
            user = User(id='owned-eq', organization_id='owned-eq', email='owned@example.invalid',
                password_hash='unused-owned', role='ORG_OWNER')
            repo = Repository(id='owned-eq', organization_id='owned-eq', name='Owned fixture',
                system='Owned', component='Owned', owner='Owned', provider='LOCAL')
            db.add_all([user, repo])
            db.flush()
            db.add(Grant(user_id=user.id, repository_id=repo.id))
            db.commit()
            for phase in phases:
                recorder.phase = phase
                inventory = capture(db, user.organization_id, repo, sources(phase == 'incremental').items(),
                                    source='OWNED_VERIFYING_EQUIVALENCE')
                db.commit()
                try:
                    with recorder.span('COMPLETE_ANALYSIS'):
                        snapshot, job = execute_analysis(db, user, repo,
                            RepositoryFiles(db, user.organization_id, repo.id, inventory.id),
                            branch='owned-warm' if phase == 'warm' else 'owned',
                            git_commit=('b' if phase == 'incremental' else 'a') * 40,
                            base_id=cold_id if phase == 'incremental' else None)
                    if phase == 'cold':
                        cold_id = snapshot.id
                    states.append({'phase': phase, 'state': job.data['state'], 'snapshot_id': snapshot.id,
                                   'metrics': len(snapshot.data['quality_metrics']), 'findings': len(snapshot.data['findings'])})
                    def nodes(value):
                        if isinstance(value, dict):
                            return 1 + sum(nodes(child) for child in value.values())
                        if isinstance(value, (list, tuple)):
                            return 1 + sum(nodes(child) for child in value)
                        return 1
                    states[-1]['snapshot_nodes'] = nodes(snapshot.data)
                    with recorder.span('QUALITY_FULL_HYDRATION'):
                        quality = db.scalar(select(QualityAnalysis).where(QualityAnalysis.snapshot_id == snapshot.id)
                                            .execution_options(populate_existing=True))
                    with recorder.span('FINDINGS_READ_TOTAL'):
                        findings = current_findings(db, quality)
                    states[-1]['producer_findings'] = len(findings)
                    del findings, quality, snapshot, job
                except Exception as error:
                    recorder.final_end(error)
                    states.append({'phase': phase, 'error': type(error).__name__ + ': ' + str(error)})
                    break
                db.expunge_all()
                user, repo = db.get(User, 'owned-eq'), db.get(Repository, 'owned-eq')
            generations = db.execute(select(AnalysisGeneration.state, func.count()).group_by(AnalysisGeneration.state)).all()
            pointers = db.scalar(select(func.count()).select_from(PublishedGeneration))
            jobs = [r.data for r in db.scalars(select(Record).where(Record.kind == 'job'))]
    finally:
        for owner in owners:
            owner.close()
        recorder.close()
        engine.dispose()
    receipt = {'scope': 'OWNED_WINDOWS_FINAL_SNAPSHOT_PROFILE_ONLY', 'metrics_override': metrics,
        'allocation_instrumented': allocation, 'limits': {'job_seconds': inventory_time_budget(),
            'spill_bytes': int(os.getenv('ANALYSIS_OBSERVATION_SPILL_BYTES', '256000000')),
            'metadata_nodes': 1000000, 'descriptor_nodes': 256000, 'encoded_stage_bytes': 64000000},
        'sample_interval_seconds': .005, 'states': states, 'generation_states': [list(r) for r in generations],
        'pointers': pointers, 'integrity': verify_database(root/'benchmark.db'),
        'events': recorder.events, 'sql': recorder.sql, 'metadata_fetches': recorder.fetches,
        'jobs': [{k: job.get(k) for k in ('state', 'stage', 'error_type', 'error_code', 'snapshot_id')} for job in jobs],
        'database_sizes': {p.name: p.stat().st_size for p in root.glob('benchmark.db*')},
        'metric_spill': getattr(recorder, 'metric_spill', None),
        'source_sha256': {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in [
            Path('backend/domain.py'), Path('backend/generations.py'), Path('backend/db.py'),
            Path('backend/generation_context.py'), Path('backend/json_export.py'), Path(__file__)]},
        'final_process': recorder.stats()}
    (root/'profile.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--metrics', type=int)
    parser.add_argument('--all-phases', action='store_true')
    parser.add_argument('--allocation', action='store_true')
    args = parser.parse_args()
    result = run(args.directory, args.metrics, phases=('cold', 'warm', 'incremental') if args.all_phases else ('cold',),
                 allocation=args.allocation)
    print(json.dumps({k: result[k] for k in ('scope', 'metrics_override', 'states', 'generation_states', 'pointers', 'integrity')}))
