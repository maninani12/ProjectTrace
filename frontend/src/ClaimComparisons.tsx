type Evidence = { id: string; path: string; hash: string };
type Verdict = {
  claim_id?: string;
  status: string;
  reason: string;
  evidence: Evidence[];
  evidence_truncated: boolean;
};
export type ClaimComparison = {
  claim_key: string;
  text: string;
  path: string;
  line?: number;
  document?: Evidence;
  before: Verdict;
  after: Verdict;
};

export default function ClaimComparisons({
  items,
  onInspect,
}: {
  items: ClaimComparison[];
  onInspect: (id: string) => void;
}) {
  return (
    <section aria-label="Claim evidence comparison">
      {items.map((item) => (
        <article className="settings-panel" key={item.claim_key}>
          <h3>Original claim: {item.text}</h3>
          <p>
            {item.path}
            {item.line ? `:${item.line}` : ""}
          </p>
          {item.document && (
            <button onClick={() => onInspect(item.document!.id)}>
              Inspect original documentation
            </button>
          )}
          <div
            className="quality-table-wrap"
            tabIndex={0}
            role="region"
            aria-label="BASE and HEAD claim evidence"
          >
            <table className="quality-table">
              <thead>
                <tr>
                  <th>Snapshot</th>
                  <th>Verdict / explanation</th>
                  <th>Source evidence</th>
                </tr>
              </thead>
              <tbody>
                {(
                  [
                    ["BASE", item.before],
                    ["HEAD", item.after],
                  ] as const
                ).map(([label, verdict]) => (
                  <tr key={label}>
                    <td>{label}</td>
                    <td>
                      <strong>{verdict.status}</strong>
                      <p>{verdict.reason}</p>
                      {verdict.claim_id && (
                        <button onClick={() => onInspect(verdict.claim_id!)}>
                          Inspect {label} claim
                        </button>
                      )}
                    </td>
                    <td>
                      {verdict.evidence.length === 0 && (
                        <p>No conclusive source evidence captured.</p>
                      )}
                      {verdict.evidence.map((source) => (
                        <p key={source.id}>
                          <button onClick={() => onInspect(source.id)}>
                            Inspect {label} source: {source.path}
                          </button>
                          <small>SHA-256: {source.hash}</small>
                        </p>
                      ))}
                      {verdict.evidence_truncated && (
                        <p>
                          First eight references shown; inspect the claim for
                          all evidence.
                        </p>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p>
            Static evidence in the captured scope. Runtime behavior and omitted
            services are unobserved.
          </p>
        </article>
      ))}
    </section>
  );
}
