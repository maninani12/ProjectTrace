import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";

type Exception = {
  id: string;
  version: number;
  target: string;
  owner: string;
  approver: string;
  reason: string;
  expires_at: string;
  state: string;
  identity_id?: string;
};

export default function TrustExceptions({
  repository,
  role,
}: {
  repository: string;
  role: string;
}) {
  const [offset, setOffset] = useState(0);
  const [filter, setFilter] = useState("");
  const [selected, setSelected] = useState<Exception | null>(null);
  const [reason, setReason] = useState("");
  const [days, setDays] = useState(7);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const cache = useQueryClient();
  useEffect(() => {
    setOffset(0);
    setSelected(null);
  }, [repository, filter]);
  const query = useQuery({
    queryKey: ["trust-exceptions", repository, offset, filter],
    queryFn: () =>
      api<{
        items: Exception[];
        total: number;
        has_more: boolean;
        basis: string;
      }>(
        "/trust/exceptions?" +
          new URLSearchParams({
            ...(repository.toUpperCase() !== "ALL"
              ? { repository_id: repository }
              : {}),
            ...(filter ? { state: filter } : {}),
            offset: String(offset),
            limit: "50",
          }),
      ),
  });
  async function change(action: "EXTEND" | "REVOKED") {
    if (!selected) return;
    setBusy(true);
    setMessage("");
    try {
      await api(`/trust/exceptions/${selected.id}`, {
        expected_version: selected.version,
        action: action === "REVOKED" ? "REVOKE" : action,
        reason,
        days,
      });
      setSelected(null);
      setReason("");
      await cache.invalidateQueries({ queryKey: ["trust-exceptions"] });
      await cache.invalidateQueries({ queryKey: ["audit-integrity"] });
      setMessage(
        "Exception updated and audited. Gate eligibility is rechecked against the current issue context.",
      );
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "Could not update exception.",
      );
    } finally {
      setBusy(false);
    }
  }
  const privileged = ["ORG_OWNER", "ADMIN", "SECURITY_REVIEWER"].includes(role);
  return (
    <section className="settings-panel">
      <h2>Expiring exceptions</h2>
      <label>
        Exception state
        <select value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="">All states</option>
          {["ACTIVE", "EXPIRED", "REVOKED"].map((s) => (
            <option key={s}>{s}</option>
          ))}
        </select>
      </label>
      {query.isLoading ? (
        <p>Loading exceptions…</p>
      ) : query.isError ? (
        <p role="alert">Could not load exceptions.</p>
      ) : (
        <>
          <p>{query.data?.basis}</p>
          <div
            className="quality-table-wrap"
            tabIndex={0}
            role="region"
            aria-label="Exception administration"
          >
            <table className="quality-table">
              <thead>
                <tr>
                  <th>Issue / identity</th>
                  <th>Owner / approver</th>
                  <th>Reason</th>
                  <th>Expiry / state</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {query.data?.items.map((row) => (
                  <tr key={row.id}>
                    <td>
                      {row.target}
                      <small>{row.identity_id || "Legacy occurrence"}</small>
                    </td>
                    <td>
                      {row.owner}
                      <small>{row.approver}</small>
                    </td>
                    <td>{row.reason}</td>
                    <td>
                      {row.expires_at}
                      <small>{row.state}</small>
                    </td>
                    <td>
                      {privileged ? (
                        <button
                          onClick={() => {
                            setSelected(row);
                            setReason("");
                          }}
                        >
                          Manage exception
                        </button>
                      ) : (
                        "Privileged reviewer required"
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!query.data?.total && (
            <p>
              No exceptions in this scope. Create a reasoned, expiring exception
              from a finding's Review tab.
            </p>
          )}
          <button
            disabled={!offset}
            onClick={() => setOffset(Math.max(0, offset - 50))}
          >
            Previous exceptions
          </button>
          <button
            disabled={!query.data?.has_more}
            onClick={() => setOffset(offset + 50)}
          >
            Next exceptions
          </button>
        </>
      )}
      {selected && (
        <fieldset disabled={busy} className="quality-form">
          <legend>Manage {selected.target}</legend>
          <label>
            Reason
            <textarea
              value={reason}
              minLength={8}
              maxLength={2000}
              onChange={(e) => setReason(e.target.value)}
            />
          </label>
          <label>
            Extension days
            <input
              type="number"
              min={1}
              max={90}
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
            />
          </label>
          <button
            disabled={reason.trim().length < 8 || days < 1 || days > 90}
            onClick={() => void change("EXTEND")}
          >
            Extend exception
          </button>
          <button
            disabled={reason.trim().length < 8}
            onClick={() => void change("REVOKED")}
          >
            Revoke exception
          </button>
          <button onClick={() => setSelected(null)}>Cancel</button>
        </fieldset>
      )}
      {message && <p role="status">{message}</p>}
    </section>
  );
}
