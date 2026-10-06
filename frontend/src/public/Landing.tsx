import { Link } from "react-router";
import Badge from "../shared/Badge";
import { AnalyzeLink } from "./PublicShell";
import { InvestigationDemo, FindingsPreview } from "./InvestigationDemo";
import { capabilities, faqs, statuses } from "./content";

function Hero() {
  return (
    <section className="public-hero">
      <div className="hero-copy">
        <span className="eyebrow">
          ENGINEERING TRUTH, CONTINUOUSLY VERIFIED
        </span>
        <h1>
          Know what your software <em>actually does.</em>
        </h1>
        <p>
          Connect what your team says with what the software implements. Find
          quality and security risks, understand what changed, and follow the
          evidence to the next action.
        </p>
        <div className="public-ctas">
          <AnalyzeLink />
          <Link className="secondary" to="/demo">
            Explore Demo <span aria-hidden="true">→</span>
          </Link>
        </div>
        <Link className="hero-explain" to="/#how-it-works">
          See how ProjectTrace works <span aria-hidden="true">↓</span>
        </Link>
        <p className="hero-note">
          Source stays unexecuted. Conclusions stay explainable.
        </p>
      </div>
      <InvestigationDemo />
    </section>
  );
}
function ProblemAndFlow() {
  const steps = [
    [
      "01",
      "Bring your source",
      "Upload an authorized repository ZIP into your own workspace.",
    ],
    [
      "02",
      "Analyze the evidence",
      "Supported code, documentation, packages and configuration become source-backed observations.",
    ],
    [
      "03",
      "Check what is true",
      "Atomic technical statements are compared with suitable current evidence.",
    ],
    [
      "04",
      "Investigate & act",
      "Follow findings, changed assumptions and ownership into a review decision.",
    ],
  ];
  return (
    <>
      <section className="public-section problem-section">
        <div>
          <span className="eyebrow">THE PROBLEM</span>
          <h2>
            Software changes.
            <br />
            Engineering knowledge falls behind.
          </h2>
          <p>
            A README says one thing. The code says another. A security finding
            lacks change context. Someone has to work out what is true and who
            should act.
          </p>
        </div>
        <div className="fragmented-flow">
          <span className="eyebrow">FROM DISCONNECTED SIGNALS</span>
          <div className="signal-tags">
            <span>Code</span>
            <span>Docs</span>
            <span>Security</span>
            <span>Dependencies</span>
            <span>Infrastructure</span>
            <span>PRs</span>
          </div>
          <div className="connected-result">
            <span aria-hidden="true">↘</span>
            <strong>One evidence-driven investigation.</strong>
            <small>What happened · why it matters · who owns it</small>
          </div>
        </div>
      </section>
      <section className="public-section how-section" id="how-it-works">
        <div className="section-intro">
          <span className="eyebrow">HOW PROJECTTRACE WORKS</span>
          <h2>From source to a decision you can explain.</h2>
        </div>
        <ol className="public-process">
          {steps.map(([number, title, text]) => (
            <li key={number}>
              <span>{number}</span>
              <h3>{title}</h3>
              <p>{text}</p>
            </li>
          ))}
        </ol>
        <details className="technical-disclosure">
          <summary>Technical details</summary>
          <p>
            Native analyzers produce snapshot-scoped evidence. The Evidence
            Graph connects it to versioned claims, findings and policies.
            Incremental observations reuse unchanged files; affected claims are
            reverified. Human decisions retain reasons and audit context.
          </p>
          <Link to="/guide/how-it-works?mode=technical">
            Explore the architecture in the Guide →
          </Link>
        </details>
      </section>
    </>
  );
}
function IntegrityShowcase() {
  return (
    <section className="public-section integrity-showcase" id="integrity">
      <div>
        <span className="eyebrow">THE CLAIM LEDGER</span>
        <h2>Your engineering claims should have evidence.</h2>
        <p>
          “We use JWT.” “Production storage is private.” “Payments use
          PostgreSQL.” Important statements should stay connected to their
          source, version and owner.
        </p>
        <p>
          ProjectTrace distinguishes direct support, inference, missing proof,
          changed evidence and contradiction.
        </p>
        <Link className="text-link" to="/guide/claims">
          Understand the Claim Ledger →
        </Link>
      </div>
      <div className="claim-preview">
        <div className="preview-heading">
          <span>CLAIM LEDGER</span>
          <span>SYNTHETIC NORTHSTAR EXAMPLES</span>
        </div>
        <div className="preview-claim">
          <Badge value="VERIFIED" />
          <strong>Database uses PostgreSQL.</strong>
          <code>payments.py · psycopg</code>
        </div>
        <div className="preview-claim">
          <Badge value="CONTRADICTED" />
          <strong>Authentication uses JWT.</strong>
          <code>auth/session.py · SessionMiddleware</code>
        </div>
        <div className="preview-claim">
          <Badge value="CONTRADICTED" />
          <strong>Production storage is private.</strong>
          <code>deploy/storage.tf · public-read</code>
        </div>
        <details>
          <summary>What do all five statuses mean?</summary>
          <dl>
            {statuses.map(([status, meaning]) => (
              <div key={status}>
                <dt>
                  <Badge value={status} />
                </dt>
                <dd>{meaning}</dd>
              </div>
            ))}
          </dl>
        </details>
      </div>
    </section>
  );
}
function EvidenceShowcase() {
  return (
    <section className="public-section evidence-showcase">
      <div className="evidence-thread">
        <span className="eyebrow">FOLLOW THE PROOF</span>
        {[
          ["Claim", "Authentication uses JWT."],
          ["Documentation", "README.md"],
          ["Implementation", "auth/session.py:4"],
          ["Change", "Synthetic PR #1842"],
          ["Owner", "Identity Team"],
          ["Action", "Review the change. Update the statement."],
        ].map(([label, value], i) => (
          <div key={label}>
            <span className="thread-dot" aria-hidden="true">
              {i + 1}
            </span>
            <small>{label}</small>
            <strong>{value}</strong>
          </div>
        ))}
      </div>
      <div>
        <span className="eyebrow">EXPLAINABLE BY DESIGN</span>
        <h2>Every important conclusion has a trail.</h2>
        <p>
          See what was observed, where it came from, which source version was
          analyzed and why the conclusion followed.
        </p>
        <p>
          A finding can be urgent and uncertain. A claim can be verified in
          source while its runtime deployment remains unknown. ProjectTrace
          keeps those distinctions visible.
        </p>
        <Link className="text-link" to="/guide/evidence">
          Learn how evidence works →
        </Link>
      </div>
    </section>
  );
}
function CodeSecurityShowcase() {
  return (
    <section className="public-section code-security" id="product">
      <div className="section-intro">
        <span className="eyebrow">NATIVE QUALITY & SECURITY</span>
        <h2>
          Useful analysis.
          <br />
          Connected engineering context.
        </h2>
        <p>
          Findings are evidence for an investigation, with a rule, source,
          version and a next action.
        </p>
      </div>
      <div className="capability-list">
        {capabilities.map((feature, i) => (
          <article key={feature.id}>
            <span className="capability-number">
              {String(i + 1).padStart(2, "0")}
            </span>
            <div>
              <div className="capability-title">
                <h3>{feature.title}</h3>
                <Badge value={feature.status} />
              </div>
              <p>{feature.description}</p>
              <details>
                <summary>Coverage & technical detail</summary>
                <p>{feature.detail}</p>
              </details>
              <Link to={`/guide/${feature.id}`}>
                Explore {feature.title.toLowerCase()} →
              </Link>
            </div>
          </article>
        ))}
      </div>
      <div className="supported-strip">
        <strong>Native syntax metrics</strong>
        <span>Python</span>
        <span>JavaScript / JSX</span>
        <span>TypeScript / TSX</span>
        <span>Java</span>
      </div>
      <p className="coverage-note">
        Coverage is explicit. Unsupported files, unqueried advisories and failed
        engines are never presented as clean.
      </p>
    </section>
  );
}
function ChangeShowcase() {
  return (
    <section className="public-section change-showcase" id="change">
      <div>
        <span className="eyebrow">DRIFT, IMPACT & PR REVIEW</span>
        <h2>
          Understand the change.
          <br />
          Then make the decision.
        </h2>
        <p>
          When evidence changes, ProjectTrace connects it to affected statements
          and documentation. A new snapshot preserves the earlier state instead
          of rewriting history.
        </p>
        <div className="drift-sequence">
          <Badge value="VERIFIED" />
          <span aria-hidden="true">→</span>
          <Badge value="STALE" />
          <span aria-hidden="true">→</span>
          <Badge value="CONTRADICTED" />
        </div>
        <p>
          A first-snapshot mismatch is a consistency problem. Drift requires a
          proven earlier state and a changed current one.
        </p>
        <Link to="/guide/drift">Follow a historical change →</Link>
      </div>
      <div className="pr-preview">
        <div className="preview-heading">
          <span>PROJECTTRACE PR DECISION</span>
          <span>DEMO / #1842</span>
        </div>
        <h3>Replace JWT with sessions</h3>
        <dl>
          <div>
            <dt>Implementation</dt>
            <dd>Session middleware observed</dd>
          </div>
          <div>
            <dt>Claims</dt>
            <dd>
              <Badge value="CONTRADICTED" />
            </dd>
          </div>
          <div>
            <dt>Documentation</dt>
            <dd>README needs review</dd>
          </div>
          <div>
            <dt>Owner</dt>
            <dd>Identity Team</dd>
          </div>
        </dl>
        <div className="pr-decision">
          <Badge value="REVIEW_REQUIRED" />
          <p>
            Inspect current evidence and update the outdated authentication
            statement.
          </p>
        </div>
        <small>
          Illustrative excerpt of the native demo gate. Live provider
          publication remains unverified.
        </small>
      </div>
    </section>
  );
}
function CloudRiskShowcase() {
  return (
    <section className="public-section cloud-showcase" id="cloud-risk">
      <div className="cloud-path">
        <span className="eyebrow">
          DECLARED CONFIGURATION / SYNTHETIC EXAMPLE
        </span>
        <strong>Production storage is private.</strong>
        <Badge value="CONTRADICTED" />
        <div>
          <code>deploy/storage.tf</code>
          <span aria-hidden="true">↓</span>
          <strong>Production bucket declaration</strong>
          <span aria-hidden="true">↓</span>
          <code>acl = "public-read"</code>
          <span aria-hidden="true">↓</span>
          <strong>Public exposure requires review</strong>
        </div>
        <small>
          Static source evidence · deployment and runtime reachability
          unobserved
        </small>
      </div>
      <div>
        <span className="eyebrow">INFRASTRUCTURE, CLOUD & RISK</span>
        <h2>
          Know which risks are declared.
          <br />
          Know what is still unobserved.
        </h2>
        <p>
          Supported infrastructure declarations become assets, identities,
          exposure signals and evidence-backed relationships.
        </p>
        <div className="cloud-availability">
          <p>
            <strong>Available:</strong> static Terraform, Kubernetes, Compose,
            CloudFormation and Docker evidence.
          </p>
          <p>
            <strong>AWS adapter implemented:</strong> bounded authorized
            read-only inventory. Live account validation is still unverified.
          </p>
          <p>
            <strong>Deferred:</strong> Azure/GCP live inventory, effective
            identity permissions and runtime attack paths.
          </p>
        </div>
        <Link to="/guide/cloud-security">Understand cloud evidence →</Link>
      </div>
    </section>
  );
}
function FindingsAndAsk() {
  return (
    <section className="public-section investigation-section">
      <div className="section-intro">
        <span className="eyebrow">ONE INVESTIGATION WORKSPACE</span>
        <h2>
          From “something is wrong”
          <br />
          to “here is the evidence.”
        </h2>
        <p>
          Open a synthetic row below to inspect its source, reasoning and
          recommended action.
        </p>
      </div>
      <FindingsPreview />
      <div className="ask-showcase">
        <div>
          <span className="eyebrow">ASK ENGINEERING</span>
          <h3>Questions deserve engineering answers.</h3>
          <p>
            Get a structured answer with scope, evidence, related claims and
            limitations. Follow the citations before acting.
          </p>
          <Link to="/guide/ask">Explore evidence-grounded questions →</Link>
        </div>
        <div className="answer-preview">
          <small>SYNTHETIC DEMO QUESTION</small>
          <h4>How is authentication implemented?</h4>
          <p>Current static evidence configures sessions.</p>
          <Badge value="VERIFIED" />
          <dl>
            <div>
              <dt>Evidence</dt>
              <dd>
                <code>auth/session.py:4</code>
              </dd>
            </div>
            <div>
              <dt>Related claim</dt>
              <dd>
                Authentication uses JWT. <Badge value="CONTRADICTED" />
              </dd>
            </div>
            <div>
              <dt>Scope</dt>
              <dd>Analyzed source snapshot; runtime unobserved</dd>
            </div>
          </dl>
        </div>
      </div>
    </section>
  );
}
function GuideAndTeams() {
  return (
    <>
      <section className="public-section guide-showcase">
        <div>
          <span className="eyebrow">PROJECTTRACE GUIDE</span>
          <h2>
            A clear starting point.
            <br />
            For everyone on the team.
          </h2>
          <p>
            Understand the product in 60 seconds, then explore its modules,
            workflows and limits. Switch between simple explanations and
            technical detail.
          </p>
          <Link className="primary" to="/guide">
            Explore ProjectTrace Guide →
          </Link>
        </div>
        <div className="guide-teaser">
          <span>01 / PROJECTTRACE IN 60 SECONDS</span>
          <p>
            “Check what the team says against what the software proves. Show
            what changed. Help the right person act.”
          </p>
          <div>
            <Link to="/guide/product-map">Interactive product map →</Link>
            <Link to="/guide/glossary">Plain-language glossary →</Link>
            <Link to="/guide/workflows">Common workflows →</Link>
          </div>
        </div>
      </section>
      <section className="public-section teams-section" id="teams">
        <div className="section-intro">
          <span className="eyebrow">DIFFERENT ROLES. SHARED EVIDENCE.</span>
          <h2>One view of what needs attention.</h2>
        </div>
        <div className="audience-list">
          {[
            [
              "Developers",
              "Inspect source, rule explanations and the impact of a change.",
            ],
            [
              "Security teams",
              "Review static flows, secrets, packages and infrastructure with clear coverage.",
            ],
            [
              "Engineering & platform leaders",
              "Follow ownership, outdated assumptions and the review decisions behind a change.",
            ],
            [
              "CTOs & CEOs",
              "Understand what is supported, what needs attention and who owns the next action.",
            ],
          ].map(([role, text]) => (
            <article key={role}>
              <h3>{role}</h3>
              <p>{text}</p>
            </article>
          ))}
        </div>
      </section>
    </>
  );
}
function TrustAndFAQ() {
  return (
    <>
      <section className="public-section trust-section">
        <div>
          <span className="eyebrow">SOURCE IS A RESPONSIBILITY</span>
          <h2>
            Controls you can understand.
            <br />
            Limits you can inspect.
          </h2>
          <p>
            Uploaded code is never executed. Secret-shaped values are masked.
            Tenant and repository checks scope investigations. No external AI or
            marketing tracker receives source from this release.
          </p>
          <p>
            Persistent source retention is operator-managed; self-service
            deletion and full enterprise controls remain deferred.
          </p>
          <div className="public-ctas">
            <Link className="secondary" to="/trust">
              Read the security model →
            </Link>
            <Link to="/privacy">What happens to source →</Link>
          </div>
        </div>
        <div className="trust-principles">
          <span>Untrusted source</span>
          <span>Bounded native analysis</span>
          <span>Scoped access</span>
          <span>Explicit provenance</span>
          <span>Human review</span>
          <span>Auditable decisions</span>
        </div>
      </section>
      <section className="public-section faq-section" id="faq">
        <div className="section-intro">
          <span className="eyebrow">A FEW USEFUL ANSWERS</span>
          <h2>Before you bring your source.</h2>
        </div>
        <div className="faq-list">
          {faqs.map(([question, answer]) => (
            <details key={question}>
              <summary>{question}</summary>
              <p>{answer}</p>
            </details>
          ))}
        </div>
      </section>
    </>
  );
}
function FinalCTA() {
  return (
    <section className="public-section final-cta">
      <span className="eyebrow">UNDERSTAND IT. VERIFY IT. KEEP IT TRUE.</span>
      <h2>
        Your software changes every day.
        <br />
        Your engineering knowledge should keep up.
      </h2>
      <p>Connect source, evidence and human decisions in ProjectTrace.</p>
      <div className="public-ctas">
        <AnalyzeLink />
        <Link className="secondary" to="/demo">
          Explore Demo →
        </Link>
      </div>
    </section>
  );
}
export default function Landing() {
  return (
    <>
      <Hero />
      <div className="capability-strip">
        <span>Unexecuted source</span>
        <span>Native quality & security</span>
        <span>Versioned claims</span>
        <span>Source-level evidence</span>
        <span>Explainable PR decisions</span>
      </div>
      <ProblemAndFlow />
      <IntegrityShowcase />
      <EvidenceShowcase />
      <CodeSecurityShowcase />
      <ChangeShowcase />
      <CloudRiskShowcase />
      <FindingsAndAsk />
      <GuideAndTeams />
      <TrustAndFAQ />
      <FinalCTA />
    </>
  );
}
