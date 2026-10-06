import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import Badge from "../shared/Badge";
import Source from "../shared/Source";
import { demo } from "./content";

export function InvestigationDemo() {
  const [stage, setStage] = useState(2);
  const status = ["VERIFIED", "STALE", "CONTRADICTED"][stage];
  return (
    <div
      className="investigation-demo"
      role="region"
      aria-label="Authentication investigation example"
    >
      <div className="demo-window-bar">
        <span className="window-mark" aria-hidden="true">
          ● ● ●
        </span>
        <span>IDENTITY PLATFORM / CLAIM INSPECTOR</span>
        <span>DEMO</span>
      </div>
      <div className="demo-investigation-body">
        <div className="demo-context">
          <span>identity-api</span>
          <span>PR #1842 · Identity Team</span>
        </div>
        <div className="demo-statement">
          <small>WHAT THE DOCUMENTATION SAYS</small>
          <h2>{demo.claim}</h2>
          <Badge value={status} />
        </div>
        <div className="demo-source">
          <div>
            <span className="eyebrow">CURRENT IMPLEMENTATION</span>
            <code>auth/session.py</code>
          </div>
          <Source
            item={{ source: stage === 0 ? demo.before : demo.after }}
            highlight={4}
          />
        </div>
        <div className="demo-verdict">
          <span aria-hidden="true">
            {stage === 0 ? "✓" : stage === 1 ? "↻" : "≠"}
          </span>
          <p>
            {stage === 0
              ? "The previous JWT implementation supports the statement."
              : stage === 1
                ? "The implementation changed. The claim needs reverification."
                : "Current code configures sessions. The README still says JWT."}
          </p>
        </div>
        <div className="demo-action">
          <strong>
            {stage === 2
              ? "Review required"
              : stage === 1
                ? "Check current evidence"
                : "Supported in the earlier snapshot"}
          </strong>
          <span>
            {stage === 2 ? "Owner · Identity Team" : "Snapshot-scoped evidence"}
          </span>
        </div>
      </div>
      <div
        className="demo-stages"
        role="group"
        aria-label="Explore the authentication change"
      >
        {["Before change", "Change detected", "Evidence checked"].map(
          (label, i) => (
            <button
              key={label}
              aria-pressed={stage === i}
              onClick={() => setStage(i)}
            >
              <span>{i + 1}</span>
              {label}
            </button>
          ),
        )}
      </div>
      <p className="demo-caption">
        Synthetic Northstar example · same source fixture as the product demo ·
        never deployed.
      </p>
    </div>
  );
}

const examples = [
  {
    title: "Authentication uses JWT.",
    category: "Claim integrity",
    status: "CONTRADICTED",
    path: "auth/session.py",
    source: demo.after,
    line: 4,
    reason:
      "The current middleware configures sessions, while README.md still declares JWT.",
    action:
      "Identity Team: review the authentication change and update the documentation.",
    rule: "Snapshot-scoped claim verification",
  },
  {
    title: "Dynamic SQL reaches an execution sink",
    category: "Application security",
    status: "HIGH",
    path: "users/search.py",
    source: demo.sql,
    line: 3,
    reason:
      "A function argument is interpolated into SQL. This static hotspot requires context; no HTTP input or runtime exploitability is proven by this snippet.",
    action:
      "Pass query parameters separately and review the caller’s input handling.",
    rule: "Native dynamic-SQL rule · contextual hotspot",
  },
  {
    title: "Production storage is declared public",
    category: "Infrastructure",
    status: "HIGH",
    path: "deploy/storage.tf",
    source: demo.terraform,
    line: 2,
    reason:
      "The synthetic production-named bucket declaration sets public-read. This conflicts with the fixture’s explicit private-production-storage claim.",
    action: "Payments Team: remove public access and review the storage claim.",
    rule: "PT-IAC-003 · declared configuration",
  },
];
export function FindingsPreview() {
  const [selected, setSelected] = useState<number | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    if (selected !== null) dialog.current?.showModal();
  }, [selected]);
  const item = selected === null ? null : examples[selected];
  return (
    <>
      <div className="public-findings">
        <div className="preview-heading">
          <span>UNIFIED FINDINGS</span>
          <span>SYNTHETIC EXAMPLES</span>
        </div>
        <table>
          <caption className="sr-only">
            Explore three synthetic, source-backed findings
          </caption>
          <thead>
            <tr>
              <th>Signal</th>
              <th>Observation</th>
              <th>Source</th>
            </tr>
          </thead>
          <tbody>
            {examples.map((example, i) => (
              <tr key={example.title}>
                <td>
                  <Badge value={example.status} />
                </td>
                <td>
                  <button onClick={() => setSelected(i)}>
                    {example.title} <span aria-hidden="true">↗</span>
                  </button>
                  <small>{example.category}</small>
                </td>
                <td>
                  <code>{example.path}</code>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {item && (
        <dialog
          ref={dialog}
          className="public-inspector"
          aria-labelledby="public-inspector-title"
          onClose={() => setSelected(null)}
        >
          <header>
            <span className="eyebrow">EVIDENCE INSPECTOR / SYNTHETIC DEMO</span>
            <button
              className="icon-button"
              aria-label="Close example inspector"
              onClick={() => dialog.current?.close()}
            >
              ×
            </button>
          </header>
          <h2 id="public-inspector-title">{item.title}</h2>
          <Badge value={item.status} />
          <h3>Why it was flagged</h3>
          <p>{item.reason}</p>
          <div className="public-source-heading">
            <code>{item.path}</code>
            <span>{item.rule}</span>
          </div>
          <Source item={item} highlight={item.line} />
          <h3>Recommended action</h3>
          <p>{item.action}</p>
          <p className="subtle">
            Read-only example from the maintained Northstar fixtures. No private
            workspace data is shown.
          </p>
          <Link className="primary" to="/demo">
            Investigate in the product demo →
          </Link>
        </dialog>
      )}
    </>
  );
}
