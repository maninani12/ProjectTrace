"""Bounded, source-mapped LCOV/Cobertura/coverage.py/JaCoCo report ingestion.

Reports are data. No test runner, path read, external entity or URL fetch occurs.
"""

import hashlib
import re
import xml.etree.ElementTree as ET
from pathlib import PurePosixPath

MAX_REPORT_BYTES = 1_000_000
MAX_LINES = 100_000


def absent():
    return {
        "state": "NOT_AVAILABLE",
        "line_percent": None,
        "branch_percent": None,
        "changed_line_percent": None,
        "files": [],
        "errors": [],
        "reason": "No supported coverage report was supplied. Static source cannot determine runtime coverage.",
    }


def percent(covered, total):
    return round(covered * 100 / total, 2) if total else None


def integer(value):
    if not re.fullmatch(r"\d+", str(value)) or not 0 <= int(value) <= 1_000_000_000:
        raise ValueError("Report contains an invalid nonnegative counter.")
    return int(value)


def import_report(
    text,
    files,
    *,
    format="auto",
    declared_commit=None,
    snapshot_commit=None,
    changed_lines=None,
    strip_prefix="",
    source_root="",
    source="uploaded report",
):
    result = {
        **absent(),
        "report_hash": hashlib.sha256(text.encode()).hexdigest(),
        "source": source[:240],
        "declared_commit": declared_commit,
        "snapshot_commit": snapshot_commit,
        "mapping": "EXACT_RELATIVE_PATH",
        "producer_commit_matches_snapshot": False,
    }
    try:
        if len(text.encode()) > MAX_REPORT_BYTES:
            raise ValueError("Coverage report exceeds its 1 MB budget.")
        if declared_commit and declared_commit != snapshot_commit:
            result["state"] = "REPORT_SNAPSHOT_MISMATCH"
            result["errors"] = ["Declared producer commit does not match the selected snapshot."]
            return result
        line_counts = {p: len(s.splitlines()) for p, s in files.items()}
        mapped, unmapped = {}, set()
        entries = 0

        def path_for(raw, roots=()):
            value = raw.replace("\\", "/")
            prefix = strip_prefix.replace("\\", "/").rstrip("/")
            if prefix and value.startswith(prefix + "/"):
                value = value[len(prefix) + 1 :]
            if "\x00" in value or ":" in value or value.startswith("/") or ".." in PurePosixPath(value).parts:
                raise ValueError("Coverage source path is outside the repository mapping.")
            value = str(PurePosixPath(value))
            candidates = {value}
            for root in [source_root, *roots]:
                if root:
                    base = PurePosixPath(root.replace("\\", "/"))
                    if not base.is_absolute() and ".." not in base.parts and ":" not in str(base):
                        candidates.add(str(base / value))
            matches = candidates & files.keys()
            if len(matches) != 1:
                unmapped.add(value)
                return None
            return next(iter(matches))

        def put(raw, line, hits, branches=None, roots=()):
            nonlocal entries
            entries += 1
            if entries > MAX_LINES:
                raise ValueError("Coverage line budget exceeded.")
            line, hits = integer(line), integer(hits)
            path = path_for(raw, roots)
            if path is None:
                return
            if not 1 <= line <= line_counts[path]:
                raise ValueError("Coverage line is outside the selected source snapshot.")
            row = mapped.setdefault(path, {"lines": {}, "branches": {}})
            previous = row["lines"].get(line)
            if previous is not None and previous != hits:
                raise ValueError("Conflicting duplicate coverage line.")
            row["lines"][line] = hits
            if branches is not None:
                covered, total = map(integer, branches)
                if covered > total:
                    raise ValueError("Covered branches exceed total branches.")
                if line in row["branches"] and row["branches"][line] != (covered, total):
                    raise ValueError("Conflicting duplicate coverage branch counter.")
                row["branches"][line] = (covered, total)

        detected = "LCOV" if not text.lstrip().startswith("<") else "XML"
        if detected == "LCOV":
            if format.lower() not in {"auto", "lcov"}:
                raise ValueError("Coverage format does not match supplied report.")
            path, lines, branch_rows = None, {}, {}

            def finish():
                if path is None:
                    raise ValueError("LCOV record is missing SF.")
                if branch_rows.keys() - lines.keys():
                    raise ValueError("LCOV branch refers to a missing line counter.")
                for line, hits in lines.items():
                    branches = branch_rows.get(line)
                    put(path, line, hits, (sum(branches.values()), len(branches)) if branches else None)

            for raw in text.splitlines():
                if raw.startswith("SF:"):
                    if path is not None:
                        raise ValueError("LCOV record is missing end_of_record.")
                    path, lines, branch_rows = raw[3:], {}, {}
                elif raw.startswith("DA:"):
                    fields = raw[3:].split(",")
                    if path is None or len(fields) < 2:
                        raise ValueError("Malformed LCOV line.")
                    number, hits = integer(fields[0]), integer(fields[1])
                    if number in lines and lines[number] != hits:
                        raise ValueError("Conflicting LCOV line.")
                    lines[number] = hits
                elif raw.startswith("BRDA:"):
                    fields = raw[5:].split(",")
                    if path is None or len(fields) != 4:
                        raise ValueError("Malformed LCOV branch.")
                    branches = branch_rows.setdefault(integer(fields[0]), {})
                    identity = (integer(fields[1]), integer(fields[2]))
                    covered = fields[3] != "-" and integer(fields[3]) > 0
                    if identity in branches and branches[identity] != covered:
                        raise ValueError("Conflicting duplicate LCOV branch.")
                    branches[identity] = covered
                elif raw == "end_of_record":
                    finish()
                    path = None
            if path is not None:
                raise ValueError("LCOV record is missing end_of_record.")
            result["format"] = "LCOV"
        else:
            upper = text.upper()
            if "<!ENTITY" in upper:
                raise ValueError("Coverage XML entity declarations are forbidden.")
            if "<!DOCTYPE" in upper:
                # Standard JaCoCo reports carry this inert declaration. Never resolve it.
                safe = r'<!DOCTYPE\s+report\s+PUBLIC\s+"-//JACOCO//DTD(?: Report | _Report_|_Report_)[0-9.]+//EN"\s+"report\.dtd"\s*>'
                cleaned, count = re.subn(safe, "", text, flags=re.I)
                if count != 1 or "<!DOCTYPE" in cleaned.upper():
                    raise ValueError("Unsupported XML document declaration.")
                text = cleaned
            root = ET.fromstring(text)
            todo, nodes = [(root, 0)], 0
            while todo:
                element, depth = todo.pop()
                nodes += 1
                if nodes > 150_000 or depth > 50:
                    raise ValueError("Coverage XML structural budget exceeded.")
                todo.extend((child, depth + 1) for child in element)
            if root.tag == "coverage":
                if format.lower() not in {"auto", "xml", "cobertura", "coverage.py"}:
                    raise ValueError("Coverage format does not match supplied report.")
                roots = [element.text or "" for element in root.findall("./sources/source")]
                for cls in root.findall(".//class"):
                    for line in cls.findall("./lines/line"):
                        branches = None
                        if line.get("branch") == "true":
                            match = re.search(r"\((\d+)/(\d+)\)", line.get("condition-coverage", ""))
                            if match:
                                branches = (match[1], match[2])
                        put(cls.get("filename", ""), line.get("number"), line.get("hits"), branches, roots)
                result["format"] = "Cobertura / coverage.py XML"
            elif root.tag == "report":
                if format.lower() not in {"auto", "xml", "jacoco"}:
                    raise ValueError("Coverage format does not match supplied report.")
                for package in root.findall(".//package"):
                    for sourcefile in package.findall("./sourcefile"):
                        raw_path = str(PurePosixPath(package.get("name", "")) / sourcefile.get("name", ""))
                        for line in sourcefile.findall("./line"):
                            missed, covered = integer(line.get("mb", "0")), integer(line.get("cb", "0"))
                            put(raw_path, line.get("nr"), integer(line.get("ci", "0")), (covered, covered + missed))
                result["format"] = "JaCoCo XML"
            else:
                raise ValueError("Unsupported coverage XML root.")
        if not mapped:
            raise ValueError("No coverage lines map to the selected source snapshot.")
        summary = []
        total, covered, branch_total, branch_covered, changed_total, changed_covered = 0, 0, 0, 0, 0, 0
        for path, value in sorted(mapped.items()):
            count, hit = len(value["lines"]), sum(hits > 0 for hits in value["lines"].values())
            bt, bc = (
                sum(pair[1] for pair in value["branches"].values()),
                sum(pair[0] for pair in value["branches"].values()),
            )
            changed = {
                line: hits
                for line, hits in value["lines"].items()
                if any(lo <= line <= hi for lo, hi in (changed_lines or {}).get(path, []))
            }
            summary.append(
                {
                    "path": path,
                    "line_total": count,
                    "line_covered": hit,
                    "line_percent": percent(hit, count),
                    "branch_total": bt,
                    "branch_covered": bc,
                    "branch_percent": percent(bc, bt),
                    "changed_total": len(changed),
                    "changed_covered": sum(h > 0 for h in changed.values()),
                    "lines": [{"line": line, "hits": hits} for line, hits in sorted(value["lines"].items())],
                }
            )
            total += count
            covered += hit
            branch_total += bt
            branch_covered += bc
            changed_total += len(changed)
            changed_covered += sum(h > 0 for h in changed.values())
        result.update(
            state="PARTIAL" if unmapped or not declared_commit else "VALID",
            files=summary,
            line_total=total,
            line_covered=covered,
            line_percent=percent(covered, total),
            branch_total=branch_total,
            branch_covered=branch_covered,
            branch_percent=percent(branch_covered, branch_total),
            changed_total=changed_total,
            changed_covered=changed_covered,
            changed_line_percent=percent(changed_covered, changed_total),
            unmapped_paths=sorted(unmapped)[:200],
            producer_commit_matches_snapshot=bool(declared_commit),
            reason="Imported report counters; producer execution is not independently verified.",
        )
        if unmapped:
            result["errors"].append("Some report paths did not map uniquely to the selected snapshot.")
        if not declared_commit:
            result["errors"].append("Producer commit was not declared; freshness is unverified.")
    except (ValueError, TypeError, ET.ParseError, RecursionError) as error:
        result.update(
            state="REPORT_INVALID",
            errors=[str(error)[:240]],
            files=[],
            line_percent=None,
            branch_percent=None,
            changed_line_percent=None,
        )
    return result
