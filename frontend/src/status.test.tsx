import { describe, expect, it } from "vitest";
import {
  analysisLabel,
  dependencyState,
  emptyMessage,
  isAnalysisActive,
  overviewState,
  repositoryState,
  repositoryEngines,
  scopeWorkspace,
} from "./status";
import type { Repository, Workspace } from "./api";

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
      risk_path: [
        { id: "risk-one", repository_id: "one" },
        { id: "risk-two", repository_id: "two" },
      ],
      edge: [{ id: "e", source: "a", target: "b", relationship: "RELATED" }],
    } as Workspace;
    const scoped = scopeWorkspace(data, "one");
    expect(scoped.claim.map((c) => c.id)).toEqual(["a"]);
    expect(scoped.risk_path?.map((risk) => risk.id)).toEqual(["risk-one"]);
    expect(scoped.edge).toEqual([]);
    expect(scoped.analysis.state).toBe("FAILED");
  });
  it("does not infer success from a missing snapshot or a running job", () => {
    expect(repositoryState({ id: "ready", snapshot: null } as never)).toBe(
      "READY",
    );
    for (const state of [
      "READY",
      "VALIDATING",
      "FINALIZING",
      "CANCELLED",
      "FAILED",
      "UNKNOWN",
    ]) {
      expect(overviewState({ ...empty, analysis: { state } })).toBe(state);
      expect(analysisLabel(state)).not.toBe("Analysis completed");
    }
    expect(isAnalysisActive("FINALIZING")).toBe(true);
    expect(isAnalysisActive("PARTIAL")).toBe(false);
  });
  it("distinguishes cached vulnerability findings from checked and unchecked declarations", () => {
    expect(
      dependencyState({
        id: "one",
        vulnerability_status: "CHECKED",
        vulnerabilities: [
          { id: "OSV-example", summary: "Known issue", url: "https://osv.dev" },
        ],
      }),
    ).toBe("VULNERABLE");
    expect(
      dependencyState({
        id: "two",
        vulnerability_status: "CHECKED",
        vulnerabilities: [],
      }),
    ).toBe("CHECKED_NO_KNOWN_ADVISORY");
    expect(dependencyState({ id: "three" })).toBe("NOT_CHECKED");
    expect(
      dependencyState({ id: "four", vulnerability_status: "CHECK_FAILED" }),
    ).toBe("CHECK_FAILED");
  });
  it("keeps native coverage while an advisory-only job is pending", () => {
    const repository = {
      id: "one",
      snapshot: {
        status: "PARTIAL",
        engines: { SAST: { state: "COMPLETED" }, OSV: { state: "COMPLETED" } },
      },
      latest_job: { id: "job", type: "ADVISORIES", state: "QUEUED" },
    } as unknown as Repository;
    expect(repositoryEngines(repository)?.SAST.state).toBe("COMPLETED");
    expect(repositoryEngines(repository)?.OSV.state).toBe("QUEUED");
    expect(
      repositoryState({
        ...repository,
        latest_job: { id: "job", type: "ADVISORIES", state: "COMPLETED" },
      } as never),
    ).toBe("PARTIAL");
  });
  it("uses published engine diagnostics only when a compact successful job matches that snapshot", () => {
    const repository = {
      id: "one",
      snapshot: {
        id: "published",
        status: "PARTIAL",
        engines: { PARSING: { state: "PARTIAL" } },
      },
      latest_job: { id: "job", state: "PARTIAL", snapshot_id: "published" },
    } as unknown as Repository;
    expect(repositoryEngines(repository)?.PARSING.state).toBe("PARTIAL");
    for (const state of ["ANALYZING", "FAILED", "CANCELLED"]) {
      expect(
        repositoryEngines({
          ...repository,
          latest_job: { ...repository.latest_job, state },
        } as Repository),
      ).toBeUndefined();
    }
    expect(
      repositoryEngines({
        ...repository,
        latest_job: { ...repository.latest_job, snapshot_id: "other" },
      } as Repository),
    ).toBeUndefined();
  });
});
