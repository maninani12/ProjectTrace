import { describe, expect, it } from "vitest";
import { analysisLabel, emptyMessage, scopeWorkspace } from "./status";
import type { Workspace } from "./api";

const empty = {
  repositories: [],
  analysis: { state: "NO_REPOSITORY" },
  claim: [],
  finding: [],
  evidence: [],
  dependency: [],
  drift: [],
  pr: [],
  job: [],
  review: [],
  exception: [],
  graph_node: [],
  edge: [],
} as unknown as Workspace;
describe("truthful analysis and scoped empty states", () => {
  it("does not describe an empty or failed workspace as completed", () => {
    expect(analysisLabel("NO_REPOSITORY")).toBe("No repository imported");
    expect(analysisLabel("FAILED")).toBe("Analysis failed");
    expect(emptyMessage("Claim Ledger", empty, false)[0]).toContain(
      "Import a repository",
    );
  });
  it("distinguishes completed, filtered, running and partial empty claims", () => {
    const data = {
      ...empty,
      repositories: [{ id: "repo" }],
      analysis: { state: "COMPLETED" },
    } as Workspace;
    expect(emptyMessage("Claim Ledger", data, false)[0]).toContain(
      "No technical claims",
    );
    expect(emptyMessage("Claim Ledger", data, true)[0]).toContain(
      "current filters",
    );
    expect(
      emptyMessage(
        "Claim Ledger",
        { ...data, analysis: { state: "VERIFYING" } },
        false,
      )[0],
    ).toContain("extracting engineering evidence");
    expect(
      emptyMessage(
        "Claim Ledger",
        { ...data, analysis: { state: "PARTIAL" } },
        false,
      )[1],
    ).toContain("partial");
  });
  it("keeps another repository's claims and graph outside the selected scope", () => {
    const data = {
      ...empty,
      repositories: [
        { id: "one", latest_job: { state: "FAILED" } },
        { id: "two" },
      ],
      claim: [
        { id: "a", repository_id: "one" },
        { id: "b", repository_id: "two" },
      ],
      edge: [{ id: "e", source: "a", target: "b", relationship: "RELATED" }],
    } as Workspace;
    const scoped = scopeWorkspace(data, "one");
    expect(scoped.claim.map((c) => c.id)).toEqual(["a"]);
    expect(scoped.edge).toEqual([]);
    expect(scoped.analysis.state).toBe("FAILED");
  });
});
