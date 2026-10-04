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
};
export type Item = {
  id: string;
  version?: number | string;
  kind?: string;
  repository_id?: string;
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
  direct?: boolean;
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
  data?: {
    old?: string;
    new?: string;
    reason?: string;
    files?: number;
    claims?: number;
    findings?: number;
  };
  expires_at?: string;
  state?: string;
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
};
export type Repository = {
  id: string;
  name: string;
  system: string;
  component: string;
  owner: string;
  provider: string;
  snapshot: Snapshot;
};
export type Workspace = {
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
export async function api<T>(
  path: string,
  body?: unknown,
  raw?: Blob,
): Promise<T> {
  const response = await fetch("/api" + path, {
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
          : "The submitted fields are invalid.";
    } catch {
      /* plain error */
    }
    throw new Error(message);
  }
  return response.json();
}
