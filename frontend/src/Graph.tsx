import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import GraphCanvas from "./GraphCanvas";
import { api, type Edge, type Item, type Workspace } from "./api";

type NodePage = { items: Item[]; total: number };
type Neighborhood = { nodes: Item[]; edges: Edge[]; total: number };

export default function Graph({
  data,
  onOpen,
}: {
  data: Workspace;
  onOpen: (item: Item) => void;
}) {
  const [repository, setRepository] = useState(data.repositories[0]?.id || "");
  const [nodeClass, setNodeClass] = useState("COMPONENT");
  const [search, setSearch] = useState("");
  const [nodeOffset, setNodeOffset] = useState(0);
  const [edgeOffset, setEdgeOffset] = useState(0);
  const [focus, setFocus] = useState("");
  const [focusedNode, setFocusedNode] = useState<Item | null>(null);
  const [relation, setRelation] = useState("ALL");
  const selected = data.repositories.find((repo) => repo.id === repository);
  useEffect(() => {
    if (!selected) setRepository(data.repositories[0]?.id || "");
  }, [selected, data.repositories]);
  const listing = useQuery({
    queryKey: [
      "graph-nodes",
      repository,
      selected?.snapshot?.id,
      nodeClass,
      search,
      nodeOffset,
    ],
    enabled: Boolean(selected?.snapshot),
    queryFn: () =>
      api<NodePage>(
        `/graph/nodes?repository_id=${encodeURIComponent(repository)}&snapshot_id=${encodeURIComponent(selected!.snapshot!.id)}&limit=50&offset=${nodeOffset}${nodeClass === "ALL" ? "" : "&node_class=" + nodeClass}${search ? "&search=" + encodeURIComponent(search) : ""}`,
      ),
  });
  const fallback = [
    ...data.claim,
    ...data.finding,
    ...data.graph_node,
    ...data.dependency,
  ]
    .filter((item) => item.repository_id === repository)
    .slice(0, 50);
  const visible = listing.data?.items || fallback;
  useEffect(() => {
    setFocus(visible[0]?.id || "");
    setEdgeOffset(0);
  }, [listing.data, repository, nodeClass, nodeOffset]);
  const neighborhood = useQuery({
    queryKey: ["graph-neighborhood", focus, relation, edgeOffset],
    enabled: Boolean(focus),
    queryFn: () =>
      api<Neighborhood>(
        `/graph/neighborhood?node_id=${encodeURIComponent(focus)}&limit=50&offset=${edgeOffset}${relation === "ALL" ? "" : "&relationship=" + encodeURIComponent(relation)}`,
      ),
  });
  const allNodes = [
    ...new Map(
      [
        ...visible,
        ...(neighborhood.data?.nodes || []),
        ...(focusedNode ? [focusedNode] : []),
      ].map((item) => [item.id, item]),
    ).values(),
  ];
  const merged = {
    ...data,
    claim: allNodes.filter((item) => item.kind === "claim"),
    finding: allNodes.filter((item) => item.kind === "finding"),
    evidence: allNodes.filter((item) => item.kind === "evidence"),
    dependency: allNodes.filter((item) => item.kind === "dependency"),
    graph_node: allNodes.filter((item) => item.kind === "graph_node"),
    edge:
      neighborhood.data?.edges ||
      data.edge
        .filter((edge) => edge.source === focus || edge.target === focus)
        .slice(0, 50),
  };
  function reset() {
    setNodeOffset(0);
    setFocusedNode(null);
    setEdgeOffset(0);
    setFocus("");
  }
  return (
    <>
      <div className="filters">
        <label>
          Graph repository{" "}
          <select
            value={repository}
            onChange={(event) => {
              setRepository(event.target.value);
              reset();
            }}
          >
            {data.repositories.map((repo) => (
              <option key={repo.id} value={repo.id}>
                {repo.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Node type{" "}
          <select
            value={nodeClass}
            onChange={(event) => {
              setNodeClass(event.target.value);
              reset();
            }}
          >
            {[
              "COMPONENT",
              "REPOSITORY",
              "ARTIFACT",
              "FUNCTION",
              "API_ENDPOINT",
              "CLOUD_RESOURCE",
              "DOCUMENTATION_SECTION",
              "ALL",
            ].map((value) => (
              <option key={value} value={value}>
                {value.replaceAll("_", " ")}
              </option>
            ))}
          </select>
        </label>
        <label>
          Find a node{" "}
          <input
            value={search}
            maxLength={120}
            onChange={(event) => {
              setSearch(event.target.value);
              reset();
            }}
          />
        </label>
        <button
          disabled={!nodeOffset}
          onClick={() => setNodeOffset(Math.max(0, nodeOffset - 50))}
        >
          Previous nodes
        </button>
        <button
          disabled={!listing.data || nodeOffset + 50 >= listing.data.total}
          onClick={() => setNodeOffset(nodeOffset + 50)}
        >
          Next nodes
        </button>
        <span>
          {listing.data?.total ?? fallback.length} captured nodes · snapshot{" "}
          {selected?.snapshot?.id.slice(0, 8) || "None"}
        </span>
      </div>
      {(listing.isError || neighborhood.isError) && (
        <p role="alert">
          The paged graph could not be loaded. Available workspace evidence is
          shown; this view may be incomplete.
        </p>
      )}
      {!selected?.snapshot ? (
        <p>No captured snapshot is available.</p>
      ) : (
        <GraphCanvas
          data={merged}
          onOpen={onOpen}
          focus={focus}
          relation={relation}
          onFocusChange={(value) => {
            setFocusedNode(allNodes.find((item) => item.id === value) || null);
            setFocus(value);
            setEdgeOffset(0);
          }}
          onRelationChange={(value) => {
            setRelation(value);
            setEdgeOffset(0);
          }}
        />
      )}
      <div className="filters">
        <button
          disabled={!edgeOffset}
          onClick={() => setEdgeOffset(Math.max(0, edgeOffset - 50))}
        >
          Previous links
        </button>
        <button
          disabled={
            !neighborhood.data || edgeOffset + 50 >= neighborhood.data.total
          }
          onClick={() => setEdgeOffset(edgeOffset + 50)}
        >
          Next links
        </button>
        <span>
          {neighborhood.data?.total ?? merged.edge.length} captured links · one
          hop
        </span>
      </div>
    </>
  );
}
