export const routes = {
  Overview: "/overview",
  Systems: "/systems",
  Components: "/components",
  Repositories: "/repositories",
  "Pull Requests": "/pull-requests",
  Findings: "/findings",
  "Code Quality": "/quality",
  Security: "/security",
  Dependencies: "/dependencies",
  Infrastructure: "/infrastructure",
  Cloud: "/cloud",
  "Claim Ledger": "/claims",
  Drift: "/drift",
  Architecture: "/architecture",
  Evidence: "/evidence",
  "Evidence Graph": "/graph",
  "Ask Engineering": "/ask",
  Policies: "/policies",
  "Audit Trail": "/audit",
  Connections: "/settings/connections",
  Settings: "/settings",
} as const;

export function routeForPage(page: string): string {
  return routes[page as keyof typeof routes] || routes.Overview;
}

export function pageForRoute(path: string): string {
  return (
    Object.entries(routes).find(([, value]) => value === path)?.[0] ||
    "Overview"
  );
}

export function legacyRoute(hash: string): string | null {
  let value: string;
  try {
    value = decodeURIComponent(hash.replace(/^#\/?/, "")).toLowerCase();
  } catch {
    return null;
  }
  if (value === "integrations") return routes.Connections;
  const page = Object.keys(routes).find((name) =>
    [name.toLowerCase(), name.toLowerCase().replaceAll(" ", "-")].includes(
      value,
    ),
  );
  if (page) return routeForPage(page);
  return Object.values(routes).find((path) => path.slice(1) === value) || null;
}
