export default function Source({
  item,
  highlight,
  startLine = 1,
}: {
  item?: { source?: string };
  highlight?: number;
  startLine?: number;
}) {
  return (
    <pre
      className="source-code"
      tabIndex={0}
      role="region"
      aria-label="Source code excerpt"
    >
      {(item?.source || "No source available in this scope.")
        .split("\n")
        .map((line, i) => (
          <span
            key={i}
            className={highlight === i + startLine ? "highlight" : ""}
          >
            <b>{i + startLine}</b>
            <code>{line || " "}</code>
          </span>
        ))}
    </pre>
  );
}
