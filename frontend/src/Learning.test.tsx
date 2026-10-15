import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, it, vi } from "vitest";
import Learning from "./Learning";
import type { Identity, Repository } from "./api";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const repository = { id: "controlled-repo", name: "Controlled project", system: "Controlled", component: "Controlled", owner: "Controlled", provider: "LOCAL", snapshot: null } satisfies Repository;
const identity: Identity = { email: "participant@example.test", role: "ENGINEER", csrf: "test", demo: false,
  access: { user_id: "participant", organization_id: "controlled", role: "ENGINEER", permissions: [],
    admin_available: false, platform_permissions: [], administered_team_ids: [], decision_version: "test", features: {} } };
const objective = { id: "objective-1", record_id: "claim-1", title: "Controlled captured API", topic: "API", explanation: "Controlled static claim", status: "INFERRED", confidence: "MEDIUM", question: "Explain the captured API and its limitations.", evidence_ids: ["evidence-1"], state: "ASSIGNED", version: 1, gap_basis: "LEARNING_OBJECTIVE" };
const journey = { id: "path-1", version: 1, mode: "NEW_HIRE", role: "BACKEND", state: "ACTIVE", revision: 1,
  repository_id: repository.id, snapshot_id: "captured-snapshot", participant_id: "participant", mentor_id: "mentor", manager_id: "manager", viewer: "PARTICIPANT", expires_at: "2099-01-01", retention_expired: false,
  refresh_required: false, can_complete: true, skills: [], objectives: [objective], progress: { approved: 0, total: 1 }, reviews: [], completion_records: [] };
function response(value: unknown, ok = true) { return { ok, status: ok ? 200 : 403, json: async () => value, text: async () => JSON.stringify(value) }; }
function mount(data = journey) {
  const fetch = vi.fn(async (url: unknown, options?: RequestInit) => {
    if (String(url).includes("/knowledge/")) return response({ snapshot_id: "captured-snapshot", branch: "main", status: "PARTIAL", maximum_records_per_kind: 100, resources: [], limitations: [] });
    if (String(url).includes("/journeys?")) return response({ items: [data], has_more: false });
    if (options?.method === "POST") return response({ ...data, objectives: [{ ...objective, state: "SUBMITTED", version: 2 }] });
    return response(data);
  });
  vi.stubGlobal("fetch", fetch);
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><Learning repository={repository.id} repositories={[repository]} identity={identity} onOpen={vi.fn()} /></QueryClientProvider>);
  return fetch;
}

it("submits a participant explanation against the objective version and captured citation", async () => {
  const fetch = mount();
  fireEvent.click(await screen.findByRole("button", { name: "New employee · BACKEND · ACTIVE" }));
  fireEvent.change(await screen.findByLabelText("Evidence-backed explanation"), { target: { value: "The captured API explains a scoped static observation and its limitations." } });
  fireEvent.click(screen.getByRole("button", { name: "Submit assessment" }));
  await waitFor(() => expect(fetch.mock.calls.some(([url]) => String(url).endsWith("/objective-1/submit"))).toBe(true));
  const submitted = fetch.mock.calls.find(([url]) => String(url).endsWith("/objective-1/submit"));
  expect(JSON.parse(String(submitted?.[1]?.body))).toMatchObject({ version: 1, evidence_ids: ["claim-1"] });
  expect(screen.queryByRole("button", { name: "Complete learning revision" })).not.toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "Assign a learning path" })).not.toBeInTheDocument();
});

it("requires an explicit mentor score and feedback before a review", async () => {
  mount({ ...journey, viewer: "MENTOR", objectives: [{ ...objective, state: "SUBMITTED" }] });
  fireEvent.click(await screen.findByRole("button", { name: "New employee · BACKEND · ACTIVE" }));
  const score = await screen.findByLabelText("Assessment score");
  expect(score).toHaveValue("");
  expect(screen.getByLabelText("Mentor feedback")).toBeRequired();
  expect(screen.queryByLabelText("Evidence-backed explanation")).not.toBeInTheDocument();
});

it("shows a source refresh gate and disables manager completion on stale knowledge", async () => {
  mount({ ...journey, viewer: "MANAGER", refresh_required: true, progress: { approved: 1, total: 1 } });
  fireEvent.click(await screen.findByRole("button", { name: "New employee · BACKEND · ACTIVE" }));
  expect(await screen.findByText("Source changed. Manager-approved refresh is required before completion.")).toBeVisible();
  expect(screen.getByRole("button", { name: "Complete learning revision" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Refresh learning after source change" })).toBeEnabled();
});

it("discloses feature denial without fabricating an empty learning success", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => response({ detail: "Learning feature is denied in your scope." }, false)));
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><Learning repository={repository.id} repositories={[repository]} identity={identity} onOpen={vi.fn()} /></QueryClientProvider>);
  expect((await screen.findAllByRole("alert"))[0]).toHaveTextContent("Learning feature is denied");
  expect(screen.queryByText("No learning paths are assigned to you yet.")).not.toBeInTheDocument();
});

it("does not reuse private learning state when the active organization changes", async () => {
  let switched = false;
  vi.stubGlobal("fetch", vi.fn(async (url: unknown) => {
    if (switched) return response({ detail: "Not available in this organization." }, false);
    if (String(url).includes("/knowledge/")) return response({ snapshot_id: "captured-snapshot", branch: "main", status: "PARTIAL", maximum_records_per_kind: 100, resources: [], limitations: [] });
    if (String(url).includes("/journeys?")) return response({ items: [journey], has_more: false });
    return response(journey);
  }));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const element = (actor: Identity) => <QueryClientProvider client={client}><Learning repository={repository.id} repositories={[repository]} identity={actor} onOpen={vi.fn()} /></QueryClientProvider>;
  const mounted = render(element(identity));
  fireEvent.click(await screen.findByRole("button", { name: "New employee · BACKEND · ACTIVE" }));
  expect(await screen.findByText(objective.title)).toBeVisible();
  switched = true;
  mounted.rerender(element({ ...identity, organization_id: "other-organization", access: { ...identity.access!, organization_id: "other-organization", decision_version: "changed" } }));
  await waitFor(() => expect(screen.queryByText(objective.title)).not.toBeInTheDocument());
  expect((await screen.findAllByRole("alert"))[0]).toHaveTextContent("Not available in this organization");
});
