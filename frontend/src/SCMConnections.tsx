import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "./api";

type Connection = {
  id?: string;
  version?: number;
  label: string;
  provider_type: string;
  web_url: string;
  api_base_url: string;
  app_id: string;
  installation_id: string;
  private_key_ref: string;
  webhook_secret_ref: string;
  ca_bundle_ref: string | null;
  api_version: string;
  enabled: boolean;
  status?: string;
  live_verification?: string;
};
const initial: Connection = {
  label: "GitHub App",
  provider_type: "GITHUB",
  web_url: "https://github.com",
  api_base_url: "https://api.github.com",
  app_id: "",
  installation_id: "",
  private_key_ref: "ENV:SCM_GITHUB_KEY",
  webhook_secret_ref: "ENV:SCM_GITHUB_WEBHOOK",
  ca_bundle_ref: null,
  api_version: "2022-11-28",
  enabled: true,
};

export default function SCMConnections() {
  const [draft, setDraft] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [selectedConnection, setSelectedConnection] = useState("");
  const [repositories, setRepositories] = useState<
    { id: number; full_name: string; private: boolean }[]
  >([]);
  const [repositoryId, setRepositoryId] = useState("");
  const [system, setSystem] = useState("Product");
  const [owner, setOwner] = useState("Engineering Team");
  const [checks, setChecks] = useState(false);
  const query = useQuery({
    queryKey: ["scm-connections"],
    queryFn: () =>
      api<{ items: Connection[]; truncated: boolean }>("/github/connections"),
  });
  async function save() {
    setBusy(true);
    setMessage("");
    try {
      const {
        id,
        version,
        status: _status,
        live_verification: _verification,
        ...configuration
      } = draft;
      // Select metadata fields: never send operator secret values or unknown response fields.
      const result = await api<Connection>("/github/connections", {
        connection_id: id || null,
        expected_version: version || 0,
        label: configuration.label,
        provider_type: configuration.provider_type,
        web_url: configuration.web_url,
        api_base_url: configuration.api_base_url,
        app_id: configuration.app_id,
        installation_id: configuration.installation_id,
        private_key_ref: configuration.private_key_ref,
        webhook_secret_ref: configuration.webhook_secret_ref,
        ca_bundle_ref: configuration.ca_bundle_ref || null,
        api_version: configuration.api_version,
        enabled: configuration.enabled,
      });
      setDraft(result);
      await query.refetch();
      setMessage(
        "Connection metadata saved and audited. Credential and TLS verification require repository discovery.",
      );
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "Could not save SCM metadata.",
      );
    } finally {
      setBusy(false);
    }
  }
  async function discover() {
    setBusy(true);
    setMessage("");
    setRepositories([]);
    setRepositoryId("");
    try {
      const result = await api<{ items: typeof repositories }>(
        `/github/connections/${selectedConnection}/repositories`,
      );
      setRepositories(result.items);
      setMessage(
        result.items.length
          ? "Authorized installation repositories discovered. Select a repository to connect."
          : "No authorized repositories returned by this installation.",
      );
    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : "Could not discover installation repositories.",
      );
    } finally {
      setBusy(false);
    }
  }
  async function connect() {
    setBusy(true);
    setMessage("");
    try {
      const result = await api<{ repository_id: string }>("/github/connect", {
        connection_id: selectedConnection,
        repository_id: Number(repositoryId),
        system,
        owner,
        checks_enabled: checks,
      });
      await query.refetch();
      setMessage(
        `Repository connected: ${result.repository_id}. Deliver an authorized push or PR webhook to capture source; runtime remains unobserved.`,
      );
    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : "Could not connect repository.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="settings-panel">
      <h2>GitHub and Enterprise Server connections</h2>
      <p>
        Configure approved provider endpoints and operator-owned secret
        references. Secret values are never entered here. TLS verification is
        required; redirects and environment proxies are disabled.
      </p>
      {query.isError ? (
        <p role="alert">Could not load SCM connections.</p>
      ) : query.isLoading ? (
        <p>Loading connections…</p>
      ) : (
        <>
          <div
            className="quality-table-wrap"
            tabIndex={0}
            role="region"
            aria-label="SCM connection inventory"
          >
            <table className="quality-table">
              <thead>
                <tr>
                  <th>Connection</th>
                  <th>Provider / API</th>
                  <th>Status / verification</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {query.data?.items.map((c) => (
                  <tr key={c.id}>
                    <td>
                      {c.label}
                      <small>{c.id}</small>
                    </td>
                    <td>
                      {c.provider_type}
                      <small>{c.api_base_url}</small>
                    </td>
                    <td>
                      {c.status}
                      <small>{c.live_verification}</small>
                    </td>
                    <td>
                      <button onClick={() => setDraft(c)}>
                        Edit {c.label}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!query.data?.items.length && (
            <p>
              No per-connection metadata configured. Existing
              operator-configured GitHub.com connections remain available.
            </p>
          )}
          {query.data?.truncated && (
            <p>
              The first 100 connections are displayed; administrator inventory
              is truncated.
            </p>
          )}
        </>
      )}
      <fieldset className="quality-form" disabled={busy}>
        <legend>
          {draft.id
            ? `Edit connection · version ${draft.version}`
            : "New connection"}
        </legend>
        <label>
          Provider
          <select
            value={draft.provider_type}
            onChange={(e) =>
              setDraft({
                ...draft,
                provider_type: e.target.value,
                web_url:
                  e.target.value === "GITHUB"
                    ? "https://github.com"
                    : "https://ghes.example",
                api_base_url:
                  e.target.value === "GITHUB"
                    ? "https://api.github.com"
                    : "https://ghes.example/api/v3",
              })
            }
          >
            <option value="GITHUB">GitHub.com</option>
            <option value="GHES">GitHub Enterprise Server</option>
          </select>
        </label>
        {(
          [
            ["label", "Connection label"],
            ["web_url", "Web URL"],
            ["api_base_url", "API base URL"],
            ["app_id", "App ID"],
            ["installation_id", "Installation ID"],
            ["private_key_ref", "Private key reference (ENV:SCM_…)"],
            ["webhook_secret_ref", "Webhook secret reference (ENV:SCM_…)"],
            ["api_version", "Provider API version"],
          ] as const
        ).map(([key, label]) => (
          <label key={key}>
            {label}
            <input
              value={draft[key]}
              maxLength={500}
              onChange={(e) => setDraft({ ...draft, [key]: e.target.value })}
            />
          </label>
        ))}
        <label>
          Custom CA file reference (optional ENV:SCM_…)
          <input
            value={draft.ca_bundle_ref || ""}
            maxLength={100}
            onChange={(e) =>
              setDraft({ ...draft, ca_bundle_ref: e.target.value || null })
            }
          />
        </label>
        <label>
          <input
            type="checkbox"
            checked={draft.enabled}
            onChange={(e) => setDraft({ ...draft, enabled: e.target.checked })}
          />
          Enable connection
        </label>
        <p>
          GHES hosts and private address ranges must be approved by the
          deployment operator. Configure the webhook URL as /api/github/webhook/
          {draft.id || "connection-id"}. Connected provider identities require a
          new connection to change hosts or installations.
        </p>
        <button
          disabled={!draft.app_id || !draft.installation_id || !draft.label}
          onClick={() => void save()}
        >
          Save SCM configuration
        </button>
        <button
          onClick={() => {
            setDraft(initial);
            setMessage("");
          }}
        >
          New connection
        </button>
      </fieldset>
      <fieldset className="quality-form" disabled={busy}>
        <legend>Discover and connect a repository</legend>
        <label>
          SCM connection
          <select
            value={selectedConnection}
            onChange={(e) => {
              setSelectedConnection(e.target.value);
              setRepositories([]);
              setRepositoryId("");
            }}
          >
            <option value="">Select connection</option>
            {query.data?.items
              .filter((c) => c.enabled)
              .map((c) => (
                <option key={c.id} value={c.id}>
                  {c.label}
                </option>
              ))}
          </select>
        </label>
        <button disabled={!selectedConnection} onClick={() => void discover()}>
          Discover authorized repositories
        </button>
        <label>
          Installation repository
          <select
            value={repositoryId}
            onChange={(e) => setRepositoryId(e.target.value)}
          >
            <option value="">Select repository</option>
            {repositories.map((r) => (
              <option key={r.id} value={r.id}>
                {r.full_name}
                {r.private ? " · private" : ""}
              </option>
            ))}
          </select>
        </label>
        <label>
          Engineering system
          <input
            value={system}
            maxLength={120}
            onChange={(e) => setSystem(e.target.value)}
          />
        </label>
        <label>
          Repository owner
          <input
            value={owner}
            maxLength={120}
            onChange={(e) => setOwner(e.target.value)}
          />
        </label>
        <label>
          <input
            type="checkbox"
            checked={checks}
            onChange={(e) => setChecks(e.target.checked)}
          />
          Enable advisory Checks API summaries, subject to tenant egress policy
        </label>
        <button
          disabled={!repositoryId || !system || !owner}
          onClick={() => void connect()}
        >
          Connect selected repository
        </button>
      </fieldset>
      {message && <p role="status">{message}</p>}
    </section>
  );
}
