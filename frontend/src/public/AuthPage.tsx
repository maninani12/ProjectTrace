import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { api, setCSRF } from "../api";
import type { Identity } from "../api";
import { routes } from "../routes";
import { Brand, usePublicSession } from "./PublicShell";
import { ThemeControl } from "../Theme";

export function safeReturnTo(value: string | null) {
  try {
    const url = new URL(value || "/app", "https://projecttrace.invalid");
    if (
      url.origin !== "https://projecttrace.invalid" ||
      !["/app", ...Object.values(routes)].includes(url.pathname)
    )
      return "/app";
    return (
      url.pathname + (url.searchParams.get("import") === "1" ? "?import=1" : "")
    );
  } catch {
    return "/app";
  }
}
export default function AuthPage({
  register = false,
  autoDemo = false,
  onAuthenticated,
}: {
  register?: boolean;
  autoDemo?: boolean;
  onAuthenticated?: (identity: Identity, demo: boolean) => void;
}) {
  const options = usePublicSession();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [oidcEnabled, setOIDCEnabled] = useState(false);
  useEffect(() => {
    if (register || autoDemo) return;
    let active = true;
    api<{ enabled: boolean }>("/auth/oidc/options")
      .then((result) => {
        if (active) setOIDCEnabled(result.enabled);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [register, autoDemo]);
  const autoStarted = useRef(false);
  const next = safeReturnTo(params.get("next"));
  async function submit(demo: boolean, event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    const fields = event ? new FormData(event.currentTarget) : null;
    setBusy(true);
    setError("");
    try {
      const result = await api<Identity>(
        demo ? "/auth/demo" : register ? "/auth/register" : "/auth/login",
        demo
          ? {}
          : {
              email: fields?.get("email"),
              password: fields?.get("password"),
              ...(register
                ? { organization: fields?.get("organization") }
                : {}),
            },
      );
      setCSRF(result.csrf);
      if (onAuthenticated) onAuthenticated(result, demo);
      else navigate(demo ? "/overview?tour=1" : next, { replace: true });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    if (
      autoDemo &&
      options.ready &&
      options.demo_available &&
      !autoStarted.current
    ) {
      autoStarted.current = true;
      void submit(true);
    }
    // One explicitly requested demo login, including React StrictMode remount checks.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoDemo, options.ready, options.demo_available]);
  const registrationDisabled =
    register && options.ready && !options.local_registration;
  return (
    <div className="login">
      <div className="login-story">
        <Link to="/">
          <Brand />
        </Link>
        <span className="eyebrow">YOUR ENGINEERING WORKSPACE</span>
        <h1>
          {register
            ? "Start with your own source."
            : "Know what’s true.\nKeep it true."}
        </h1>
        <p>
          Upload → analyze → investigate & act. ProjectTrace keeps every
          important conclusion connected to its evidence.
        </p>
        <Link to="/guide">New here? Open ProjectTrace Guide →</Link>
        <div className="login-foot">
          <ThemeControl />
        </div>
      </div>
      <main className="login-form">
        <div>
          <Link to="/" className="auth-back">
            ← ProjectTrace home
          </Link>
          <h2>
            {register
              ? "Create a local workspace"
              : autoDemo
                ? "Open the Northstar demo"
                : "Welcome to ProjectTrace"}
          </h2>
          {register && (
            <p>
              Local development account. Your workspace starts with no demo
              imports.
            </p>
          )}
          {registrationDisabled ? (
            <p role="status">
              Local account creation is disabled on this server. Sign in with an
              existing account supplied by your organization.
            </p>
          ) : (
            !autoDemo && (
              <form onSubmit={(e) => submit(false, e)}>
                {register && (
                  <label>
                    Workspace name
                    <input
                      name="organization"
                      required
                      maxLength={120}
                      defaultValue="ProjectTrace"
                      autoComplete="organization"
                    />
                  </label>
                )}
                <label>
                  Email
                  <input
                    name="email"
                    type="email"
                    required
                    maxLength={200}
                    autoComplete="username"
                  />
                </label>
                <label>
                  Password
                  <input
                    name="password"
                    type="password"
                    required
                    minLength={register ? 16 : undefined}
                    maxLength={200}
                    autoComplete={
                      register ? "new-password" : "current-password"
                    }
                  />
                </label>
                {register && (
                  <small>
                    Use at least 16 characters. Keep this password private.
                  </small>
                )}
                <button
                  className="primary full"
                  disabled={busy || (register && !options.local_registration)}
                >
                  {busy
                    ? "Connecting…"
                    : register
                      ? "Create workspace & continue"
                      : "Sign in"}
                </button>
              </form>
            )
          )}
          {!options.ready && <p role="status">Checking account options…</p>}
          {oidcEnabled && !register && !autoDemo && (
            <a className="secondary full" href="/api/auth/oidc/start">
              Sign in with your organization
            </a>
          )}
          {options.error && (
            <p role="alert" className="error">
              {options.error}{" "}
              <button onClick={() => window.location.reload()}>
                Retry connection
              </button>
            </p>
          )}
          {options.demo_available && (
            <>
              <div className="divider">or explore before importing</div>
              <button
                className="secondary full"
                disabled={busy}
                onClick={() => submit(true)}
              >
                {busy ? "Opening workspace…" : "Explore Northstar demo"}
              </button>
              <small className="demo-note">
                Labeled synthetic data · separate from your source
              </small>
            </>
          )}
          {autoDemo && options.ready && !options.demo_available && (
            <p role="status">
              The hosted demo is disabled on this server. The public
              investigation examples and Guide remain available.
            </p>
          )}
          {error && (
            <p role="alert" className="error">
              {error}
              {autoDemo && (
                <button onClick={() => submit(true)} disabled={busy}>
                  Retry demo
                </button>
              )}
            </p>
          )}
          <p className="auth-alternative">
            {register || autoDemo ? (
              <Link to={`/login?next=${encodeURIComponent(next)}`}>
                Sign in to your workspace →
              </Link>
            ) : (
              options.local_registration && (
                <Link to={`/signup?next=${encodeURIComponent(next)}`}>
                  Create a local workspace →
                </Link>
              )
            )}
          </p>
          <small className="subtle">
            Uploaded code is never executed. External AI is not configured.
          </small>
        </div>
      </main>
    </div>
  );
}
