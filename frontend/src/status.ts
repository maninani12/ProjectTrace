import type { Workspace } from "./api";

export function analysisLabel(state: string) {
  const labels: Record<string, string> = {
    NO_REPOSITORY: "No repository imported",
    QUEUED: "Analysis queued",
    FETCHING: "Fetching source",
    PARSING: "Parsing source",
    ANALYZING: "Analyzing source",
    BUILDING_EVIDENCE: "Building evidence",
    EXTRACTING_CLAIMS: "Extracting claims",
    VERIFYING: "Verifying claims",
    CORRELATING: "Correlating evidence",
    COMPLETED: "Analysis completed",
    COMPLETED_NO_FINDINGS: "Completed · no findings",
    PARTIAL: "Analysis partial",
    FAILED: "Analysis failed",
    CANCELLED: "Analysis cancelled",
    UNKNOWN: "Analysis status unavailable",
  };
  return labels[state] || "Analysis status unavailable";
}

export function scopeWorkspace(data: Workspace, repository: string): Workspace {
  if (repository === "ALL") return data;
  const repositories = data.repositories.filter((r) => r.id === repository);
  const scoped = { ...data, repositories };
  for (const key of [
    "claim",
    "finding",
    "evidence",
    "dependency",
    "drift",
    "pr",
    "review",
    "exception",
    "job",
    "graph_node",
  ] as const) {
    scoped[key] = (data[key] || []).filter(
      (item) =>
        item.repository_id === repository ||
        item.scope?.repository_id === repository,
    );
  }
  const ids = new Set(
    [
      ...scoped.claim,
      ...scoped.finding,
      ...scoped.evidence,
      ...scoped.dependency,
      ...scoped.graph_node,
    ].map((i) => i.id),
  );
  scoped.edge = data.edge.filter((e) => ids.has(e.source) && ids.has(e.target));
  scoped.analysis = {
    ...data.analysis,
    state:
      repositories[0]?.latest_job?.state ||
      repositories[0]?.snapshot?.status ||
      "QUEUED",
  };
  return scoped;
}

export function emptyMessage(page: string, data: Workspace, filtered: boolean) {
  if (!data.repositories.length)
    return [
      "Import a repository to begin analysis.",
      "Upload your source ZIP from Repositories.",
    ];
  const state = data.analysis?.state;
  if (state === "CANCELLED")
    return [
      "Analysis was cancelled.",
      "Upload a new snapshot to run analysis again.",
    ];
  if (state === "FAILED")
    return [
      "Analysis failed.",
      "Open Repositories to inspect the job error and upload a corrected snapshot.",
    ];
  if (
    state &&
    [
      "QUEUED",
      "FETCHING",
      "PARSING",
      "ANALYZING",
      "BUILDING_EVIDENCE",
      "EXTRACTING_CLAIMS",
      "VERIFYING",
      "CORRELATING",
    ].includes(state)
  )
    return [
      "ProjectTrace is extracting engineering evidence.",
      analysisLabel(state),
    ];
  if (filtered)
    return [
      "No results match the current filters.",
      "Clear the search and status filters to view the selected repository's results.",
    ];
  if (state === "PARTIAL")
    return [
      "No results in the completed analysis coverage.",
      "Analysis is partial. Review the warnings in Repositories before drawing conclusions.",
    ];
  if (page === "Claim Ledger" || page === "Architecture")
    return [
      "No technical claims were identified in the selected scope.",
      "Supported syntax and documentation were analyzed; unsupported claim types may require more evidence.",
    ];
  if (page === "Drift")
    return [
      "No historical drift detected.",
      "Upload a new snapshot to the same repository to compare changes. Initial documentation contradictions appear in Findings.",
    ];
  return [
    "No findings detected in the supported analysis scope.",
    "This is a static analysis result; runtime behavior and unsupported rules remain outside coverage.",
  ];
}
