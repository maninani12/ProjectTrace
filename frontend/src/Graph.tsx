import { useEffect, useState } from "react";
import { ReactFlow, Background, Controls, MarkerType } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import Badge from "./shared/Badge";
import type { Workspace, Item } from "./api";
function label(item: Item) {
  return item.text || item.title || item.path || item.name || item.id;
}
export default function Graph({
  data,
  onOpen,
}: {
  data: Workspace;
  onOpen: (i: Item) => void;
}) {
  const candidates = [
    ...data.claim,
    ...data.finding,
    ...(data.graph_node || []),
    ...data.dependency,
  ];
  const [focus, setFocus] = useState(
    candidates.find((c) => c.status === "CONTRADICTED")?.id ||
      candidates[0]?.id ||
      "",
  );
  const [relation, setRelation] = useState("ALL");
  useEffect(() => {
    if (!candidates.some((c) => c.id === focus))
      setFocus(candidates[0]?.id || "");
  }, [candidates, focus]);
  const center = candidates.find((c) => c.id === focus);
  const edges = data.edge.filter(
    (e) =>
      (e.source === focus || e.target === focus) &&
      (relation === "ALL" || e.relationship === relation),
  );
  const connectedIds = new Set(edges.flatMap((e) => [e.source, e.target]));
  const items = [
    ...data.claim,
    ...data.finding,
    ...data.evidence,
    ...data.dependency,
    ...(data.graph_node || []),
  ].filter((i) => connectedIds.has(i.id) || i.id === focus);
  const nodes = items.map((i, n) => ({
    id: i.id,
    position: {
      x: i.id === focus ? 40 : 420,
      y: i.id === focus ? 130 : (n - items.indexOf(center!)) * 130 + 40,
    },
    data: {
      label: (
        <div className="graph-label">
          <small>{i.kind || i.category || i.class}</small>
          <strong>{label(i)}</strong>
          <Badge value={i.status || i.severity || i.authority} />
        </div>
      ),
    },
    style: {
      width: 280,
      borderColor: i.status === "CONTRADICTED" ? "#cf917a" : "#c7d3ce",
      background: "var(--surface)",
      color: "var(--text)",
      borderRadius: 6,
    },
  }));
  return (
    <>
      <div className="filters">
        <select
          aria-label="Graph focus"
          value={focus}
          onChange={(e) => setFocus(e.target.value)}
        >
          {candidates.map((c) => (
            <option key={c.id} value={c.id}>
              {label(c)}
            </option>
          ))}
        </select>
        <select
          aria-label="Graph relationship"
          value={relation}
          onChange={(e) => setRelation(e.target.value)}
        >
          <option value="ALL">All relationships</option>
          {[...new Set(data.edge.map((e) => e.relationship))].map((r) => (
            <option key={r}>{r}</option>
          ))}
        </select>
        <span className="subtle">Select a node to inspect evidence</span>
      </div>
      <div className="graph-canvas">
        <ReactFlow
          key={focus + relation}
          nodes={nodes}
          edges={edges.map((e) => ({
            ...e,
            label: e.relationship.replaceAll("_", " "),
            markerEnd: { type: MarkerType.ArrowClosed },
            style: { stroke: "#647c70" },
            labelStyle: { fill: "#647c70", fontSize: 10 },
          }))}
          fitView
          minZoom={0.25}
          maxZoom={1.5}
          onNodeClick={(_, node) => {
            const item = items.find((i) => i.id === node.id);
            if (item) onOpen(item);
          }}
        >
          <Background gap={24} />
          <Controls />
        </ReactFlow>
      </div>
      <div className="context-note">
        This neighborhood is derived from stored evidence edges. It does not
        infer runtime topology or network reachability.
      </div>
    </>
  );
}
