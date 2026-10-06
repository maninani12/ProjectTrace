import type { Item, Repository, Workspace } from "./api";

const activeStates = new Set([
  "QUEUED",
  "FETCHING",
  "VALIDATING",
  "PARSING",
  "ANALYZING",
  "BUILDING_EVIDENCE",
  "EXTRACTING_CLAIMS",
  "VERIFYING",
  "CORRELATING",
  "FINALIZING",
]);
export function isAnalysisActive(state: string) {
  return activeStates.has(state);
}
export function repositoryState(repository: Repository) {
  if (
    repository.latest_job?.type === "ADVISORIES" &&
    !isAnalysisActive(repository.latest_job.state || "UNKNOWN") &&
    ["PARTIAL", "FAILED", "CANCELLED"].includes(
      repository.snapshot?.status || "",
    )
  )
    return repository.snapshot!.status;
  return repository.latest_job?.state || repository.snapshot?.status || "READY";
}
export function repositoryEngines(repository: Repository) {
  const job = repository.latest_job;
  if (job?.type !== "ADVISORIES")
    return job ? job.engines : repository.snapshot?.engines;
  const engines = { ...repository.snapshot?.engines, ...job.engines };
  if (
    isAnalysisActive(job.state || "UNKNOWN") ||
    ["FAILED", "CANCELLED"].includes(job.state || "")
  ) {
    engines.OSV = {
      ...engines.OSV,
      state: job.state || "UNKNOWN",
      errors: job.errors,
      warnings: job.warnings,
      limitations: [
        "Exact declared versions only; this advisory job has not completed.",
      ],
    };
  }
  return engines;
}
export function overviewState(data: Workspace) {
  const state = data.analysis?.state || "UNKNOWN";
  if (!["COMPLETED", "COMPLETED_NO_FINDINGS"].includes(state)) return state;
  return data.claim.some((claim) => claim.status === "CONTRADICTED") ||
    data.finding.some(
      (finding) =>
        ["HIGH", "CRITICAL"].includes(finding.severity || "") &&
        !["RESOLVED", "FALSE_POSITIVE"].includes(finding.review_status || ""),
    )
    ? "REVIEW_REQUIRED"
    : "SUPPORTED_SCOPE_COMPLETE";
}
export function dependencyState(item: Item) {
  if (item.vulnerability_status === "CHECKED")
    return item.vulnerabilities?.length
      ? "VULNERABLE"
      : "CHECKED_NO_KNOWN_ADVISORY";
  return item.vulnerability_status || "NOT_CHECKED";
}

export function analysisLabel(state: string) {
  const labels: Record<string, string> = {
    NO_REPOSITORY: "No repository imported",
    READY: "Ready for analysis",
    QUEUED: "Analysis queued",
    FETCHING: "Fetching source",
    VALIDATING: "Validating source",
    PARSING: "Parsing source",
    ANALYZING: "Analyzing source",
    BUILDING_EVIDENCE: "Building evidence",
    EXTRACTING_CLAIMS: "Extracting claims",
    VERIFYING: "Verifying claims",
    CORRELATING: "Correlating evidence",
    FINALIZING: "Finalizing analysis",
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
    "risk_path",
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
    state: repositories.length
      ? repositoryState(repositories[0])
      : "NO_REPOSITORY",
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
  if (state === "READY")
    return [
      "Repository is ready for its first analysis.",
      "Upload a source snapshot from Repositories to start the native pipeline.",
    ];
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
  if (state && isAnalysisActive(state))
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
