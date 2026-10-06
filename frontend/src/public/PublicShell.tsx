import { createContext, useContext, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { Link, useLocation } from "react-router";
import { ThemeControl } from "../Theme";

export type AuthOptions = {
  authenticated: boolean;
  local_registration: boolean;
  demo_available: boolean;
  ready?: boolean;
  error?: string;
};
export const PublicSession = createContext<AuthOptions>({
  authenticated: false,
  local_registration: false,
  demo_available: false,
});
export const usePublicSession = () => useContext(PublicSession);
export function AnalyzeLink({
  children,
  className = "primary",
}: {
  children?: ReactNode;
  className?: string;
}) {
  const options = usePublicSession();
  const next = "/repositories?import=1";
  return (
    <Link
      className={className}
      to={
        options.authenticated
          ? next
          : `${options.local_registration ? "/signup" : "/login"}?next=${encodeURIComponent(next)}`
      }
    >
      {children ||
        (options.authenticated
          ? "Open ProjectTrace"
          : "Analyze a Repository")}{" "}
      <span aria-hidden="true">↗</span>
    </Link>
  );
}
export function Brand() {
  return (
    <span className="public-brand">
      <svg
        aria-hidden="true"
        viewBox="0 0 32 32"
        width="30"
        height="30"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
      >
        <path d="m8 8 16 16M24 8 8 24M8 8v16M24 8v16" />
        <circle cx="8" cy="8" r="3" fill="var(--surface)" />
        <circle cx="24" cy="8" r="3" fill="var(--surface)" />
        <circle cx="8" cy="24" r="3" fill="var(--surface)" />
        <circle cx="24" cy="24" r="3" fill="var(--surface)" />
      </svg>
      <span>ProjectTrace</span>
    </span>
  );
}
function PublicNavbar() {
  const session = usePublicSession();
  const [open, setOpen] = useState(false);
  const toggle = useRef<HTMLButtonElement>(null);
  const location = useLocation();
  useEffect(() => setOpen(false), [location.pathname, location.hash]);
  useEffect(() => {
    const close = (e: KeyboardEvent) => {
      if (e.key === "Escape" && open) {
        setOpen(false);
        toggle.current?.focus();
      }
    };
    document.addEventListener("keydown", close);
    return () => document.removeEventListener("keydown", close);
  }, [open]);
  return (
    <header className="public-header">
      <div className="public-nav">
        <Link to="/" aria-label="ProjectTrace home">
          <Brand />
        </Link>
        <button
          ref={toggle}
          className="public-menu-toggle"
          aria-expanded={open}
          aria-controls="public-navigation"
          onClick={() => setOpen(!open)}
        >
          {open ? "Close menu" : "Menu"}{" "}
          <span aria-hidden="true">{open ? "×" : "+"}</span>
        </button>
        <nav
          id="public-navigation"
          aria-label="Public navigation"
          className={open ? "open" : ""}
        >
          <Link to="/#product">Product</Link>
          <Link to="/#teams">For teams</Link>
          <Link to="/trust">Security</Link>
          <Link to="/guide">Guide</Link>
          <Link to="/docs">Docs</Link>
          <ThemeControl />
          <Link
            className="public-signin"
            to={session.authenticated ? "/app" : "/login"}
          >
            {session.authenticated ? "Open ProjectTrace" : "Sign in"}
          </Link>
        </nav>
        <div className="nav-cta">
          <AnalyzeLink />
        </div>
      </div>
    </header>
  );
}
function PublicFooter() {
  return (
    <footer className="public-footer">
      <div>
        <Link to="/">
          <Brand />
        </Link>
        <p>
          Understand it. Verify it.
          <br />
          Secure it. Keep it true.
        </p>
        <small>Native analysis. Explicit limits. Human decisions.</small>
      </div>
      <div>
        <strong>Product</strong>
        <Link to="/#product">Quality & security</Link>
        <Link to="/#integrity">Engineering integrity</Link>
        <Link to="/#cloud-risk">Cloud & risk</Link>
        <Link to="/#change">Pull requests</Link>
      </div>
      <div>
        <strong>Resources</strong>
        <Link to="/guide">ProjectTrace Guide</Link>
        <Link to="/docs">Documentation</Link>
        <Link to="/changelog">Changelog</Link>
        <Link to="/about">About ProjectTrace</Link>
      </div>
      <div>
        <strong>Trust</strong>
        <Link to="/trust">Security model</Link>
        <Link to="/privacy">Source & privacy</Link>
        <Link to="/guide/limitations">Current limitations</Link>
        <Link to="/login">Open a workspace</Link>
      </div>
      <div className="footer-baseline">
        <span>ProjectTrace · Engineering integrity, quality & security</span>
        <span>Public pricing has not been finalized.</span>
      </div>
    </footer>
  );
}
export default function PublicShell({ children }: { children: ReactNode }) {
  return (
    <div className="public-site">
      <a className="skip-link" href="#public-main">
        Skip to content
      </a>
      <PublicNavbar />
      <main id="public-main" tabIndex={-1}>
        {children}
      </main>
      <PublicFooter />
    </div>
  );
}
