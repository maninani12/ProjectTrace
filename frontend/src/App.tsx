import { lazy, Suspense, useEffect, useRef, useState } from "react";
import {
  BrowserRouter,
  Link,
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from "react-router";
import { api } from "./api";
import { legacyRoute, routes } from "./routes";
import { ThemeProvider } from "./Theme";
import PublicShell, { PublicSession } from "./public/PublicShell";
import type { AuthOptions } from "./public/PublicShell";
import Landing from "./public/Landing";
import AuthPage from "./public/AuthPage";
import { AppBoundary, NotFound } from "./public/Errors";

const Workspace = lazy(() => import("./WorkspaceApp"));
const Guide = lazy(() => import("./public/Guide"));
const Documents = lazy(() => import("./public/Documents"));

function RouteEffects() {
  const location = useLocation();
  const navigate = useNavigate();
  const previous = useRef<string | null>(null);
  useEffect(() => {
    const legacy = legacyRoute(location.hash);
    if (legacy) navigate(legacy, { replace: true });
    const changed =
      previous.current !== null && previous.current !== location.pathname;
    previous.current = location.pathname;
    const frame = requestAnimationFrame(() => {
      if (location.hash && !legacy) {
        try {
          document
            .getElementById(decodeURIComponent(location.hash.slice(1)))
            ?.scrollIntoView();
        } catch {
          /* malformed hash */
        }
      } else {
        window.scrollTo(0, 0);
        if (changed)
          (
            document.getElementById("public-main") ||
            document.getElementById("main")
          )?.focus({ preventScroll: true });
      }
    });
    return () => cancelAnimationFrame(frame);
  }, [location.pathname, location.hash, navigate]);
  return null;
}
export function SiteRoutes() {
  const location = useLocation();
  const authBoundary = ["/login", "/signup", "/demo"].includes(
    location.pathname,
  )
    ? location.pathname
    : ["/app", ...Object.values(routes)].includes(location.pathname)
      ? "workspace"
      : "public";
  const [options, setOptions] = useState<AuthOptions>({
    authenticated: false,
    local_registration: false,
    demo_available: false,
    ready: false,
  });
  useEffect(() => {
    let current = true;
    api<AuthOptions>("/auth/options")
      .then((value) => {
        if (current) setOptions({ ...value, ready: true });
      })
      .catch((error: unknown) => {
        if (current)
          setOptions({
            authenticated: false,
            local_registration: false,
            demo_available: false,
            ready: true,
            error:
              error instanceof Error
                ? error.message
                : "Could not load account options.",
          });
      });
    return () => {
      current = false;
    };
  }, [authBoundary]);
  return (
    <PublicSession.Provider value={options}>
      <RouteEffects />
      <Suspense
        fallback={
          <main className="loading" role="status">
            Loading ProjectTrace…
          </main>
        }
      >
        <Routes>
          <Route
            path="/"
            element={
              <PublicShell>
                <Landing />
              </PublicShell>
            }
          />
          <Route
            path="/guide"
            element={
              <PublicShell>
                <Guide />
              </PublicShell>
            }
          />
          <Route
            path="/guide/:topic"
            element={
              <PublicShell>
                <Guide />
              </PublicShell>
            }
          />
          {["trust", "privacy", "docs", "about", "changelog"].map((page) => (
            <Route
              key={page}
              path={`/${page}`}
              element={
                <PublicShell>
                  <Documents page={page} />
                </PublicShell>
              }
            />
          ))}
          <Route path="/login" element={<AuthPage />} />
          <Route path="/signup" element={<AuthPage register />} />
          <Route path="/demo" element={<AuthPage autoDemo />} />
          <Route path="/app" element={<Workspace />} />
          {Object.values(routes).map((path) => (
            <Route key={path} path={path} element={<Workspace />} />
          ))}
          {Object.values(routes).map((path) => (
            <Route
              key={`app${path}`}
              path={`/app${path}`}
              element={<Navigate to={path} replace />}
            />
          ))}
          <Route
            path="*"
            element={
              <PublicShell>
                <NotFound />
              </PublicShell>
            }
          />
        </Routes>
      </Suspense>
    </PublicSession.Provider>
  );
}
export default function App() {
  return (
    <AppBoundary>
      <ThemeProvider>
        <BrowserRouter>
          <SiteRoutes />
        </BrowserRouter>
      </ThemeProvider>
    </AppBoundary>
  );
}
