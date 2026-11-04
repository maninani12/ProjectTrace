"""File-rule ordering is stable across independent interpreter hash seeds."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

PROGRAM = r'''
import json,sys
from analyzers.engine import analyze
from analyzers.code_quality.core import compare,gate
def source(name, lines=24):
    return 'def '+name+'(a,b,c,d,e,f,g,h):\n    return a\n'+'VALUE = 1\n'*(lines-2)
base={'nested/z.py':source('z'),'a.py':source('a'),'nested/deeper/m.py':source('m')}
cases={
 'unchanged':base,
 'mixed-severity':{**base,'complex.py':'def work():\n'+'    value = 1\n'*90},
 'repeated-evidence':{**base,'repeat.py':'try:\n    work()\nexcept:\n    pass\n'*2},
 'partial':{**base,'broken.py':'def broken(\n','unknown.go':'package main\n'},
 'empty':{'README.md':'# Owned empty source scope\n'},
 'large':{f'nested/{i%7}/module{i:03}.py':source('work'+str(i)) for i in range(64)},
 'addition':{**base,'added.py':source('added')},
 'resolution':{'a.py':'VALUE = 1\n','nested/deeper/m.py':base['nested/deeper/m.py']},
 'regression':{**base,'nested/z.py':source('z',40)},
}
profile={'quality':{'rules':{'PT-QUALITY-013':{'threshold':10,'severity':'MEDIUM'},'PT-QUALITY-009':{'severity':'HIGH'}}}}
output={}
prior=analyze(base,profile=profile)
for name,files in cases.items():
    result=analyze(files,profile=profile)
    quality=result['code_quality']; quality.get('performance',{}).pop('quality_ms',None)
    if name in {'unchanged','addition','resolution','regression'}:
        compare(quality,result['findings'],prior['findings'],{p:[(1,1000)] for p in files},base_id='owned-base')
    output[name]={'findings':result['findings'],'quality':quality,'gate':gate(quality,result['findings'])}
print(json.dumps(output,sort_keys=True,separators=(',',':')))
'''


@pytest.fixture(scope="module")
def seeded_results():
    results = []
    for seed in ("0", "1", "2", "3"):
        env = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONDONTWRITEBYTECODE": "1"}
        completed = subprocess.run([sys.executable, "-B", "-c", PROGRAM], cwd=Path(__file__).resolve().parents[1],
                                   env=env, capture_output=True, text=True, timeout=180)
        assert completed.returncode == 0, completed.stderr
        results.append(json.loads(completed.stdout))
    return results


@pytest.mark.parametrize("case", ["unchanged", "mixed-severity", "repeated-evidence", "partial", "empty",
                                 "large", "addition", "resolution", "regression"])
def test_fresh_process_order_content_identity_and_serialization(seeded_results, case):
    expected = seeded_results[0][case]
    for result in seeded_results:
        actual = result[case]
        assert actual == expected
        assert json.dumps(actual, sort_keys=True) == json.dumps(expected, sort_keys=True)
        rows = [f for f in actual["findings"] if f["rule"] == "PT-QUALITY-013"]
        assert [f["path"] for f in rows] == sorted(f["path"] for f in rows)
        assert len({f["fingerprint"] for f in rows}) == len(rows)


def test_rule_group_and_severity_order_are_preserved(seeded_results):
    rows = seeded_results[0]["mixed-severity"]["findings"]
    file_positions = [i for i, row in enumerate(rows) if row["rule"] == "PT-QUALITY-013"]
    parameter_positions = [i for i, row in enumerate(rows) if row["rule"] == "PT-QUALITY-009"]
    assert file_positions and parameter_positions
    assert max(parameter_positions) < min(file_positions)
    assert all(rows[i]["severity"] == "HIGH" for i in parameter_positions)
    assert all(rows[i]["severity"] == "MEDIUM" for i in file_positions)


def test_missing_evidence_and_real_comparison_remain_explicit(seeded_results):
    result = seeded_results[0]
    assert result["partial"]["quality"]["state"] == "PARTIAL"
    assert result["partial"]["gate"]["status"] == "REVIEW_REQUIRED"
    assert result["empty"]["findings"] == []
    assert any(f["delta"] == "NEW" for f in result["addition"]["findings"])
    assert result["resolution"]["quality"]["resolved"]
    assert any(f.get("new_code") for f in result["regression"]["findings"])
