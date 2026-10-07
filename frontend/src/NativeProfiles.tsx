import { useEffect, useLayoutEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
import ComponentAssignments from "./ComponentAssignments";
import InfrastructurePolicy, {
  defaultInfrastructure,
  type InfrastructureSettings,
} from "./InfrastructurePolicy";

type Rule = {
  id: string;
  category: string;
  title: string;
  default_severity: string;
  remediation: string;
  version: string;
  languages: string[];
  example: { trigger: string; remedy: string };
};
type Profile = {
  version: number;
  rules: Record<string, { enabled?: boolean; severity?: string }>;
  licenses: { approved?: string[]; restricted?: string[] };
  gate_scope?: string;
  infrastructure?: InfrastructureSettings;
};

export default function NativeProfiles({
  repository,
  role,
}: {
  repository: string;
  role: string;
}) {
  const [message, setMessage] = useState("");
  const [selected, setSelected] = useState("");
  const [severity, setSeverity] = useState("HIGH");
  const [gateScope, setGateScope] = useState("ALL_FINDINGS");
  const [approved, setApproved] = useState("");
  const [restricted, setRestricted] = useState("");
  const [busy, setBusy] = useState(false);
  const [infrastructure, setInfrastructure] = useState(defaultInfrastructure);
  const rules = useQuery({
    queryKey: ["native-rules"],
    queryFn: () => api<{ rules: Rule[] }>("/native/rules"),
  });
  const suffix =
    repository === "ALL"
      ? ""
      : `?repository_id=${encodeURIComponent(repository)}`;
  const profile = useQuery({
    queryKey: ["native-profile", repository],
    queryFn: () => api<Profile>("/native/profile" + suffix),
  });
  const canEdit = ["ORG_OWNER", "ADMIN"].includes(role);
  useLayoutEffect(() => {
    setGateScope(profile.data?.gate_scope || "ALL_FINDINGS");
    setApproved(profile.data?.licenses.approved?.join(", ") || "");
    setRestricted(profile.data?.licenses.restricted?.join(", ") || "");
    setInfrastructure({
      ...defaultInfrastructure,
      ...profile.data?.infrastructure,
    });
  }, [repository, profile.data]);
  useEffect(() => setMessage(""), [repository]);
  const selectedRule = rules.data?.rules.find((rule) => rule.id === selected);
  async function save(enabled?: boolean) {
    if (!profile.data || (enabled !== undefined && !selected)) return;
    setBusy(true);
    try {
      await api("/native/profile", {
        repository_id: repository === "ALL" ? null : repository,
        version: profile.data.version,
        rules:
          enabled === undefined
            ? profile.data.rules
            : { ...profile.data.rules, [selected]: { enabled, severity } },
        licenses: {
          approved: approved
            .split(",")
            .map((value) => value.trim())
            .filter(Boolean),
          restricted: restricted
            .split(",")
            .map((value) => value.trim())
            .filter(Boolean),
        },
        gate_scope: gateScope,
        infrastructure,
      });
      await profile.refetch();
      setMessage(
        "Profile saved. Analyze a new snapshot to apply these settings; previous snapshots retain their profile.",
      );
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "Profile could not be saved.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="settings-panel">
      <h2>Native rule profiles</h2>
      <p>
        {repository === "ALL"
          ? "Organization defaults"
          : "Repository overrides"}{" "}
        · version {profile.data?.version ?? 0}. Every snapshot records the
        profile used.
      </p>
      {rules.isError || profile.isError ? (
        <p className="error">Could not load native profiles.</p>
      ) : (
        <>
          <label>
            Rule{" "}
            <select
              aria-label="Native rule"
              value={selected}
              onChange={(e) => setSelected(e.target.value)}
            >
              <option value="">Select a native rule</option>
              {rules.data?.rules.map((rule) => (
                <option key={rule.id} value={rule.id}>
                  {rule.id} · {rule.category} · {rule.title}
                </option>
              ))}
            </select>
          </label>
          {selectedRule && (
            <div>
              <p>
                {selectedRule.remediation} · {selectedRule.languages.join(", ")}
              </p>
              <p>
                <code>{selectedRule.example.trigger}</code>
              </p>
            </div>
          )}
          {canEdit ? (
            <div className="filters">
              <select
                aria-label="Rule severity"
                value={severity}
                onChange={(e) => setSeverity(e.target.value)}
              >
                {["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"].map((value) => (
                  <option key={value}>{value}</option>
                ))}
              </select>
              <button
                className="secondary"
                disabled={!selected || !profile.data || busy}
                onClick={() => save(true)}
              >
                Enable rule
              </button>
              <button
                className="secondary"
                disabled={!selected || !profile.data || busy}
                onClick={() => save(false)}
              >
                Disable rule
              </button>
            </div>
          ) : (
            <p>
              Organization administrators manage profiles. You can inspect rule
              coverage and remedies.
            </p>
          )}
          <label>
            Gate scope{" "}
            <select
              aria-label="Native gate scope"
              value={gateScope}
              disabled={!canEdit || !profile.data || busy}
              onChange={(event) => setGateScope(event.target.value)}
            >
              <option value="ALL_FINDINGS">All findings</option>
              <option value="NEW_FINDINGS">New findings</option>
            </select>
          </label>
          <p>
            New findings exclude unchanged legacy issues and analyzer-only
            baseline changes. Claim contradictions still require review.
          </p>
          <label>
            Approved SPDX identifiers (comma separated){" "}
            <input
              aria-label="Approved licenses"
              value={approved}
              disabled={!canEdit || !profile.data || busy}
              maxLength={7000}
              onChange={(event) => setApproved(event.target.value)}
            />
          </label>
          <label>
            Restricted SPDX identifiers (comma separated){" "}
            <input
              aria-label="Restricted licenses"
              value={restricted}
              disabled={!canEdit || !profile.data || busy}
              maxLength={7000}
              onChange={(event) => setRestricted(event.target.value)}
            />
          </label>
          <InfrastructurePolicy
            value={infrastructure}
            onChange={setInfrastructure}
            disabled={!canEdit || !profile.data || busy}
            selectedRule={selected}
          />
          {canEdit && (
            <button
              className="secondary"
              disabled={!profile.data || busy}
              onClick={() => save()}
            >
              {busy
                ? "Saving…"
                : "Save gate, license and infrastructure policy"}
            </button>
          )}
          {message && <p role="status">{message}</p>}
        </>
      )}
      <ComponentAssignments repository={repository} canEdit={canEdit} />
    </section>
  );
}
