import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router";
import { api } from "./api";
import type { Item, Repository } from "./api";
import Badge from "./shared/Badge";
import Source from "./shared/Source";

type Row = Record<string, unknown>;
type Page = {
  items: Row[];
  total: number;
  state: string;
  files?: Row[];
  [key: string]: unknown;
};
type Configuration = {
  name: string;
  baseline_id: string | null;
  rules: Record<
    string,
    { enabled?: boolean; severity?: string; threshold?: number }
  >;
  scope: {
    include: string[];
    exclude: string[];
    test_paths: string[];
    generated_patterns: string[];
    vendor_patterns: string[];
    language_overrides: Record<string, string>;
  };
  gate: {
    scope: string;
    max_new_high: number;
    max_new_reliability: number;
    max_new_complexity: number;
    max_new_duplication_percent: number | null;
    min_changed_coverage: number | null;
    min_analysis_coverage_percent: number | null;
    max_new_nesting?: number | null;
    required_languages?: string[];
    conditions?: Row[];
  };
};
type Overview = {
  state: string;
  reason?: string;
  snapshot_id: string;
  branch: string;
  commit: string;
  base_id?: string;
  configuration: Configuration;
  profile_version: number;
  version: string;
  summary: {
    total: number;
    new: number;
    resolved: number;
    functions: number;
    dimensions: Record<string, number>;
  };
  scope_counts: Record<string, number>;
  languages: Row[];
  limitations: string[];
  resolved: Row[];
  coverage: Row;
  duplication: Row;
  gate: { status: string; scope: string; results: Row[] };
};
const tabs = [
  "Overview",
  "New Code",
  "Findings",
  "Maintenance Hotspots",
  "Metrics",
  "Coverage",
  "Duplication",
  "Trends",
  "Rules & Profiles",
];
const sections: Record<string, string> = {
  "New Code": "findings",
  Findings: "findings",
  "Maintenance Hotspots": "hotspots",
  Metrics: "metrics",
  Coverage: "coverage",
  Duplication: "duplication",
  Trends: "trends",
};
function text(value: unknown): string {
  return value === null || value === undefined
    ? "Not available"
    : typeof value === "object"
      ? JSON.stringify(value)
      : String(value);
}

export default function CodeQuality({
  repositories,
  selectedRepository,
  role,
  onOpen,
}: {
  repositories: Repository[];
  selectedRepository: string;
  role: string;
  onOpen: (item: Item) => void;
}) {
  const [repository, setRepository] = useState(
    selectedRepository === "ALL"
      ? repositories[0]?.id || ""
      : selectedRepository,
  );
  const [snapshot, setSnapshot] = useState("");
  const effectiveSnapshot =
    snapshot ||
    repositories.find((item) => item.id === repository)?.snapshot?.id ||
    "";
  const [tab, setTab] = useState("Overview");
  const [search, setSearch] = useState("");
  const [severity, setSeverity] = useState("");
  const [dimension, setDimension] = useState("");
  const [language, setLanguage] = useState("");
  const [review, setReview] = useState("");
  const [offset, setOffset] = useState(0);
  const [days, setDays] = useState(30);
  const [inspected, setInspected] = useState<Row | null>(null);
  const [duplicate, setDuplicate] = useState<Row | null>(null);
  useEffect(() => {
    if (selectedRepository !== "ALL") {
      setRepository(selectedRepository);
      setSnapshot("");
    }
  }, [selectedRepository]);
  useEffect(() => {
    setOffset(0);
    setInspected(null);
    setDuplicate(null);
  }, [
    tab,
    search,
    repository,
    snapshot,
    effectiveSnapshot,
    severity,
    dimension,
    language,
    review,
  ]);
  const snapshots = useQuery({
    queryKey: ["quality-snapshots", repository],
    queryFn: () =>
      api<{ items: Row[] }>(`/code-quality/${repository}/snapshots`),
    enabled: !!repository,
  });
  const suffix = effectiveSnapshot
    ? `?snapshot_id=${encodeURIComponent(effectiveSnapshot)}`
    : "";
  const overview = useQuery({
    queryKey: ["quality-overview", repository, effectiveSnapshot],
    queryFn: () =>
      api<Overview>(`/code-quality/${repository}/overview${suffix}`),
    enabled: !!repository,
  });
  const section = sections[tab];
  const params = new URLSearchParams({
    offset: String(offset),
    limit: "50",
    q: search,
    severity,
    dimension,
    language,
    review,
    days: String(days),
  });
  if (effectiveSnapshot) params.set("snapshot_id", effectiveSnapshot);
  if (tab === "New Code") params.set("new_code", "true");
  const rows = useQuery({
    queryKey: [
      "quality-rows",
      repository,
      effectiveSnapshot,
      tab,
      search,
      offset,
      severity,
      dimension,
      language,
      review,
      days,
    ],
    queryFn: () =>
      api<Page>(`/code-quality/${repository}/${section}?${params}`),
    enabled:
      !!repository && !!section && overview.data?.state !== "NOT_AVAILABLE",
  });
  const data = overview.data;
  if (!repositories.length)
    return (
      <section className="settings-panel">
        <h2>Import source to begin Code Intelligence</h2>
        <p>
          Upload your repository ZIP on the Repositories page. Coverage is
          imported separately after analysis.
        </p>
        <Link to="/repositories?import=1">Import a repository</Link>
      </section>
    );
  return (
    <div className="quality-module">
      <div className="quality-context">
        <label>
          Quality repository
          <select
            aria-label="Quality repository"
            value={repository}
            onChange={(e) => {
              setRepository(e.target.value);
              setSnapshot("");
            }}
          >
            {repositories.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          HEAD snapshot
          <select
            aria-label="Quality snapshot"
            value={snapshot}
            onChange={(e) => setSnapshot(e.target.value)}
          >
            <option value="">Latest snapshot</option>
            {snapshots.data?.items.map((s) => (
              <option key={text(s.id)} value={text(s.id)}>
                {text(s.branch)} · {text(s.commit).slice(0, 10)} ·{" "}
                {new Date(text(s.created_at)).toLocaleString()}
              </option>
            ))}
          </select>
        </label>
        {data && (
          <p>
            <strong>{data.branch}</strong> · HEAD{" "}
            <code>{data.commit.slice(0, 12)}</code>
            <br />
            BASE <code>{data.base_id || "Not selected"}</code> ·{" "}
            {data.configuration?.name || "Historical profile"} v
            {data.profile_version ?? "—"}
            <br />
            Coverage: {text(data.coverage?.state)}
          </p>
        )}
      </div>
      <nav className="quality-tabs" aria-label="Code Quality views">
        {tabs.map((name) => (
          <button
            key={name}
            className={tab === name ? "active" : ""}
            aria-current={tab === name ? "page" : undefined}
            onClick={() => setTab(name)}
          >
            {name}
          </button>
        ))}
      </nav>
      {overview.isLoading ? (
        <p role="status">Loading quality snapshot…</p>
      ) : overview.isError ? (
        <p className="error">
          {overview.error.message}
          <button onClick={() => overview.refetch()}>Retry</button>
        </p>
      ) : data?.state === "NOT_AVAILABLE" && tab !== "Rules & Profiles" ? (
        <section className="context-note">
          <h2>Quality analysis not available</h2>
          <p>{data.reason}</p>
          <Link to="/repositories">Analyze a new source snapshot</Link>
        </section>
      ) : (
        <>
          {data?.state === "PARTIAL" && (
            <p className="context-note">
              Partial analysis: inspect language coverage and file diagnostics
              before using this result as a gate.
            </p>
          )}
          {tab === "Overview" && data?.summary && (
            <>
              <div className="stats compact">
                {[
                  ["Quality observations", data.summary.total],
                  ["Reliability", data.summary.dimensions.RELIABILITY || 0],
                  [
                    "Maintainability",
                    data.summary.dimensions.MAINTAINABILITY || 0,
                  ],
                  ["New Code", data.summary.new],
                ].map(([label, value]) => (
                  <button
                    key={label}
                    onClick={() => {
                      setDimension(
                        label === "Reliability"
                          ? "RELIABILITY"
                          : label === "Maintainability"
                            ? "MAINTAINABILITY"
                            : "",
                      );
                      setTab(label === "New Code" ? "New Code" : "Findings");
                    }}
                  >
                    <span>{label}</span>
                    <strong>{value}</strong>
                  </button>
                ))}
              </div>
              <section className="settings-panel">
                <h2>
                  Native quality gate <Badge value={data.gate.status} />
                </h2>
                <p>
                  {data.gate.scope.replaceAll("_", " ")} · Advisory result also
                  feeds the engineering and PR gate.
                </p>
                <QualityTable
                  items={data.gate.results}
                  columns={[
                    "policy",
                    "result",
                    "measured",
                    "threshold",
                    "reason",
                    "remediation",
                  ]}
                />
              </section>
              <section className="settings-panel">
                <h2>Analysis coverage</h2>
                <p>
                  {Object.entries(data.scope_counts)
                    .map(([k, v]) => `${k.replaceAll("_", " ")}: ${v}`)
                    .join(" · ")}
                </p>
                <QualityTable
                  items={data.languages}
                  columns={[
                    "language",
                    "maturity",
                    "analyzed",
                    "partial",
                    "total",
                    "reason",
                  ]}
                />
                <button onClick={() => setTab("Metrics")}>
                  Inspect measured functions and file scope
                </button>
                <details>
                  <summary>Limits and identity model</summary>
                  {data.limitations.map((l) => (
                    <p key={l}>{l}</p>
                  ))}
                </details>
              </section>
            </>
          )}
          {tab === "Rules & Profiles" && (
            <QualityProfiles
              repository={repository}
              role={role}
              snapshots={snapshots.data?.items || []}
            />
          )}
          {section && (
            <>
              <div className="quality-filter">
                <label>
                  Search {tab.toLowerCase()}
                  <input
                    aria-label="Quality search"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Path, symbol or title"
                  />
                </label>
                {["Findings", "New Code"].includes(tab) && (
                  <>
                    <label>
                      Severity
                      <select
                        aria-label="Quality severity"
                        value={severity}
                        onChange={(e) => setSeverity(e.target.value)}
                      >
                        {["", "CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"].map(
                          (s) => (
                            <option key={s} value={s}>
                              {s || "All severities"}
                            </option>
                          ),
                        )}
                      </select>
                    </label>
                    <label>
                      Dimension
                      <select
                        aria-label="Quality dimension"
                        value={dimension}
                        onChange={(e) => setDimension(e.target.value)}
                      >
                        <option value="">Both dimensions</option>
                        <option>RELIABILITY</option>
                        <option>MAINTAINABILITY</option>
                      </select>
                    </label>
                    <label>
                      Language
                      <select
                        aria-label="Quality language"
                        value={language}
                        onChange={(e) => setLanguage(e.target.value)}
                      >
                        <option value="">All languages</option>
                        {["Python", "JavaScript", "TypeScript", "Java"].map(
                          (value) => (
                            <option key={value}>{value}</option>
                          ),
                        )}
                      </select>
                    </label>
                    <label>
                      Human review
                      <select
                        aria-label="Quality review"
                        value={review}
                        onChange={(e) => setReview(e.target.value)}
                      >
                        <option value="">All review states</option>
                        {[
                          "OPEN",
                          "IN_REVIEW",
                          "CONFIRMED",
                          "FALSE_POSITIVE",
                          "ACCEPTED",
                          "RESOLVED",
                        ].map((value) => (
                          <option key={value}>{value}</option>
                        ))}
                      </select>
                    </label>
                  </>
                )}
                {tab === "Trends" && (
                  <label>
                    Observed window
                    <select
                      value={days}
                      onChange={(e) => setDays(Number(e.target.value))}
                    >
                      {[7, 30, 90].map((d) => (
                        <option key={d} value={d}>
                          {d} days
                        </option>
                      ))}
                    </select>
                  </label>
                )}
              </div>
              {tab === "New Code" && (
                <p className="context-note">
                  BASE:{" "}
                  {data?.base_id ||
                    "No baseline selected. Choose BASE in Rules & Profiles and analyze HEAD."}{" "}
                  · Harmless line movement retains symbol identity.
                  Analyzer/profile changes require a new comparable baseline.
                  {!!data?.resolved.length &&
                    ` ${data.resolved.length} prior observations are absent in HEAD.`}
                </p>
              )}
              {tab === "Coverage" && (
                <CoverageImport
                  repository={repository}
                  data={data}
                  snapshot={effectiveSnapshot}
                />
              )}
              {tab === "Maintenance Hotspots" && (
                <p>
                  Priority uses measured complexity, open quality observations,
                  duplicated lines and observed snapshot changes. Git authorship
                  and commit frequency are unavailable.
                </p>
              )}
              {tab === "Duplication" && (
                <p>
                  Native function-body token blocks: minimum 50 tokens and 6
                  lines by default. Comments and local names are normalized;
                  operators and literal values are retained as hashes. This beta
                  result needs review.
                </p>
              )}
              {tab === "Trends" && (
                <p>
                  Each row is a recorded snapshot. Profile, scope or analyzer
                  changes are annotated. Review counts are captured at analysis;
                  current human reviews are shown in Findings.
                </p>
              )}
              {rows.isLoading ? (
                <p role="status">Loading {tab.toLowerCase()}…</p>
              ) : rows.isError ? (
                <p className="error">
                  {rows.error.message}
                  <button onClick={() => rows.refetch()}>Retry</button>
                </p>
              ) : tab === "Coverage" ? (
                <>
                  <p>
                    <Badge value={text(rows.data?.state)} /> · Line coverage{" "}
                    {text(rows.data?.line_percent)}
                    {rows.data?.line_percent != null && "%"} · Branch coverage{" "}
                    {text(rows.data?.branch_percent)} · Changed-line coverage{" "}
                    {text(rows.data?.changed_line_percent)}
                  </p>
                  <p>{text(rows.data?.reason)}</p>
                  <p>
                    {Array.isArray(rows.data?.errors)
                      ? rows.data.errors.map(text).join(" · ")
                      : ""}
                  </p>
                  <QualityTable
                    items={rows.data?.files || []}
                    columns={[
                      "path",
                      "line_total",
                      "line_covered",
                      "line_percent",
                      "branch_total",
                      "branch_covered",
                      "changed_total",
                      "changed_covered",
                    ]}
                    onInspect={setInspected}
                  />
                </>
              ) : (
                <QualityTable
                  items={rows.data?.items || []}
                  columns={
                    tab === "Metrics"
                      ? [
                          "path",
                          "qualified_name",
                          "language",
                          "cyclomatic",
                          "cognitive_approximation",
                          "length",
                          "nesting",
                          "parameters",
                        ]
                      : tab === "Maintenance Hotspots"
                        ? ["path", "score", "owner", "factors", "history_scope"]
                        : tab === "Trends"
                          ? [
                              "at",
                              "commit",
                              "total",
                              "new",
                              "resolved",
                              "line_coverage",
                              "duplication_percent",
                              "annotation",
                            ]
                          : tab === "Duplication"
                            ? [
                                "language",
                                "tokens",
                                "occurrences",
                                "normalization",
                              ]
                            : [
                                "title",
                                "dimension",
                                "severity",
                                "confidence",
                                "path",
                                "symbol",
                                "delta",
                                "review_status",
                              ]
                  }
                  onInspect={(row) => {
                    if (["Findings", "New Code"].includes(tab))
                      onOpen(row as Item);
                    else if (tab === "Duplication") setDuplicate(row);
                    else setInspected(row);
                  }}
                />
              )}
              {!!rows.data?.total && (
                <div className="quality-pagination">
                  <button
                    disabled={!offset}
                    onClick={() => setOffset(Math.max(0, offset - 50))}
                  >
                    Previous
                  </button>
                  <span>
                    {offset + 1}–{Math.min(offset + 50, rows.data.total)} of{" "}
                    {rows.data.total}
                  </span>
                  <button
                    disabled={offset + 50 >= rows.data.total}
                    onClick={() => setOffset(offset + 50)}
                  >
                    Next
                  </button>
                </div>
              )}
              {tab === "Metrics" && (
                <FileScope
                  repository={repository}
                  snapshot={effectiveSnapshot}
                />
              )}
              {tab === "New Code" && !!data?.resolved.length && (
                <details>
                  <summary>
                    Resolved machine observations in this comparison
                  </summary>
                  <QualityTable
                    items={data.resolved}
                    columns={["title", "path", "rule", "machine_status"]}
                  />
                </details>
              )}
              {["Findings", "New Code"].includes(tab) && (
                <div className="quality-filter">
                  <a
                    href={`/api/code-quality/${repository}/exports/csv${suffix}`}
                    download
                  >
                    Download CSV
                  </a>
                  <a
                    href={`/api/code-quality/${repository}/exports/json${suffix}`}
                    download
                  >
                    Download JSON
                  </a>
                  <button
                    onClick={async () => {
                      const report = await api(
                        `/code-quality/${repository}/export${suffix}`,
                      );
                      const url = URL.createObjectURL(
                        new Blob([JSON.stringify(report, null, 2)], {
                          type: "application/json",
                        }),
                      );
                      const a = document.createElement("a");
                      a.href = url;
                      a.download = "ProjectTrace-quality.sarif";
                      a.click();
                      URL.revokeObjectURL(url);
                    }}
                  >
                    Download SARIF 2.1
                  </button>
                </div>
              )}
            </>
          )}
          {inspected && (
            <section
              className="settings-panel"
              aria-label="Quality metric inspector"
            >
              <h2>
                {text(
                  inspected.qualified_name || inspected.path || "Observation",
                )}
              </h2>
              <button onClick={() => setInspected(null)}>
                Close inspector
              </button>
              {Array.isArray(inspected.lines) && (
                <>
                  <h3>Reported line hits</h3>
                  <QualityTable
                    items={(inspected.lines as Row[]).slice(0, 100)}
                    columns={["line", "hits"]}
                  />
                </>
              )}
              <dl>
                {Object.entries(inspected)
                  .filter(([k]) => !["source", "lines"].includes(k))
                  .map(([k, v]) => (
                    <div key={k}>
                      <dt>{k.replaceAll("_", " ")}</dt>
                      <dd>{text(v)}</dd>
                    </div>
                  ))}
              </dl>
              {!!inspected.path && (
                <QualitySource
                  repository={repository}
                  snapshot={data?.snapshot_id || snapshot}
                  path={text(inspected.path)}
                  line={Number(inspected.line)}
                />
              )}
            </section>
          )}
          {duplicate && (
            <section className="settings-panel">
              <h2>Duplicate occurrences</h2>
              <button onClick={() => setDuplicate(null)}>
                Close comparison
              </button>
              <div className="quality-duplicate">
                {(duplicate.occurrences as Row[]).slice(0, 4).map((o) => (
                  <div key={text(o.path) + text(o.line)}>
                    <h3>
                      {text(o.path)}:{text(o.line)}–{text(o.end_line)}
                    </h3>
                    <QualitySource
                      repository={repository}
                      snapshot={data?.snapshot_id || snapshot}
                      path={text(o.path)}
                      line={Number(o.line)}
                    />
                  </div>
                ))}
              </div>
            </section>
          )}
        </>
      )}
    </div>
  );
}

function QualityTable({
  items,
  columns,
  onInspect,
}: {
  items: Row[];
  columns: string[];
  onInspect?: (row: Row) => void;
}) {
  if (!items.length)
    return (
      <p className="context-note">
        No matching results in the selected snapshot and filters.
      </p>
    );
  return (
    <div
      className="quality-table-wrap"
      tabIndex={0}
      role="region"
      aria-label="Quality results table"
    >
      <table className="quality-table">
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c} scope="col">
                {c.replaceAll("_", " ")}
              </th>
            ))}
            {onInspect && <th scope="col">Evidence</th>}
          </tr>
        </thead>
        <tbody>
          {items.map((item, i) => (
            <tr key={text(item.id || item.fingerprint || item.path || i) + i}>
              {columns.map((c) => (
                <td key={c}>
                  {[
                    "result",
                    "maturity",
                    "severity",
                    "confidence",
                    "delta",
                    "review_status",
                    "machine_status",
                  ].includes(c) ? (
                    <Badge value={text(item[c])} />
                  ) : (
                    text(item[c])
                  )}
                </td>
              ))}
              {onInspect && (
                <td>
                  <button
                    aria-label={`Inspect ${text(item.title || item.qualified_name || item.path || "result")}`}
                    onClick={() => onInspect(item)}
                  >
                    Inspect
                  </button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function QualitySource({
  repository,
  snapshot,
  path,
  line,
}: {
  repository: string;
  snapshot: string;
  path: string;
  line: number;
}) {
  const result = useQuery({
    queryKey: ["quality-source", repository, snapshot, path],
    queryFn: () =>
      api<{ source: string; first_line: number; total_lines: number }>(
        `/code-quality/${repository}/source?${new URLSearchParams({ snapshot_id: snapshot, q: path, offset: String(Math.max(0, (line || 1) - 30)), limit: "100" })}`,
      ),
  });
  return result.isLoading ? (
    <p>Loading source…</p>
  ) : result.isError ? (
    <p className="error">{result.error.message}</p>
  ) : (
    <>
      <p>
        Source window: {result.data?.first_line}–
        {Math.min(
          (result.data?.first_line || 1) + 99,
          result.data?.total_lines || 0,
        )}{" "}
        of {result.data?.total_lines} lines · recorded, redacted evidence
      </p>
      <Source
        item={result.data}
        highlight={line}
        startLine={result.data?.first_line}
      />
    </>
  );
}
function FileScope({
  repository,
  snapshot,
}: {
  repository: string;
  snapshot: string;
}) {
  const result = useQuery({
    queryKey: ["quality-inventory", repository, snapshot],
    queryFn: () =>
      api<Page>(
        `/code-quality/${repository}/inventory?limit=100${snapshot ? `&snapshot_id=${snapshot}` : ""}`,
      ),
  });
  return (
    <details>
      <summary>
        File scope and parser diagnostics ({result.data?.total || 0} files)
      </summary>
      <p>
        First 100 files; full scope is available through the paginated inventory
        API.
      </p>
      <QualityTable
        items={result.data?.items || []}
        columns={[
          "path",
          "language",
          "kind",
          "parser_state",
          "physical_lines",
          "logical_statements",
          "comment_lines",
          "bytes",
          "reason",
        ]}
      />
    </details>
  );
}

function CoverageImport({
  repository,
  data,
  snapshot,
}: {
  repository: string;
  data?: Overview;
  snapshot: string;
}) {
  const client = useQueryClient();
  const [report, setReport] = useState<File | null>(null);
  const [commit, setCommit] = useState("");
  const [prefix, setPrefix] = useState("");
  const [root, setRoot] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!report || !data) return;
    setBusy(true);
    try {
      const result = await api<{ state: string }>(
        `/code-quality/${repository}/coverage`,
        {
          snapshot_id: data.snapshot_id,
          report: await report.text(),
          declared_commit: commit || null,
          strip_prefix: prefix,
          source_root: root,
          source: report.name,
        },
      );
      setMessage(
        `Imported ${result.state}. The initial analysis is preserved; the effective gate uses this report.`,
      );
      await client.invalidateQueries({ queryKey: ["quality-rows"] });
      await client.invalidateQueries({ queryKey: ["quality-overview"] });
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Report import failed.");
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    setMessage("");
    setCommit("");
    setReport(null);
  }, [repository, snapshot]);
  return (
    <details className="settings-panel">
      <summary>Import a coverage report</summary>
      <p>
        LCOV, Cobertura / coverage.py XML or JaCoCo XML. Reports are mapped to
        this HEAD. Enter the producer commit or content digest from your report
        process; selecting HEAD does not prove report freshness. No test runner
        executes.
      </p>
      <form onSubmit={submit} className="quality-form">
        <label>
          Report file
          <input
            type="file"
            accept=".xml,.lcov,.info"
            onChange={(e) => setReport(e.target.files?.[0] || null)}
          />
        </label>
        <label>
          Declared producer commit
          <input
            value={commit}
            onChange={(e) => setCommit(e.target.value)}
            maxLength={80}
          />
        </label>
        <label>
          Explicit path prefix to strip
          <input
            value={prefix}
            onChange={(e) => setPrefix(e.target.value)}
            placeholder="Optional producer workspace prefix"
          />
        </label>
        <label>
          Repository source root
          <input
            value={root}
            onChange={(e) => setRoot(e.target.value)}
            placeholder="Optional: src/main/java"
          />
        </label>
        <button disabled={!report || busy}>
          {busy ? "Importing…" : "Import report into HEAD"}
        </button>
        <p role="status">{message}</p>
      </form>
    </details>
  );
}

function QualityProfiles({
  repository,
  role,
  snapshots,
}: {
  repository: string;
  role: string;
  snapshots: Row[];
}) {
  const [scope, setScope] = useState("REPOSITORY");
  const [teamId, setTeamId] = useState("");
  const repoId = scope === "REPOSITORY" ? repository : null;
  const profileParams = new URLSearchParams({
    ...(repoId ? { repository_id: repoId } : {}),
    ...(scope === "TEAM" ? { team_id: teamId } : {}),
  });
  const profile = useQuery({
    queryKey: ["quality-profile", repoId, scope, teamId],
    queryFn: () =>
      api<{
        version: number;
        configuration: Configuration;
        overrides?: Row;
        source: string;
        inheritance?: { scope: string; version: number }[];
        team_id?: string;
      }>(`/code-quality/profiles/current?${profileParams}`),
    enabled: scope !== "TEAM" || !!teamId,
  });
  const versions = useQuery({
    queryKey: ["quality-profile-versions", repoId, scope, teamId],
    queryFn: () =>
      api<{ items: Row[]; total: number }>(
        `/code-quality/profiles/versions?${profileParams}`,
      ),
    enabled: scope !== "TEAM" || !!teamId,
  });
  const rules = useQuery({
    queryKey: ["quality-rules"],
    queryFn: () => api<{ rules: Row[] }>("/code-quality/rules"),
  });
  const [draft, setDraft] = useState<Configuration | null>(null);
  const [rule, setRule] = useState("PT-QUALITY-001");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [conditionId, setConditionId] = useState("custom-condition");
  const [conditionMetric, setConditionMetric] = useState("finding_count");
  const [conditionOperator, setConditionOperator] = useState("LTE");
  const [conditionThreshold, setConditionThreshold] = useState(0);
  const [conditionFailure, setConditionFailure] = useState("REVIEW_REQUIRED");
  const [conditionBlocking, setConditionBlocking] = useState(false);
  useEffect(() => {
    setDraft(
      profile.data?.configuration
        ? structuredClone(profile.data.configuration)
        : null,
    );
  }, [profile.data, repoId]);
  useEffect(() => setMessage(""), [repoId]);
  const canEdit = ["ORG_OWNER", "ADMIN"].includes(role);
  const selected = rules.data?.rules.find((r) => r.id === rule);
  async function save(e: FormEvent) {
    e.preventDefault();
    if (!draft || !profile.data) return;
    setBusy(true);
    try {
      function overrides(before: Row, after: Row, existing: Row): Row {
        const result = structuredClone(existing);
        for (const [key, value] of Object.entries(after)) {
          if (JSON.stringify(value) === JSON.stringify(before[key])) continue;
          result[key] =
            value && typeof value === "object" && !Array.isArray(value)
              ? overrides(
                  (before[key] || {}) as Row,
                  value as Row,
                  (existing[key] || {}) as Row,
                )
              : value;
        }
        return result;
      }
      await api("/code-quality/profiles/current", {
        repository_id: repoId,
        team_id: scope === "TEAM" ? teamId : null,
        expected_version: profile.data.version,
        configuration: overrides(
          profile.data.configuration as unknown as Row,
          draft as unknown as Row,
          profile.data.overrides || {},
        ),
      });
      await profile.refetch();
      await versions.refetch();
      setMessage(
        "Profile saved. Analyze a new HEAD snapshot to apply it. Historical snapshots retain their captured settings.",
      );
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Profile save failed.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="settings-panel">
      <h2>Native quality rules and profiles</h2>
      <p>
        Recommended defaults inherit through organization, team and repository
        scope. Each save captures an immutable version. No repository
        configuration code executes.
      </p>
      <label>
        Profile scope
        <select value={scope} onChange={(e) => setScope(e.target.value)}>
          <option value="REPOSITORY">Repository override</option>
          <option value="ORGANIZATION">Organization default</option>
          <option value="TEAM">Team profile</option>
        </select>
      </label>
      <label>
        Team profile ID
        <input
          value={teamId}
          onChange={(e) => setTeamId(e.target.value)}
          placeholder="For example, payments"
          pattern="[A-Za-z0-9_-]{1,60}"
        />
      </label>
      {scope === "REPOSITORY" && canEdit && (
        <button
          disabled={busy || !profile.data}
          onClick={async () => {
            if (!profile.data) return;
            setBusy(true);
            try {
              await api("/code-quality/profiles/team-assignment", {
                repository_id: repository,
                team_id: teamId || null,
                expected_version: profile.data.version,
              });
              await profile.refetch();
              await versions.refetch();
              setMessage(
                "Team assignment saved and audited. Analyze a new HEAD to apply it.",
              );
            } catch (error) {
              setMessage(
                error instanceof Error ? error.message : "Assignment failed.",
              );
            } finally {
              setBusy(false);
            }
          }}
        >
          {teamId ? "Assign team profile" : "Clear team assignment"}
        </button>
      )}
      {profile.isError ? (
        <p className="error">{profile.error.message}</p>
      ) : !draft ? (
        <p>Loading profile…</p>
      ) : (
        <form onSubmit={save} className="quality-form">
          <p>
            Source: {profile.data?.source} · version {profile.data?.version}
          </p>
          <p>
            Inheritance: Recommended
            {profile.data?.inheritance
              ?.map((p) => ` → ${p.scope} v${p.version}`)
              .join("")}
          </p>
          <fieldset disabled={!canEdit || busy}>
            <legend>Quality configuration</legend>
            <label>
              Profile name
              <input
                value={draft.name}
                onChange={(e) => setDraft({ ...draft, name: e.target.value })}
              />
            </label>
            <label>
              BASE for subsequent analysis
              <select
                aria-label="BASE for subsequent analysis"
                value={draft.baseline_id || ""}
                disabled={!repoId}
                onChange={(e) =>
                  setDraft({ ...draft, baseline_id: e.target.value || null })
                }
              >
                <option value="">
                  Caller-selected BASE / no configured baseline
                </option>
                {snapshots.map((s) => (
                  <option key={text(s.id)} value={text(s.id)}>
                    {text(s.branch)} · {text(s.commit).slice(0, 12)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Rule
              <select value={rule} onChange={(e) => setRule(e.target.value)}>
                {rules.data?.rules.map((r) => (
                  <option key={text(r.id)} value={text(r.id)}>
                    {text(r.id)} · {text(r.title)}
                  </option>
                ))}
              </select>
            </label>
            {selected && (
              <>
                <p>
                  <Badge value={text(selected.status)} /> ·{" "}
                  {text(selected.dimension)} · {text(selected.detection)}
                </p>
                <p>
                  Trigger: {text(selected.bad_example)}
                  <br />
                  Remediation: {text(selected.good_example)}
                </p>
                <label>
                  <input
                    type="checkbox"
                    checked={draft.rules[rule]?.enabled !== false}
                    onChange={(e) =>
                      setDraft({
                        ...draft,
                        rules: {
                          ...draft.rules,
                          [rule]: {
                            ...draft.rules[rule],
                            enabled: e.target.checked,
                          },
                        },
                      })
                    }
                  />{" "}
                  Rule enabled
                </label>
                <label>
                  Severity
                  <select
                    value={
                      draft.rules[rule]?.severity ||
                      text(selected.default_severity)
                    }
                    onChange={(e) =>
                      setDraft({
                        ...draft,
                        rules: {
                          ...draft.rules,
                          [rule]: {
                            ...draft.rules[rule],
                            severity: e.target.value,
                          },
                        },
                      })
                    }
                  >
                    {["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"].map((s) => (
                      <option key={s}>{s}</option>
                    ))}
                  </select>
                </label>
                {selected.default_threshold != null && (
                  <label>
                    Threshold
                    <input
                      type="number"
                      min={Number(selected.threshold_min || 1)}
                      max={10000}
                      value={
                        draft.rules[rule]?.threshold ??
                        Number(selected.default_threshold)
                      }
                      onChange={(e) =>
                        setDraft({
                          ...draft,
                          rules: {
                            ...draft.rules,
                            [rule]: {
                              ...draft.rules[rule],
                              threshold: Number(e.target.value),
                            },
                          },
                        })
                      }
                    />
                  </label>
                )}
              </>
            )}
            {(
              [
                "include",
                "exclude",
                "test_paths",
                "generated_patterns",
                "vendor_patterns",
              ] as const
            ).map((key) => (
              <label key={key}>
                {key.replaceAll("_", " ")} (comma-separated globs)
                <input
                  key={key + String(profile.data?.version) + scope}
                  defaultValue={draft.scope[key].join(", ")}
                  onBlur={(e) =>
                    setDraft({
                      ...draft,
                      scope: {
                        ...draft.scope,
                        [key]: e.target.value
                          .split(",")
                          .map((s) => s.trim())
                          .filter(Boolean),
                      },
                    })
                  }
                />
              </label>
            ))}
            <label>
              Gate scope
              <select
                value={draft.gate.scope}
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    gate: { ...draft.gate, scope: e.target.value },
                  })
                }
              >
                <option value="NEW_CODE">New Code</option>
                <option value="OVERALL">Overall</option>
              </select>
            </label>
            {(
              [
                "max_new_high",
                "max_new_reliability",
                "max_new_complexity",
              ] as const
            ).map((key) => (
              <label key={key}>
                {key.replaceAll("_", " ")}
                <input
                  type="number"
                  min={0}
                  value={draft.gate[key]}
                  onChange={(e) =>
                    setDraft({
                      ...draft,
                      gate: { ...draft.gate, [key]: Number(e.target.value) },
                    })
                  }
                />
              </label>
            ))}
            <label>
              Minimum changed-line coverage % (blank disables)
              <input
                type="number"
                min={0}
                max={100}
                value={draft.gate.min_changed_coverage ?? ""}
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    gate: {
                      ...draft.gate,
                      min_changed_coverage:
                        e.target.value === "" ? null : Number(e.target.value),
                    },
                  })
                }
              />
            </label>
            <label>
              Minimum parsed-file analysis coverage % (blank disables)
              <input
                type="number"
                min={0}
                max={100}
                value={draft.gate.min_analysis_coverage_percent ?? ""}
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    gate: {
                      ...draft.gate,
                      min_analysis_coverage_percent:
                        e.target.value === "" ? null : Number(e.target.value),
                    },
                  })
                }
              />
            </label>
            <p>
              Rule precision remains unmeasured. Exceeded rule thresholds
              request review; imported test coverage and explicitly configured
              parsed-file coverage use their measured evidence.
            </p>
            <label>
              Maximum nesting (blank disables)
              <input
                type="number"
                min={0}
                max={100}
                value={draft.gate.max_new_nesting ?? ""}
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    gate: {
                      ...draft.gate,
                      max_new_nesting:
                        e.target.value === "" ? null : Number(e.target.value),
                    },
                  })
                }
              />
            </label>
            <label>
              Required parser languages
              <input
                defaultValue={draft.gate.required_languages?.join(", ") || ""}
                key={String(profile.data?.version) + scope + "required"}
                onBlur={(e) =>
                  setDraft({
                    ...draft,
                    gate: {
                      ...draft.gate,
                      required_languages: e.target.value
                        .split(",")
                        .map((s) => s.trim())
                        .filter(Boolean),
                    },
                  })
                }
                placeholder="Python, TypeScript"
              />
            </label>
            <fieldset>
              <legend>Additional gate condition</legend>
              <label>
                Name
                <input
                  value={conditionId}
                  onChange={(e) => setConditionId(e.target.value)}
                  maxLength={100}
                />
              </label>
              <label>
                Measurement
                <select
                  value={conditionMetric}
                  onChange={(e) => setConditionMetric(e.target.value)}
                >
                  {[
                    "finding_count",
                    "cyclomatic",
                    "nesting",
                    "parameters",
                    "length",
                    "cognitive_approximation",
                    "changed_coverage",
                    "analysis_coverage",
                    "duplication_percent",
                    "parser_failures",
                  ].map((m) => (
                    <option key={m} value={m}>
                      {m.replaceAll("_", " ")}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Comparison
                <select
                  value={conditionOperator}
                  onChange={(e) => setConditionOperator(e.target.value)}
                >
                  {["EQ", "LT", "LTE", "GT", "GTE"].map((op) => (
                    <option key={op}>{op}</option>
                  ))}
                </select>
              </label>
              <label>
                Threshold
                <input
                  type="number"
                  min={0}
                  max={10000}
                  value={conditionThreshold}
                  onChange={(e) =>
                    setConditionThreshold(Number(e.target.value))
                  }
                />
              </label>
              <label>
                When exceeded
                <select
                  value={conditionFailure}
                  onChange={(e) => setConditionFailure(e.target.value)}
                >
                  {["WARNING", "REVIEW_REQUIRED", "FAIL"].map((s) => (
                    <option key={s}>{s}</option>
                  ))}
                </select>
              </label>
              <label>
                <input
                  type="checkbox"
                  checked={conditionBlocking}
                  onChange={(e) => setConditionBlocking(e.target.checked)}
                />
                Deliberately permit this condition to block despite unmeasured
                rule precision
              </label>
              <button
                type="button"
                disabled={
                  !conditionId ||
                  draft.gate.conditions?.some((c) => c.id === conditionId)
                }
                onClick={() =>
                  setDraft({
                    ...draft,
                    gate: {
                      ...draft.gate,
                      conditions: [
                        ...(draft.gate.conditions || []),
                        {
                          id: conditionId,
                          metric: conditionMetric,
                          operator: conditionOperator,
                          threshold: conditionThreshold,
                          failure: conditionFailure,
                          allow_unvalidated_blocking: conditionBlocking,
                        },
                      ],
                    },
                  })
                }
              >
                Add condition
              </button>
              {draft.gate.conditions?.map((c) => (
                <p key={String(c.id)}>
                  {String(c.id)} · {String(c.metric)} {String(c.operator)}{" "}
                  {String(c.threshold)} · {String(c.failure)}{" "}
                  <button
                    type="button"
                    onClick={() =>
                      setDraft({
                        ...draft,
                        gate: {
                          ...draft.gate,
                          conditions: draft.gate.conditions?.filter(
                            (item) => item.id !== c.id,
                          ),
                        },
                      })
                    }
                  >
                    Remove condition
                  </button>
                </p>
              ))}
            </fieldset>
            <button type="submit">
              {busy ? "Saving…" : "Save quality profile"}
            </button>
          </fieldset>
          {!canEdit && (
            <p>
              Administrators can change profiles. You can inspect rules and
              captured results.
            </p>
          )}
          <p role="status">{message}</p>
        </form>
      )}
      <details>
        <summary>
          Profile and gate version history ({versions.data?.total || 0})
        </summary>
        {versions.isError ? (
          <p>Version history could not be loaded.</p>
        ) : (
          versions.data?.items.map((v) => (
            <p key={String(v.id)}>
              Version {String(v.version)} · gate {String(v.gate_version)} ·{" "}
              {String(v.actor)} · {String(v.recorded_at)}
            </p>
          ))
        )}
        <p>
          Earlier snapshots retain their settings. New versions apply to
          subsequent analyses.
        </p>
      </details>
      <details>
        <summary>
          Implemented quality registry ({rules.data?.rules.length || 0} rules)
        </summary>
        <QualityTable
          items={rules.data?.rules || []}
          columns={[
            "id",
            "title",
            "dimension",
            "status",
            "default_threshold",
            "languages",
            "supported_versions",
          ]}
        />
      </details>
    </section>
  );
}
