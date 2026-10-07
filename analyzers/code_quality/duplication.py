"""Bounded native token-window duplication; operators and literal hashes retained."""

import hashlib
from collections import defaultdict


def detect(metrics, minimum=50, *, window_budget=100000, pair_budget=20000, token_budget=5000000):
    index, groups, seen = defaultdict(list), [], set()
    windows = pairs = 0
    token_work = 0
    partial = False
    matched_ranges = defaultdict(list)

    def work(count):
        nonlocal token_work, partial
        token_work += count
        if token_work > token_budget:
            partial = True
            return False
        return True

    for number, metric in enumerate(metrics):
        tokens = metric.get("duplicate_tokens", [])
        # Ignore short/one-line declarations and trivial repeating boilerplate.
        for offset in range(max(0, len(tokens) - minimum + 1)):
            windows += 1
            if windows > window_budget:
                partial = True
                break
            if not work(minimum):
                break
            values = tuple(t["value"] for t in tokens[offset : offset + minimum])
            if len(set(values)) < 8:
                continue
            key = (metric["language"], hashlib.sha256("\0".join(values).encode()).hexdigest())
            candidates = index[key]
            if len(candidates) > 30:
                partial = True
                continue
            for prior_number, prior_offset in candidates:
                pairs += 1
                if pairs > pair_budget:
                    partial = True
                    break
                if prior_number == number:
                    continue
                if any(
                    lo <= offset and offset + minimum <= hi and prior_offset - offset == shift
                    for lo, hi, shift in matched_ranges[(prior_number, number)]
                ):
                    continue
                other = metrics[prior_number]
                prior = other.get("duplicate_tokens", [])
                # Verify hashes by values, then extend both directions.
                if not work(minimum):
                    break
                if [t["value"] for t in prior[prior_offset : prior_offset + minimum]] != list(values):
                    continue
                left = 0
                while (
                    offset > left
                    and prior_offset > left
                    and work(1)
                    and tokens[offset - left - 1]["value"] == prior[prior_offset - left - 1]["value"]
                ):
                    left += 1
                count = minimum
                while (
                    offset + count < len(tokens)
                    and prior_offset + count < len(prior)
                    and work(1)
                    and tokens[offset + count]["value"] == prior[prior_offset + count]["value"]
                ):
                    count += 1
                if token_work > token_budget:
                    break
                start, old_start, count = offset - left, prior_offset - left, count + left
                matched_ranges[(prior_number, number)].append((start, start + count, old_start - start))
                spans = [(other, prior, old_start), (metric, tokens, start)]
                occurrences = [
                    {
                        "path": m["path"],
                        "symbol": m.get("qualified_name", m["name"]),
                        "line": ts[i]["line"],
                        "end_line": ts[i + count - 1]["line"],
                    }
                    for m, ts, i in spans
                ]
                if any(o["end_line"] - o["line"] + 1 < 6 for o in occurrences):
                    continue
                if occurrences[0]["path"] == occurrences[1]["path"] and not (
                    occurrences[0]["end_line"] < occurrences[1]["line"]
                    or occurrences[1]["end_line"] < occurrences[0]["line"]
                ):
                    continue
                signature = tuple((o["path"], o["line"], o["end_line"]) for o in occurrences)
                if signature in seen:
                    continue
                seen.add(signature)
                digest = hashlib.sha256(
                    "\0".join(t["value"] for t in tokens[start : start + count]).encode()
                ).hexdigest()
                groups.append(
                    {
                        "id": digest,
                        "language": metric["language"],
                        "tokens": count,
                        "normalization": "Parser tokens; comments/formatting removed; local bindings renamed; operators/literal hashes retained",
                        "occurrences": occurrences,
                    }
                )
            candidates.append((number, offset))
            if pairs > pair_budget or token_work > token_budget:
                break
        if windows > window_budget or pairs > pair_budget or token_work > token_budget:
            break
    # Merge the same maximal token block across all occurrences.
    merged = {}
    for group in sorted(groups, key=lambda g: -g["tokens"]):
        row = merged.setdefault(group["id"], {**group, "occurrences": []})
        for occurrence in group["occurrences"]:
            if occurrence not in row["occurrences"]:
                row["occurrences"].append(occurrence)
    rows = list(merged.values())[:200]
    covered = defaultdict(set)
    for row in rows:
        for o in row["occurrences"]:
            covered[o["path"]].update(range(o["line"], o["end_line"] + 1))
    return {
        "state": "PARTIAL" if partial or len(merged) > 200 else "COMPLETED",
        "groups": rows,
        "duplicated_lines": sum(map(len, covered.values())),
        "lines_by_path": {p: sorted(v) for p, v in covered.items()},
        "windows_examined": windows,
        "pairs_examined": pairs,
        "token_work": token_work,
        "token_budget": token_budget,
        "minimum_tokens": minimum,
        "minimum_lines": 6,
        "limitations": [
            "Function-body blocks only; local binding equivalence is syntactic, not type/semantic equivalence.",
            "Default work caps: 100,000 windows, 20,000 pairs, 5 million window/comparison token operations, 31 candidates/window, 200 groups.",
        ],
    }
