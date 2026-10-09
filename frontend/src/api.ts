export type Scope = {
  repository: string;
  repository_id: string;
  system: string;
  component: string;
  branch: string;
  commit: string;
  snapshot_id: string;
  analysis_at: string;
  analyzer_version: string;
  rule_version?: string;
};
export type EngineResult = {
  state: string;
  coverage?: string | string[];
  limitations?: string[];
  warnings?: { message: string; path?: string }[] | string[];
  errors?: string[];
  finding_count?: number;
  result_count?: number;
  supported_files?: number;
  findings?: number;
  declarations?: number;
  analyzer_version?: string;
  checked_declarations?: number;
  failed_declarations?: number;
  unknown_version_declarations?: number;
  unchecked_declarations?: number;
  cache_hits?: number;
  provider?: string;
};
export type Impact = {
  base_id?: string | null;
  changed_files: string[];
  affected_claims: string[];
  affected_documentation?: string[];
  affected_architecture?: string[];
  affected_api?: string[];
  affected_findings?: string[];
  affected_policies?: string[];
  removed_claims?: string[];
  verification?: {
    reused: number;
    reverified: number;
    reused_claim_ids?: string[];
    reverified_claim_ids?: string[];
  };
  affected_nodes?: {
    id: string;
    class: string;
    path?: string | null;
    snapshot_id: string;
    via: string[];
  }[];
};
export type Item = {
  error_detail?: {
    code: string;
    message: string;
    budget?: string;
    actual?: number | string;
    maximum?: number;
    remediation?: string;
  };
  retry_count?: number;
  dimension?: string;
  symbol?: string;
  measured?: number;
  threshold?: number;
  metric?: string;
  machine_status?: string;
  fingerprint_version?: string;
  first_line?: number;
  id: string;
  version?: number | string;
  kind?: string;
  repository_id?: string;
  snapshot_id?: string;
  branch?: string;
  scope?: Scope;
  text?: string;
  title?: string;
  status?: string;
  severity?: string;
  confidence?: string;
  category?: string;
  owner?: string;
  path?: string;
  line?: number;
  source?: string;
  class?: string;
  authority?: string;
  reason?: string;
  explanation?: string;
  recommendation?: string;
  remediation?: string;
  review_status?: string;
  review_reason?: string;
  rule?: string;
  rule_id?: string;
  rule_version?: string;
  analyzer_version?: string;
  language?: string;
  line_end?: number;
  end_line?: number;
  secret_context?: string;
  classification?: string;
  delta?: string;
  new_code?: boolean;
  asset_kind?: string;
  public?: string;
  encryption?: string;
  verification_scope?: string;
  factors?: string[];
  node_ids?: string[];
  flow?: { kind: string; path: string; line: number; symbol: string }[];
  license_status?: string;
  credential_context?: string;
  context?: string;
  provider?: string;
  provenance?: string;
  advisory_checked_at?: string;
  advisory_provider?: string;
  advisory_error?: string;
  fingerprint?: string;
  first_seen?: string;
  last_seen?: string;
  identity_id?: string;
  claim_version?: number;
  previous_version_id?: string;
  cwe?: string;
  evidence_ids?: string[];
  supporting_ids?: string[];
  contradicting_ids?: string[];
  history?: { status: string; at: string; reason: string }[];
  type?: string;
  old_status?: string;
  pr_number?: number;
  number?: number;
  base_id?: string;
  head_id?: string;
  changed_files?: string[];
  gate?: Gate;
  affected_claims?: string[];
  name?: string;
  ecosystem?: string;
  direct?: boolean | null;
  license?: string;
  vulnerability_status?: string;
  vulnerabilities?: { id: string; summary: string; url: string }[];
  advisory?: { id: string; url: string };
  source_id?: string;
  target?: string;
  relationship?: string;
  actor?: string;
  action?: string;
  created_at?: string;
  state?: string;
  started_at?: string;
  finished_at?: string;
  stage?: string;
  warnings?: { message: string; path?: string; analyzer?: string }[];
  errors?: string[];
  engines?: Record<string, EngineResult>;
  execution?: string;
  duration_ms?: number;
  origin?: string;
  version_kind?: string;
  dependency_kind?: string;
  manifest?: string;
  data?: {
    old?: string;
    new?: string;
    reason?: string;
    files?: number;
    claims?: number;
    findings?: number;
  };
  expires_at?: string;
};
export type Edge = {
  id: string;
  source: string;
  target: string;
  relationship: string;
};
export type Gate = {
  overall: string;
  mode: string;
  results: {
    policy: string;
    result: string;
    reason: string;
    target?: string;
  }[];
};
export type Snapshot = {
  id: string;
  branch: string;
  commit: string;
  file_count: number;
  changed_files: string[];
  gate: Gate;
  scope: Scope;
  status: string;
  changed_files_count?: number;
  warnings_count?: number;
  coverage_summary?: {
    source_analysis_percent?: number;
    source_files?: number;
    source_files_parsed?: number;
  };
  impact_list_counts?: Record<string, number>;
  commit_source?: string;
  source_provenance?: {
    source?: string;
    source_url?: string;
    ref?: string;
    commit?: string;
    archive_sha256?: string;
  };
  engines?: Record<string, EngineResult>;
  impact?: Impact;
  reused_files?: number;
  analyzer_version?: string;
  base_id?: string;
  quality_metrics?: {
    path: string;
    line: number;
    name: string;
    language: string;
    cyclomatic: number;
    length: number;
    nesting: number;
    formula: string;
  }[];
  warnings?: { message: string; path?: string }[];
  claim_extraction?: {
    state: string;
    implementation: number;
    documentation: number;
    documentation_files: number;
  };
};
export type Repository = {
  id: string;
  name: string;
  system: string;
  component: string;
  owner: string;
  provider: string;
  snapshot: Snapshot | null;
  latest_job?: Item;
};
export type Workspace = {
  repository_page?: {
    offset: number;
    limit: number;
    total: number;
    has_more: boolean;
    search: string;
  };
  organization: string;
  demo: boolean;
  repositories: Repository[];
  claim: Item[];
  finding: Item[];
  evidence: Item[];
  edge: Edge[];
  dependency: Item[];
  drift: Item[];
  pr: Item[];
  review: Item[];
  exception: Item[];
  job: Item[];
  limitations: string[];
  graph_node: Item[];
  risk_path?: Item[];
  analysis: { state: string; truncated?: boolean; warnings?: string[] };
  counts?: WorkspaceCounts & {
    complete: boolean;
    scope: string;
    repositories: Record<string, WorkspaceCounts>;
  };
  record_page?: RecordPage;
  capabilities?: {
    job_mode: "sync" | "local" | "celery";
    advisories_enabled: boolean;
    private_scm_available?: boolean;
  };
};
export type WorkspaceCounts = {
  totals: Record<string, number>;
  claim_status: Record<string, number>;
  finding_severity: Record<string, number>;
  material_findings: number;
};
export type RecordPage = {
  items: Item[];
  total: number;
  offset: number;
  limit: number;
  has_more: boolean;
  severity_counts: Record<string, number>;
  snapshot_ids: Record<string, string>;
};
export type Identity = {
  email: string;
  role: string;
  csrf: string;
  organization?: string;
  demo: boolean;
};
export type Answer = {
  answer: string;
  verification: string;
  confidence: string;
  claims: Item[];
  evidence: Item[];
  provider: string;
  limitations: string[];
};
let csrf = "";
export function setCSRF(value: string) {
  csrf = value;
}
export class APIError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "APIError";
  }
}

export async function api<T>(
  path: string,
  body?: unknown,
  raw?: Blob,
): Promise<T> {
  const controller = new AbortController();
  // Reads fail visibly instead of keeping a page spinner alive indefinitely.
  // Uploads retain the server's intake budget; aborting a fetch does not cancel its job.
  const timer =
    body === undefined && !raw
      ? setTimeout(() => controller.abort(), 15000)
      : undefined;
  try {
    const response = await fetch("/api" + path, {
      signal: controller.signal,
      credentials: "include",
      method: body !== undefined || raw ? "POST" : "GET",
      headers: {
        ...(raw
          ? { "Content-Type": "application/zip" }
          : body !== undefined
            ? { "Content-Type": "application/json" }
            : {}),
        "X-CSRF-Token": csrf,
      },
      body: raw || (body !== undefined ? JSON.stringify(body) : undefined),
    });
    if (!response.ok) {
      let message = await response.text();
      try {
        const error = JSON.parse(message);
        message =
          typeof error.detail === "string"
            ? error.detail
            : error.detail?.message
              ? `${error.detail.message}${error.detail.budget ? ` ${error.detail.budget}: ${error.detail.actual} / ${error.detail.maximum}.` : ""}${error.detail.remediation ? ` ${error.detail.remediation}` : ""}`
              : "The submitted fields are invalid.";
      } catch {
        /* plain error */
      }
      throw new APIError(message, response.status);
    }
    return await response.json();
  } catch (error) {
    if (controller.signal.aborted)
      throw new Error(
        "This request did not complete within 15 seconds. Retry or select a repository; existing analysis jobs continue.",
      );
    throw error;
  } finally {
    if (timer !== undefined) clearTimeout(timer);
  }
}
