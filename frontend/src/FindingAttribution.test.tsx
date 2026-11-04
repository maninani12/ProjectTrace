import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";
import WorkspaceScreen from "./WorkspaceApp";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it.each([false, true])(
  "keeps lifecycle separate from new-code attribution (%s)",
  async (newCode) => {
    const finding = {
      id: "changed-finding",
      kind: "finding",
      category: "QUALITY",
      title: "Long function from changed source",
      path: "popover.tsx",
      line: 16,
      classification: "DETERMINISTIC_STATIC",
      delta: newCode ? "NEW" : "ANALYZER_BASELINE",
      new_code: newCode,
      identity_confidence: "HIGH",
      review_status: "OPEN",
      severity: "MEDIUM",
      scope: {
        repository_id: "repo",
        repository: "owner/repo",
        snapshot_id: "head",
        commit: "b".repeat(40),
      },
    };
    const repository = {
      id: "repo",
      name: "owner/repo",
      system: "Owned",
      component: "Owned",
      owner: "Owner",
      provider: "GITHUB_PUBLIC",
      snapshot: { id: "head", status: "PARTIAL" },
    };
    const workspace = {
      organization: "Owned",
      demo: false,
      repositories: [repository],
      analysis: { state: "PARTIAL" },
      claim: [],
      finding: [finding],
      evidence: [],
      drift: [],
      edge: [],
      graph_node: [],
      dependency: [],
      pr: [],
      review: [],
      counts: {
        complete: true,
        totals: { finding: 1 },
        repositories: {},
        material_findings: 1,
        claim_status: {},
        finding_severity: { MEDIUM: 1 },
      },
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: unknown) => {
        const path = String(url);
        const data = path.endsWith("/auth/me")
          ? {
              email: "owner@example.invalid",
              role: "ORG_OWNER",
              organization_id: "owned",
            }
          : path.includes("/workspace/records")
            ? {
                items: [finding],
                total: 1,
                offset: 0,
                limit: 50,
                has_more: false,
                severity_counts: { MEDIUM: 1 },
                state_counts: {},
                kind_counts: { finding: 1 },
              }
            : path.includes("/findings/changed-finding/history")
              ? {
                  total: 1,
                  items: [
                    {
                      id: "event",
                      status: "INTRODUCED",
                      path: "popover.tsx",
                      line: 16,
                      reason: "Observed relative to the selected BASE.",
                      at: "2026-11-04T00:00:00Z",
                    },
                  ],
                }
              : path.includes("/workspace?")
                ? workspace
                : path.includes("/repositories?")
                  ? { repositories: [repository], has_more: false }
                  : { items: [], total: 0 };
        return { ok: true, json: async () => data };
      }),
    );
    render(
      <MemoryRouter initialEntries={["/findings"]}>
        <WorkspaceScreen />
      </MemoryRouter>,
    );
    fireEvent.click(
      await screen.findByRole("button", {
        name: /Long function from changed source/,
      }),
    );
    const inspector = within(screen.getByRole("dialog"));
    expect(
      inspector.getByText(
        newCode ? "Changed code" : "Not attributed to new code",
      ),
    ).toBeVisible();
    expect(
      inspector.queryByText("Outside changed lines"),
    ).not.toBeInTheDocument();
    fireEvent.click(
      inspector.getByRole("button", { name: "History" }),
    );
    expect(await inspector.findByText("INTRODUCED")).toBeVisible();
  },
);
