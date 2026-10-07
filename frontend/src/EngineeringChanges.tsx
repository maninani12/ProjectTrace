import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
import type { Item } from "./api";

type Change = {
  id: string;
  component: string;
  owner: string;
  at: string;
  branch: string;
  commit: string;
  base_snapshot_id: string;
  head_snapshot_id: string;
  pr_number?: number;
  priority: number;
  priority_factors: { reason: string; weight: number }[];
  counts: Record<string, number>;
  analysis_model_changed: boolean;
  total_changes: number;
};
type Detail = Change & {
  actor: string;
  actor_basis: string;
  files: string[];
  authority: string;
  runtime_evidence: string;
  captured_gate?: { overall: string; mode: string };
  linked_record_ids: string[];
  links_truncated: boolean;
  truncated: boolean;
  limitations: string[];
  changes: {
    category: string;
    label: string;
    before: unknown;
    after: unknown;
    reason: string;
    authority: string;
    target_id?: string;
    path?: string;
    comparison_basis?: string;
  }[];
  impact: {
    affected_claims?: string[];
    affected_documentation?: string[];
    affected_architecture?: string[];
  };
};

function value(v: unknown): string {
  return v == null
    ? "Not observed"
    : typeof v === "object"
      ? JSON.stringify(v)
      : String(v);
}

export default function EngineeringChanges({
  repository,
  onOpen,
}: {
  repository: string;
  onOpen: (item: Item) => void;
}) {
  const [days, setDays] = useState(7);
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState("");
  const [message, setMessage] = useState("");
  useEffect(() => {
    setOffset(0);
    setSelected("");
  }, [repository, days]);
  const list = useQuery({
    queryKey: ["engineering-changes", repository, days, offset],
    queryFn: () =>
      api<{ total: number; has_more: boolean; items: Change[] }>(
        "/engineering-changes?" +
          new URLSearchParams({
            ...(repository.toUpperCase() !== "ALL"
              ? { repository_id: repository }
              : {}),
            days: String(days),
            offset: String(offset),
            limit: "25",
          }),
      ),
  });
  const detail = useQuery({
    queryKey: ["engineering-change", selected],
    queryFn: () => api<Detail>(`/engineering-changes/${selected}`),
    enabled: !!selected,
  });
  async function inspect(id: string) {
    setMessage("");
    try {
      onOpen(await api<Item>(`/record/${id}`));
    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : "Linked evidence could not be loaded.",
      );
    }
  }
  return (
    <div className="quality-module">
      <section className="settings-panel">
        <h2>Engineering Changes</h2>
        <p>
          Review important BASE-to-HEAD correlations across claims,
          implementation, documentation, quality, security, dependencies,
          infrastructure and policy.
        </p>
        <label>
          Time window
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
          >
            <option value={7}>Last 7 days</option>
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
            <option value={365}>Last year</option>
          </select>
        </label>
        {list.isLoading ? (
          <p>Loading engineering changes…</p>
        ) : list.isError ? (
          <p role="alert">Could not load engineering changes.</p>
        ) : (
          <>
            <p>
              {list.data?.total || 0} captured comparisons in this scope.
              Priority uses visible deterministic factors.
            </p>
            {!list.data?.total && (
              <p>
                No engineering changes captured in this window. Analyze a new
                snapshot with an explicit BASE. An initial import establishes
                the baseline.
              </p>
            )}
            {list.data?.items.map((change) => (
              <article key={change.id} className="settings-panel">
                <h3>
                  {change.component || "Repository change"} · {change.branch}
                </h3>
                <p>
                  {change.pr_number ? `PR #${change.pr_number} · ` : ""}
                  {change.commit.slice(0, 12)} · {change.at} · Owner:{" "}
                  {change.owner || "Unassigned"}
                </p>
                <p>
                  {Object.entries(change.counts)
                    .map(
                      ([category, count]) =>
                        `${category.replaceAll("_", " ")}: ${count}`,
                    )
                    .join(" · ")}
                </p>
                {change.analysis_model_changed && (
                  <p>
                    Analyzer re-evaluation: classification differences cannot be
                    attributed solely to source changes.
                  </p>
                )}
                <ul>
                  {change.priority_factors.map((factor, i) => (
                    <li key={i}>
                      {factor.reason} · priority weight {factor.weight}
                    </li>
                  ))}
                </ul>
                <button onClick={() => setSelected(change.id)}>
                  Inspect engineering change
                </button>
              </article>
            ))}
            <button
              disabled={!offset}
              onClick={() => setOffset(Math.max(0, offset - 25))}
            >
              Previous changes
            </button>
            <button
              disabled={!list.data?.has_more}
              onClick={() => setOffset(offset + 25)}
            >
              Next changes
            </button>
          </>
        )}
      </section>
      {selected && (
        <section
          className="settings-panel"
          aria-label="Engineering change details"
        >
          <h2>Change evidence</h2>
          {detail.isLoading ? (
            <p>Loading captured comparison…</p>
          ) : detail.isError ? (
            <p role="alert">Comparison unavailable in authorized scope.</p>
          ) : (
            detail.data && (
              <>
                <p>
                  BASE {detail.data.base_snapshot_id} → HEAD{" "}
                  {detail.data.head_snapshot_id}
                </p>
                <p>
                  Captured gate:{" "}
                  {detail.data.captured_gate?.overall || "Not available"} ·{" "}
                  {detail.data.captured_gate?.mode}
                </p>
                <p>
                  {detail.data.authority} · Runtime:{" "}
                  {detail.data.runtime_evidence} · Analysis initiated by{" "}
                  {detail.data.actor}. Commit authorship is unobserved.
                </p>
                <p>
                  {detail.data.files.length} changed file paths ·{" "}
                  {detail.data.impact.affected_claims?.length || 0} affected
                  claims ·{" "}
                  {detail.data.impact.affected_documentation?.length || 0}{" "}
                  affected documentation nodes ·{" "}
                  {detail.data.impact.affected_architecture?.length || 0}{" "}
                  affected architecture nodes.
                </p>
                <details>
                  <summary>Changed files</summary>
                  <ul>
                    {detail.data.files.map((path) => (
                      <li key={path}>{path}</li>
                    ))}
                  </ul>
                </details>
                <div
                  className="quality-table-wrap"
                  tabIndex={0}
                  role="region"
                  aria-label="Correlated engineering observations"
                >
                  <table className="quality-table">
                    <thead>
                      <tr>
                        <th>Category / target</th>
                        <th>Before</th>
                        <th>After</th>
                        <th>Why / authority</th>
                        <th>Evidence</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detail.data.changes.map((change, i) => (
                        <tr key={i}>
                          <td>
                            {change.category}
                            <small>{change.label}</small>
                            <small>{change.path}</small>
                          </td>
                          <td>{value(change.before)}</td>
                          <td>{value(change.after)}</td>
                          <td>
                            {change.reason}
                            <small>
                              {change.authority} ·{" "}
                              {change.comparison_basis ||
                                "EXPLICIT BASE / HEAD"}
                            </small>
                          </td>
                          <td>
                            {change.target_id ? (
                              <button
                                onClick={() => void inspect(change.target_id!)}
                              >
                                Inspect evidence
                              </button>
                            ) : (
                              "See affected graph records below"
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {detail.data.truncated && (
                  <p>
                    Showing 500 of {detail.data.total_changes} observations.
                    Counts include the full captured comparison.
                  </p>
                )}
                <details>
                  <summary>
                    Existing impact graph records (
                    {detail.data.linked_record_ids.length})
                  </summary>
                  {detail.data.linked_record_ids.map((id) => (
                    <button key={id} onClick={() => void inspect(id)}>
                      Inspect {id}
                    </button>
                  ))}
                  {detail.data.links_truncated && (
                    <p>
                      Record links are bounded to 500; the full graph remains
                      available in Evidence Graph.
                    </p>
                  )}
                </details>
                {detail.data.limitations.map((text) => (
                  <p key={text}>{text}</p>
                ))}
              </>
            )
          )}
          <button onClick={() => setSelected("")}>Close change</button>
          {message && <p role="alert">{message}</p>}
        </section>
      )}
    </div>
  );
}
