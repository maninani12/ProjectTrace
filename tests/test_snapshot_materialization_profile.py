"""Fresh-process diagnostics exercise real snapshot, guard and publication paths."""
import json
import os
import subprocess
import sys

import pytest


@pytest.mark.parametrize('metrics', [None, 10000, 30000, 50000])
def test_owned_final_snapshot_profile(tmp_path, metrics, record_property):
    root = tmp_path / 'owned'
    command = [sys.executable, '-m', 'tests.snapshot_materialization_probe', str(root)]
    command += ['--all-phases'] if metrics is None else ['--metrics', str(metrics)]
    completed = subprocess.run(command, env={**os.environ, 'PYTHONHASHSEED': '0'},
                               capture_output=True, text=True, timeout=600)
    assert completed.returncode == 0, completed.stderr[-3000:]
    receipt = json.loads((root/'profile.json').read_text())
    record_property('snapshot_profile', json.dumps({'command': command, 'exit_code': completed.returncode,
                    'root': str(root), 'receipt': receipt, 'stderr': completed.stderr}))
    assert receipt['integrity'] == {'sqlite_integrity': 'ok', 'foreign_key_violations': 0}
    assert receipt['limits'] == {'job_seconds': 900, 'spill_bytes': 256000000,
        'metadata_nodes': 1000000, 'descriptor_nodes': 256000, 'encoded_stage_bytes': 64000000}
    names = {event['name'] for event in receipt['events']}
    assert 'FINAL_SANITIZE' in names and 'COMPLETE_FINAL_SNAPSHOT_PATH' in names
    if metrics == 50000:
        assert receipt['pointers'] == 0
        assert receipt['generation_states'] == [['STAGING', 1]]
        assert receipt['jobs'][0]['state'] == 'FAILED'
        assert receipt['jobs'][0]['error_type'] == 'ValueError'
        assert 'Sanitization structure budget exceeded' in receipt['states'][0]['error']
        assert 'PROMOTE_GENERATION' not in names
    else:
        count = 3 if metrics is None else 1
        assert receipt['pointers'] == (2 if metrics is None else 1)
        assert receipt['generation_states'] == [['PUBLISHED', count]]
        assert all(row['state'] == 'PARTIAL' and row['metrics'] == (metrics or 147) for row in receipt['states'])
        assert all(row['snapshot_nodes'] <= 1000000 for row in receipt['states'])
        assert {'DB_EXECUTE_SNAPSHOT_WRITE', 'VALIDATE_GENERATION', 'CANONICAL_SNAPSHOT_STRING',
                'CANONICAL_SNAPSHOT_UTF8_AND_HASH', 'ATOMIC_PUBLICATION_COMMIT'} <= names
    if metrics is not None:
        assert receipt['metric_spill']['cache_size'] == -1024
        assert receipt['metric_spill']['ciphertext_bytes'] <= 256000000
