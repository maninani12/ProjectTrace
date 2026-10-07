import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";
import TrustExceptions from "./TrustExceptions";
import OIDCAdministration from "./OIDCAdministration";
import SCMConnections from "./SCMConnections";

type Policy = {
  version: number;
  source_egress: string;
  ai_mode: string;
  package_coordinate_advisories: boolean;
  github_check_metadata: boolean;
  maximum_exception_days: number;
};
type Capability = {
  language: string;
  parser: string;
  parser_version: string;
  grammar_version?: string;
  maturity: string;
  quality: string;
  sast: string;
  flow: string;
  precision: string;
};
type Registry = {
  version: string;
  languages: Capability[];
  unsupported: string;
  parser_isolation: string;
  rule_blocking: string;
  scale: Record<string, string>;
};
type Integrity = {
  state: string;
  linked_events: number;
  legacy_unlinked_events: number;
  digest: string;
  checkpoint: unknown;
  limitations: string[];
};
type Health = {
  validation?: {
    state: string;
    case_count?: number;
    production_precision: string;
    groups: {
      domain: string;
      rule: string;
      language: string;
      framework: string;
      tier: number;
      tp: number;
      tn: number;
      fp: number;
      fn: number;
      precision: number | null;
      recall: number | null;
      qualification: string;
    }[];
    limitations: string[];
  };
  groups: {
    rule: string;
    rule_version: string;
    language: string;
    reviewed_occurrences: number;
    dismissed: number;
    dismissal_fraction: number;
    precision: string;
  }[];
  limitations: string[];
  truncated: boolean;
};

type Coverage = {
  state: string;
  repository_id?: string;
  snapshot_id?: string;
  branch?: string;
  commit?: string;
  analyzer_version?: string;
  profile_version?: number;
  job_id?: string;
  analysis_at?: string;
  authority?: string;
  runtime_evidence?: string;
  customer_code_executed?: boolean;
  external_llm_used?: boolean;
  source_sent_to_external_ai?: boolean;
  ruleset_version?: string;
  quality_gate_version?: string;
  infrastructure?: {
    format: string;
    files: number;
    analyzed_files: number;
    resources: number;
    parse_failures: number;
    maturity: string;
    authority: string;
    runtime_evidence: string;
    diagnostics: { path: string; code?: string; message?: string }[];
  }[];
  summary: {
    files_discovered?: number;
    source_files?: number;
    source_files_parsed?: number;
    source_analysis_percent?: number | null;
    states?: Record<string, number>;
  };
  languages: {
    language: string;
    files: number;
    loc: number;
    loc_unknown_files: number;
    parsed_files: number;
    maturity: string;
  }[];
  items: {
    path: string;
    language: string;
    analysis_state: string;
    parser_state: string;
    native_scan_performed: boolean;
    reason: string;
    loc: number | null;
    diagnostics: { code?: string; message?: string }[];
  }[];
  total: number;
  has_more?: boolean;
  limitations?: string[];
};

export default function EnterpriseTrust({
  role,
  compact = false,
  repository = "all",
}: {
  role: string;
  compact?: boolean;
  repository?: string;
}) {
  const admin = ["ORG_OWNER", "ADMIN"].includes(role);
  const queryClient = useQueryClient();
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);
  const [coverageState, setCoverageState] = useState("");
  const [coverageSearch, setCoverageSearch] = useState("");
  const [coverageOffset, setCoverageOffset] = useState(0);
  const [snapshot, setSnapshot] = useState("");
  const [snapshotOffset, setSnapshotOffset] = useState(0);
  useEffect(() => {
    setSnapshot("");
    setSnapshotOffset(0);
  }, [repository]);
  const snapshots = useQuery({
    queryKey: ["trust-snapshots", repository, snapshotOffset],
    queryFn: () =>
      api<{
        items: {
          id: string;
          branch: string;
          commit: string;
          analysis_at: string;
        }[];
        has_more: boolean;
      }>(
        "/trust/snapshots?" +
          new URLSearchParams({
            ...(repository.toUpperCase() !== "ALL"
              ? { repository_id: repository }
              : {}),
            offset: String(snapshotOffset),
          }),
      ),
    enabled: !compact,
  });
  useEffect(() => {
    setCoverageOffset(0);
  }, [repository, snapshot, coverageState, coverageSearch]);
  const coverage = useQuery({
    queryKey: [
      "analysis-coverage",
      repository,
      coverageState,
      coverageSearch,
      coverageOffset,
      snapshot,
    ],
    queryFn: () =>
      api<Coverage>(
        "/trust/coverage?" +
          new URLSearchParams({
            ...(repository.toUpperCase() !== "ALL"
              ? { repository_id: repository }
              : {}),
            ...(snapshot ? { snapshot_id: snapshot } : {}),
            state: coverageState,
            q: coverageSearch,
            offset: String(coverageOffset),
            limit: "50",
          }),
      ),
    enabled: !compact,
  });
  const controls = useQuery({
    queryKey: ["trust-policy"],
    queryFn: () => api<Policy>("/trust/policy"),
  });
  const capabilities = useQuery({
    queryKey: ["trust-capabilities"],
    queryFn: () => api<Registry>("/trust/capabilities"),
    enabled: !compact,
  });
  const audit = useQuery({
    queryKey: ["audit-integrity"],
    queryFn: () => api<Integrity>("/trust/audit-integrity"),
    enabled: admin,
  });
  const health = useQuery({
    queryKey: ["rule-health", repository],
    queryFn: () =>
      api<Health>(
        "/trust/rule-health" +
          (repository.toUpperCase() !== "ALL"
            ? `?repository_id=${encodeURIComponent(repository)}`
            : ""),
      ),
    enabled: !compact,
  });
  const oidc = useQuery({
    queryKey: ["oidc-options"],
    queryFn: () =>
      api<{ enabled: boolean; issuer?: string }>("/auth/oidc/options"),
  });
  async function save(
    key: "package_coordinate_advisories" | "github_check_metadata",
    enabled: boolean,
  ) {
    if (!controls.data || saving) return;
    const previous = controls.data;
    queryClient.setQueryData(["trust-policy"], { ...previous, [key]: enabled });
    setSaving(true);
    setMessage("");
    try {
      await api("/trust/policy", { ...previous, [key]: enabled });
      await controls.refetch();
      await audit.refetch();
      setMessage("Tenant policy saved and audited.");
    } catch (error) {
      queryClient.setQueryData(["trust-policy"], previous);
      void controls.refetch();
      setMessage(
        error instanceof Error ? error.message : "Could not save policy.",
      );
    } finally {
      setSaving(false);
    }
  }
  return (
    <div className="quality-module">
      <section className="settings-panel">
        <h2>Data &amp; AI Egress</h2>
        <p>
          Source stays inside this deployment. External AI is disabled. Package
          advisories and GitHub checks require separate tenant authorization.
        </p>
        {controls.isError ? (
          <p role="alert">Could not load tenant controls.</p>
        ) : !controls.data ? (
          <p role="status">Loading tenant controls…</p>
        ) : (
          <>
            <p>
              <strong>{controls.data.source_egress}</strong> · AI:{" "}
              {controls.data.ai_mode} · policy version {controls.data.version}
            </p>
            <div className="quality-form">
              <label>
                <input
                  type="checkbox"
                  checked={controls.data.package_coordinate_advisories}
                  disabled={!admin || saving}
                  onChange={(e) =>
                    void save("package_coordinate_advisories", e.target.checked)
                  }
                />
                Allow package coordinates to OSV (ecosystem, package name and
                version; no source)
              </label>
              <label>
                <input
                  type="checkbox"
                  checked={controls.data.github_check_metadata}
                  disabled={!admin || saving}
                  onChange={(e) =>
                    void save("github_check_metadata", e.target.checked)
                  }
                />
                Allow advisory GitHub check summaries (system policy names and
                result states; no source excerpts)
              </label>
            </div>
            <p>
              Maximum exception duration: {controls.data.maximum_exception_days}{" "}
              days. Administrators manage this organization policy.
            </p>
          </>
        )}
        {message && <p role="status">{message}</p>}
        <p>
          OIDC:{" "}
          {oidc.data?.enabled
            ? `Configured · ${oidc.data.issuer} · explicit subject membership`
            : "Not configured on this deployment"}
          . No automatic membership from email domains.
        </p>
      </section>
      {admin && (
        <section className="settings-panel">
          <h2>Audit integrity</h2>
          {audit.isError ? (
            <p role="alert">Could not verify the audit chain.</p>
          ) : (
            <>
              <p>
                {audit.data?.state || "Checking…"} ·{" "}
                {audit.data?.linked_events ?? 0} linked events ·{" "}
                {audit.data?.legacy_unlinked_events ?? 0} legacy unlinked events
              </p>
              <p>
                {audit.data?.checkpoint
                  ? "An operator-keyed checkpoint is available."
                  : "Signed checkpoint key is not configured."}{" "}
                Immutable archival is unconfigured.
              </p>
              <button onClick={() => void audit.refetch()}>
                Verify audit chain
              </button>
              {audit.data?.checkpoint != null && (
                <button
                  onClick={() => {
                    const url = URL.createObjectURL(
                      new Blob([JSON.stringify(audit.data, null, 2)], {
                        type: "application/json",
                      }),
                    );
                    const anchor = document.createElement("a");
                    anchor.href = url;
                    anchor.download = "projecttrace-audit-checkpoint.json";
                    anchor.click();
                    URL.revokeObjectURL(url);
                  }}
                >
                  Download checkpoint
                </button>
              )}
              {audit.data?.limitations.map((text) => (
                <p key={text}>{text}</p>
              ))}
            </>
          )}
        </section>
      )}
      {admin && compact && <OIDCAdministration role={role} />}
      {admin && compact && <SCMConnections />}
      {!compact && (
        <>
          <section className="settings-panel">
            <h2>Captured analysis coverage</h2>
            <label>
              Analysis snapshot
              <select
                value={snapshot}
                onChange={(e) => setSnapshot(e.target.value)}
              >
                <option value="">Latest authorized snapshot</option>
                {snapshots.data?.items.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.branch} · {s.commit.slice(0, 12)} · {s.analysis_at}
                  </option>
                ))}
              </select>
            </label>
            <button
              disabled={!snapshotOffset}
              onClick={() => {
                setSnapshot("");
                setSnapshotOffset(Math.max(0, snapshotOffset - 50));
              }}
            >
              Newer snapshots
            </button>
            <button
              disabled={!snapshots.data?.has_more}
              onClick={() => {
                setSnapshot("");
                setSnapshotOffset(snapshotOffset + 50);
              }}
            >
              Older snapshots
            </button>
            {snapshots.isError && (
              <p role="alert">Could not load snapshot choices.</p>
            )}
            {coverage.isError ? (
              <p role="alert">Could not load analysis coverage.</p>
            ) : coverage.isLoading ? (
              <p>Loading captured coverage…</p>
            ) : (
              <>
                <p>
                  {coverage.data?.state} ·{" "}
                  {coverage.data?.repository_id || "No analyzed repository"} ·{" "}
                  {coverage.data?.branch} · {coverage.data?.commit}
                </p>
                <p>
                  Snapshot {coverage.data?.snapshot_id || "Not available"} ·
                  analyzer {coverage.data?.analyzer_version || "Not available"}{" "}
                  · profile {coverage.data?.profile_version ?? "Not available"}{" "}
                  · job {coverage.data?.job_id || "Not available"}
                </p>
                <p>
                  Analysis timestamp{" "}
                  {coverage.data?.analysis_at || "Not available"} · ruleset{" "}
                  {coverage.data?.ruleset_version || "Not available"} · Quality
                  Gate version{" "}
                  {coverage.data?.quality_gate_version || "Not available"}
                </p>
                <p>
                  {coverage.data?.summary.files_discovered ?? 0} discovered
                  files · {coverage.data?.summary.source_files_parsed ?? 0} /{" "}
                  {coverage.data?.summary.source_files ?? 0} source files parsed
                  · analysis coverage{" "}
                  {coverage.data?.summary.source_analysis_percent == null
                    ? "Not available"
                    : `${coverage.data.summary.source_analysis_percent}%`}
                </p>
                <p>
                  {coverage.data?.authority || "Authority not measured"}.
                  Runtime evidence:{" "}
                  {coverage.data?.runtime_evidence || "Not measured"}. Customer
                  code executed:{" "}
                  {coverage.data?.customer_code_executed === false
                    ? "NO"
                    : coverage.data?.customer_code_executed === true
                      ? "YES"
                      : "Not measured"}
                  . External LLM used:{" "}
                  {coverage.data?.external_llm_used === false
                    ? "NO"
                    : coverage.data?.external_llm_used === true
                      ? "YES"
                      : "Not measured"}
                  . Source sent to external AI:{" "}
                  {coverage.data?.source_sent_to_external_ai === false
                    ? "NO"
                    : coverage.data?.source_sent_to_external_ai === true
                      ? "YES"
                      : "Not measured"}
                  .
                </p>
                <p>
                  {Object.entries(coverage.data?.summary.states || {})
                    .map(([state, count]) => `${state}: ${count}`)
                    .join(" · ")}
                </p>
                <div
                  className="quality-table-wrap"
                  tabIndex={0}
                  role="region"
                  aria-label="Captured language inventory"
                >
                  <table className="quality-table">
                    <thead>
                      <tr>
                        <th>Language / format</th>
                        <th>Files</th>
                        <th>Parsed</th>
                        <th>LOC</th>
                        <th>Maturity</th>
                      </tr>
                    </thead>
                    <tbody>
                      {coverage.data?.languages.map((row) => (
                        <tr key={row.language}>
                          <td>{row.language}</td>
                          <td>{row.files}</td>
                          <td>{row.parsed_files}</td>
                          <td>
                            {row.loc}
                            {row.loc_unknown_files
                              ? ` + ${row.loc_unknown_files} unknown files`
                              : ""}
                          </td>
                          <td>{row.maturity}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="quality-form">
                  <label>
                    Find a file
                    <input
                      value={coverageSearch}
                      onChange={(e) => setCoverageSearch(e.target.value)}
                    />
                  </label>
                  <label>
                    Analysis state
                    <select
                      value={coverageState}
                      onChange={(e) => setCoverageState(e.target.value)}
                    >
                      <option value="">All states</option>
                      {[
                        "PARTIAL",
                        "UNSUPPORTED",
                        "PARSE_FAILED",
                        "EXCLUDED_GENERATED",
                        "EXCLUDED_VENDOR",
                        "SKIPPED_SIZE_LIMIT",
                        "BINARY",
                        "IGNORED_BY_POLICY",
                      ].map((state) => (
                        <option key={state}>{state}</option>
                      ))}
                    </select>
                  </label>
                </div>
                <p>
                  {coverage.data?.total || 0} matching files. A completed parser
                  does not establish complete semantic or security coverage.
                </p>
                <div
                  className="quality-table-wrap"
                  tabIndex={0}
                  role="region"
                  aria-label="Captured file states"
                >
                  <table className="quality-table">
                    <thead>
                      <tr>
                        <th>File</th>
                        <th>State</th>
                        <th>Parser</th>
                        <th>Reason / diagnostics</th>
                      </tr>
                    </thead>
                    <tbody>
                      {coverage.data?.items.map((row) => (
                        <tr key={row.path}>
                          <td>
                            {row.path}
                            <small>{row.language}</small>
                          </td>
                          <td>{row.analysis_state}</td>
                          <td>{row.parser_state}</td>
                          <td>
                            {row.reason}
                            {row.diagnostics.map((d, i) => (
                              <p key={i}>
                                {d.code} · {d.message}
                              </p>
                            ))}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <button
                  disabled={!coverageOffset}
                  onClick={() =>
                    setCoverageOffset(Math.max(0, coverageOffset - 50))
                  }
                >
                  Previous files
                </button>
                <button
                  disabled={!coverage.data?.has_more}
                  onClick={() => setCoverageOffset(coverageOffset + 50)}
                >
                  Next files
                </button>
                {coverage.data?.limitations?.map((text) => (
                  <p key={text}>{text}</p>
                ))}
              </>
            )}
          </section>
          <section className="settings-panel">
            <h2>Captured infrastructure coverage</h2>
            <p>
              Five supported static formats have partial semantic maturity. This
              inventory belongs to the selected analysis snapshot.
            </p>
            <div
              className="quality-table-wrap"
              tabIndex={0}
              role="region"
              aria-label="Infrastructure format coverage"
            >
              <table className="quality-table">
                <thead>
                  <tr>
                    <th>Format</th>
                    <th>Files / analyzed</th>
                    <th>Resources</th>
                    <th>Parser failures</th>
                    <th>Authority / maturity</th>
                  </tr>
                </thead>
                <tbody>
                  {coverage.data?.infrastructure?.map((row) => (
                    <tr key={row.format}>
                      <td>{row.format}</td>
                      <td>
                        {row.files} / {row.analyzed_files}
                      </td>
                      <td>{row.resources}</td>
                      <td>{row.parse_failures}</td>
                      <td>
                        {row.authority} · {row.maturity}
                        <small>Runtime: {row.runtime_evidence}</small>
                        {row.diagnostics.map((d, i) => (
                          <p key={i}>
                            {d.path} · {d.code} · {d.message}
                          </p>
                        ))}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!coverage.data?.infrastructure && (
              <p>
                Infrastructure format measurements are unavailable for this
                legacy snapshot. Run a new analysis to capture them.
              </p>
            )}
          </section>
          <TrustExceptions repository={repository} role={role} />
          <section className="settings-panel">
            <h2>Language &amp; parser coverage</h2>
            <p>
              Version {capabilities.data?.version}. Syntax support does not
              establish complete framework, flow or security coverage.
            </p>
            {capabilities.isError && (
              <p role="alert">Could not load capability registry.</p>
            )}
            <div
              className="quality-table-wrap"
              tabIndex={0}
              role="region"
              aria-label="Capability registry"
            >
              <table className="quality-table trust-capability-table">
                <thead>
                  <tr>
                    {[
                      "Language",
                      "Parser",
                      "Maturity",
                      "Quality",
                      "Security",
                      "Flow",
                      "Precision",
                    ].map((label) => (
                      <th key={label}>{label}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {capabilities.data?.languages.map((row) => (
                    <tr key={row.language}>
                      <td>{row.language}</td>
                      <td>
                        {row.parser} · {row.parser_version}
                        {row.grammar_version
                          ? ` / grammar ${row.grammar_version}`
                          : ""}
                      </td>
                      <td>{row.maturity}</td>
                      <td>{row.quality}</td>
                      <td>{row.sast}</td>
                      <td>{row.flow}</td>
                      <td>{row.precision}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p>{capabilities.data?.unsupported}</p>
            <p>{capabilities.data?.parser_isolation}</p>
            <p>{capabilities.data?.rule_blocking}</p>
            <p>
              Larger repositories use encrypted inventories and bounded parser
              partitions. Local synthetic benchmarks describe owned fixtures;
              production repository and concurrent-PR capacity remain
              unmeasured. Live OIDC/GHES and managed-service restore and key
              rotation validation remain outstanding.
            </p>
          </section>
          <section className="settings-panel">
            <h2>Rule feedback</h2>
            <h3>Labeled analyzer evaluation</h3>
            <p>
              {health.data?.validation?.state || "Not available"} ·{" "}
              {health.data?.validation?.case_count ?? 0} labeled cases ·
              production precision{" "}
              {health.data?.validation?.production_precision || "UNMEASURED"}.
              Small selected corpora do not establish a universal accuracy
              score.
            </p>
            <div
              className="quality-table-wrap"
              tabIndex={0}
              role="region"
              aria-label="Labeled accuracy by rule"
            >
              <table className="quality-table">
                <thead>
                  <tr>
                    {[
                      "Domain / rule",
                      "Language / framework",
                      "Tier",
                      "TP / TN",
                      "FP / FN",
                      "Precision / recall",
                    ].map((label) => (
                      <th key={label}>{label}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {health.data?.validation?.groups.map((row, i) => (
                    <tr key={row.rule + i}>
                      <td>
                        {row.domain}
                        <small>{row.rule}</small>
                      </td>
                      <td>
                        {row.language}
                        <small>{row.framework}</small>
                      </td>
                      <td>{row.tier}</td>
                      <td>
                        {row.tp} / {row.tn}
                      </td>
                      <td>
                        {row.fp} / {row.fn}
                      </td>
                      <td>
                        {row.precision == null
                          ? "Not measured"
                          : row.precision.toFixed(3)}{" "}
                        /{" "}
                        {row.recall == null
                          ? "Not measured"
                          : row.recall.toFixed(3)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {health.data?.validation?.limitations.map((text) => (
              <p key={text}>{text}</p>
            ))}
            <h3>Human review feedback</h3>
            <p>
              Latest confirmed/dismissed judgments per reviewed occurrence,
              scoped to repositories you can access. This is feedback, not an
              accuracy benchmark.
            </p>
            {health.isError && (
              <p role="alert">Could not load rule feedback.</p>
            )}
            {health.data && !health.data.groups.length && (
              <p>No versioned rule judgments in your authorized scope.</p>
            )}
            {health.data?.groups.map((row) => (
              <p key={`${row.rule}:${row.rule_version}:${row.language}`}>
                {row.rule} · {row.rule_version} · {row.language}:{" "}
                {row.dismissed} dismissals / {row.reviewed_occurrences} reviewed
                occurrences · precision {row.precision}
              </p>
            ))}
            {health.data?.limitations.map((text) => (
              <p key={text}>{text}</p>
            ))}
            {health.data?.truncated && (
              <p>
                Feedback window is limited to the latest 20,000 review events.
              </p>
            )}
          </section>
        </>
      )}
    </div>
  );
}
