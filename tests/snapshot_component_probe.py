"""Fresh-process attribution experiments; no production optimization is installed."""
import argparse
import gc
import hashlib
import json
import os
import sqlite3
import time
from pathlib import Path

from tests.snapshot_materialization_probe import Recorder
from tests.sqlite_memory_probe import SQLiteMemory


def database_component(path, mode, *, allocation=False):
    with sqlite3.connect('file:' + path.resolve().as_posix() + '?mode=ro', uri=True) as db:
        identity, raw = db.execute("SELECT id,data FROM records WHERE kind='snapshot' ORDER BY created_at,id LIMIT 1").fetchone()
        input_hash, size = hashlib.sha256(raw.encode()).hexdigest(), len(raw)
        if mode.startswith('hash_'):
            value = [identity, 'snapshot', json.loads(raw)]
            del raw
        gc.collect()
        recorder = Recorder()
        memory = SQLiteMemory()
        sqlite_before = memory.begin()
        if allocation:
            import tracemalloc
            tracemalloc.start(1)
        with recorder.span(mode) as event:
            started = time.process_time()
            if mode == 'hash_whole':
                combined = json.dumps(value, sort_keys=True, separators=(',', ':')).encode()
                result = {'sha256': hashlib.sha256(combined).hexdigest(), 'bytes': len(combined)}
                del combined
            elif mode == 'hash_stream':
                combined, length = hashlib.sha256(), 0
                for part in json.JSONEncoder(sort_keys=True, separators=(',', ':')).iterencode(value):
                    encoded = part.encode()
                    combined.update(encoded)
                    length += len(encoded)
                result = {'sha256': combined.hexdigest(), 'bytes': length}
            elif mode == 'sqlite_length':
                result = {'value': db.execute('SELECT length(?)', (raw,)).fetchone()[0]}
            elif mode == 'sqlite_json':
                result = {'value': db.execute("SELECT json_extract(?, '$.scope.snapshot_id')", (raw,)).fetchone()[0]}
            elif mode == 'sqlite_indexes':
                schema = db.execute("SELECT sql FROM sqlite_master WHERE name IN "
                    "('ix_records_graph_snapshot','ix_records_graph_source','ix_records_graph_target','ix_records_graph_class') ORDER BY name").fetchall()
                columns = ','.join(sql[0].partition('(')[2].rpartition(')')[0] for sql in schema)
                query = "WITH records(organization_id,repository_id,kind,data,id) AS (VALUES('owned-eq','owned-eq','snapshot',?,?)) SELECT " + columns + ' FROM records'
                result = {'value': list(db.execute(query, (raw, identity)).fetchone()), 'index_count': len(schema),
                    'query': query}
            else:
                raise ValueError(mode)
            event['attributes']['cpu_seconds'] = time.process_time() - started
        recorder.close()
        native = memory.end(sqlite_before)
        traced = None
        if allocation:
            traced = tracemalloc.get_traced_memory()
            tracemalloc.stop()
        functions = [row[5] for row in db.execute('EXPLAIN UPDATE records SET data=? WHERE id=?', ('{}', identity))
                     if row[1] in ('Function', 'PureFunc')]
    return {'scope': 'OWNED_READ_ONLY_COMPONENT_EXPERIMENT', 'mode': mode, 'input_sha256': input_hash,
        'input_characters': size, 'result': result, 'events': recorder.events, 'sqlite_version': sqlite3.sqlite_version,
        'update_explain_functions': functions, 'python_allocation_current_peak': traced,
        'allocation_instrumented': allocation, 'sqlite_malloc': native}


def ancestor_component(root, depth):
    os.environ.update(APP_ENV='demo', PROJECTTRACE_PARSER_ISOLATION='development')
    import pytest

    from backend.json_export import write_json
    from tests.generation_json_export_probe import Sink
    from tests.generation_map_iteration_probe import CountingCipher
    from tests.test_generation_context import context
    from tests.test_repository_store import storage
    root.mkdir()
    mp = pytest.MonkeyPatch()
    fixture = storage.__wrapped__(root, mp)
    source = next(fixture)
    generation, state = context(source)
    value = {str(i): i for i in range(200)}
    for _ in range(depth):
        value = {'0': {'child': value, 'pad': 'x' * 1_000_000}, **{str(i): i for i in range(1, 200)}}
    sink = Sink()
    write_json(value, sink)
    expected = {'sha256': sink.hash.hexdigest(), 'bytes': sink.size}
    state['map'] = value
    generation.save('SNAPSHOT', state)
    del state, value
    gc.collect()
    value = generation.load('SNAPSHOT')['map']
    cipher = CountingCipher(value.rows.owner.rows.key)
    value.rows.owner.rows.key = cipher
    recorder = Recorder()
    sink = Sink()
    with recorder.span('ACTIVE_ANCESTOR_STREAM', depth=depth, scalar_characters=1_000_000):
        write_json(value, sink)
    recorder.close()
    actual = {'sha256': sink.hash.hexdigest(), 'bytes': sink.size}
    assert actual == expected
    result = {'scope': 'OWNED_ACTIVE_ANCESTOR_ONLY', 'depth': depth, 'logical': actual,
        'events': recorder.events, 'decryptions': cipher.decryptions, 'maximum_write': sink.maximum_write,
        'cache_size': value.connection.execute('PRAGMA cache_size').fetchone()[0]}
    value.rows.close()
    fixture.close()
    mp.undo()
    return result


def callback_component(count):
    os.environ.update(APP_ENV='demo', PROJECTTRACE_PARSER_ISOLATION='development')
    from backend.generations import encoded
    from backend.json_export import write_json
    from tests.generation_json_export_probe import Sink
    value = {str(i) for i in range(count)}
    recorder, calls = Recorder(), []
    def observed(node):
        import sys
        with recorder.span('TYPED_SET_CALLBACK'):
            result = encoded(node)
            calls.append({'members': len(result['$set']), 'list_container_bytes': sys.getsizeof(result['$set'])})
            return result
    sink = Sink()
    with recorder.span('TYPED_SET_EXPORT'):
        write_json(value, sink, default=observed)
    recorder.close()
    return {'scope': 'OWNED_TYPED_CALLBACK_ONLY', 'members': count, 'callbacks': calls,
        'events': recorder.events, 'logical': {'sha256': sink.hash.hexdigest(), 'bytes': sink.size}}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('hash_whole', 'hash_stream', 'sqlite_length', 'sqlite_json', 'sqlite_indexes',
                                       'ancestor', 'callback'))
    parser.add_argument('output', type=Path)
    parser.add_argument('--database', type=Path)
    parser.add_argument('--depth', type=int, default=4)
    parser.add_argument('--allocation', action='store_true')
    args = parser.parse_args()
    if args.mode == 'ancestor':
        result = ancestor_component(args.output.with_suffix(''), args.depth)
    elif args.mode == 'callback':
        result = callback_component(50000)
    else:
        result = database_component(args.database, args.mode, allocation=args.allocation)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: value for key, value in result.items() if key != 'events'}))
