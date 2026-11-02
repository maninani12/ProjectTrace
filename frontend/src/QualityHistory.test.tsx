import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import CodeQuality from "./CodeQuality";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it("discloses unresolved history even when source parsing completed", async () => {
  vi.stubGlobal("fetch", vi.fn(async (url: unknown) => ({ ok: true,
    json: async () => String(url).includes("/overview") ? {
      state: "COMPLETED", branch: "main", commit: "a".repeat(40), base_id: "legacy-base",
      comparison_identity_unresolved: true, limitations: [], languages: [], scope_counts: {},
      configuration: { name: "Owned profile" }, coverage: {}, duplication: {},
      summary: { total: 1, new: 0, resolved: 0, functions: 1, dimensions: {} },
      gate: { status: "REVIEW_REQUIRED", scope: "NEW_CODE", results: [{
        policy: "Quality: comparison identity", result: "REVIEW_REQUIRED",
        reason: "Identity comparison is unresolved.",
      }] },
    } : { items: [], total: 0 },
  })));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<MemoryRouter><QueryClientProvider client={client}><CodeQuality
    repositories={[{ id: "repo", name: "owner/repo", provider: "GITHUB_PUBLIC",
      system: "Owned", component: "Owned", owner: "Owner", snapshot: null }]}
    selectedRepository="repo" role="ORG_OWNER" onOpen={vi.fn()} />
  </QueryClientProvider></MemoryRouter>);
  expect(await screen.findByRole("alert")).toHaveTextContent("introductions and resolutions are unverified");
  expect(screen.getByText("Quality: comparison identity")).toBeVisible();
});
