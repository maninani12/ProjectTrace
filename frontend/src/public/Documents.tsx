import { Link } from "react-router";
import { guideTopics } from "./guideContent";
export default function PublicDocument({ page }: { page: string }) {
  const titles: Record<string, string> = {
    trust: "Security built around evidence.",
    privacy: "What happens to your source.",
    about: "Engineering knowledge should keep up.",
    docs: "ProjectTrace documentation.",
    changelog: "Changes you can trace.",
  };
  return (
    <article className="public-document">
      <span className="eyebrow">PROJECTTRACE / {page.toUpperCase()}</span>
      <h1>{titles[page]}</h1>
      {page === "trust" ? (
        <>
          <p className="guide-intro">
            Uploaded repositories are untrusted data. ProjectTrace reads
            supported files and records evidence; it does not execute their
            code.
          </p>
          <h2>Source and credentials</h2>
          <p>
            ZIP imports enforce path, symlink, byte and file-count limits.
            Supported grammar extensions run in a bounded helper process.
            Secret-shaped values are redacted in stored source and derived
            observations. A full OS filesystem/network parser sandbox is still
            deferred.
          </p>
          <h2>Workspace access</h2>
          <p>
            Server-side organization, repository and role checks scope records,
            jobs, profiles, graph retrieval and reviews. Local passwords use
            Argon2. HttpOnly sessions, origin checks and CSRF checks protect
            authenticated changes.
          </p>
          <h2>Controlled connections</h2>
          <p>
            No external AI is configured or called. Optional OSV checks send
            package identity/version, not source. GitHub fetching and read-only
            AWS inventory require authorized configuration. AWS inventory never
            writes cloud resources; its live account validation remains
            unverified here.
          </p>
          <h2>Validation is bounded</h2>
          <p>
            Regression, authorization and real queue/recovery tests support the
            implemented controls. They are not a penetration-test certification,
            compliance claim or guarantee of complete security coverage.
          </p>
          <Link to="/guide/security-privacy">
            Read the technical security guide →
          </Link>
        </>
      ) : page === "privacy" ? (
        <>
          <p className="guide-intro">
            Keep the difference between a temporary upload and retained
            engineering evidence clear.
          </p>
          <h2>What is stored?</h2>
          <p>
            The workspace database retains redacted source, original content
            hashes, claims, findings, dependency metadata, snapshot history,
            reviews and audit events. Session tokens are stored as digests.
          </p>
          <h2>How long?</h2>
          <p>
            Queued raw analysis inputs are encrypted and expiring. Persistent
            source and derived history are operator-managed. There is no
            configurable self-service retention or deletion workflow in this
            release. Backups also need protected handling.
          </p>
          <h2>What leaves ProjectTrace?</h2>
          <p>
            No source is sent to an AI provider. Optional advisory queries send
            package metadata to OSV. Authorized GitHub fetches and AWS reads
            contact their providers. The public site uses no third-party
            marketing tracker.
          </p>
          <h2>Can I delete source?</h2>
          <p>
            A complete tenant-wide deletion workflow covering all derived
            records, backups and audit retention is deferred. Do not assume
            enterprise deletion guarantees. Ask your deployment operator about
            retention before importing sensitive source.
          </p>
          <Link to="/guide/limitations">Read current limits →</Link>
        </>
      ) : page === "about" ? (
        <>
          <p className="guide-intro">
            ProjectTrace continuously checks whether what an organization says
            about its software is still supported by what the software
            implements.
          </p>
          <h2>One connected investigation</h2>
          <p>
            Code quality, security, dependencies and infrastructure create
            evidence. The Claim Ledger and Evidence Graph connect that evidence
            to current statements, changes, ownership and human decisions.
          </p>
          <h2>Built on explicit limits</h2>
          <p>
            Native analysis works independently of competitor services. A static
            finding is distinct from runtime proof; a first-snapshot mismatch is
            distinct from historical drift. Unsupported capabilities remain
            visible.
          </p>
          <Link to="/guide">Understand the product →</Link>
        </>
      ) : page === "changelog" ? (
        <>
          <h2>1.5.0 · Native Code Intelligence</h2>
          <p>
            Separate reliability and maintainability observations, explainable
            function metrics, configurable quality profiles and gates, stable
            symbol fingerprints, explicit BASE/HEAD history, bounded
            duplicate-block comparison, imported coverage reports, maintenance
            hotspots and snapshot trends. Quality findings connect to existing
            evidence, reviews, policies and PR results. Supported languages
            remain at partial maturity; full control-flow semantics, live Git
            history and large-monorepo capacity are unverified.
          </p>
          <h2>1.4.0 · Public product experience</h2>
          <p>
            A separate public landing page, a 31-topic Guide with simple and
            technical explanations, an interactive product map, local account
            creation, contextual help, shared themes and static public-page
            generation. Native analysis retains engine version 1.3.3.
          </p>
          <h2>1.3.3 · Native engineering integrity</h2>
          <p>
            Four-language syntax metrics, bounded Python flows, native profiles,
            supported IaC assets and risk paths, parser process isolation and
            real service/recovery validation. Live AWS validation and full
            enterprise capabilities remain incomplete.
          </p>
          <h2>1.2 · Source-backed investigation</h2>
          <p>
            Repository snapshots, impact, claim history, explainable gates,
            scoped review, dependency coverage and grounded retrieval evolved in
            the existing application.
          </p>
          <Link to="/guide/limitations">
            Current coverage and limitations →
          </Link>
        </>
      ) : (
        <>
          <p className="guide-intro">
            Start with a plain explanation. Open technical detail when you need
            the rules, inputs and boundaries.
          </p>
          <div className="docs-index">
            {guideTopics.map((topic) => (
              <Link key={topic.id} to={`/guide/${topic.id}?mode=technical`}>
                <strong>{topic.title}</strong>
                <span>{topic.simple}</span>
              </Link>
            ))}
          </div>
          <h2>Deployment</h2>
          <p>
            The source bundle contains README, ARCHITECTURE, SECURITY and
            deployment/operations documentation. SQLite and local accounts are
            development adapters. Production requires PostgreSQL, Redis/Celery,
            protected input encryption, explicit origins and deployment-specific
            validation.
          </p>
          <p>
            Live provider credentials, domain ownership and production
            operations must be configured by an authorized operator. Public
            pricing and commercial plan logic have not been finalized.
          </p>
        </>
      )}
    </article>
  );
}
