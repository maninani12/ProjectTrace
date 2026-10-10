import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router";
import { api, setCSRF } from "./api";
import type { Identity } from "./api";

export default function Invitation() {
  const navigate = useNavigate();
  const [token] = useState(
    () => new URLSearchParams(window.location.hash.slice(1)).get("token") || "",
  );
  const [preview, setPreview] = useState<{
    organization: string;
    role: string;
    expires_at: string;
  }>();
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [signed, setSigned] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    // The invitation secret remains in memory, never in request URLs, history or analytics.
    window.history.replaceState(null, "", window.location.pathname);
    let current = true;
    Promise.all([
      api<{ organization: string; role: string; expires_at: string }>(
        "/auth/invitations/preview",
        { token },
      ).then((value) => {
        if (current) setPreview(value);
      }),
      api<Identity>("/auth/me")
        .then((value) => {
          if (current) {
            setCSRF(value.csrf);
            setSigned(true);
          }
        })
        .catch(async () => {
          // A restricted membership may still accept an authorized invitation
          // into another organization using its existing session and CSRF.
          try {
            const value = await api<{ csrf: string }>("/auth/organizations?limit=1");
            if (current && value.csrf) { setCSRF(value.csrf); setSigned(true); }
          } catch { /* An unauthenticated invitee supplies their own password. */ }
        }),
    ])
      .catch((failure) => {
        if (current)
          setError(
            failure instanceof Error
              ? failure.message
              : "Invitation unavailable.",
          );
      })
      .finally(() => {
        if (current) setLoading(false);
      });
    return () => {
      current = false;
    };
  }, [token]);
  async function accept(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await api<Identity>("/auth/invitations/accept", {
        token,
        display_name: name || null,
        ...(password ? { password } : {}),
      });
      setCSRF(result.csrf);
      setPassword("");
      navigate("/repositories", { replace: true });
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : "Invitation could not be accepted.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="content" id="public-main" tabIndex={-1}>
      <div className="admin-panel">
        <h1>Join your ProjectTrace organization</h1>
        {loading ? (
          <p role="status">Checking invitation…</p>
        ) : preview ? (
          <form className="admin-form" onSubmit={accept}>
            <p>
              Invitation to <strong>{preview.organization}</strong> as{" "}
              {preview.role.replaceAll("_", " ")}. Expires{" "}
              {new Date(preview.expires_at).toLocaleString()}.
            </p>
            <label>
              Display name (optional)
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                maxLength={120}
              />
            </label>
            {signed ? (
              <p>
                Your current account must match the invited account. Signing in
                never resets an existing password.
              </p>
            ) : (
              <label>
                New account password or existing local account password
                <input
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  minLength={12}
                  maxLength={128}
                  required
                />
                <small>
                  New accounts require at least 16 characters. Existing
                  OIDC-only accounts must sign in through their provider first.
                </small>
              </label>
            )}
            <label>
              <input type="checkbox" required />I accept membership in this
              organization.
            </label>
            <button className="primary" disabled={busy}>
              {busy ? "Accepting invitation…" : "Accept invitation"}
            </button>
          </form>
        ) : (
          <p>
            This invitation is missing, unavailable, expired or already used.
          </p>
        )}
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <a href="/login">Sign in to your existing account</a>
      </div>
    </main>
  );
}
