# Engineering Changes

An initial import establishes a baseline. Each subsequent analysis with an explicit BASE can capture a repository/component comparison derived from existing snapshots, claim transitions, finding lineage, quality observations and the authoritative Impact Engine. The projection retains BASE/HEAD/branch/commit/PR scope, changed files, owners, before/after observations, captured gate decisions and linked graph records. It does not replace the Evidence Graph.

The screen loads authorized paginated summaries for a selected time window; comparison detail and evidence load on demand. Priority is a displayed sum of deterministic factors (new contradiction, high static security evidence, failed captured policy, measured metric increase). Analyzer re-evaluation is labeled separately and gets review priority rather than attributing reclassification to code. Static/declared observations never establish runtime execution or exposure. The recorded actor is the analysis initiator; commit authorship is unobserved unless supplied by a connector. Counts include all observations; displayed observations and graph links are bounded to 500 with explicit truncation.

New capture is an immutable historical decision. Later human reviews retain their existing audit/record history; they do not rewrite the captured comparison. Legacy snapshots are preserved and are not backfilled into invented changes. Existing repository permissions scope list, detail and evidence reads.

Validation: comparison/access/history and claim-transition/model-re-evaluation tests pass; the UI production build passes. Controlled interface tests verify explicit-baseline empty state. External provider authorship and live PR delivery remain credential-gated.
