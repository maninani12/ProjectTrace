import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { Overview } from "./WorkspaceApp";
import { api, type Workspace } from "./api";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

it("uses complete summary counts when all preview arrays are empty", () => {
  const data = {
    organization: "Real result fixture",
    repositories: [
      {
        id: "repo",
        name: "Repository",
        system: "System",
        snapshot: { status: "PARTIAL", id: "snapshot" },
      },
    ],
    claim: [],
    finding: [],
    evidence: [],
    graph_node: [],
    edge: [],
    drift: [],
    analysis: { state: "PARTIAL" },
    counts: {
      complete: true,
      totals: { claim: 1500, finding: 7904 },
      claim_status: { VERIFIED: 934, INFERRED: 559, UNVERIFIED: 7 },
      material_findings: 1368,
      repositories: { repo: { totals: { claim: 1500, finding: 7904 } } },
    },
  } as unknown as Workspace;
  render(<Overview data={data} onOpen={vi.fn()} navigate={vi.fn()} />);
  expect(screen.getAllByText("1500").length).toBeGreaterThan(0);
  expect(screen.getByText("1368")).toBeVisible();
  expect(screen.getByText("934 directly verified")).toBeVisible();
  expect(screen.getByText("1500 claims")).toBeVisible();
  expect(
    screen.getAllByText("PARTIAL", { exact: true }).length,
  ).toBeGreaterThan(0);
  expect(
    screen.queryByText("No high or critical findings in the current results."),
  ).not.toBeInTheDocument();
  expect(
    screen.getByText("1368 findings require review; open All findings."),
  ).toBeVisible();
});

it("bounds a stalled read and reports an error instead of returning fabricated zero data", async () => {
  vi.useFakeTimers();
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockImplementation(
        (_url, options) =>
          new Promise((_resolve, reject) =>
            options.signal.addEventListener("abort", () =>
              reject(new Error("aborted")),
            ),
          ),
      ),
  );
  const read = api("/workspace?summary=1");
  const checked = expect(read).rejects.toThrow(
    "did not complete within 15 seconds",
  );
  await vi.advanceTimersByTimeAsync(15000);
  await checked;
});
