import {
  render,
  screen,
  fireEvent,
  waitFor,
  cleanup,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, it, vi } from "vitest";
import { RepositoryPage } from "./WorkspaceApp";
import { setCSRF } from "./api";
import type { Workspace } from "./api";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  setCSRF("");
});
function show(mode: "sync" | "celery" = "celery", demo = false) {
  const data = {
    demo,
    capabilities: { job_mode: mode },
    repositories: [
      {
        id: "repo",
        name: "owned/repo",
        system: "System",
        component: "Component",
        owner: "Owner",
        provider: "GITHUB",
        snapshot: null,
        latest_job: {
          id: "existing-job",
          state: "FAILED",
          branch: "refs/heads/test",
        },
      },
    ],
  } as unknown as Workspace;
  render(
    <QueryClientProvider client={new QueryClient()}>
      <RepositoryPage
        data={data}
        page="Repositories"
        navigate={vi.fn()}
        onImport={vi.fn()}
      />
    </QueryClientProvider>,
  );
}

it("retries the existing job through the authenticated CSRF-protected API", async () => {
  setCSRF("fixture-csrf");
  const fetch = vi
    .fn()
    .mockResolvedValue({
      ok: true,
      json: async () => ({ id: "existing-job", state: "QUEUED" }),
    });
  vi.stubGlobal("fetch", fetch);
  show();
  fireEvent.click(screen.getByRole("button", { name: "Retry analysis" }));
  await waitFor(() => expect(fetch).toHaveBeenCalledOnce());
  expect(fetch).toHaveBeenCalledWith(
    "/api/jobs/existing-job/retry",
    expect.objectContaining({
      method: "POST",
      credentials: "include",
      body: "{}",
      headers: expect.objectContaining({ "X-CSRF-Token": "fixture-csrf" }),
    }),
  );
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "Retry analysis" }),
    ).toBeEnabled(),
  );
});

it("shows the server rejection instead of inventing a successful retry", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValue({
        ok: false,
        text: async () => '{"detail":"Retry limit reached."}',
      }),
  );
  show();
  fireEvent.click(screen.getByRole("button", { name: "Retry analysis" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Retry limit reached.",
  );
});

it.each([
  ["sync", false],
  ["celery", true],
] as const)(
  "does not offer provider retry in %s mode / demo=%s",
  (mode, demo) => {
    show(mode, demo);
    expect(
      screen.queryByRole("button", { name: "Retry analysis" }),
    ).not.toBeInTheDocument();
  },
);
