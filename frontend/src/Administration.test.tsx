import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import { afterEach, expect, it, vi } from "vitest";
import Administration from "./Administration";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const identity = { email: "controlled@example.test", role: "ORG_OWNER", csrf: "controlled-csrf", organization: "Controlled fixture", organization_id: "organization", demo: false };
const context = {
  user_id: "owner", organization_id: "organization", role: "ORG_OWNER", membership_version: 3,
  permissions: ["users.read", "users.invite", "users.suspend", "users.reactivate", "features.manage", "usage.read"],
  platform_permissions: [], administered_team_ids: [], admin_available: true, features: { exports: { allowed: true } },
  permission_definitions: {}, roles: [], unavailable_controls: [], active_job_policy: "Active work retains declared scope.",
  feature_catalog: [{ id: "zip_import", label: "ZIP import", description: "Submit ZIP snapshots" }],
};
function mount(section: string) {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter initialEntries={[`/administration?section=${encodeURIComponent(section)}`]}><Administration identity={identity} changed={vi.fn()} /></MemoryRouter></QueryClientProvider>);
}
function response(value: unknown, ok = true) { return { ok, status: ok ? 200 : 503, json: async () => value, text: async () => JSON.stringify(value) }; }

it("loads administration without requesting the engineering workspace or graph", async () => {
  const fetch = vi.fn(async (url: unknown) => response(String(url).includes("/admin/context") ? context : { members: { total: 27 }, repositories: 5, cpu_seconds: null }));
  vi.stubGlobal("fetch", fetch); mount("Dashboard");
  expect(await screen.findByText("total: 27")).toBeVisible();
  expect(fetch.mock.calls.every(([url]) => !String(url).includes("/workspace"))).toBe(true);
  expect(screen.getByText("Unavailable")).toBeVisible();
});

it("shows an aggregate failure without rendering fabricated zeros", async () => {
  vi.stubGlobal("fetch", vi.fn(async (url: unknown) => String(url).includes("/admin/context") ? response(context) : response({ detail: "Controlled database unavailable" }, false)));
  mount("Dashboard");
  expect(await screen.findByRole("alert")).toHaveTextContent("Controlled database unavailable");
  expect(screen.queryByText("total: 0")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Retry" })).toBeVisible();
});

it("paginates users on the server and confirms a versioned suspension", async () => {
  const fetch = vi.fn(async (url: unknown, options?: RequestInit) => {
    if (String(url).includes("/admin/context")) return response(context);
    if (options?.method === "POST") return response({ state: "SUSPENDED", audit_event_id: "controlled-audit" });
    return response({ items: [{ id: "member", email: "member@example.test", role: "ENGINEER", state: "ACTIVE", version: 7 }], page: { total: 51, offset: String(url).includes("offset=25") ? 25 : 0, limit: 25, has_more: true } });
  });
  vi.stubGlobal("fetch", fetch); mount("Users");
  fireEvent.click(await screen.findByRole("button", { name: "Next page" }));
  await waitFor(() => expect(fetch.mock.calls.some(([url]) => String(url).includes("offset=25"))).toBe(true));
  fireEvent.click(await screen.findByRole("button", { name: "Suspend" }));
  fireEvent.change(screen.getByLabelText("Reason"), { target: { value: "Controlled suspension review" } });
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.click(screen.getByRole("button", { name: "Confirm operation" }));
  await waitFor(() => expect(fetch.mock.calls.some(([, options]) => options?.method === "POST" && String(options.body).includes('"expected_version":7') && String(options.body).includes('"action":"SUSPEND"'))).toBe(true));
  expect(await screen.findByText("controlled-audit")).toBeVisible();
});

it("requires a reviewed feature preview before submitting the actual change", async () => {
  const fetch = vi.fn(async (url: unknown, options?: RequestInit) => {
    if (String(url).includes("/admin/context")) return response(context);
    if (String(url).endsWith("/features/preview")) return response({ preview_id: "bound-preview", candidate_memberships: 45, sample: [], active_job_policy: "Existing work continues" });
    if (options?.method === "POST") return response({ state: "APPLIED", audit_event_id: "feature-audit" });
    return response({ items: [], page: { total: 0, has_more: false } });
  });
  vi.stubGlobal("fetch", fetch); mount("Feature Access");
  fireEvent.click(await screen.findByRole("button", { name: "Review change" }));
  fireEvent.change(screen.getByLabelText("Decision"), { target: { value: "DENY" } });
  fireEvent.change(screen.getByLabelText("Reason"), { target: { value: "Controlled preview security review" } });
  fireEvent.click(screen.getByRole("button", { name: "Preview effective access" }));
  expect(await screen.findByText(/45 memberships/)).toBeVisible();
  expect(fetch.mock.calls.filter(([url, options]) => String(url).endsWith("/features") && options?.method === "POST")).toHaveLength(0);
  fireEvent.click(screen.getByRole("checkbox", { name: /reviewed the preview/ }));
  fireEvent.click(screen.getByRole("button", { name: "Confirm reviewed policy" }));
  await waitFor(() => expect(fetch.mock.calls.some(([, options]) => String(options?.body).includes('"preview_id":"bound-preview"'))).toBe(true));
  expect(await screen.findByText("feature-audit")).toBeVisible();
});
