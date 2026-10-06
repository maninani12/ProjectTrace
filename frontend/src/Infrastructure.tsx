import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
import type { Item } from "./api";
import NativeProfiles from "./NativeProfiles";

type Resource = Item & {
  format?: string;
  identity: string;
  asset_kind: string;
  runtime_observed: boolean;
  final_stage?: boolean;
  end_line?: number;
};
type Report = {
  resources: Resource[];
  findings: (Item & { infrastructure_format?: string })[];
  format_counts: Record<string, number>;
  has_more_resources: boolean;
  has_more_findings: boolean;
  scope_truncated: boolean;
  limitations: string[];
  coverage: {
    snapshot_id: string;
    repository_id: string;
    engine: { state?: string; supported_files?: number };
    diagnostics: { path: string; code: string; message: string }[];
  }[];
};
const tabs = [
  "Overview",
  "Findings",
  "Resources",
  "Terraform",
  "CloudFormation",
  "Kubernetes",
  "Compose",
  "Dockerfile",
  "Rules & Profiles",
  "Coverage",
];
export default function Infrastructure({
  repository,
  role,
  onOpen,
}: {
  repository: string;
  role: string;
  onOpen: (item: Item) => void;
}) {
  const [tab, setTab] = useState("Overview");
  const [offset, setOffset] = useState(0);
  useEffect(() => setOffset(0), [repository, tab]);
  const suffix = new URLSearchParams({ offset: String(offset), limit: "100" });
  if (repository !== "ALL") suffix.set("repository_id", repository);
  const format = tab.toUpperCase();
  const formatted = [
    "TERRAFORM",
    "CLOUDFORMATION",
    "KUBERNETES",
    "COMPOSE",
    "DOCKERFILE",
  ].includes(format);
  if (formatted) suffix.set("format", format);
  const report = useQuery({
    queryKey: [
      "infrastructure",
      repository,
      offset,
      formatted ? format : "ALL",
    ],
    queryFn: () => api<Report>("/trust/infrastructure?" + suffix),
  });
  const resources = (report.data?.resources || []).filter(
    (row) => !formatted || row.format === format,
  );
  const findings = (report.data?.findings || []).filter(
    (row) => !formatted || row.infrastructure_format === format,
  );
  return (
    <div className="quality-module">
      <p className="context-note">
        STATIC · declared configuration · runtime unobserved. Templates, builds,
        remote modules and source commands are never executed.
      </p>
      {report.data?.scope_truncated && (
        <p role="note">
          This view is limited to 200 authorized repository snapshots. Choose a
          repository to inspect its complete bounded inventory.
        </p>
      )}
      <nav className="quality-tabs" aria-label="Infrastructure views">
        {tabs.map((name) => (
          <button
            key={name}
            className={tab === name ? "active" : ""}
            aria-pressed={tab === name}
            onClick={() => setTab(name)}
          >
            {name}
          </button>
        ))}
      </nav>
      {report.isError ? (
        <p role="alert" className="error">
          Could not load infrastructure evidence: {report.error.message}
        </p>
      ) : report.isPending ? (
        <p role="status">Loading infrastructure evidence…</p>
      ) : (
        <>
          {tab === "Overview" && (
            <section className="settings-panel">
              <h2>Native infrastructure inventory</h2>
              <p>
                Latest captured snapshot per authorized repository. Unsupported
                or unresolved configuration remains a coverage gap.
              </p>
              <div className="stats compact">
                {Object.entries(report.data.format_counts).map(
                  ([name, count]) => (
                    <div key={name}>
                      <strong>{count}</strong>
                      <span>{name} configuration declarations</span>
                    </div>
                  ),
                )}
              </div>
              {report.data.limitations.map((text) => (
                <p key={text}>{text}</p>
              ))}
            </section>
          )}
          {(tab === "Findings" || formatted) && (
            <section>
              <h2>
                {formatted ? `${tab} findings` : "Infrastructure findings"}
              </h2>
              {!findings.length ? (
                <p>
                  No matching findings on this page. Inspect coverage before
                  interpreting this result.
                </p>
              ) : (
                <div
                  className="quality-table-wrap"
                  role="region"
                  aria-label="Infrastructure findings table"
                  tabIndex={0}
                >
                  <table className="quality-table">
                    <thead>
                      <tr>
                        <th>Finding</th>
                        <th>Rule</th>
                        <th>Location</th>
                        <th>Authority</th>
                      </tr>
                    </thead>
                    <tbody>
                      {findings.map((row) => (
                        <tr key={row.id}>
                          <td>
                            <button onClick={() => onOpen(row)}>
                              {row.title}
                            </button>
                            <p>
                              {row.severity} · {row.review_status}
                            </p>
                          </td>
                          <td>
                            {row.rule}
                            <p>{row.rule_version}</p>
                          </td>
                          <td>
                            {row.path}:{row.line}
                          </td>
                          <td>STATIC · hotspot</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          )}
          {(tab === "Resources" || formatted) && (
            <section>
              <h2>{formatted ? `${tab} resources` : "Declared resources"}</h2>
              {!resources.length ? (
                <p>No matching configuration declarations on this page.</p>
              ) : (
                <div
                  className="quality-table-wrap"
                  role="region"
                  aria-label="Infrastructure resources table"
                  tabIndex={0}
                >
                  <table className="quality-table">
                    <thead>
                      <tr>
                        <th>Resource</th>
                        <th>Kind / format</th>
                        <th>Location</th>
                        <th>Declared state</th>
                      </tr>
                    </thead>
                    <tbody>
                      {resources.map((row) => (
                        <tr key={row.id}>
                          <td>
                            <button onClick={() => onOpen(row)}>
                              {row.identity}
                            </button>
                          </td>
                          <td>
                            {row.asset_kind}
                            <p>
                              {row.format || "LEGACY_UNKNOWN"}
                              {row.final_stage ? " · final stage" : ""}
                            </p>
                          </td>
                          <td>
                            {row.path}:{row.line}–{row.end_line || row.line}
                          </td>
                          <td>
                            {row.public || "UNKNOWN"}
                            <p>
                              Encryption: {row.encryption || "UNKNOWN"} ·
                              runtime unobserved
                            </p>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          )}
          {tab === "Coverage" && (
            <section className="settings-panel">
              <h2>Infrastructure coverage</h2>
              {!report.data.coverage.length && (
                <p>
                  Import and analyze configuration to establish a coverage
                  record.
                </p>
              )}
              {report.data.coverage.map((row) => (
                <div key={row.snapshot_id}>
                  <h3>{row.repository_id}</h3>
                  <p>
                    {row.engine.state || "NOT_AVAILABLE"} ·{" "}
                    {row.engine.supported_files || 0} captured configuration
                    files · snapshot {row.snapshot_id}
                  </p>
                  {row.diagnostics.map((item, index) => (
                    <p key={index}>
                      {item.path} · {item.code}: {item.message}
                    </p>
                  ))}
                </div>
              ))}
            </section>
          )}
          {tab === "Rules & Profiles" && (
            <NativeProfiles repository={repository} role={role} />
          )}
          {(tab === "Findings" || tab === "Resources" || formatted) && (
            <div className="quality-pagination">
              <button
                disabled={!offset}
                onClick={() => setOffset(Math.max(0, offset - 100))}
              >
                Previous page
              </button>
              <span>
                Evidence page {offset / 100 + 1}; format filtering is enforced
                by the server before paging.
              </span>
              <button
                disabled={
                  !report.data.has_more_findings &&
                  !report.data.has_more_resources
                }
                onClick={() => setOffset(offset + 100)}
              >
                Next page
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
