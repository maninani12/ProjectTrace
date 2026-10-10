import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import {
  QueryClient,
  QueryClientProvider,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useLocation, useNavigate } from "react-router";
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from "@tanstack/react-table";

import {
  Activity,
  ArrowDownToLine,
  ArrowRight,
  Bell,
  Boxes,
  Check,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  Command,
  Database,
  FileCode2,
  GitBranch,
  GitPullRequest,
  Globe,
  Layers,
  LayoutDashboard,
  ListChecks,
  LoaderCircle,
  LogOut,
  Menu,
  Network,
  Search,
  Settings2,
  Shield,
  Sparkles,
  SquareArrowOutUpRight,
  Terminal,
  Upload,
  Waypoints,
  X,
} from "lucide-react";
import { api, APIError, setCSRF } from "./api";
import {
  analysisLabel,
  emptyMessage,
  isAnalysisActive,
  repositoryState,
  repositoryEngines,
  overviewState,
  dependencyState,
} from "./status";
import { routeForPage, pageForRoute } from "./routes";
import Badge from "./shared/Badge";
import Source from "./shared/Source";
import AuthPage from "./public/AuthPage";
import { ThemeControl } from "./Theme";
import { guideForPage } from "./public/guideContent";
export { default as Badge } from "./shared/Badge";
import type {
  Answer,
  EngineResult,
  Gate,
  Identity,
  Item,
  Repository,
  Workspace,
  RecordPage,
} from "./api";

import NativeProfiles from "./NativeProfiles";
import Administration, {
  OwnershipNotices,
  OwnNotifications,
  WorkspaceSelector,
} from "./Administration";
import type { AccessContext } from "./api";

const CodeQuality = lazy(() => import("./CodeQuality"));
const EnterpriseTrust = lazy(() => import("./EnterpriseTrust"));
const Infrastructure = lazy(() => import("./Infrastructure"));
const EngineeringChanges = lazy(() => import("./EngineeringChanges"));
const Graph = lazy(() => import("./Graph"));
const navigation = [
  {
    label: "Engineering",
    items: [
      ["Overview", LayoutDashboard],
      ["Systems", Boxes],
      ["Components", Layers],
      ["Repositories", GitBranch],
      ["Pull Requests", GitPullRequest],
      ["Engineering Changes", Activity],
    ],
  },
  {
    label: "Quality & Security",
    items: [
      ["Code Quality", FileCode2],
      ["Security", Shield],
      ["Dependencies", Database],
      ["Secrets", Shield],
      ["Infrastructure", Terminal],
      ["Cloud", Globe],
      ["Cloud Assets", Boxes],
      ["Cloud Identities", Shield],
      ["Exposure", Globe],
      ["Risk Paths", Waypoints],
    ],
  },
  {
    label: "Integrity",
    items: [
      ["Claim Ledger", Check],
      ["Drift", Activity],
      ["Architecture", Network],
      ["API Integrity", Network],
      ["Evidence", FileCode2],
      ["Evidence Graph", Waypoints],
      ["Ask Engineering", Sparkles],
    ],
  },
  {
    label: "Governance",
    items: [
      ["Findings", ListChecks],
      ["Policies", ListChecks],
      ["Reviews", Check],
      ["Audit Trail", Activity],
      ["Trust & Coverage", Shield],
    ],
  },
  {
    label: "Configuration",
    items: [
      ["Connections", Boxes],
      ["Settings", Settings2],
    ],
  },
] as const;
const descriptions: Record<string, string> = {
  Administration:
    "Observe organization operations, review scoped access, and verify every administrative change.",
  Overview:
    "See what your engineering organization claims, what the evidence supports, and what needs attention.",
  Systems:
    "Connect repositories and components to the engineering systems they serve.",
  Components:
    "Trace ownership and verification scope across the parts of your systems.",
  Repositories:
    "Immutable source snapshots form the foundation of every engineering conclusion.",
  "Pull Requests":
    "Understand how a change affects security, engineering claims, and documentation in one review.",
  "Engineering Changes":
    "Trace important BASE-to-HEAD changes through claims, source evidence, quality, security, infrastructure, ownership and policy.",
  Findings:
    "One review queue for native analysis and external evidence, with source-level provenance.",
  "Code Quality":
    "Review supported reliability, maintainability and change evidence with explicit source coverage.",
  Security:
    "Prioritize security evidence by severity, confidence, and affected component.",
  Dependencies:
    "Pinned dependencies and cached vulnerability advisories, with explicit coverage.",
  Infrastructure:
    "Review static infrastructure configuration. Imported infrastructure is never executed.",
  Cloud:
    "Start with infrastructure evidence. Live cloud inventory requires an authorized read-only connection.",
  "Claim Ledger":
    "Tracks technical statements and verifies whether current engineering evidence still supports them.",
  Drift:
    "Shows where documentation, architecture, or APIs need review after implementation changes.",
  Architecture:
    "Compare declared system relationships with current source signals.",
  Evidence:
    "Explore the source artifacts behind every claim, finding, and conclusion.",
  "Evidence Graph":
    "Explore a focused neighborhood of claims, source artifacts, and findings.",
  "Ask Engineering":
    "Investigate a technical question using evidence from your authorized snapshots.",
  Policies:
    "Explainable, advisory gates help teams decide which changes require review.",
  "Audit Trail":
    "Follow who changed or reviewed an engineering conclusion, when, and why.",
  Connections:
    "Provider permissions, connection status, and verification are always explicit.",
  Secrets:
    "Review masked credential observations, context, ownership, and remediation.",
  "Cloud Assets":
    "Inspect supported infrastructure declarations and authorized control-plane observations.",
  "Cloud Identities":
    "Inspect declared identities and observed inventory with explicit permission coverage.",
  Exposure:
    "Review explicit public access declarations and exposure that still requires verification.",
  "Risk Paths":
    "Follow actual observed configuration and finding relationships; runtime reachability remains explicit.",
  "API Integrity":
    "Compare supported API contract statements against implementation evidence.",
  Reviews:
    "Inspect review decisions, owners, and evidence changes across current snapshots.",
  Settings:
    "Manage your local experience and understand the workspace data boundary.",
};
function Empty({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="empty">
      <CircleHelp size={28} />
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}
function date(value?: string) {
  return value
    ? new Date(value).toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "—";
}
function label(item: Item) {
  return item.text || item.title || item.path || item.name || item.id;
}
function isSecurityFinding(item: Item) {
  return [
    "SAST",
    "SECRET",
    "SECRETS",
    "SCA",
    "IAC",
    "SECURITY",
    "CLOUD",
  ].includes(item.category || "");
}
const helper = createColumnHelper<Item>();

function DataTable({
  items,
  onOpen,
  mode = "claim",
  emptyTitle = "No findings detected in the supported analysis scope.",
  emptyDetail = "Static analysis cannot establish runtime safety.",
}: {
  items: Item[];
  onOpen: (item: Item) => void;
  mode?: string;
  emptyTitle?: string;
  emptyDetail?: string;
}) {
  const columns = useMemo(
    () => [
      helper.display({
        id: "name",
        header:
          mode === "claim"
            ? "Engineering claim"
            : mode === "drift"
              ? "Changed claim"
              : "Finding",
        cell: ({ row }) => (
          <button className="row-link" onClick={() => onOpen(row.original)}>
            <span>{label(row.original)}</span>
            <small>
              {row.original.path
                ? `${row.original.path}${row.original.line ? ":" + row.original.line : ""}`
                : row.original.scope?.repository}
              {row.original.rule ? " · " + row.original.rule : ""}
            </small>
          </button>
        ),
      }),
      helper.accessor("status", {
        header: mode === "claim" ? "Verification" : "Review",
        cell: ({ row }) => (
          <Badge
            value={
              mode === "claim"
                ? row.original.status
                : row.original.review_status
            }
          />
        ),
      }),
      helper.accessor("severity", {
        header: "Severity",
        cell: ({ getValue }) => <Badge value={getValue()} />,
      }),
      helper.display({
        id: "context",
        header: mode === "claim" ? "Confidence" : "Category",
        cell: ({ row }) => (
          <span>
            {mode === "claim"
              ? row.original.confidence
              : row.original.category ||
                row.original.type?.replaceAll("_", " ")}
          </span>
        ),
      }),
      helper.accessor("owner", {
        header: "Owner",
        cell: ({ getValue }) => (
          <span className="subtle">{getValue() || "Unassigned"}</span>
        ),
      }),
      helper.display({
        id: "scope",
        header: "Snapshot",
        cell: ({ row }) => (
          <code title={row.original.scope?.commit}>
            {row.original.scope?.commit.slice(0, 8) || "—"}
          </code>
        ),
      }),
    ],
    [onOpen, mode],
  );
  const table = useReactTable({
    data: items,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });
  if (!items.length) return <Empty title={emptyTitle}>{emptyDetail}</Empty>;
  return (
    <div className="table-scroll">
      <table>
        <thead>
          {table.getHeaderGroups().map((g) => (
            <tr key={g.id}>
              {g.headers.map((h) => (
                <th key={h.id}>
                  {flexRender(h.column.columnDef.header, h.getContext())}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((r) => (
            <tr key={r.id}>
              {r.getVisibleCells().map((c) => (
                <td key={c.id}>
                  {flexRender(c.column.columnDef.cell, c.getContext())}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Modal({
  title,
  onClose,
  children,
  wide = false,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement;
    ref.current?.focus();
    const listener = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
      if (event.key === "Tab") {
        const nodes = Array.from(
          ref.current?.querySelectorAll<HTMLElement>(
            "button,input,select,textarea,a[href]",
          ) || [],
        );
        const first = nodes[0],
          last = nodes.at(-1);
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last?.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first?.focus();
        }
      }
    };
    document.addEventListener("keydown", listener);
    return () => {
      document.removeEventListener("keydown", listener);
      previous?.focus();
    };
  }, [onClose]);
  return (
    <div
      className="overlay"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className={"modal " + (wide ? "wide" : "")}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        ref={ref}
        tabIndex={-1}
      >
        <div className="modal-head">
          <h2>{title}</h2>
          <button
            className="icon-button"
            aria-label="Close dialog"
            onClick={onClose}
          >
            <X size={20} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

export default function WorkspaceScreen() {
  const [workspaceClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
      }),
  );
  return (
    <QueryClientProvider client={workspaceClient}>
      <WorkspaceApp />
    </QueryClientProvider>
  );
}

async function loadWorkspaceSummary(path: string) {
  const result = await api<Workspace>(path);
  if (!result.counts?.complete)
    throw new Error(
      "Complete workspace summary is unavailable. Refresh after the API is ready; preview rows cannot verify zero results.",
    );
  return result;
}

function WorkspaceApp() {
  const client = useQueryClient();
  const location = useLocation();
  const routerNavigate = useNavigate();
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [identityLoaded, setIdentityLoaded] = useState(false);
  const [identityError, setIdentityError] = useState("");
  const [identityAttempt, setIdentityAttempt] = useState(0);
  const page = pageForRoute(location.pathname);
  const administration = page === "Administration";
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("ALL");
  const [repoFilter, setRepoFilter] = useState("ALL");
  const [selected, setSelected] = useState<Item | null>(null);
  const [importing, setImporting] = useState(false);
  const [importTarget, setImportTarget] = useState("NEW");
  const [tour, setTour] = useState(false);
  const [command, setCommand] = useState(false);
  const [mobile, setMobile] = useState(false);
  const [error, setError] = useState("");
  const [recordOffset, setRecordOffset] = useState(0);
  const [repositoryOffset, setRepositoryOffset] = useState(0);
  const [repositorySearch, setRepositorySearch] = useState("");
  const [catalogOffset, setCatalogOffset] = useState(0);
  const listView = ["Systems", "Components", "Repositories"].includes(page);
  const tenantKey = `${identity?.email || ""}:${identity?.organization_id || "primary"}`;
  const accessVersion = useRef<string | undefined>(undefined);
  const featureAllowed = (feature: string) =>
    identity?.access?.features?.[feature]?.allowed !== false;
  const pageFeature = [
    "Cloud",
    "Cloud Assets",
    "Cloud Identities",
    "Exposure",
    "Risk Paths",
  ].includes(page)
    ? "cloud"
    : page === "Ask Engineering"
      ? "ask_engineering"
      : null;
  const engineeringAllowed =
    featureAllowed("api_access") &&
    (!pageFeature || featureAllowed(pageFeature));
  const catalog = useQuery({
    queryKey: ["workspace", "catalog", tenantKey, catalogOffset],
    queryFn: () =>
      api<Workspace>(
        `/repositories?include_analysis=false&limit=100&offset=${catalogOffset}`,
      ),
    enabled: !!identity && !administration && engineeringAllowed,
    retry: false,
    staleTime: 10000,
  });
  const repositoryList = useQuery({
    queryKey: [
      "workspace",
      "repository-list",
      tenantKey,
      repoFilter,
      repositorySearch,
      repositoryOffset,
    ],
    queryFn: () =>
      api<Workspace>(
        "/repositories?" +
          new URLSearchParams({
            offset: String(repositoryOffset),
            limit: "25",
            search: repositorySearch,
            ...(repoFilter !== "ALL" ? { repository_id: repoFilter } : {}),
          }),
      ),
    enabled: !!identity && !administration && engineeringAllowed && listView,
    retry: false,
    staleTime: 10000,
    refetchInterval: (query) =>
      query.state.data?.repositories.some((repo) =>
        isAnalysisActive(repositoryState(repo)),
      )
        ? 1500
        : false,
  });
  useEffect(() => setRepositoryOffset(0), [repoFilter, repositorySearch]);
  const workspace = useQuery({
    queryKey: ["workspace", "summary", tenantKey, "ALL"],
    queryFn: () => loadWorkspaceSummary("/workspace?summary=1"),
    enabled:
      !!identity &&
      !administration &&
      engineeringAllowed &&
      !listView &&
      repoFilter === "ALL",
    retry: false,
    staleTime: 10000,
    refetchInterval: (query) =>
      query.state.data?.repositories.some((repo) =>
        isAnalysisActive(repositoryState(repo)),
      )
        ? 1500
        : false,
  });
  const scopedSummary = useQuery({
    queryKey: ["workspace", "summary", tenantKey, "scope", repoFilter],
    queryFn: () =>
      loadWorkspaceSummary(
        "/workspace?summary=1&repository_id=" + encodeURIComponent(repoFilter),
      ),
    enabled:
      !!identity &&
      !administration &&
      engineeringAllowed &&
      !listView &&
      repoFilter !== "ALL",
    retry: false,
    staleTime: 10000,
    refetchInterval: (query) =>
      query.state.data?.repositories.some((repo) =>
        isAnalysisActive(repositoryState(repo)),
      )
        ? 1500
        : false,
  });
  const summary = listView
    ? repositoryList
    : repoFilter === "ALL"
      ? workspace
      : scopedSummary;
  const scopeRepositories = [...(catalog.data?.repositories || [])];
  for (const repo of summary.data?.repositories || []) {
    if (
      repo.id === repoFilter &&
      !scopeRepositories.some((item) => item.id === repo.id)
    )
      scopeRepositories.push(repo);
  }
  const recordView = [
    "Claim Ledger",
    "Architecture",
    "API Integrity",
    "Findings",
    "Security",
    "Secrets",
    "Drift",
    "Dependencies",
    "Evidence",
    "Pull Requests",
    "Reviews",
    "Cloud",
    "Cloud Assets",
    "Cloud Identities",
    "Exposure",
    "Risk Paths",
  ].includes(page);
  const records = useQuery({
    queryKey: [
      "workspace-records",
      tenantKey,
      page,
      repoFilter,
      query,
      filter,
      recordOffset,
      summary.data?.repositories.map((repo) => repo.snapshot?.id).join(","),
    ],
    queryFn: () => {
      const params = new URLSearchParams({
        view: page,
        offset: String(recordOffset),
        limit: "50",
        search: query,
        state: filter,
        ...(repoFilter !== "ALL" ? { repository_id: repoFilter } : {}),
      });
      for (const repo of summary.data?.repositories || []) {
        if (repo.snapshot) params.append("snapshot_ids", repo.snapshot.id);
      }
      return api<RecordPage>("/workspace/records?" + params);
    },
    enabled:
      !!identity &&
      !administration &&
      engineeringAllowed &&
      !!summary.data &&
      recordView,
  });
  useEffect(() => setRecordOffset(0), [page, repoFilter, query, filter]);
  useEffect(() => {
    setFilter("ALL");
    setQuery("");
  }, [page]);
  const data = useMemo(() => {
    if (!summary.data) return undefined;
    if (!recordView || !records.data) return summary.data;
    const result = { ...summary.data, record_page: records.data };
    for (const kind of [
      "claim",
      "finding",
      "evidence",
      "dependency",
      "drift",
      "pr",
      "graph_node",
      "risk_path",
    ] as const) {
      result[kind] = records.data.items.filter((item) => item.kind === kind);
    }
    return result;
  }, [summary.data, records.data, recordView]);
  useEffect(() => {
    let current = true;
    setIdentityLoaded(false);
    setIdentityError("");
    api<Identity>("/auth/me")
      .then((i) => {
        if (!current) return;
        setCSRF(i.csrf);
        accessVersion.current = i.access?.decision_version;
        setIdentity(i);
      })
      .catch((error: unknown) => {
        if (current && !(error instanceof APIError && error.status === 401))
          setIdentityError(
            error instanceof Error
              ? error.message
              : "Workspace access could not be checked.",
          );
      })
      .finally(() => {
        if (current) setIdentityLoaded(true);
      });
    return () => {
      current = false;
    };
  }, [identityAttempt]);
  function acceptAccess(next: AccessContext) {
    if (
      !next.features ||
      !Array.isArray(next.permissions) ||
      typeof next.organization_id !== "string" ||
      typeof next.decision_version !== "string"
    )
      return;
    if (
      accessVersion.current &&
      accessVersion.current !== next.decision_version
    ) {
      const protectedQuery = (query: { queryKey: readonly unknown[] }) =>
        !["administration", "organizations"].includes(
          String(query.queryKey[0]),
        );
      client.cancelQueries({ predicate: protectedQuery });
      client.removeQueries({ predicate: protectedQuery });
      client.invalidateQueries({ queryKey: ["administration"] });
      setSelected(null);
      setRepoFilter("ALL");
      setImporting(false);
    }
    accessVersion.current = next.decision_version;
    setIdentity((current) =>
      current
        ? {
            ...current,
            role: next.role,
            organization_id: next.organization_id,
            access: next,
          }
        : current,
    );
  }
  async function refreshAccess() {
    try {
      acceptAccess(await api<AccessContext>("/auth/access"));
    } catch (failure) {
      if (failure instanceof APIError && [401, 403].includes(failure.status)) {
        client.cancelQueries();
        client.clear();
        setSelected(null);
        setImporting(false);
        setIdentity(null);
        if (failure.status === 403) setIdentityError(failure.message);
      }
    }
  }
  useEffect(() => {
    if (!identity?.access) return;
    let current = true;
    const update = async () => {
      try {
        const next = await api<AccessContext>("/auth/access");
        if (current) acceptAccess(next);
      } catch (failure) {
        if (
          current &&
          failure instanceof APIError &&
          [401, 403].includes(failure.status)
        ) {
          client.cancelQueries();
          client.clear();
          setSelected(null);
          setImporting(false);
          setIdentity(null);
          if (failure.status === 403) setIdentityError(failure.message);
        }
      }
    };
    update();
    const timer = setInterval(update, 10000);
    return () => {
      current = false;
      clearInterval(timer);
    };
  }, [identity?.email, identity?.organization_id, client]);
  function selectWorkspace(next: Identity) {
    client.cancelQueries();
    client.clear();
    setSelected(null);
    setRepoFilter("ALL");
    setCatalogOffset(0);
    setImporting(false);
    setCSRF(next.csrf);
    accessVersion.current = next.access?.decision_version;
    setIdentityError("");
    setIdentity(next);
    routerNavigate("/repositories");
  }
  useEffect(() => {
    const fn = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "k") {
        e.preventDefault();
        setCommand((v) => !v);
      }
    };
    document.addEventListener("keydown", fn);
    return () => document.removeEventListener("keydown", fn);
  }, []);
  const navigate = (target: string) => {
    routerNavigate(
      target === "ProjectTrace Guide" ? "/guide" : routeForPage(target),
    );
    setFilter("ALL");
    setQuery("");
    setMobile(false);
  };
  useEffect(() => {
    setFilter("ALL");
    setQuery("");
    setSelected(null);
    setMobile(false);
    document.documentElement.scrollTop = 0;
    document.body.scrollTop = 0;
  }, [location.pathname]);
  useEffect(() => {
    if (!identity) return;
    const params = new URLSearchParams(location.search);
    if (params.get("tour") === "1") {
      setTour(true);
      routerNavigate(location.pathname, { replace: true });
    }
    if (params.get("import") === "1" && !identity.demo) {
      setImportTarget("NEW");
      setImporting(true);
      routerNavigate(location.pathname, { replace: true });
    }
  }, [identity, location.pathname, location.search, routerNavigate]);
  const filtered = (items: Item[]) =>
    recordView
      ? items
      : items.filter(
          (i) =>
            (repoFilter === "ALL" ||
              i.scope?.repository_id === repoFilter ||
              i.repository_id === repoFilter) &&
            (filter === "ALL" ||
              i.status === filter ||
              i.severity === filter ||
              i.category === filter ||
              i.classification === filter ||
              i.review_status === filter) &&
            (query === "" ||
              JSON.stringify([label(i), i.path, i.owner, i.category])
                .toLowerCase()
                .includes(query.toLowerCase())),
        );
  const tableEmpty = data
    ? emptyMessage(page, data, query !== "" || filter !== "ALL")
    : ["Loading analysis", ""];
  const open = (item: Item) => setSelected(item);
  if (!identityLoaded)
    return (
      <main className="loading" role="status">
        Checking workspace access…
      </main>
    );
  if (!identity && identityError)
    return (
      <main className="loading">
        <h1>Workspace access unavailable</h1>
        <p role="alert">{identityError}</p>
        <WorkspaceSelector selected={selectWorkspace} />
        <button onClick={() => setIdentityAttempt((attempt) => attempt + 1)}>
          Retry access
        </button>
      </main>
    );
  if (!identity)
    return (
      <AuthPage
        onAuthenticated={(result, demo) => {
          client.clear();
          setRepoFilter("ALL");
          setSelected(null);
          setIdentity(result);
          setIdentityAttempt((attempt) => attempt + 1);
          if (demo) setTour(true);
        }}
      />
    );
  return (
    <div className="app-shell">
      <a
        href="#main"
        className="skip-link"
        onClick={(event) => {
          event.preventDefault();
          document.getElementById("main")?.focus();
        }}
      >
        Skip to content
      </a>
      <aside className={"sidebar " + (mobile ? "mobile-open" : "")}>
        <button className="brand" onClick={() => navigate("Overview")}>
          <Waypoints size={25} />
          <span>ProjectTrace</span>
        </button>
        {identity.organization_id ? (
          <WorkspaceSelector identity={identity} selected={selectWorkspace} />
        ) : (
          <div className="workspace-switch">
            {identity.organization || "ProjectTrace workspace"}
          </div>
        )}
        <nav aria-label="Main navigation">
          {navigation.map((group) => (
            <div className="nav-group" key={group.label}>
              <span className="nav-label">{group.label}</span>
              {group.items
                .filter(
                  ([name]) =>
                    !(
                      [
                        "Cloud",
                        "Cloud Assets",
                        "Cloud Identities",
                        "Exposure",
                        "Risk Paths",
                      ].includes(name) && !featureAllowed("cloud")
                    ) &&
                    !(
                      name === "Ask Engineering" &&
                      !featureAllowed("ask_engineering")
                    ),
                )
                .map(([name, Icon]) => (
                  <button
                    key={name}
                    className={"nav-item " + (page === name ? "active" : "")}
                    aria-current={page === name ? "page" : undefined}
                    onClick={() => navigate(name)}
                  >
                    <Icon size={16} />
                    <span>{name}</span>
                    {name === "Drift" &&
                      !!(data?.counts?.totals.drift ?? data?.drift.length) && (
                        <span className="nav-count">
                          {data?.counts?.totals.drift ?? data?.drift.length}
                        </span>
                      )}
                  </button>
                ))}
            </div>
          ))}
          {identity.access?.admin_available && (
            <div className="nav-group">
              <span className="nav-label">Administration</span>
              <button
                className={"nav-item " + (administration ? "active" : "")}
                aria-current={administration ? "page" : undefined}
                onClick={() => navigate("Administration")}
              >
                <Shield size={16} />
                <span>Control Center</span>
              </button>
            </div>
          )}
          <div className="nav-group">
            <span className="nav-label">Learn</span>
            <button
              className="nav-item"
              onClick={() => navigate("ProjectTrace Guide")}
            >
              <CircleHelp size={16} />
              <span>ProjectTrace Guide</span>
            </button>
          </div>
        </nav>
        <div className="sidebar-foot">
          <div className="avatar">DE</div>
          <div>
            <strong>
              {identity.email === "demo@projecttrace.local"
                ? "Demo engineer"
                : identity.email.split("@")[0]}
            </strong>
            <small>{identity.role.replaceAll("_", " ")}</small>
          </div>
          <button
            className="icon-button"
            title="Sign out"
            aria-label="Sign out"
            onClick={async () => {
              await api("/auth/logout", {});
              client.clear();
              setIdentity(null);
            }}
          >
            <LogOut size={16} />
          </button>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <button
            className="icon-button mobile-menu"
            aria-label="Open navigation"
            onClick={() => setMobile(!mobile)}
          >
            <Menu size={20} />
          </button>
          <div className="breadcrumb">
            Workspace <ChevronRight size={14} /> <strong>{page}</strong>
          </div>
          <div className="top-actions">
            <button
              className="search-button"
              aria-label="Search workspace"
              onClick={() => setCommand(true)}
            >
              <Search size={15} />
              <span>Search evidence or navigate</span>
              <kbd>Ctrl K</kbd>
            </button>
            <select
              aria-label="Global repository"
              hidden={administration}
              value={repoFilter}
              onChange={(e) => {
                setRepoFilter(e.target.value);
                setSelected(null);
              }}
            >
              <option value="ALL">All repositories</option>
              {scopeRepositories.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name}
                </option>
              ))}
            </select>
            {(catalogOffset > 0 || catalog.data?.repository_page?.has_more) && (
              <>
                <button
                  disabled={!catalogOffset}
                  onClick={() =>
                    setCatalogOffset(Math.max(0, catalogOffset - 100))
                  }
                >
                  Previous repository choices
                </button>
                <button
                  disabled={!catalog.data?.repository_page?.has_more}
                  onClick={() => setCatalogOffset(catalogOffset + 100)}
                >
                  Next repository choices
                </button>
              </>
            )}
            {catalog.isError && (
              <button onClick={() => catalog.refetch()}>
                Retry repository choices
              </button>
            )}
            <span
              hidden={administration}
              className={
                "analysis-state " +
                (data?.analysis?.state || "UNKNOWN").toLowerCase()
              }
              role="status"
            >
              <i />{" "}
              {summary.isError
                ? listView
                  ? "Repository data unavailable"
                  : "Analysis data unavailable"
                : summary.isLoading
                  ? listView
                    ? "Loading repositories"
                    : "Loading analysis status"
                  : analysisLabel(data?.analysis?.state || "UNKNOWN")}
            </span>
            <button
              className="icon-button"
              aria-label="View activity"
              onClick={() =>
                routerNavigate(
                  identity.access?.admin_available
                    ? "/administration?section=Notifications"
                    : "/settings",
                )
              }
            >
              <Bell size={18} />
            </button>
          </div>
        </header>
        {data?.demo && (
          <div className="demo-banner">
            <span>
              <strong>
                {data.repositories.some(
                  (repository) => repository.provider === "LOCAL",
                )
                  ? "DEMO WORKSPACE"
                  : "DEMO DATA"}
              </strong>{" "}
              Northstar Labs ·{" "}
              {data.repositories.some(
                (repository) => repository.provider === "LOCAL",
              )
                ? "demo fixtures and retained historical source"
                : "deterministic repository fixtures"}
            </span>
            <button onClick={() => setTour(true)}>
              Follow the story <ArrowRight size={13} />
            </button>
          </div>
        )}
        <main id="main" tabIndex={-1} className="content">
          <div className="page-title">
            <div>
              <div className="eyebrow">
                {page === "Overview"
                  ? `${data?.organization || "ProjectTrace"} / ENGINEERING INTEGRITY`
                  : "ENGINEERING WORKSPACE"}
              </div>
              <h1>
                {page === "Overview"
                  ? "Engineering, backed by evidence."
                  : page}
              </h1>
              <p>{descriptions[page] || descriptions.Overview}</p>
              <a
                className="context-help"
                href={`/guide/${guideForPage[page] || "start"}`}
              >
                What is {page === "Overview" ? "ProjectTrace" : page}?{" "}
                <CircleHelp size={13} />
              </a>
            </div>
            {!administration &&
              engineeringAllowed &&
              featureAllowed("analyses") &&
              (featureAllowed("zip_import") ||
                featureAllowed("public_github")) &&
              !data?.demo &&
              (page === "Repositories" || !data?.repositories.length) && (
                <button
                  className="secondary"
                  onClick={() => {
                    setImportTarget("NEW");
                    setImporting(true);
                  }}
                >
                  <Upload size={15} /> Import repository
                </button>
              )}
          </div>
          {!administration && identity.access && (
            <OwnershipNotices
              changed={refreshAccess}
              userId={identity.access.user_id}
            />
          )}
          {page === "Settings" && identity.access && <OwnNotifications />}
          {administration ? (
            <Administration identity={identity} changed={refreshAccess} />
          ) : !engineeringAllowed ? (
            <div className="error" role="alert">
              This feature is unavailable by your access policy. Contact your
              organization administrator. Existing published evidence remains
              retained.
            </div>
          ) : summary.isLoading ? (
            <div className="loading">
              <LoaderCircle className="spin" />{" "}
              {listView
                ? "Loading repositories…"
                : "Loading engineering evidence…"}
            </div>
          ) : summary.isError ? (
            <div className="error" role="alert">
              {summary.error.message}
              <button onClick={() => summary.refetch()}>Retry</button>
            </div>
          ) : (
            data && (
              <>
                {data.analysis?.warnings?.map((warning) => (
                  <p className="error" role="alert" key={warning}>
                    {warning}
                  </p>
                ))}
                {listView && (
                  <div className="filters">
                    <label>
                      Search repositories{" "}
                      <input
                        aria-label="Search repositories"
                        value={repositorySearch}
                        onChange={(event) =>
                          setRepositorySearch(event.target.value)
                        }
                      />
                    </label>
                    <span>
                      {data.repository_page?.total} matching repositories
                    </span>
                    <button
                      disabled={!repositoryOffset}
                      onClick={() =>
                        setRepositoryOffset(Math.max(0, repositoryOffset - 25))
                      }
                    >
                      Previous repositories
                    </button>
                    <button
                      disabled={!data.repository_page?.has_more}
                      onClick={() => setRepositoryOffset(repositoryOffset + 25)}
                    >
                      Next repositories
                    </button>
                  </div>
                )}
                {!data.repositories.length &&
                !["Connections", "Settings", "Audit Trail"].includes(page) ? (
                  <Empty
                    title={
                      listView &&
                      (repositorySearch ||
                        repositoryOffset ||
                        repoFilter !== "ALL")
                        ? "No repositories match this selection."
                        : "Import a repository to begin analysis."
                    }
                  >
                    {listView &&
                    (repositorySearch ||
                      repositoryOffset ||
                      repoFilter !== "ALL")
                      ? "Change the search, repository selection or page."
                      : "Use Import repository to upload your own source ZIP. Native analysis works without external connections."}
                  </Empty>
                ) : recordView && records.isLoading ? (
                  <p role="status">Loading this page of records…</p>
                ) : recordView && records.isError ? (
                  <div className="error" role="alert">
                    Records unavailable: {records.error.message}
                    <button onClick={() => records.refetch()}>
                      Retry records
                    </button>
                  </div>
                ) : page === "Overview" ? (
                  <Overview data={data} onOpen={open} navigate={navigate} />
                ) : ["Systems", "Components", "Repositories"].includes(page) ? (
                  <RepositoryPage
                    data={data}
                    page={page}
                    navigate={navigate}
                    onExplore={(id) => {
                      setRepoFilter(id);
                      setSelected(null);
                      navigate("Evidence");
                    }}
                    onImport={(repository) => {
                      setImportTarget(repository || "NEW");
                      setImporting(true);
                    }}
                  />
                ) : page === "Claim Ledger" || page === "Architecture" ? (
                  <>
                    <Filters
                      filter={filter}
                      setFilter={setFilter}
                      query={query}
                      setQuery={setQuery}
                      repoFilter={repoFilter}
                      setRepoFilter={setRepoFilter}
                      repositories={scopeRepositories}
                      statuses={[
                        "VERIFIED",
                        "INFERRED",
                        "UNVERIFIED",
                        "CONTRADICTED",
                        "STALE",
                      ]}
                    />
                    <div className="section-head">
                      <h2>
                        {page === "Architecture"
                          ? "Architecture statements"
                          : "Current engineering claims"}
                      </h2>
                      <span>
                        {data.record_page?.total ??
                          filtered(
                            data.claim.filter(
                              (i) =>
                                page !== "Architecture" ||
                                i.category === "ARCHITECTURE",
                            ),
                          ).length}{" "}
                        claims
                      </span>
                    </div>
                    <DataTable
                      emptyTitle={tableEmpty[0]}
                      emptyDetail={tableEmpty[1]}
                      items={filtered(
                        data.claim.filter(
                          (i) =>
                            page !== "Architecture" ||
                            i.category === "ARCHITECTURE",
                        ),
                      )}
                      onOpen={open}
                    />
                  </>
                ) : page === "Code Quality" ? (
                  <Suspense fallback={<p>Loading Code Intelligence…</p>}>
                    <CodeQuality
                      repositories={data.repositories}
                      selectedRepository={repoFilter}
                      role={identity.role}
                      onOpen={open}
                    />
                  </Suspense>
                ) : page === "Infrastructure" ? (
                  <Suspense fallback={<p>Loading Infrastructure…</p>}>
                    <Infrastructure
                      repository={repoFilter}
                      snapshot={
                        repoFilter !== "ALL"
                          ? data.repositories[0]?.snapshot?.id
                          : undefined
                      }
                      role={identity.role}
                      onOpen={open}
                    />
                  </Suspense>
                ) : page === "Engineering Changes" ? (
                  <Suspense fallback={<p>Loading Engineering Changes…</p>}>
                    <EngineeringChanges repository={repoFilter} onOpen={open} />
                  </Suspense>
                ) : page === "Trust & Coverage" ? (
                  <Suspense fallback={<p>Loading Trust &amp; Coverage…</p>}>
                    <EnterpriseTrust
                      role={identity.role}
                      repository={repoFilter}
                      currentSnapshot={
                        repoFilter !== "ALL"
                          ? data.repositories[0]?.snapshot?.id
                          : undefined
                      }
                    />
                  </Suspense>
                ) : [
                    "Findings",
                    "Security",
                    "Secrets",
                    "Code Quality",
                    "Infrastructure",
                  ].includes(page) ? (
                  <>
                    <div className="stats compact">
                      {["CRITICAL", "HIGH", "MEDIUM", "LOW"].map((s) => (
                        <div key={s}>
                          <span>{s.toLowerCase()}</span>
                          <strong>
                            {data.record_page?.severity_counts[s] ??
                              data.finding.filter(
                                (f) =>
                                  f.severity === s &&
                                  (page === "Findings" ||
                                    (page === "Security" &&
                                      isSecurityFinding(f)) ||
                                    (page === "Secrets" &&
                                      f.category === "SECRET") ||
                                    (page === "Code Quality" &&
                                      f.category === "QUALITY") ||
                                    (page === "Infrastructure" &&
                                      f.category === "IAC")),
                              ).length}
                          </strong>
                        </div>
                      ))}
                    </div>
                    {page === "Security" && (
                      <div className="context-note">
                        <strong>
                          {
                            data.finding.filter(
                              (item) =>
                                item.classification ===
                                "CONFIRMED_STATIC_FINDING",
                            ).length
                          }{" "}
                          confirmed static flows ·{" "}
                          {
                            data.finding.filter(
                              (item) =>
                                item.classification === "SECURITY_HOTSPOT",
                            ).length
                          }{" "}
                          security hotspots on this page
                        </strong>
                        <p>
                          Static flows show modeled source-to-sink paths.
                          Hotspots require context review. Runtime reachability
                          remains unobserved.
                        </p>
                      </div>
                    )}

                    <Filters
                      filter={filter}
                      setFilter={setFilter}
                      query={query}
                      setQuery={setQuery}
                      repoFilter={repoFilter}
                      setRepoFilter={setRepoFilter}
                      repositories={scopeRepositories}
                      statuses={[
                        "CRITICAL",
                        "HIGH",
                        "MEDIUM",
                        "LOW",
                        "OPEN",
                        "CONFIRMED",
                        "RESOLVED",
                        "FALSE_POSITIVE",
                        "REVIEW_REQUIRED",
                        "CONFIRMED_STATIC_FINDING",
                        "SECURITY_HOTSPOT",
                      ]}
                    />
                    <DataTable
                      emptyTitle={tableEmpty[0]}
                      emptyDetail={tableEmpty[1]}
                      mode="finding"
                      items={filtered(
                        data.finding.filter(
                          (f) =>
                            page === "Findings" ||
                            (page === "Security" && isSecurityFinding(f)) ||
                            (page === "Secrets" && f.category === "SECRET") ||
                            (page === "Code Quality" &&
                              f.category === "QUALITY") ||
                            (page === "Infrastructure" && f.category === "IAC"),
                        ),
                      )}
                      onOpen={open}
                    />
                    {page === "Code Quality" && (
                      <div className="context-note">
                        Python uses native AST quality rules. JavaScript,
                        TypeScript, TSX and Java use versioned syntax grammars.
                        Metrics disclose their formulas; complete control-flow,
                        dead-code and unused-symbol resolution remain outside
                        coverage.
                      </div>
                    )}
                    <AnalysisCoverage data={data} />
                  </>
                ) : page === "Drift" ? (
                  <>
                    <Filters
                      filter={filter}
                      setFilter={setFilter}
                      query={query}
                      setQuery={setQuery}
                      repoFilter={repoFilter}
                      setRepoFilter={setRepoFilter}
                      repositories={scopeRepositories}
                      statuses={[
                        "CONTRADICTED",
                        "UNVERIFIED",
                        "OPEN",
                        "RESOLVED",
                      ]}
                    />
                    <DataTable
                      emptyTitle={tableEmpty[0]}
                      emptyDetail={tableEmpty[1]}
                      mode="drift"
                      items={filtered(data.drift)}
                      onOpen={open}
                    />
                    <ImpactSummary data={data} onOpen={open} />
                  </>
                ) : page === "Dependencies" ? (
                  <Dependencies data={data} onOpen={open} />
                ) : page === "Pull Requests" ? (
                  <PullRequests data={data} onOpen={open} />
                ) : page === "Evidence" ? (
                  <Evidence data={data} onOpen={open} />
                ) : page === "Evidence Graph" ? (
                  <Suspense
                    fallback={
                      <div className="loading">Loading evidence graph…</div>
                    }
                  >
                    <Graph data={data} onOpen={open} />
                  </Suspense>
                ) : page === "Ask Engineering" ? (
                  <Investigation data={data} onOpen={open} />
                ) : page === "Audit Trail" ? (
                  <AuditPage
                    query={query}
                    setQuery={setQuery}
                    repository={repoFilter}
                  />
                ) : page === "Policies" ? (
                  <PolicyPage data={data} />
                ) : page === "Connections" ? (
                  <IntegrationPage />
                ) : [
                    "Cloud",
                    "Cloud Assets",
                    "Cloud Identities",
                    "Exposure",
                    "Risk Paths",
                  ].includes(page) ? (
                  <NativeCloudEvidence
                    page={page}
                    data={data}
                    onOpen={open}
                    role={identity.role}
                  />
                ) : page === "API Integrity" ? (
                  <DataTable
                    mode="claim"
                    items={data.claim.filter((item) => item.category === "API")}
                    onOpen={open}
                    emptyTitle="No supported API contracts"
                    emptyDetail="Import an OpenAPI contract and supported route implementations to compare their evidence."
                  />
                ) : page === "Reviews" ? (
                  <>
                    <h2>Current review decisions</h2>
                    <DataTable
                      mode="finding"
                      items={[
                        ...data.claim,
                        ...data.finding,
                        ...data.drift,
                      ].filter(
                        (item) =>
                          item.review_status && item.review_status !== "OPEN",
                      )}
                      onOpen={open}
                      emptyTitle="No current review decisions"
                      emptyDetail="Open a claim or finding to review its evidence and record a decision."
                    />
                  </>
                ) : page === "Settings" ? (
                  <div className="settings-panel">
                    <Suspense fallback={<p>Loading trust controls…</p>}>
                      <EnterpriseTrust role={identity.role} compact />
                    </Suspense>
                    <NativeProfiles
                      repository={repoFilter}
                      role={identity.role}
                    />
                    <h2>Workspace preferences</h2>
                    <ThemeControl />
                    <h2>Identity & permissions</h2>
                    <p>
                      {identity.email} · {identity.role}
                    </p>
                    <p>
                      Repository grants are enforced on the server for claims,
                      evidence, graph, questions, and exports.
                    </p>
                    <h2>Data & privacy</h2>
                    <p>
                      Local snapshots store redacted source, SHA-256 hashes,
                      derived claims and findings. No source is sent to external
                      AI. Review decisions are retained in an append-oriented
                      audit trail.
                    </p>
                    <div className="context-note">
                      Local demo adapter: SQLite. Live integrations and
                      enterprise identity are not configured. This build has not
                      passed production deployment gates.
                    </div>
                  </div>
                ) : (
                  <Empty title="Page unavailable">
                    Choose a page in the workspace navigation.
                  </Empty>
                )}
                {recordView && records.data && !records.isError && (
                  <div className="filters" aria-label="Record pagination">
                    <span>
                      {records.data.total === 0
                        ? "0 matching records"
                        : `${records.data.offset + 1}–${Math.min(records.data.offset + records.data.items.length, records.data.total)} of ${records.data.total} matching records`}
                    </span>
                    <button
                      disabled={!recordOffset || records.isFetching}
                      onClick={() =>
                        setRecordOffset(Math.max(0, recordOffset - 50))
                      }
                    >
                      Previous records
                    </button>
                    <button
                      disabled={!records.data.has_more || records.isFetching}
                      onClick={() => setRecordOffset(recordOffset + 50)}
                    >
                      Next records
                    </button>
                  </div>
                )}
              </>
            )
          )}
        </main>
        <footer className="footer">
          <span>
            <Waypoints size={13} /> Evidence first. Every conclusion has a
            scope.
          </span>
          <span>Static analysis · v1.6.0</span>
        </footer>
      </div>
      {selected && data && (
        <Inspector
          item={selected}
          data={data}
          onClose={() => setSelected(null)}
          role={identity.role}
          onOpen={open}
          onUpdated={(item) => {
            setSelected((current) =>
              current?.id === item.id ? item : current,
            );
            client.invalidateQueries({ queryKey: ["workspace"] });
            client.invalidateQueries({ queryKey: ["workspace-records"] });
            client.invalidateQueries({ queryKey: ["audit"] });
            client.invalidateQueries({ queryKey: ["quality-rows"] });
            client.invalidateQueries({ queryKey: ["quality-overview"] });
          }}
        />
      )}
      {importing && (
        <ImportDialog
          access={identity.access}
          repositories={data?.repositories || []}
          initialTarget={importTarget}
          onRefresh={() =>
            client.invalidateQueries({ queryKey: ["workspace"] })
          }
          onClose={() => setImporting(false)}
          onConnect={() => {
            setImporting(false);
            navigate("Connections");
          }}
          onDone={(repository) => {
            setRepoFilter(repository);
            setImporting(false);
            client.invalidateQueries({ queryKey: ["workspace"] });
            navigate("Repositories");
          }}
        />
      )}
      {tour && (
        <Modal
          title="Follow one engineering change"
          onClose={() => setTour(false)}
        >
          <div className="tour">
            <span className="eyebrow">THE NORTHSTAR STORY</span>
            <h3>A code change made the README untrue.</h3>
            <p>
              PR #1842 replaces JWT with server-side sessions. The documentation
              still promises JWT. ProjectTrace connects the claim, current code,
              change history, and review action.
            </p>
            {[
              ["01", "See the contradicted claim", "Claim Ledger"],
              ["02", "Inspect the PR gate", "Pull Requests"],
              ["03", "Review the evidence graph", "Evidence Graph"],
              ["04", "Follow the decision history", "Audit Trail"],
            ].map(([n, title, target]) => (
              <button
                key={n}
                onClick={() => {
                  setTour(false);
                  navigate(target);
                }}
              >
                <code>{n}</code>
                <strong>{title}</strong>
                <ArrowRight size={17} />
              </button>
            ))}
            <small className="subtle">
              All demo findings come from safe static fixtures. No fixture is
              executed.
            </small>
          </div>
        </Modal>
      )}
      {command && (
        <Modal title="Search your workspace" onClose={() => setCommand(false)}>
          <CommandPalette
            data={data}
            navigate={(target) => {
              setCommand(false);
              navigate(target);
            }}
            onOpen={(item) => {
              setCommand(false);
              open(item);
            }}
          />
        </Modal>
      )}
    </div>
  );
}

function Filters({
  filter,
  setFilter,
  query,
  setQuery,
  repoFilter,
  setRepoFilter,
  repositories,
  statuses,
}: {
  filter: string;
  setFilter: (s: string) => void;
  query: string;
  setQuery: (s: string) => void;
  repoFilter: string;
  setRepoFilter: (s: string) => void;
  repositories: Repository[];
  statuses: string[];
}) {
  return (
    <div className="filters">
      <div className="filter-input">
        <Search size={15} />
        <input
          aria-label="Filter results"
          placeholder="Filter claims, paths, or owners…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>
      <select
        aria-label="Status filter"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
      >
        <option value="ALL">All statuses</option>
        {statuses.map((s) => (
          <option key={s} value={s}>
            {s.replaceAll("_", " ")}
          </option>
        ))}
      </select>
      <span className="subtle">
        {repoFilter === "ALL"
          ? "All repositories"
          : repositories.find((r) => r.id === repoFilter)?.name}
      </span>
      <button
        className="text-button"
        onClick={() => {
          setFilter("ALL");
          setQuery("");
          setRepoFilter(repoFilter);
        }}
      >
        Clear
      </button>
    </div>
  );
}

export function Overview({
  data,
  onOpen,
  navigate,
}: {
  data: Workspace;
  onOpen: (i: Item) => void;
  navigate: (s: string) => void;
}) {
  const claimCount = data.counts?.totals.claim ?? data.claim.length;
  const claimStatus = (state: string) =>
    data.counts?.claim_status[state] ??
    data.claim.filter((c) => c.status === state).length;
  const verified = claimStatus("VERIFIED");
  const contradicted = data.claim
    .filter((c) => c.status === "CONTRADICTED")
    .sort(
      (a, b) =>
        Number(b.category === "AUTHENTICATION") -
        Number(a.category === "AUTHENTICATION"),
    );
  const risk = data.finding.filter(
    (f) =>
      ["HIGH", "CRITICAL"].includes(f.severity || "") &&
      !["RESOLVED", "FALSE_POSITIVE"].includes(f.review_status || ""),
  );
  const primary = contradicted[0];
  const demoStory =
    primary?.scope?.repository === "identity-api" &&
    data.repositories.some(
      (r) => r.id === primary.scope?.repository_id && r.provider === "DEMO",
    );
  return (
    <>
      {data.repositories.some((repo) =>
        isAnalysisActive(repositoryState(repo)),
      ) && (
        <p className="context-note" role="status">
          Analysis is still running. These counts describe published snapshots
          and exclude unfinished attempts.
        </p>
      )}
      {data.repositories.some((repo) => repo.snapshot) &&
        ["FAILED", "CANCELLED"].includes(data.analysis.state) && (
          <p className="context-note" role="status">
            The latest attempt {data.analysis.state.toLowerCase()}. These counts
            describe retained published snapshots; unfinished attempts are
            excluded.
          </p>
        )}
      <div className="stats">
        <div>
          <span>Engineering systems</span>
          <strong>
            {new Set(data.repositories.map((r) => r.system)).size}
          </strong>
          <small>{data.repositories.length} repositories in scope</small>
        </div>
        <div>
          <span>Engineering claims</span>
          <strong>{claimCount}</strong>
          <small>{verified} directly verified</small>
        </div>
        <div>
          <span>Claims to review</span>
          <strong className="warning-text">{claimCount - verified}</strong>
          <small>
            {claimStatus("CONTRADICTED")} contradicted ·{" "}
            {data.counts?.totals.drift ?? data.drift.length} drift events
          </small>
        </div>
        <div>
          <span>Material findings</span>
          <strong>{data.counts?.material_findings ?? risk.length}</strong>
          <small>High or critical · static evidence</small>
        </div>
      </div>
      <div className="overview-grid">
        <section className="story-panel">
          <div className="section-head">
            <span className="eyebrow">ENGINEERING INTENT → REALITY</span>
            <Badge value={overviewState(data)} />
          </div>
          <h2>
            {primary
              ? data.drift.some(
                  (d) =>
                    d.scope?.repository_id === primary.scope?.repository_id,
                )
                ? "A change landed. The claim didn’t."
                : "Documentation and implementation disagree."
              : "Your engineering evidence is connected."}
          </h2>
          <p>
            {demoStory
              ? "Identity Platform moved to session authentication. Its README still describes JWT. One change connects documentation integrity and security review."
              : primary?.reason ||
                "Explore current engineering statements and their supporting evidence."}
          </p>
          {primary && (
            <>
              <div className="claim-story">
                <div>
                  <small>WHAT THE DOCUMENT SAYS</small>
                  <strong>“{primary.text}”</strong>
                  <code>
                    {primary.path}:{primary.line}
                  </code>
                </div>
                <ArrowRight className="story-arrow" />
                <div>
                  <small>WHAT THE CODE CONFIGURES</small>
                  <strong>
                    {demoStory
                      ? "Server-side sessions"
                      : "Conflicting current evidence"}
                  </strong>
                  <code>
                    {demoStory
                      ? "auth/session.py:4"
                      : data.evidence.find((e) =>
                          primary.contradicting_ids?.includes(e.id),
                        )?.path}
                  </code>
                </div>
              </div>
              <div className="story-bottom">
                <span>
                  <GitPullRequest size={15} />{" "}
                  {demoStory ? "PR #1842" : primary.scope?.branch}{" "}
                  <span className="subtle">· {primary.owner}</span>
                </span>
                <button className="primary" onClick={() => onOpen(primary)}>
                  Inspect the evidence <ArrowRight size={15} />
                </button>
              </div>
            </>
          )}
        </section>
        <section className="integrity-panel">
          <div className="section-head">
            <h2>Verification coverage</h2>
            <CircleHelp size={15} />
          </div>
          <div className="coverage-number">
            {verified}
            <span> / {claimCount}</span>
          </div>
          <p>claims directly supported by current static evidence</p>
          <div
            className="coverage-bar"
            aria-label={`${verified} of ${claimCount} verified`}
          >
            {[
              "VERIFIED",
              "INFERRED",
              "UNVERIFIED",
              "CONTRADICTED",
              "STALE",
            ].map((s) => (
              <span
                key={s}
                className={s.toLowerCase()}
                style={{
                  flex: claimStatus(s),
                }}
              />
            ))}
          </div>
          <div className="legend">
            {[
              "VERIFIED",
              "INFERRED",
              "UNVERIFIED",
              "CONTRADICTED",
              "STALE",
            ].map((s) => (
              <div key={s}>
                <span>
                  <i className={s.toLowerCase()} />
                  {s.toLowerCase()}
                </span>
                <strong>{claimStatus(s)}</strong>
              </div>
            ))}
          </div>
          <button
            className="text-button"
            onClick={() => navigate("Claim Ledger")}
          >
            Open Claim Ledger <ArrowRight size={14} />
          </button>
        </section>
      </div>
      <div className="section-head section-space">
        <h2>Systems in view</h2>
        <button className="text-button" onClick={() => navigate("Systems")}>
          All systems <ArrowRight size={14} />
        </button>
      </div>
      <div className="system-list">
        {data.repositories.map((repo) => {
          const claims = data.claim.filter(
            (c) => c.scope?.repository_id === repo.id,
          );
          const findings = data.finding.filter(
            (f) => f.scope?.repository_id === repo.id,
          );
          return (
            <button key={repo.id} onClick={() => navigate("Repositories")}>
              <div className="system-icon">
                <Boxes size={20} />
              </div>
              <div>
                <strong>{repo.system}</strong>
                <small>
                  {repo.name} · {repo.owner}
                </small>
              </div>
              <span>
                {data.counts?.repositories[repo.id]?.totals.claim ??
                  claims.length}{" "}
                claims
              </span>
              <Badge
                value={
                  !["COMPLETED", "COMPLETED_NO_FINDINGS"].includes(
                    repositoryState(repo),
                  )
                    ? repositoryState(repo)
                    : (data.counts?.repositories[repo.id]?.totals.finding ??
                        findings.length)
                      ? "REVIEW_REQUIRED"
                      : "NO_FINDINGS_IN_SCOPE"
                }
              />
              <ChevronRight size={16} />
            </button>
          );
        })}
      </div>
      <div className="section-head section-space">
        <h2>Priority review queue</h2>
        <button className="text-button" onClick={() => navigate("Findings")}>
          All findings <ArrowRight size={14} />
        </button>
      </div>
      <DataTable
        items={risk.slice(0, 5)}
        mode="finding"
        onOpen={onOpen}
        emptyTitle={
          data.counts?.material_findings
            ? `${data.counts.material_findings} findings require review; open All findings.`
            : "No high or critical findings in the current results."
        }
        emptyDetail="Review analyzer coverage and unchecked dependencies before drawing a security conclusion."
      />
      <AnalysisCoverage data={data} />
      <div className="context-note">
        <Shield size={16} />
        <span>
          Conclusions are scoped to imported source snapshots. Runtime,
          deployment exposure, and live provider connections are not verified.
        </span>
      </div>
    </>
  );
}

export function RepositoryPage({
  data,
  page,
  navigate,
  onImport,
  onExplore,
}: {
  data: Workspace;
  page: string;
  navigate: (s: string) => void;
  onImport: (repository?: string) => void;
  onExplore?: (repository: string) => void;
}) {
  const client = useQueryClient();
  const [retrying, setRetrying] = useState<string | null>(null);
  const [retryError, setRetryError] = useState("");
  async function retryAnalysis(jobId: string) {
    setRetrying(jobId);
    setRetryError("");
    try {
      await api(`/jobs/${jobId}/retry`, {});
      await client.invalidateQueries({ queryKey: ["workspace"] });
    } catch (error) {
      setRetryError(
        error instanceof Error ? error.message : "Analysis retry failed.",
      );
    } finally {
      setRetrying(null);
    }
  }
  return (
    <>
      <div className="section-head">
        <h2>
          {data.repository_page?.total ?? data.repositories.length} repositories
          · {data.repositories.length} on this page
        </h2>
        {data.demo && (
          <span className="subtle">
            Demo workspace · sign in to import your own source
          </span>
        )}
      </div>
      {retryError && (
        <p className="error" role="alert">
          {retryError}
        </p>
      )}
      <div className="repo-grid">
        {data.repositories.map((r) => (
          <article className="repo-card" key={r.id}>
            <div className="section-head">
              <GitBranch size={21} />
              <Badge value={r.provider} />
            </div>
            <h2>
              {page === "Systems"
                ? r.system
                : page === "Components"
                  ? r.component
                  : r.name}
            </h2>
            <p>
              {r.system} / {r.component}
            </p>
            <dl>
              <dt>Owner</dt>
              <dd>{r.owner}</dd>
              <dt>Captured text files</dt>
              <dd>
                {r.snapshot ? r.snapshot.file_count : "Awaiting snapshot"}
              </dd>
              <dt>Snapshot</dt>
              <dd>
                <code>{r.snapshot?.commit.slice(0, 12) || "Not created"}</code>
              </dd>
              <dt>Branch</dt>
              <dd>
                <code>{r.snapshot?.branch || r.latest_job?.branch || "—"}</code>
              </dd>
              <dt>Analysis</dt>
              <dd>
                <Badge value={repositoryState(r)} />
              </dd>
              <dt>Stage</dt>
              <dd>
                {r.latest_job?.stage || r.snapshot?.status || "Not started"}
              </dd>
              <dt>Started</dt>
              <dd>{date(r.latest_job?.started_at)}</dd>
              <dt>Finished</dt>
              <dd>{date(r.latest_job?.finished_at)}</dd>
              <dt>Claims</dt>
              <dd>
                {r.snapshot?.claim_extraction
                  ? `${r.snapshot.claim_extraction.implementation} implementation · ${r.snapshot.claim_extraction.documentation} documentation`
                  : r.snapshot
                    ? "Legacy snapshot"
                    : "Not extracted"}
              </dd>
            </dl>
            {r.latest_job?.warnings?.map((w, i) => (
              <p className="context-note" key={i}>
                {w.path}: {w.message}
              </p>
            ))}
            {r.latest_job?.errors?.map((error) => (
              <p className="error" role="alert" key={error}>
                {error}
              </p>
            ))}
            {r.latest_job?.error_detail?.budget && (
              <p className="context-note">
                {r.latest_job.error_detail.budget}:{" "}
                {r.latest_job.error_detail.actual} /{" "}
                {r.latest_job.error_detail.maximum}
              </p>
            )}
            {r.latest_job?.error_detail?.remediation && (
              <p className="context-note">
                {r.latest_job.error_detail.remediation}
              </p>
            )}
            {r.snapshot?.source_provenance?.source_url && (
              <p className="subtle">
                {r.snapshot.source_provenance.source_url} ·{" "}
                {r.snapshot.source_provenance.ref}
              </p>
            )}
            {!data.demo && (
              <button className="secondary" onClick={() => onImport(r.id)}>
                Upload new snapshot
              </button>
            )}
            {!data.demo &&
              (data.capabilities?.job_mode === "celery" ||
                (data.capabilities?.job_mode === "local" &&
                  (["ZIP", "LOCAL", "GITHUB_PUBLIC"].includes(r.provider) ||
                    data.capabilities.private_scm_available))) &&
              r.latest_job &&
              ["FAILED", "PARTIAL", "QUEUED"].includes(
                r.latest_job.state || "",
              ) && (
                <button
                  className="secondary"
                  disabled={retrying !== null}
                  onClick={() => retryAnalysis(r.latest_job!.id)}
                >
                  {retrying === r.latest_job.id
                    ? "Retrying analysis…"
                    : "Retry analysis"}
                </button>
              )}
            <div className="repo-card-footer">
              <span className="subtle">
                {r.snapshot
                  ? r.snapshot.commit_source === "GIT_SHA"
                    ? "Provider Git revision"
                    : "Content-addressed snapshot"
                  : "Job output pending"}
              </span>
              <button
                className="text-button"
                onClick={() =>
                  onExplore ? onExplore(r.id) : navigate("Evidence")
                }
              >
                Explore <ArrowRight size={14} />
              </button>
            </div>
            {r.snapshot && <RepositoryDiagnostics repository={r} />}
          </article>
        ))}
      </div>
      <div className="context-note">
        ZIP snapshots use a content digest. GitHub snapshots identify the
        resolved provider commit and ref. Review Trust & Coverage for partial,
        skipped and unsupported files before drawing conclusions.
      </div>
      {page === "Repositories" && <AnalysisCoverage data={data} />}
    </>
  );
}

function RepositoryDiagnostics({ repository }: { repository: Repository }) {
  const [expanded, setExpanded] = useState(false);
  const snapshot = repository.snapshot;
  const diagnostic = useQuery({
    queryKey: ["repository-diagnostics", repository.id, snapshot?.id],
    queryFn: () =>
      api<{
        partial_engines: Record<string, string>;
        warning_count: number;
        warnings: { path?: string; message: string }[];
        warnings_complete: boolean;
        effective_claim_extraction_state: string;
      }>(
        `/repositories/${encodeURIComponent(repository.id)}/analysis?snapshot_id=${encodeURIComponent(snapshot!.id)}`,
      ),
    enabled: expanded && !!snapshot,
    retry: false,
  });
  if (!snapshot) return null;
  return (
    <details onToggle={(event) => setExpanded(event.currentTarget.open)}>
      <summary>Analysis diagnostics · {snapshot.status}</summary>
      <p>
        Snapshot <code>{snapshot.id}</code> · runtime unobserved
      </p>
      {snapshot.coverage_summary && (
        <p>
          {snapshot.coverage_summary.source_files_parsed} /{" "}
          {snapshot.coverage_summary.source_files} source files parsed (
          {snapshot.coverage_summary.source_analysis_percent?.toFixed(2)}%).
        </p>
      )}
      {diagnostic.isLoading ? (
        <p role="status">Loading diagnostics…</p>
      ) : diagnostic.isError ? (
        <p role="alert">
          Diagnostics unavailable: {diagnostic.error.message}{" "}
          <button onClick={() => diagnostic.refetch()}>
            Retry diagnostics
          </button>
        </p>
      ) : (
        diagnostic.data && (
          <>
            <p>
              Claim extraction:{" "}
              {diagnostic.data.effective_claim_extraction_state}.{" "}
              {diagnostic.data.warning_count} recorded diagnostics.
            </p>
            {Object.entries(diagnostic.data.partial_engines).map(
              ([name, state]) => (
                <p key={name}>
                  {name}: {state}
                </p>
              ),
            )}
            {diagnostic.data.warnings.map((warning, i) => (
              <p key={i}>
                {warning.path}: {warning.message}
              </p>
            ))}
            {!diagnostic.data.warnings_complete && (
              <p>
                First 50 diagnostics shown. Trust &amp; Coverage provides
                paginated file coverage.
              </p>
            )}
          </>
        )
      )}
    </details>
  );
}

export function AnalysisCoverage({ data }: { data: Workspace }) {
  return (
    <section
      className="analysis-coverage"
      aria-label="Native analyzer coverage"
    >
      <div className="section-head section-space">
        <h2>Native analyzer coverage</h2>
        <span>Reported by the analysis job</span>
      </div>
      {data.repositories.map((repository) => {
        const engines = repositoryEngines(repository);
        return (
          <details
            key={repository.id}
            open={
              data.repositories.length === 1 ||
              ["FAILED", "PARTIAL"].includes(repositoryState(repository))
            }
          >
            <summary>
              <strong>{repository.name}</strong>
              <Badge value={repositoryState(repository)} />
            </summary>
            {engines && Object.keys(engines).length ? (
              <div className="engine-list">
                {Object.entries(engines).map(([name, engine]) => (
                  <EngineCoverage key={name} name={name} engine={engine} />
                ))}
              </div>
            ) : (
              <p className="subtle">
                No per-analyzer diagnostic was recorded for this job. Aggregate
                completion does not establish coverage of every language or
                rule.
              </p>
            )}
          </details>
        );
      })}
      <p className="subtle">
        Completed means the supported checks ran. Skipped, unchecked, failed,
        and unsupported areas remain outside that conclusion. Static checks do
        not establish runtime safety.
      </p>
    </section>
  );
}

function EngineCoverage({
  name,
  engine,
}: {
  name: string;
  engine: EngineResult;
}) {
  const coverage = Array.isArray(engine.coverage)
    ? engine.coverage.join(" · ")
    : engine.coverage;
  return (
    <div className="engine-result">
      <div>
        <strong>{name.replaceAll("_", " ")}</strong>
        <Badge value={engine.state} />
      </div>
      {engine.supported_files != null && (
        <p className="subtle">
          {engine.supported_files} supported files
          {engine.findings != null ? ` · ${engine.findings} findings` : ""}
          {engine.declarations != null
            ? ` · ${engine.declarations} declarations`
            : ""}
          {engine.analyzer_version
            ? ` · analyzer ${engine.analyzer_version}`
            : ""}
        </p>
      )}
      {engine.checked_declarations != null && (
        <p className="subtle">
          {engine.checked_declarations} declarations checked ·{" "}
          {engine.failed_declarations || 0} failed ·{" "}
          {engine.unknown_version_declarations || 0} unknown versions ·{" "}
          {engine.unchecked_declarations || 0} unchecked ·{" "}
          {engine.cache_hits || 0} cache hits
        </p>
      )}
      {coverage && <p>{coverage}</p>}
      {engine.limitations?.map((limitation, index) => (
        <p className="subtle" key={index}>
          {limitation}
        </p>
      ))}
      {engine.warnings?.map((warning, index) => (
        <p className="subtle" key={index}>
          {typeof warning === "string"
            ? warning
            : `${warning.path ? warning.path + ": " : ""}${warning.message}`}
        </p>
      ))}
      {engine.errors?.map((error, index) => (
        <p className="error" role="alert" key={index}>
          {error}
        </p>
      ))}
    </div>
  );
}

export function ImpactSummary({
  data,
  onOpen,
}: {
  data: Workspace;
  onOpen: (item: Item) => void;
}) {
  const records = [...data.claim, ...data.finding, ...data.graph_node];
  const compared = data.repositories.filter(
    (repository) => repository.snapshot?.impact?.base_id,
  );
  if (!compared.length) return null;
  return (
    <section className="impact-summary" aria-label="Snapshot change impact">
      <div className="section-head section-space">
        <h2>Snapshot change impact</h2>
        <span>Observed graph relationships</span>
      </div>
      {compared.map((repository) => {
        const impact = repository.snapshot!.impact!;
        const impactCount = (key: string, fallback: number) =>
          repository.snapshot!.impact_list_counts?.[key] ?? fallback;
        const affected = records.filter((record) =>
          impact.affected_claims.includes(record.id),
        );
        return (
          <article key={repository.id}>
            <div className="section-head">
              <h3>{repository.name}</h3>
              <code title={impact.base_id || ""}>
                {impact.base_id?.slice(0, 8)} →{" "}
                {repository.snapshot!.id.slice(0, 8)}
              </code>
            </div>
            <div className="impact-counts">
              <span>
                <strong>
                  {impactCount("changed_files", impact.changed_files.length)}
                </strong>{" "}
                changed files
              </span>
              <span>
                <strong>
                  {impactCount(
                    "affected_claims",
                    impact.affected_claims.length,
                  )}
                </strong>{" "}
                affected claims
              </span>
              <span>
                <strong>
                  {impactCount(
                    "affected_documentation",
                    impact.affected_documentation?.length || 0,
                  )}
                </strong>{" "}
                documentation paths
              </span>
              <span>
                <strong>
                  {impactCount(
                    "affected_api",
                    impact.affected_api?.length || 0,
                  )}
                </strong>{" "}
                API nodes
              </span>
              <span>
                <strong>
                  {impactCount(
                    "affected_findings",
                    impact.affected_findings?.length || 0,
                  )}
                </strong>{" "}
                findings
              </span>
              <span>
                <strong>
                  {impactCount(
                    "affected_policies",
                    impact.affected_policies?.length || 0,
                  )}
                </strong>{" "}
                policies
              </span>
            </div>
            {impact.verification && (
              <p className="subtle">
                {impact.verification.reverified} declared claims reverified ·{" "}
                {impact.verification.reused} declared claims reused from
                unchanged evidence
              </p>
            )}
            <details>
              <summary>Changed source paths (bounded preview)</summary>
              <div className="file-list">
                {impact.changed_files.map((path) => (
                  <div key={path}>
                    <FileCode2 size={14} />
                    <code>{path}</code>
                  </div>
                ))}
              </div>
            </details>
            {affected.map((claim) => (
              <button
                className="answer-claim"
                key={claim.id}
                onClick={() => onOpen(claim)}
              >
                <span>{label(claim)}</span>
                <Badge value={claim.status} />
                <ArrowRight size={14} />
              </button>
            ))}
            {!!impact.removed_claims?.length && (
              <p className="subtle">
                {impactCount("removed_claims", impact.removed_claims.length)}{" "}
                prior claim identities disappeared from this snapshot; their
                evidence remains in snapshot history.
              </p>
            )}
          </article>
        );
      })}
      <p className="subtle">
        Impact follows stored evidence relationships. Runtime calls, deployment
        reachability, and unsupported relationships are not inferred.
        Implementation facts are refreshed from static syntax and configuration.
      </p>
    </section>
  );
}

function Dependencies({
  data,
  onOpen,
}: {
  data: Workspace;
  onOpen: (i: Item) => void;
}) {
  const client = useQueryClient();
  const [advisoryBusy, setAdvisoryBusy] = useState(false);
  const [advisoryError, setAdvisoryError] = useState("");
  const [advisoryNotice, setAdvisoryNotice] = useState("");
  const snapshot =
    data.repositories.length === 1 ? data.repositories[0].snapshot : null;
  useEffect(() => {
    setAdvisoryError("");
    setAdvisoryNotice("");
  }, [snapshot?.id]);
  async function checkAdvisories() {
    if (!snapshot) return;
    setAdvisoryBusy(true);
    setAdvisoryError("");
    setAdvisoryNotice("");
    try {
      const result = await api<{ job_id: string; state: string }>(
        "/snapshots/" + snapshot.id + "/advisories",
        {},
      );
      setAdvisoryNotice(
        result.state === "QUEUED"
          ? "Advisory check queued. Coverage will update as the job progresses."
          : "Advisory job status: " + result.state.replaceAll("_", " "),
      );
      client.invalidateQueries({ queryKey: ["workspace"] });
    } catch (error) {
      setAdvisoryError((error as Error).message);
    } finally {
      setAdvisoryBusy(false);
    }
  }
  return (
    <>
      <div className="section-head">
        <h2>
          {data.counts?.totals.dependency ?? data.dependency.length} dependency
          declarations
        </h2>
        <button
          className="secondary"
          disabled={
            advisoryBusy || !snapshot || !data.capabilities?.advisories_enabled
          }
          onClick={checkAdvisories}
        >
          {advisoryBusy ? (
            <LoaderCircle className="spin" size={14} />
          ) : (
            <Shield size={14} />
          )}{" "}
          Check advisories
        </button>
      </div>
      {!snapshot ? (
        <p className="subtle">
          Select a repository with an analyzed snapshot to check advisories.
        </p>
      ) : !data.capabilities?.advisories_enabled ? (
        <p className="subtle">
          Live advisory lookup is not configured for this workspace. Cached
          advisories and unchecked coverage remain explicit.
        </p>
      ) : null}
      {advisoryError && (
        <p className="error" role="alert">
          {advisoryError}
        </p>
      )}
      {advisoryNotice && (
        <p className="context-note" role="status">
          {advisoryNotice}
        </p>
      )}
      <div
        className="coverage-counts"
        aria-label="Dependency advisory coverage on this page"
      >
        <span>Current page:</span>
        {[
          "VULNERABLE",
          "CHECKED_NO_KNOWN_ADVISORY",
          "NOT_CHECKED",
          "CHECK_FAILED",
          "UNKNOWN_VERSION",
        ].map((state) => (
          <span key={state}>
            <strong>
              {
                data.dependency.filter(
                  (dependency) => dependencyState(dependency) === state,
                ).length
              }
            </strong>{" "}
            {state.replaceAll("_", " ").toLowerCase()}
          </span>
        ))}
      </div>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Package</th>
              <th>Version</th>
              <th>Ecosystem</th>
              <th>Advisory coverage</th>
              <th>Known advisories</th>
              <th>Manifest / license</th>
              <th>Repository</th>
            </tr>
          </thead>
          <tbody>
            {data.dependency.map((d) => (
              <tr key={d.id}>
                <td>
                  <button className="row-link" onClick={() => onOpen(d)}>
                    {d.name}
                    <small>
                      {d.direct == null
                        ? "Unknown directness"
                        : d.direct
                          ? "Direct"
                          : "Transitive"}{" "}
                      dependency
                    </small>
                  </button>
                </td>
                <td>
                  <code>{d.version}</code>
                  {d.version_kind && (
                    <small className="subtle">
                      {" "}
                      {d.version_kind.replaceAll("_", " ").toLowerCase()}
                    </small>
                  )}
                </td>
                <td>{d.ecosystem}</td>
                <td>
                  <Badge value={dependencyState(d)} />
                </td>
                <td>
                  {["VULNERABLE", "CHECKED_NO_KNOWN_ADVISORY"].includes(
                    dependencyState(d),
                  )
                    ? d.vulnerabilities?.length || 0
                    : "—"}
                </td>
                <td>
                  <code>{d.path}</code>
                  <small className="subtle">
                    {" "}
                    {d.license || "License unknown"}
                  </small>
                </td>
                <td>{d.scope?.repository}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="section-head section-space">
        <h2>Export software bill of materials</h2>
        <span>CycloneDX 1.5</span>
      </div>
      <div className="export-list">
        {data.repositories
          .filter((r) => r.snapshot)
          .map((r) => (
            <a
              className="secondary"
              key={r.id}
              href={"/api/sbom/" + r.snapshot!.id}
              target="_blank"
              rel="noreferrer"
            >
              <ArrowDownToLine size={15} />
              {r.name}
            </a>
          ))}
      </div>
      <div className="context-note">
        Cached OSV advisories are attached only to an exact known package
        version. Version constraints remain unchecked. NOT CHECKED means
        vulnerability status is unknown. SBOM dependency relationships are
        limited to the parsed manifest; licenses are shown only when present.
      </div>
      <AnalysisCoverage data={data} />
    </>
  );
}

function PullRequests({
  data,
  onOpen,
}: {
  data: Workspace;
  onOpen: (i: Item) => void;
}) {
  const [selectedPr, setSelectedPr] = useState("");
  const pr = data.pr.find((item) => item.id === selectedPr) || data.pr[0];
  const gate = useQuery({
    queryKey: ["gate", pr?.head_id],
    queryFn: () => api<Gate>("/gate/" + pr?.head_id),
    enabled: !!pr,
  });
  const [claimOffset, setClaimOffset] = useState(0);
  useEffect(() => setClaimOffset(0), [pr?.id]);
  const claimImpact = useQuery({
    queryKey: ["pr-claims", pr?.head_id, claimOffset],
    queryFn: () =>
      api<RecordPage>(
        `/workspace/records?view=Claim%20Ledger&snapshot_id=${encodeURIComponent(pr!.head_id!)}&offset=${claimOffset}&limit=50`,
      ),
    enabled: !!pr?.head_id,
  });
  if (!pr)
    return (
      <Empty title="No pull request analyses">
        Connect an authorized GitHub App to ingest changes. Imported snapshots
        can be compared through the analysis API.
      </Empty>
    );
  return (
    <>
      <div className="pr-heading">
        <label>
          Pull request analysis
          <select
            aria-label="Pull request analysis"
            value={pr.id}
            onChange={(event) => setSelectedPr(event.target.value)}
          >
            {data.pr.map((item) => (
              <option key={item.id} value={item.id}>
                #{item.number} · {item.title}
              </option>
            ))}
          </select>
        </label>
        <GitPullRequest size={25} />
        <div>
          <h2>
            #{pr.number} · {pr.title}
          </h2>
          <p>
            {pr.scope?.repository} · {pr.owner} ·{" "}
            {data.repositories.find((r) => r.id === pr.scope?.repository_id)
              ?.provider === "DEMO"
              ? "demo change"
              : "provider analysis"}
          </p>
        </div>
        <Badge value={gate.data?.overall || pr.gate?.overall} />
      </div>
      <div className="split-layout">
        <section>
          <div className="section-head">
            <h2>Changed files</h2>
            <span>{pr.changed_files?.length} files</span>
          </div>
          <div className="file-list">
            {pr.changed_files?.map((p) => (
              <div key={p}>
                <FileCode2 size={16} />
                <code>{p}</code>
                <Badge value="CHANGED" />
              </div>
            ))}
          </div>
          <div className="section-head section-space">
            <h2>Claim impact</h2>
          </div>
          {claimImpact.isLoading ? (
            <p role="status">Loading claim impact…</p>
          ) : claimImpact.isError ? (
            <p role="alert" className="error">
              Claim impact unavailable: {claimImpact.error.message}
            </p>
          ) : (
            <>
              <DataTable
                items={claimImpact.data?.items || []}
                onOpen={onOpen}
              />
              <p>{claimImpact.data?.total} claims in this head snapshot</p>
              <button
                disabled={!claimOffset}
                onClick={() => setClaimOffset(Math.max(0, claimOffset - 50))}
              >
                Previous claims
              </button>
              <button
                disabled={!claimImpact.data?.has_more}
                onClick={() => setClaimOffset(claimOffset + 50)}
              >
                Next claims
              </button>
            </>
          )}
        </section>
        <section className="gate-panel">
          <div className="section-head">
            <h2>ProjectTrace gate</h2>
            <Badge value="ADVISORY" />
          </div>
          <p>
            One explainable review across security and engineering integrity.
          </p>
          {(gate.data || pr.gate)?.results.map((r, i) => (
            <div className="gate-result" key={i}>
              <Badge value={r.result} />
              <strong>{r.policy}</strong>
              <p>{r.reason}</p>
            </div>
          ))}
          <small className="subtle">
            No check has been published to GitHub. Live integration is not
            configured.
          </small>
        </section>
      </div>
    </>
  );
}

function Evidence({
  data,
  onOpen,
}: {
  data: Workspace;
  onOpen: (i: Item) => void;
}) {
  const [id, setId] = useState(
    data.evidence.find((e) => e.path === "auth/session.py")?.id ||
      data.evidence[0]?.id,
  );
  useEffect(() => {
    if (!data.evidence.some((e) => e.id === id)) setId(data.evidence[0]?.id);
  }, [data.evidence, id]);
  const node = data.evidence.find((e) => e.id === id);
  const source = useQuery({
    queryKey: ["evidence-source", id],
    queryFn: () => api<Item>("/record/" + encodeURIComponent(id || "")),
    enabled: !!id,
  });
  const [relatedOffset, setRelatedOffset] = useState(0);
  useEffect(() => setRelatedOffset(0), [id]);
  const linked = useQuery({
    queryKey: ["evidence-neighborhood", id, relatedOffset],
    queryFn: () =>
      api<{ nodes: Item[]; total: number }>(
        `/graph/neighborhood?node_id=${encodeURIComponent(id || "")}&offset=${relatedOffset}&limit=50`,
      ),
    enabled: !!id,
  });
  const related =
    linked.data?.nodes.filter((item) =>
      ["claim", "finding"].includes(item.kind || ""),
    ) || [];
  return (
    <div className="evidence-layout">
      <aside>
        <span className="eyebrow">SOURCE ARTIFACTS</span>
        {data.repositories.map((r) => (
          <div className="artifact-group" key={r.id}>
            <strong>
              <GitBranch size={14} />
              {r.name}
            </strong>
            {data.evidence
              .filter((e) => e.scope?.repository_id === r.id)
              .map((e) => (
                <button
                  key={e.id}
                  className={id === e.id ? "selected" : ""}
                  onClick={() => setId(e.id)}
                >
                  <FileCode2 size={13} />
                  <span>{e.path}</span>
                </button>
              ))}
          </div>
        ))}
      </aside>
      <section className="source-panel">
        <div className="source-heading">
          <code>{node?.path}</code>
          <Badge value={node?.authority} />
        </div>
        {source.isLoading ? (
          <p role="status">Loading redacted source…</p>
        ) : source.isError ? (
          <p className="error" role="alert">
            Source unavailable: {source.error.message}
          </p>
        ) : (
          <Source item={source.data} />
        )}
        <div className="source-scope">
          <code>
            {node?.scope?.branch} @ {node?.scope?.commit.slice(0, 12)}
          </code>
          <small>Redacted source · static evidence</small>
        </div>
      </section>
      <aside className="related-panel">
        <span className="eyebrow">CONNECTED CONCLUSIONS</span>
        {linked.isLoading ? (
          <p role="status">Loading connected conclusions…</p>
        ) : linked.isError ? (
          <p className="error" role="alert">
            Connected evidence unavailable: {linked.error.message}
          </p>
        ) : related.length ? (
          related.map((c) => (
            <button
              className="related-item"
              key={c.id}
              onClick={() => onOpen(c)}
            >
              <Badge value={c.status || c.severity} />
              <strong>{label(c)}</strong>
              <small>{c.category}</small>
            </button>
          ))
        ) : (
          <p className="subtle">
            No claim or finding in this page of recorded relationships.
          </p>
        )}
        {!!linked.data && (
          <div className="filters">
            <span>{linked.data.total} recorded relationships</span>
            <button
              disabled={!relatedOffset}
              onClick={() => setRelatedOffset(Math.max(0, relatedOffset - 50))}
            >
              Previous relationships
            </button>
            <button
              disabled={relatedOffset + 50 >= linked.data.total}
              onClick={() => setRelatedOffset(relatedOffset + 50)}
            >
              Next relationships
            </button>
          </div>
        )}
      </aside>
    </div>
  );
}

function Investigation({
  data,
  onOpen,
}: {
  data: Workspace;
  onOpen: (i: Item) => void;
}) {
  const [question, setQuestion] = useState(
    "How is authentication implemented?",
  );
  const [repo, setRepo] = useState(
    data.repositories.length === 1
      ? data.repositories[0].id
      : data.repositories.find(
          (r) => r.provider === "DEMO" && r.id === "identity",
        )?.id || "",
  );
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const scopeIds = data.repositories
    .map((r) => `${r.id}:${r.snapshot?.id || ""}`)
    .join(",");
  const requestGeneration = useRef(0);
  useEffect(() => {
    requestGeneration.current++;
    if (repo && !data.repositories.some((r) => r.id === repo))
      setRepo(data.repositories.length === 1 ? data.repositories[0].id : "");
    setAnswer(null);
    setError("");
    setBusy(false);
  }, [scopeIds, repo]);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const generation = requestGeneration.current;
    try {
      const result = await api<Answer>("/ask", {
        question,
        repository_id: repo || null,
        snapshot_ids: data.repositories
          .filter((r) => !repo || r.id === repo)
          .flatMap((r) => (r.snapshot ? [r.snapshot.id] : [])),
      });
      if (requestGeneration.current === generation) setAnswer(result);
    } catch (e) {
      if (requestGeneration.current === generation)
        setError((e as Error).message);
    } finally {
      if (requestGeneration.current === generation) setBusy(false);
    }
  }
  return (
    <>
      <form className="investigation-form" onSubmit={submit}>
        <label>
          Engineering question
          <textarea
            aria-label="Engineering question"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            required
            minLength={3}
            maxLength={1000}
          />
        </label>
        <div>
          <select
            aria-label="Investigation repository"
            value={repo}
            onChange={(e) => setRepo(e.target.value)}
          >
            <option value="">All authorized repositories</option>
            {data.repositories.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
              </option>
            ))}
          </select>
          <button className="primary" disabled={busy}>
            {busy ? (
              <LoaderCircle className="spin" size={16} />
            ) : (
              <Search size={16} />
            )}{" "}
            Investigate with evidence
          </button>
        </div>
      </form>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {answer && (
        <div className="investigation-result">
          <div className="section-head">
            <span className="eyebrow">EVIDENCE-BASED ANSWER</span>
            <Badge value={answer.verification} />
          </div>
          <h2>{answer.answer}</h2>
          <p className="subtle">
            Confidence: {answer.confidence} · {answer.provider}
          </p>
          <div className="section-head section-space">
            <h3>Related claims</h3>
          </div>
          {answer.claims.map((c) => (
            <button
              className="answer-claim"
              key={c.id}
              onClick={() => onOpen(c)}
            >
              <span>{c.text}</span>
              <Badge value={c.status} />
              <ArrowRight size={15} />
            </button>
          ))}
          <div className="section-head section-space">
            <h3>Source evidence</h3>
          </div>
          <div className="export-list">
            {answer.evidence.map((e) => (
              <button
                className="secondary"
                key={e.id}
                onClick={() => onOpen(e)}
              >
                <FileCode2 size={15} />
                {e.path}
              </button>
            ))}
          </div>
          <div className="context-note">{answer.limitations.join(" ")}</div>
        </div>
      )}
    </>
  );
}

function AuditPage({
  query,
  setQuery,
  repository,
}: {
  repository: string;
  query: string;
  setQuery: (s: string) => void;
}) {
  const events = useQuery({
    queryKey: ["audit", repository],
    queryFn: () =>
      api<Item[]>(
        "/audit?limit=200" +
          (repository === "ALL"
            ? ""
            : "&repository_id=" + encodeURIComponent(repository)),
      ),
  });
  return (
    <>
      <div className="filters">
        <div className="filter-input">
          <Search size={15} />
          <input
            aria-label="Filter audit history"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filter actor, action, or reason…"
          />
        </div>
        <span>Most recent 200 events · append-oriented</span>
      </div>
      {events.isLoading ? (
        <p>Loading history…</p>
      ) : events.isError ? (
        <p className="error">{events.error.message}</p>
      ) : (
        <div className="audit-list">
          {events.data
            ?.filter((e) =>
              JSON.stringify(e).toLowerCase().includes(query.toLowerCase()),
            )
            .map((e) => (
              <div key={e.id}>
                <div className="audit-dot" />
                <div>
                  <strong>{e.action?.replaceAll("_", " ")}</strong>
                  <p>
                    {e.data?.reason ||
                      `${e.data?.files || 0} files analyzed; ${e.data?.claims || 0} engineering claims; ${e.data?.findings || 0} findings.`}
                  </p>
                  <span>
                    {e.actor} · <code>{e.repository_id}</code>
                    {e.data?.new && (
                      <>
                        {" "}
                        · {e.data?.old || "NEW"} → <Badge value={e.data.new} />
                      </>
                    )}
                  </span>
                </div>
                <time>{date(e.created_at)}</time>
              </div>
            ))}
        </div>
      )}
    </>
  );
}

function PolicyPage({ data }: { data: Workspace }) {
  const [offset, setOffset] = useState(0);
  const repository =
    data.repositories.length === 1 ? data.repositories[0].id : "ALL";
  useEffect(() => setOffset(0), [repository]);
  const exceptions = useQuery({
    queryKey: ["policy-exceptions", repository, offset],
    queryFn: () =>
      api<{ items: Item[]; total: number; has_more: boolean }>(
        `/trust/exceptions?offset=${offset}&limit=50${repository === "ALL" ? "" : "&repository_id=" + encodeURIComponent(repository)}`,
      ),
  });
  return (
    <>
      <div className="context-note">
        Default policy v1 · Advisory mode. A gate recommends review; it does not
        merge or block a live GitHub PR.
      </div>
      <div className="policy-list">
        {[
          [
            "No high-confidence critical findings",
            "Critical severity AND high confidence",
            "FAIL",
          ],
          [
            "Review material security risks",
            "High / critical finding in supported scope",
            "REVIEW_REQUIRED",
          ],
          [
            "Review contradicted engineering claims",
            "Verification status is CONTRADICTED",
            "REVIEW_REQUIRED",
          ],
        ].map(([title, condition, result]) => (
          <article key={title}>
            <div>
              <h2>{title}</h2>
              <p>When: {condition}</p>
            </div>
            <Badge value={result} />
          </article>
        ))}
      </div>
      <div className="section-head section-space">
        <h2>Expiring exceptions</h2>
        <span>
          {exceptions.data
            ? `${exceptions.data.total} recorded`
            : "Count unavailable"}
        </span>
      </div>
      {exceptions.isLoading ? (
        <p role="status">Loading exceptions…</p>
      ) : exceptions.isError ? (
        <p role="alert" className="error">
          Exceptions unavailable: {exceptions.error.message}
        </p>
      ) : exceptions.data?.items.length ? (
        exceptions.data.items.map((e) => (
          <p key={e.id}>
            {e.reason} · expires {date(e.expires_at)}
          </p>
        ))
      ) : (
        <Empty title="No exceptions recorded">
          Administrators and security reviewers can accept scoped risk with a
          reason and expiry. Expired exceptions no longer change the gate.
        </Empty>
      )}
      {!!exceptions.data?.total && (
        <div className="filters">
          <button
            disabled={!offset}
            onClick={() => setOffset(Math.max(0, offset - 50))}
          >
            Previous exceptions
          </button>
          <button
            disabled={!exceptions.data.has_more}
            onClick={() => setOffset(offset + 50)}
          >
            Next exceptions
          </button>
        </div>
      )}
    </>
  );
}

function IntegrationPage() {
  const result = useQuery({
    queryKey: ["integrations"],
    queryFn: () =>
      api<
        {
          name: string;
          status: string;
          live_verification: string;
          permissions: string;
          last_sync: null;
          group: string;
          optional: boolean;
          implementation: string;
        }[]
      >("/connections"),
  });
  return (
    <div className="integration-list">
      <p className="context-note">
        ProjectTrace native analysis works independently. Connections provide
        optional source synchronization, authorized read-only cloud inventory,
        or AI enrichment.
      </p>
      {result.isLoading ? (
        <p>Loading provider status…</p>
      ) : result.isError ? (
        <p className="error">{result.error.message}</p>
      ) : (
        result.data?.map((i) => (
          <article key={i.name}>
            <div className="integration-icon">
              <Boxes size={22} />
            </div>
            <div>
              <small>
                {i.group}
                {i.optional ? " · OPTIONAL" : " · SOURCE CONNECTIVITY"}
              </small>
              <h2>{i.name}</h2>
              <p>{i.permissions}</p>
              {i.implementation === "DEFERRED" && (
                <p>Adapter deferred in this release.</p>
              )}
              <small>
                Live verification: {i.live_verification.replaceAll("_", " ")} ·
                {i.last_sync ? date(i.last_sync) : "No sync recorded"}
              </small>
            </div>
            <Badge value={i.status} />
          </article>
        ))
      )}
    </div>
  );
}

function AWSInventoryForm({ data, role }: { data: Workspace; role: string }) {
  const client = useQueryClient();
  const [repository, setRepository] = useState(data.repositories[0]?.id || "");
  const [account, setAccount] = useState("");
  const [region, setRegion] = useState("us-east-1");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  if (!["ORG_OWNER", "ADMIN"].includes(role))
    return <p>Organization administrators authorize account inventory.</p>;
  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    try {
      const result = await api<{
        status: string;
        asset_ids: string[];
        warnings: string[];
      }>("/cloud/aws/inventory", {
        repository_id: repository,
        account_id: account,
        region,
      });
      setMessage(
        `${result.asset_ids.length} assets observed · ${result.status}. ${result.warnings.join(" ")}`,
      );
      await client.invalidateQueries();
    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : "Inventory could not be synchronized.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <form className="settings-panel" onSubmit={submit}>
      <label>
        Repository{" "}
        <select
          aria-label="Cloud repository"
          value={repository}
          onChange={(event) => setRepository(event.target.value)}
          required
        >
          <option value="">Select a repository</option>
          {data.repositories.map((repo) => (
            <option value={repo.id} key={repo.id}>
              {repo.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        AWS account ID{" "}
        <input
          aria-label="AWS account ID"
          value={account}
          onChange={(event) => setAccount(event.target.value)}
          pattern="[0-9]{12}"
          maxLength={12}
          placeholder="12-digit account ID"
          required
        />
      </label>
      <label>
        Region{" "}
        <select
          aria-label="AWS region"
          value={region}
          onChange={(event) => setRegion(event.target.value)}
        >
          {[
            "us-east-1",
            "us-east-2",
            "us-west-2",
            "ap-south-1",
            "ap-south-2",
            "eu-west-1",
            "eu-central-1",
          ].map((item) => (
            <option key={item}>{item}</option>
          ))}
        </select>
      </label>
      <button
        className="secondary"
        type="submit"
        disabled={busy || !repository}
      >
        {busy ? "Reading account inventory…" : "Sync read-only AWS inventory"}
      </button>
      {message && <p role="status">{message}</p>}
    </form>
  );
}

function NativeCloudEvidence({
  page,
  data,
  onOpen,
  role,
}: {
  page: string;
  data: Workspace;
  onOpen: (item: Item) => void;
  role: string;
}) {
  const inventory = (data.graph_node || []).filter((item) =>
    [
      "CLOUD_RESOURCE",
      "CLOUD_IDENTITY",
      "CONTAINER_WORKLOAD",
      "EXPOSURE",
    ].includes(item.class || ""),
  );
  const assets = inventory.filter((item) =>
    page === "Cloud Identities"
      ? item.class === "CLOUD_IDENTITY"
      : page === "Exposure"
        ? item.class === "EXPOSURE" ||
          (item.public &&
            !["UNKNOWN", "NO_INTERNET_RANGE_OBSERVED"].includes(item.public))
        : item.class !== "EXPOSURE",
  );
  const paths = data.risk_path || [];
  return (
    <>
      <p className="context-note">
        Static inventory describes declared configuration. Direct AWS
        observations describe the control plane. Deployment mappings, effective
        permissions and application reachability require their own evidence.
      </p>
      {page === "Risk Paths" ? (
        paths.length ? (
          paths.map((path) => (
            <section className="settings-panel" key={path.id}>
              <h2>{path.title}</h2>
              <Badge value={path.classification} />
              <p>{path.factors?.join(" · ")}</p>
              <div className="filters">
                {path.node_ids?.map((id) => {
                  const item = [...inventory, ...data.finding].find(
                    (node) => node.id === id,
                  );
                  return item ? (
                    <button
                      className="secondary"
                      key={id}
                      onClick={() => onOpen(item)}
                    >
                      {item.title || item.id}
                    </button>
                  ) : null;
                })}
              </div>
              <p>{path.remediation}</p>
            </section>
          ))
        ) : (
          <Empty title="No supported risk paths">
            A path requires observed resource, exposure, and finding
            relationships in the selected snapshot.
          </Empty>
        )
      ) : assets.length ? (
        <div className="integration-list">
          {assets.map((asset) => (
            <article key={asset.id}>
              <div>
                <small>
                  {asset.provider} · {asset.asset_kind || asset.class}
                </small>
                <h2>{asset.title}</h2>
                <p>
                  {asset.public || "Exposure unknown"} · encryption{" "}
                  {asset.encryption || "unknown"}
                </p>
                <small>
                  {asset.path || asset.verification_scope} · {asset.owner}
                </small>
              </div>
              <Badge value={asset.authority || asset.provenance} />
              <button className="secondary" onClick={() => onOpen(asset)}>
                Inspect evidence
              </button>
            </article>
          ))}
        </div>
      ) : (
        <Empty title="No supported cloud assets">
          Import Terraform, Kubernetes, Compose, or CloudFormation
          configuration. An authorized native AWS inventory can add
          control-plane observations.
        </Empty>
      )}
      {page === "Cloud" && (
        <>
          <h2>Native infrastructure and cloud findings</h2>
          <DataTable
            mode="finding"
            items={data.finding.filter((item) =>
              ["IAC", "CLOUD"].includes(item.category || ""),
            )}
            onOpen={onOpen}
          />
          <h2>Read-only account inventory</h2>
          <p>
            Authorized AWS accounts add read-only S3, security group and
            identity inventory. Your administrator must enable the account's
            read-only credentials before syncing. Azure and GCP live adapters
            are deferred.
          </p>
          <AWSInventoryForm data={data} role={role} />
        </>
      )}
    </>
  );
}

function Inspector({
  item,
  data,
  onClose,
  onOpen,
  onUpdated,
  role,
}: {
  item: Item;
  data: Workspace;
  onClose: () => void;
  onOpen: (i: Item) => void;
  onUpdated: (i: Item) => void;
  role: string;
}) {
  const [action, setAction] = useState("CONFIRM");
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [owner, setOwner] = useState(item.owner || "");
  const [expiresDays, setExpiresDays] = useState(7);
  const [tab, setTab] = useState("Evidence");
  const [historyOffset, setHistoryOffset] = useState(0);
  const findingHistory = useQuery({
    queryKey: ["finding-history", item.id, historyOffset],
    queryFn: () =>
      api<{
        identity_version: string;
        total: number;
        items: {
          id: string;
          status: string;
          at: string;
          reason: string;
          path?: string;
          line?: number;
        }[];
      }>(`/findings/${item.id}/history?offset=${historyOffset}&limit=50`),
    enabled: item.kind === "finding" && tab === "History",
  });
  useEffect(() => {
    setOwner(item.owner || "");
    setReason("");
    setAction("CONFIRM");
    setTab("Evidence");
    setHistoryOffset(0);
  }, [item.id]);
  const linkedEvidence = new Set(item.evidence_ids || []);
  data.edge.forEach((edge) => {
    if (edge.source === item.id) linkedEvidence.add(edge.target);
    if (edge.target === item.id) linkedEvidence.add(edge.source);
  });
  const qualitySource = useQuery({
    queryKey: ["quality-inspector-source", item.id],
    queryFn: () =>
      api<Item>(
        `/code-quality/${item.scope?.repository_id}/source?${new URLSearchParams({ snapshot_id: item.scope?.snapshot_id || "", q: item.path || "", offset: String(Math.max(0, (item.line || 1) - 30)), limit: "100" })}`,
      ),
    enabled:
      item.category === "QUALITY" &&
      !!item.path &&
      !data.evidence.some((e) => linkedEvidence.has(e.id)),
  });
  const evidence = qualitySource.data
    ? [qualitySource.data]
    : item.kind === "evidence"
      ? [item]
      : data.evidence.filter((e) => linkedEvidence.has(e.id));
  const linkedSource = useQuery({
    queryKey: ["inspector-linked-evidence", item.id, item.evidence_ids],
    queryFn: () =>
      Promise.all(
        (item.evidence_ids || [])
          .slice(0, 5)
          .map((id) => api<Item>("/record/" + id)),
      ),
    enabled:
      item.category !== "QUALITY" &&
      evidence.length === 0 &&
      !!item.evidence_ids?.length,
  });
  const sourceEvidence = evidence.length ? evidence : linkedSource.data || [];
  const canReview =
    [
      "ORG_OWNER",
      "ADMIN",
      "ENGINEER",
      "SECURITY_REVIEWER",
      "REVIEWER",
    ].includes(role) &&
    ["claim", "finding", "drift", "pr"].includes(item.kind || "");
  async function review(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      onUpdated(
        await api<Item>("/record/" + item.id + "/review", {
          action,
          reason,
          ...(action === "ASSIGN" ? { owner } : {}),
          ...(["ACCEPT_RISK", "CREATE_EXCEPTION"].includes(action)
            ? { expires_days: expiresDays }
            : {}),
          expected_version: item.version,
        }),
      );
      setReason("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal title="Evidence inspector" onClose={onClose} wide>
      <div className="inspector-title">
        <div className="eyebrow">
          {item.category || item.kind || "ENGINEERING EVIDENCE"} ·{" "}
          {item.scope?.repository}
        </div>
        <h2>{label(item)}</h2>
        <div className="inspector-badges">
          <Badge
            value={
              item.status ||
              item.severity ||
              item.authority ||
              item.vulnerability_status
            }
          />
          {item.confidence && <span>Confidence: {item.confidence}</span>}
          {item.review_status && <Badge value={item.review_status} />}
        </div>
        <p>
          {item.reason ||
            item.explanation ||
            (item.kind === "graph_node"
              ? "Graph node derived from recorded relationships in this snapshot."
              : "Source evidence retained from this snapshot.")}
        </p>
      </div>
      <div className="inspector-scope">
        <span>
          <GitBranch size={14} />
          {item.scope?.branch} @ <code>{item.scope?.commit.slice(0, 12)}</code>
        </span>
        <span>Owner: {item.owner || "Source artifact"}</span>
        <span>Analyzed {date(item.scope?.analysis_at)}</span>
      </div>
      <dl className="inspector-metadata">
        <dt>Snapshot</dt>
        <dd>
          <code>{item.scope?.snapshot_id || "Unavailable"}</code>
        </dd>
        {(item.rule_id || item.rule) && (
          <>
            <dt>Rule / version</dt>
            <dd>
              <code>{item.rule_id || item.rule}</code> ·{" "}
              {item.rule_version || item.scope?.rule_version || "Not recorded"}
            </dd>
          </>
        )}
        {item.category === "QUALITY" && (
          <>
            <dt>Quality dimension / symbol</dt>
            <dd>
              {item.dimension} · {item.symbol}
            </dd>
            <dt>Machine observation / human review</dt>
            <dd>
              {item.machine_status || "OPEN"} · {item.review_status || "OPEN"}
            </dd>
            {item.measured != null && (
              <>
                <dt>Measured / threshold</dt>
                <dd>
                  {item.metric}: {item.measured} / {item.threshold}
                </dd>
              </>
            )}
          </>
        )}
        {item.language && (
          <>
            <dt>Language</dt>
            <dd>{item.language}</dd>
          </>
        )}
        {item.path && (
          <>
            <dt>Source location</dt>
            <dd>
              <code>
                {item.path}
                {item.line
                  ? `:${item.line}${(item.end_line || item.line_end) && (item.end_line || item.line_end) !== item.line ? "–" + (item.end_line || item.line_end) : ""}`
                  : ""}
              </code>
            </dd>
          </>
        )}
        {(item.analyzer_version || item.scope?.analyzer_version) && (
          <>
            <dt>Analyzer</dt>
            <dd>{item.analyzer_version || item.scope?.analyzer_version}</dd>
          </>
        )}
        {item.origin && (
          <>
            <dt>Claim origin</dt>
            <dd>{item.origin.replaceAll("_", " ")}</dd>
          </>
        )}
        {item.identity_id && (
          <>
            <dt>Claim identity / version</dt>
            <dd>
              <code>{item.identity_id}</code> · {item.claim_version || 1}
            </dd>
          </>
        )}
        {item.provider && (
          <>
            <dt>Evidence provider</dt>
            <dd>{item.provider}</dd>
          </>
        )}
        {item.provenance && (
          <>
            <dt>Graph provenance</dt>
            <dd>
              <Badge value={item.provenance} />
            </dd>
          </>
        )}
        {(item.secret_context || item.credential_context) && (
          <>
            <dt>Credential context</dt>
            <dd>
              <Badge value={item.secret_context || item.credential_context} />
              <span className="subtle">
                {" "}
                Masked pattern; validity and runtime use are unverified.
              </span>
            </dd>
          </>
        )}
        {item.kind === "dependency" && (
          <>
            <dt>Advisory coverage</dt>
            <dd>
              <Badge value={dependencyState(item)} />
            </dd>
            <dt>Declared version</dt>
            <dd>
              {item.version} · {item.version_kind || "Unknown version kind"}
            </dd>
            <dt>License</dt>
            <dd>{item.license || "Unknown"}</dd>
            <dt>Advisory provider / time</dt>
            <dd>
              {item.advisory_provider || "Not recorded"} ·{" "}
              {date(item.advisory_checked_at)}
            </dd>
          </>
        )}
        {item.fingerprint && (
          <>
            <dt>Finding fingerprint</dt>
            <dd>
              <code>{item.fingerprint}</code>
            </dd>
          </>
        )}
      </dl>
      {item.classification && (
        <p>
          <Badge value={item.classification} />{" "}
          {item.delta && <Badge value={item.delta} />}{" "}
          {item.new_code !== undefined &&
            (item.new_code ? "Changed code" : "Outside changed lines")}
        </p>
      )}
      {item.flow?.length ? (
        <section className="evidence-block">
          <h3>Static flow evidence</h3>
          <ol>
            {item.flow.map((step, index) => (
              <li key={index}>
                <Badge value={step.kind} />{" "}
                <code>
                  {step.path}:{step.line}
                </code>{" "}
                · {step.symbol}
              </li>
            ))}
          </ol>
          <p className="subtle">
            Conservative static path. Runtime reachability is unobserved;
            unknown transformations remain review hotspots.
          </p>
        </section>
      ) : null}
      <div className="tabs">
        {["Evidence", "History", ...(canReview ? ["Review"] : [])].map((t) => (
          <button
            className={tab === t ? "active" : ""}
            key={t}
            onClick={() => setTab(t)}
          >
            {t}
          </button>
        ))}
      </div>
      <div className="inspector-body">
        {tab === "Evidence" ? (
          <>
            {sourceEvidence.length ? (
              sourceEvidence.map((e) => (
                <section className="evidence-block" key={e.id}>
                  <div className="section-head">
                    <code>{e.path}</code>
                    <Badge
                      value={
                        item.contradicting_ids?.includes(e.id)
                          ? "CONTRADICTING"
                          : item.supporting_ids?.includes(e.id)
                            ? "SUPPORTING"
                            : e.authority
                      }
                    />
                  </div>
                  <Source
                    item={e}
                    highlight={item.path === e.path ? item.line : undefined}
                    startLine={e.first_line}
                  />
                </section>
              ))
            ) : (
              <p>
                {qualitySource.isLoading || linkedSource.isLoading
                  ? "Loading source evidence…"
                  : qualitySource.isError
                    ? "Source evidence unavailable: " +
                      qualitySource.error.message
                    : linkedSource.isError
                      ? "Source evidence unavailable: " +
                        linkedSource.error.message
                      : "No source artifact is attached to this result. Review its scope and analyzer limitation."}
              </p>
            )}
            {item.vulnerabilities?.map((v) => (
              <p key={v.id}>
                <a href={v.url} target="_blank" rel="noreferrer">
                  {v.id} <SquareArrowOutUpRight size={12} />
                </a>{" "}
                · {v.summary}
              </p>
            ))}
            {item.advisory && (
              <a href={item.advisory.url} target="_blank" rel="noreferrer">
                Open OSV advisory
              </a>
            )}
            <div className="recommendation">
              <strong>Recommended action</strong>
              <p>
                {item.recommendation ||
                  item.remediation ||
                  "Review the artifact together with connected claims and findings."}
              </p>
            </div>
            {item.kind === "drift" && (
              <button
                className="secondary"
                onClick={() => {
                  const claim = data.claim.find(
                    (c) =>
                      c.id ===
                      String((item as Item & { claim_id?: string }).claim_id),
                  );
                  if (claim) onOpen(claim);
                }}
              >
                Inspect related claim <ArrowRight size={15} />
              </button>
            )}
          </>
        ) : tab === "History" ? (
          <div className="audit-list">
            {item.kind === "finding" ? (
              findingHistory.isLoading ? (
                <p>Loading finding history…</p>
              ) : findingHistory.isError ? (
                <p>Finding history could not be loaded.</p>
              ) : (
                <>
                  <p>
                    {findingHistory.data?.identity_version} ·{" "}
                    {findingHistory.data?.total || 0} recorded observations
                  </p>
                  {findingHistory.data?.items.map((h) => (
                    <div key={h.id}>
                      <div className="audit-dot" />
                      <div>
                        <Badge value={h.status} />
                        <p>{h.reason}</p>
                        <small>
                          {h.path}
                          {h.line ? `:${h.line}` : ""} · {date(h.at)}
                        </small>
                      </div>
                    </div>
                  ))}
                  <button
                    disabled={!historyOffset}
                    onClick={() =>
                      setHistoryOffset(Math.max(0, historyOffset - 50))
                    }
                  >
                    Newer observations
                  </button>
                  <button
                    disabled={
                      historyOffset + 50 >= (findingHistory.data?.total || 0)
                    }
                    onClick={() => setHistoryOffset(historyOffset + 50)}
                  >
                    Older observations
                  </button>
                  {!findingHistory.data?.total && (
                    <p>
                      Earlier findings retain their snapshot and audit history.
                      Structural lineage starts with a new analysis.
                    </p>
                  )}
                </>
              )
            ) : item.history?.length ? (
              item.history.map((h, i) => (
                <div key={i}>
                  <div className="audit-dot" />
                  <div>
                    <Badge value={h.status} />
                    <p>{h.reason}</p>
                    <small>{date(h.at)}</small>
                  </div>
                </div>
              ))
            ) : (
              <Empty title="No claim transition history">
                Human decisions are recorded in the Audit Trail. Evidence
                artifacts are immutable within their snapshot.
              </Empty>
            )}
          </div>
        ) : (
          <form className="review-form" onSubmit={review}>
            <p>
              A review records a human decision. Verification status continues
              to reflect analyzer evidence.
            </p>
            <label>
              Review action
              <select
                value={action}
                onChange={(e) => setAction(e.target.value)}
              >
                {[
                  "CONFIRM",
                  "FALSE_POSITIVE",
                  "ASSIGN",
                  "REQUEST_MORE_EVIDENCE",
                  "RESOLVE",
                  ...(item.category === "QUALITY"
                    ? ["IN_REVIEW", "REOPEN"]
                    : []),
                  "CREATE_EXCEPTION",
                  "ACCEPT_RISK",
                ]
                  .filter(
                    (value) =>
                      !["ACCEPT_RISK", "CREATE_EXCEPTION"].includes(value) ||
                      ["ADMIN", "ORG_OWNER", "SECURITY_REVIEWER"].includes(
                        role,
                      ),
                  )
                  .map((a) => (
                    <option key={a}>{a}</option>
                  ))}
              </select>
            </label>
            {action === "ASSIGN" && (
              <label>
                Owner
                <input
                  value={owner}
                  onChange={(event) => setOwner(event.target.value)}
                  required
                  maxLength={120}
                  placeholder="Team or responsible engineer"
                />
              </label>
            )}
            {["ACCEPT_RISK", "CREATE_EXCEPTION"].includes(action) && (
              <label>
                Exception expiry in days
                <input
                  type="number"
                  value={expiresDays}
                  onChange={(event) =>
                    setExpiresDays(Number(event.target.value))
                  }
                  required
                  min={1}
                  max={90}
                />
                <small className="subtle">
                  The exception is scoped to this result and stops affecting
                  policy after expiry.
                </small>
              </label>
            )}
            <label>
              Reason
              <textarea
                required
                minLength={10}
                maxLength={2000}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Explain the decision and cite any additional evidence."
              />
            </label>
            {error && (
              <p className="error" role="alert">
                {error}
              </p>
            )}
            <button className="primary" disabled={busy}>
              {busy ? (
                <LoaderCircle className="spin" size={16} />
              ) : (
                <Check size={16} />
              )}{" "}
              Record review
            </button>
          </form>
        )}
      </div>
    </Modal>
  );
}

export function ImportDialog({
  access,
  repositories,
  initialTarget,
  onRefresh,
  onClose,
  onDone,
  onConnect,
}: {
  access?: AccessContext;
  onClose: () => void;
  onDone: (repository: string) => void;
  repositories: Repository[];
  initialTarget: string;
  onRefresh: () => void;
  onConnect: () => void;
}) {
  const destinations = repositories.filter((r) =>
    ["ZIP", "LOCAL"].includes(r.provider),
  );
  const [target, setTarget] = useState(
    destinations.some((r) => r.id === initialTarget) ? initialTarget : "NEW",
  );
  const [mode, setMode] = useState<"ZIP" | "PUBLIC">(
    access?.features.zip_import.allowed === false ? "PUBLIC" : "ZIP",
  );
  const [url, setUrl] = useState("");
  const [ref, setRef] = useState("");
  const requestKey = useRef(crypto.randomUUID());
  const [name, setName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (
      access?.features.analyses.allowed === false ||
      access?.features[mode === "ZIP" ? "zip_import" : "public_github"]
        .allowed === false
    ) {
      setError("This import is restricted by access policy.");
      return;
    }
    if (mode === "ZIP" && !file) return;
    setBusy(true);
    setError("");
    try {
      const result =
        mode === "PUBLIC"
          ? await api<{ repository_id: string }>("/github/public/import", {
              url,
              ref: ref || null,
              request_key: requestKey.current,
            })
          : await api<{ repository_id: string; state?: string }>(
              target === "NEW"
                ? "/archive/stream/import?name=" +
                    encodeURIComponent(name) +
                    "&request_key=" +
                    requestKey.current
                : "/repositories/" +
                    encodeURIComponent(target) +
                    "/source-archive?request_key=" +
                    requestKey.current,
              undefined,
              file || undefined,
            );
      onDone(result.repository_id);
    } catch (e) {
      setError((e as Error).message);
      onRefresh();
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal title="Import a repository snapshot" onClose={onClose}>
      <div className="section-head" aria-label="Import source">
        <button
          className={mode === "ZIP" ? "primary" : "secondary"}
          disabled={busy || access?.features.zip_import.allowed === false}
          onClick={() => {
            setMode("ZIP");
            setError("");
          }}
        >
          Upload ZIP
        </button>
        <button
          className={mode === "PUBLIC" ? "primary" : "secondary"}
          disabled={busy || access?.features.public_github.allowed === false}
          onClick={() => {
            setMode("PUBLIC");
            setError("");
          }}
        >
          Public GitHub URL
        </button>
        <button
          className="secondary"
          disabled={busy || access?.features.private_scm.allowed === false}
          onClick={onConnect}
        >
          Connect private GitHub
        </button>
      </div>
      <form className="import-form" onSubmit={submit}>
        <p>
          {mode === "ZIP"
            ? "Upload source files for a separate ZIP snapshot."
            : "Import a public repository once, pinned to its resolved Git commit. No GitHub App or webhook is required."}{" "}
          ProjectTrace inspects source as untrusted data and stores redacted
          evidence.
        </p>
        {mode === "PUBLIC" ? (
          <>
            <label>
              Public repository URL
              <input
                type="url"
                required
                value={url}
                onChange={(e) => {
                  setUrl(e.target.value);
                  requestKey.current = crypto.randomUUID();
                }}
                placeholder="https://github.com/owner/repository"
                maxLength={500}
              />
            </label>
            <label>
              Branch, tag or commit (optional)
              <input
                value={ref}
                onChange={(e) => {
                  setRef(e.target.value);
                  requestKey.current = crypto.randomUUID();
                }}
                maxLength={256}
                placeholder="Default branch"
              />
            </label>
          </>
        ) : (
          <>
            <label>
              Destination
              <select
                aria-label="Import destination"
                value={target}
                onChange={(e) => {
                  setTarget(e.target.value);
                  requestKey.current = crypto.randomUUID();
                }}
              >
                <option value="NEW">New repository</option>
                {destinations.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.name} · new snapshot
                  </option>
                ))}
              </select>
            </label>
            {target === "NEW" && (
              <label>
                Repository name
                <input
                  value={name}
                  onChange={(e) => {
                    setName(e.target.value);
                    requestKey.current = crypto.randomUUID();
                  }}
                  required
                  maxLength={120}
                  pattern="[\w .-]+"
                  placeholder="checkout-api"
                />
              </label>
            )}
            <label>
              Source archive
              <input
                type="file"
                accept=".zip"
                required
                onChange={(e) => {
                  setFile(e.target.files?.[0] || null);
                  requestKey.current = crypto.randomUUID();
                }}
              />
            </label>
          </>
        )}
        <div className="context-note">
          Encrypted streaming intake · 512,000 bytes per-file parser limit.
          Unsafe paths, encrypted entries and decompression bombs are rejected.
          Symlinks are recorded as UNSUPPORTED without being followed.
          Oversized, binary and unsupported files remain visible in Trust &
          Coverage.
        </div>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <button className="primary" disabled={busy}>
          {busy ? (
            <LoaderCircle className="spin" size={16} />
          ) : (
            <Upload size={16} />
          )}{" "}
          {busy
            ? mode === "PUBLIC"
              ? "Requesting public snapshot…"
              : "Uploading and capturing source…"
            : mode === "PUBLIC"
              ? "Import public snapshot"
              : target === "NEW"
                ? "Analyze source snapshot"
                : "Analyze and compare snapshot"}
        </button>
      </form>
    </Modal>
  );
}

function CommandPalette({
  data,
  navigate,
  onOpen,
}: {
  data?: Workspace;
  navigate: (s: string) => void;
  onOpen: (i: Item) => void;
}) {
  const [q, setQ] = useState("");
  const pages = [
    ...navigation.flatMap((g) => g.items.map(([name]) => name)),
    "ProjectTrace Guide",
  ].filter((p) => p.toLowerCase().includes(q.toLowerCase()));
  const records = q
    ? [
        ...(data?.claim || []),
        ...(data?.finding || []),
        ...(data?.evidence || []),
      ]
        .filter((i) => label(i).toLowerCase().includes(q.toLowerCase()))
        .slice(0, 8)
    : [];
  return (
    <div className="command-palette">
      <div className="filter-input">
        <Search size={18} />
        <input
          autoFocus
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search claims, files, or pages…"
          aria-label="Search workspace"
        />
      </div>
      <span className="eyebrow">PAGES</span>
      {pages.map((p) => (
        <button key={p} onClick={() => navigate(p)}>
          <Command size={14} />
          {p}
          <ArrowRight size={14} />
        </button>
      ))}
      {records.length > 0 && (
        <span className="eyebrow">EVIDENCE & CONCLUSIONS</span>
      )}
      {records.map((i) => (
        <button key={i.id} onClick={() => onOpen(i)}>
          <FileCode2 size={14} />
          <span>{label(i)}</span>
          <Badge value={i.status || i.severity || i.authority} />
        </button>
      ))}
    </div>
  );
}
