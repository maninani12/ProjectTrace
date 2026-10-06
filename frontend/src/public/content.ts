export const capabilities = [
  {
    title: "Code quality",
    id: "code-quality",
    status: "AVAILABLE",
    description:
      "Review function complexity, nesting, length and exact duplicate bodies. Follow a finding to its rule and source.",
    detail:
      "Python, JavaScript/JSX, TypeScript/TSX and Java syntax metrics. Cognitive complexity is an approximation; full symbol and control-flow analysis is deferred.",
  },
  {
    title: "Application security",
    id: "application-security",
    status: "BETA",
    description:
      "Inspect modeled Python input-to-sink paths, masked secrets and security hotspots that need a person’s review.",
    detail:
      "Bounded Python flows and narrow static rules. A static finding is not proof of runtime exploitability. Framework and cross-file coverage is limited.",
  },
  {
    title: "Dependencies",
    id: "dependencies",
    status: "AVAILABLE",
    description:
      "See observed package versions, advisory coverage and licenses. Export a CycloneDX inventory.",
    detail:
      "Supported npm/Python manifest and lockfile subsets. Optional exact-version OSV checks send package metadata only. NOT_CHECKED never means safe.",
  },
  {
    title: "Infrastructure",
    id: "infrastructure",
    status: "AVAILABLE",
    description:
      "Inspect supported Terraform, Kubernetes, Compose, CloudFormation and Docker declarations as source evidence.",
    detail:
      "Configuration is never executed. Unrendered templates, effective IAM permissions and deployment state remain unproven.",
  },
] as const;

export const faqs = [
  [
    "What is ProjectTrace?",
    "ProjectTrace connects what a team says about its software to current evidence. It shows supported claims, contradictions, quality and security findings, change impact, ownership and review decisions.",
  ],
  [
    "Does ProjectTrace execute uploaded code?",
    "No. Uploaded repositories are untrusted data. ProjectTrace reads supported files with bounded static parsers; it does not run their scripts, builds, tests or dependency installers.",
  ],
  [
    "Do I need SonarQube or Wiz?",
    "No. ProjectTrace’s native quality, security and infrastructure engines operate independently. Cloud APIs and optional advisory feeds supply external observations, not competitor analysis.",
  ],
  [
    "What languages are supported?",
    "Native syntax metrics cover Python, JavaScript/JSX, TypeScript/TSX and Java. Modeled data-flow analysis currently focuses on Python. Unsupported or partial coverage stays visible.",
  ],
  [
    "Can I analyze a private repository?",
    "You can upload an authorized source ZIP into your own workspace. A GitHub App integration exists, but live private-source authorization and end-to-end checks are not yet verified in this installation.",
  ],
  [
    "Does ProjectTrace use AI?",
    "This release uses deterministic analysis and evidence-grounded retrieval. No external AI model is configured or called; source is not sent to an AI provider.",
  ],
  [
    "What is a claim, and what is drift?",
    "A claim is an atomic technical statement, such as ‘Authentication uses JWT.’ Drift requires earlier and current snapshots showing a change. A contradiction on the first snapshot is a consistency problem, not historical drift.",
  ],
  [
    "Can ProjectTrace review pull requests?",
    "The native gate combines findings, affected claims, drift, policies and review exceptions into an explainable decision. The deterministic PR demo works; live GitHub check publication still needs authorized end-to-end validation.",
  ],
  [
    "Does it connect to cloud accounts?",
    "Static infrastructure analysis works now. A bounded read-only AWS adapter is implemented, but live account validation has not been completed. Azure and GCP live inventory are deferred.",
  ],
  [
    "What happens to uploaded source?",
    "Redacted source, hashes, derived evidence and history are retained in the workspace database. Queued raw inputs are encrypted and expire. Retention is operator-managed; a self-service deletion workflow is not implemented.",
  ],
] as const;

export const statuses = [
  ["VERIFIED", "Current strong evidence directly supports the claim."],
  ["INFERRED", "Evidence suggests the statement without directly proving it."],
  ["UNVERIFIED", "There is not enough suitable evidence to decide."],
  ["STALE", "Supporting evidence changed and needs reverification."],
  ["CONTRADICTED", "Current evidence conflicts with the statement."],
] as const;

// Public, deliberately synthetic examples from samples/demo.json. Never tenant data.
export const demo = {
  claim: "Authentication uses JWT.",
  before:
    "import jwt\n\ndef issue_token(user):\n    return jwt.encode({'sub': user.id}, user.signing_key, algorithm='HS256')",
  after:
    "from starlette.middleware.sessions import SessionMiddleware\n\ndef configure_auth(app, settings):\n    app.add_middleware(SessionMiddleware, secret_key=settings.session_key, https_only=True, same_site='strict')",
  sql: "def search_users(connection, name):\n    # Deliberately unsafe static benchmark; never executed.\n    return connection.execute(f\"SELECT id FROM users WHERE name = '{name}'\")",
  terraform:
    'resource "aws_s3_bucket" "demo_production" {\n acl = "public-read"\n}',
};
