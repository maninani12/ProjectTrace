import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";

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

export default function EnterpriseTrust({
  role,
  compact = false,
}: {
  role: string;
  compact?: boolean;
}) {
  const admin = ["ORG_OWNER", "ADMIN"].includes(role);
  const queryClient = useQueryClient();
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);
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
    queryKey: ["rule-health"],
    queryFn: () => api<Health>("/trust/rule-health"),
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
      {!compact && (
        <>
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
              Three-million-line repositories: unsupported by current intake
              limits. One hundred concurrent PRs: UNMEASURED. Live OIDC/GHES,
              managed-key rotation and production restore validation remain
              outstanding.
            </p>
          </section>
          <section className="settings-panel">
            <h2>Rule feedback</h2>
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
