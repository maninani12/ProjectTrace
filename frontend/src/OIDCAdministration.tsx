import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "./api";

type Mapping = { role: string; repositories: string[] };
type Settings = {
  version: number;
  label?: string;
  issuer?: string;
  state?: string;
  jit_enabled?: boolean;
  require_mapped_group?: boolean;
  allow_admin_roles?: boolean;
  groups_claim?: string;
  role_mappings?: Record<string, Mapping>;
};
type Member = {
  id: string;
  email: string;
  role: string;
  enabled: boolean;
  local_login_allowed: boolean;
  bindings: { subject: string; issuer: string; enabled: boolean }[];
};

export default function OIDCAdministration({ role }: { role: string }) {
  const [draft, setDraft] = useState<Settings>({ version: 0 });
  const [group, setGroup] = useState("");
  const [mappedRole, setMappedRole] = useState("VIEWER");
  const [repositories, setRepositories] = useState("");
  const [userId, setUserId] = useState("");
  const [subject, setSubject] = useState("");
  const [offset, setOffset] = useState(0);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const profile = useQuery({
    queryKey: ["oidc-provider"],
    queryFn: () => api<Settings>("/auth/oidc/provider"),
  });
  const options = useQuery({
    queryKey: ["oidc-options"],
    queryFn: () =>
      api<{ enabled: boolean; issuer?: string }>("/auth/oidc/options"),
  });
  const members = useQuery({
    queryKey: ["oidc-members", offset],
    queryFn: () =>
      api<{ items: Member[]; has_more: boolean }>(
        `/auth/oidc/members?offset=${offset}&limit=50`,
      ),
  });
  useEffect(() => {
    if (profile.data) setDraft(profile.data);
  }, [profile.data]);
  async function mutate(path: string, body: object) {
    setBusy(true);
    setMessage("");
    try {
      await api(path, body);
      await profile.refetch();
      await members.refetch();
      setMessage(
        "Organization identity control saved and audited. Affected sessions are revoked.",
      );
    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : "Identity control could not be saved.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="settings-panel">
      <h2>Organization SSO</h2>
      <p>
        {options.data?.enabled
          ? `Operator-configured issuer: ${options.data.issuer}`
          : "OIDC endpoints and credentials are not configured by the deployment operator."}
      </p>
      <p>
        Authorization Code with PKCE, verified signatures, state and nonce.
        Groups never grant administrator access solely from an email domain. New
        provisioned accounts cannot use local passwords.
      </p>
      {profile.isError || members.isError ? (
        <p role="alert">Could not load organization identity controls.</p>
      ) : profile.isLoading ? (
        <p>Loading identity controls…</p>
      ) : (
        <>
          <fieldset
            disabled={busy || !options.data?.enabled}
            className="quality-form"
          >
            <legend>Versioned provider policy</legend>
            <label>
              Public sign-in label
              <input
                value={draft.label || "Organization SSO"}
                maxLength={80}
                onChange={(e) => setDraft({ ...draft, label: e.target.value })}
              />
            </label>
            <label>
              Provider state
              <select
                value={draft.state || "ENABLED"}
                onChange={(e) => setDraft({ ...draft, state: e.target.value })}
              >
                {["ENABLED", "DISABLED", "REMOVED"].map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
            </label>
            <label>
              <input
                type="checkbox"
                checked={draft.jit_enabled || false}
                onChange={(e) =>
                  setDraft({ ...draft, jit_enabled: e.target.checked })
                }
              />
              Allow controlled provisioning for verified email and explicitly
              mapped groups
            </label>
            <label>
              <input
                type="checkbox"
                checked={draft.require_mapped_group ?? true}
                onChange={(e) =>
                  setDraft({ ...draft, require_mapped_group: e.target.checked })
                }
              />
              Require a mapped group for every login
            </label>
            <label>
              <input
                type="checkbox"
                disabled={role !== "ORG_OWNER"}
                checked={draft.allow_admin_roles || false}
                onChange={(e) =>
                  setDraft({ ...draft, allow_admin_roles: e.target.checked })
                }
              />
              Owner authorizes administrator group mappings
            </label>
            <label>
              Signed groups claim
              <input
                value={draft.groups_claim || "groups"}
                maxLength={64}
                onChange={(e) =>
                  setDraft({ ...draft, groups_claim: e.target.value })
                }
              />
            </label>
            <p>
              Changing provider policy revokes its sessions. Removed providers
              leave an auditable disabled record. Previously granted
              repositories remain explicit grants and require separate
              revocation.
            </p>
            <label>
              Group identifier
              <input
                value={group}
                maxLength={250}
                onChange={(e) => setGroup(e.target.value)}
              />
            </label>
            <label>
              Mapped role
              <select
                value={mappedRole}
                onChange={(e) => setMappedRole(e.target.value)}
              >
                {[
                  "VIEWER",
                  "ENGINEER",
                  "REVIEWER",
                  "SECURITY_REVIEWER",
                  ...(draft.allow_admin_roles ? ["ADMIN"] : []),
                ].map((r) => (
                  <option key={r}>{r}</option>
                ))}
              </select>
            </label>
            <label>
              Explicit repository IDs (comma separated)
              <input
                value={repositories}
                maxLength={5000}
                onChange={(e) => setRepositories(e.target.value)}
              />
            </label>
            <button
              disabled={!group.trim()}
              onClick={() => {
                setDraft({
                  ...draft,
                  role_mappings: {
                    ...draft.role_mappings,
                    [group.trim()]: {
                      role: mappedRole,
                      repositories: repositories
                        .split(",")
                        .map((r) => r.trim())
                        .filter(Boolean),
                    },
                  },
                });
                setGroup("");
              }}
            >
              Add or replace group mapping
            </button>
            <ul>
              {Object.entries(draft.role_mappings || {}).map(
                ([name, mapping]) => (
                  <li key={name}>
                    {name} → {mapping.role} ·{" "}
                    {mapping.repositories.join(", ") || "No repositories"}
                    <button
                      onClick={() =>
                        setDraft({
                          ...draft,
                          role_mappings: Object.fromEntries(
                            Object.entries(draft.role_mappings || {}).filter(
                              ([key]) => key !== name,
                            ),
                          ),
                        })
                      }
                    >
                      Remove {name}
                    </button>
                  </li>
                ),
              )}
            </ul>
            <button
              disabled={!profile.data}
              onClick={() =>
                void mutate("/auth/oidc/provider", {
                  expected_version: draft.version,
                  label: draft.label || "Organization SSO",
                  state: draft.state || "ENABLED",
                  jit_enabled: draft.jit_enabled || false,
                  require_mapped_group: draft.require_mapped_group ?? true,
                  allow_admin_roles: draft.allow_admin_roles || false,
                  groups_claim: draft.groups_claim || "groups",
                  role_mappings: draft.role_mappings || {},
                })
              }
            >
              Save provider policy
            </button>
          </fieldset>
          <h3>Explicit membership and account availability</h3>
          <fieldset
            disabled={busy || !options.data?.enabled}
            className="quality-form"
          >
            <label>
              Organization member
              <select
                value={userId}
                onChange={(e) => setUserId(e.target.value)}
              >
                <option value="">Choose member</option>
                {members.data?.items.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.email}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Exact issuer subject
              <input
                value={subject}
                maxLength={250}
                onChange={(e) => setSubject(e.target.value)}
              />
            </label>
            <button
              disabled={!userId || !subject.trim()}
              onClick={() =>
                void mutate("/auth/oidc/membership", {
                  user_id: userId,
                  subject: subject.trim(),
                  enabled: true,
                })
              }
            >
              Enable explicit subject
            </button>
            <button
              disabled={!userId || !subject.trim()}
              onClick={() =>
                void mutate("/auth/oidc/membership", {
                  user_id: userId,
                  subject: subject.trim(),
                  enabled: false,
                })
              }
            >
              Disable explicit subject
            </button>
          </fieldset>
          <div
            className="quality-table-wrap"
            tabIndex={0}
            role="region"
            aria-label="Organization members"
          >
            <table className="quality-table">
              <thead>
                <tr>
                  <th>Member / role</th>
                  <th>Account</th>
                  <th>OIDC bindings</th>
                  <th>Availability</th>
                </tr>
              </thead>
              <tbody>
                {members.data?.items.map((m) => (
                  <tr key={m.id}>
                    <td>
                      {m.email}
                      <small>
                        {m.role} · {m.id}
                      </small>
                    </td>
                    <td>
                      {m.enabled ? "Enabled" : "Disabled"}
                      <small>
                        {m.local_login_allowed
                          ? "Local login allowed"
                          : "OIDC only"}
                      </small>
                    </td>
                    <td>
                      {m.bindings.map((b) => (
                        <p key={b.issuer + b.subject}>
                          {b.issuer} · {b.subject} ·{" "}
                          {b.enabled ? "Enabled" : "Disabled"}
                        </p>
                      ))}
                    </td>
                    <td>
                      <button
                        disabled={busy}
                        onClick={() =>
                          void mutate(`/auth/oidc/members/${m.id}`, {
                            enabled: !m.enabled,
                          })
                        }
                      >
                        {m.enabled ? "Disable account" : "Enable account"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <button
            disabled={!offset}
            onClick={() => setOffset(Math.max(0, offset - 50))}
          >
            Previous members
          </button>
          <button
            disabled={!members.data?.has_more}
            onClick={() => setOffset(offset + 50)}
          >
            Next members
          </button>
        </>
      )}
      {message && <p role="status">{message}</p>}
    </section>
  );
}
