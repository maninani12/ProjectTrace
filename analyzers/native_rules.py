"""ProjectTrace-owned native rules. Parser libraries supply syntax, not findings."""

NATIVE_RULES = {
    "PT-CLOUD-001": (
        "CLOUD",
        "HIGH",
        "Observed public ACL requires access review",
        "Correlate bucket and account access blocks and remove unnecessary public grants.",
        "CWE-732",
    ),
    "PT-CLOUD-002": (
        "CLOUD",
        "HIGH",
        "Observed Internet-wide security group ingress",
        "Restrict ingress and review actual resource attachments.",
        "CWE-284",
    ),
    "PT-SAST-005": (
        "SAST",
        "HIGH",
        "Dynamic code evaluation",
        "Replace evaluation with structured data handling.",
        "CWE-95",
    ),
    "PT-IAC-004": (
        "IAC",
        "HIGH",
        "Internet-wide ingress declared",
        "Restrict source ranges and expose only required services.",
        "CWE-284",
    ),
    "PT-IAC-005": (
        "IAC",
        "HIGH",
        "Wildcard identity permissions declared",
        "Scope actions and resources to the required workload.",
        "CWE-250",
    ),
    "PT-IAC-006": (
        "IAC",
        "HIGH",
        "Host namespace or filesystem access declared",
        "Remove host namespaces and hostPath mounts unless explicitly required.",
        "CWE-250",
    ),
    "PT-IAC-007": (
        "IAC",
        "MEDIUM",
        "Container privilege escalation permitted",
        "Set allowPrivilegeEscalation to false and drop unnecessary capabilities.",
        "CWE-250",
    ),
    "PT-IAC-008": (
        "IAC",
        "LOW",
        "Container resource limits missing",
        "Declare CPU and memory limits for every workload container.",
        None,
    ),
    "PT-IAC-009": (
        "IAC",
        "MEDIUM",
        "Public access prevention disabled",
        "Enable every public access block setting and review the bucket policy.",
        "CWE-732",
    ),
    "PT-QUALITY-006": (
        "QUALITY",
        "MEDIUM",
        "Empty exception handler",
        "Handle the failure explicitly or rethrow with safe context.",
        None,
    ),
    "PT-QUALITY-007": (
        "QUALITY",
        "LOW",
        "Duplicate function body",
        "Consider sharing the duplicated behavior after reviewing its responsibilities.",
        None,
    ),
    "PT-LICENSE-001": (
        "LICENSE",
        "MEDIUM",
        "Observed license requires review",
        "Review the observed SPDX identifier against the organization's license policy.",
        None,
    ),
}

RULE_LANGUAGES = {
    **{f"PT-SAST-{number:03}": ["Python"] for number in (1, 2, 3, 4, 7, 8, 9, 10)},
    "PT-SAST-005": ["JavaScript", "TypeScript", "Java"],
    "PT-SAST-006": ["Python", "JavaScript", "TypeScript"],
    "PT-QUALITY-005": ["Python"],
    "PT-QUALITY-006": ["JavaScript", "TypeScript", "Java"],
    "PT-IAC-001": ["Kubernetes YAML", "Compose YAML"],
    "PT-IAC-002": ["Kubernetes YAML", "Compose YAML", "Dockerfile"],
    **{f"PT-IAC-{number:03}": ["Terraform HCL", "CloudFormation YAML/JSON"] for number in (3, 4, 5)},
    "PT-IAC-006": ["Kubernetes YAML", "Compose YAML"],
    "PT-IAC-007": ["Kubernetes YAML"],
    "PT-IAC-008": ["Kubernetes YAML"],
    "PT-IAC-009": ["Terraform HCL"],
    "PT-CLOUD-001": ["AWS control-plane inventory"],
    "PT-CLOUD-002": ["AWS control-plane inventory"],
    "PT-SECRET-001": ["Supported text files"],
    "PT-LICENSE-001": ["Supported dependency manifests/lockfiles"],
}

RULE_EXAMPLES = {
    "PT-SAST-001": "db.execute(f'SELECT * FROM users WHERE id={value}')",
    "PT-SAST-002": "subprocess.run(request.args['cmd'], shell=True)",
    "PT-SAST-003": "pickle.loads(request.data)",
    "PT-SAST-004": "hashlib.md5(payload)",
    "PT-SAST-005": "eval(userInput)",
    "PT-SAST-006": "element.innerHTML = userInput",
    "PT-SAST-007": "send_file(request.args['path'])",
    "PT-SAST-008": "requests.get(request.args['url'])",
    "PT-SAST-009": "tempfile.mktemp()",
    "PT-SAST-010": "jwt.decode(token, options={'verify_signature': False})",
    "PT-SECRET-001": "api_key = '<credential-shaped literal>'",
    "PT-IAC-001": "securityContext: {privileged: true}",
    "PT-IAC-002": "USER root",
    "PT-IAC-003": 'resource "aws_s3_bucket" "production" { acl = "public-read" }',
    "PT-IAC-004": 'ingress { cidr_blocks = ["0.0.0.0/0"] }',
    "PT-IAC-005": '{"Statement": [{"Effect": "Allow", "Action": "*", "Resource": "*"}]}',
    "PT-IAC-006": "hostNetwork: true",
    "PT-IAC-007": "securityContext: {allowPrivilegeEscalation: true}",
    "PT-IAC-008": "containers: [{name: app, image: fixture:v1}]",
    "PT-IAC-009": "block_public_acls = false",
    "PT-QUALITY-001": "A function with measured cyclomatic complexity greater than 10.",
    "PT-QUALITY-002": "A function whose source span is greater than 80 lines.",
    "PT-QUALITY-003": "A function with more than four nested control-flow levels.",
    "PT-QUALITY-004": "A class whose source span is greater than 200 lines.",
    "PT-QUALITY-005": "try: work()\nexcept: pass",
    "PT-QUALITY-006": "try { work(); } catch (error) {}",
    "PT-QUALITY-007": "Two functions sharing an identical normalized body of at least 30 syntax nodes/tokens.",
    "PT-PARSE-001": "A syntax tree containing a parser error or a missing syntax node.",
    "PT-LICENSE-001": "A lockfile observes GPL-3.0-only while the configured profile restricts that identifier.",
    "PT-CLOUD-001": "An observed S3 ACL grants AllUsers and observed IgnorePublicAcls does not suppress it.",
    "PT-CLOUD-002": "An observed EC2 security group admits 0.0.0.0/0 or ::/0.",
}


def registry(rules, version):
    """Complete, reviewable metadata for the implemented rules, not a rule-count score."""
    return [
        {
            "id": key,
            "version": version,
            "category": value[0],
            "default_severity": value[1],
            "title": value[2],
            "remediation": value[3],
            "cwe": value[4],
            "enabled_by_default": True,
            "languages": RULE_LANGUAGES.get(key, ["Python", "JavaScript", "TypeScript", "Java"]),
            "explanation": value[2]
            + ". Findings describe static observations; runtime exploitability is not inferred.",
            "example": {"trigger": RULE_EXAMPLES[key], "remedy": value[3]},
            "references": ["https://cwe.mitre.org/data/definitions/" + value[4].split("-")[1] + ".html"]
            if value[4]
            else [],
        }
        for key, value in sorted(rules.items())
    ]
