import { useLayoutEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "./api";

type Boundary = { root: string; name: string };
type Assignment = {
  version: number | null;
  configuration: { version: number; components: Boundary[] };
};

export default function ComponentAssignments({
  repository,
  canEdit,
}: {
  repository: string;
  canEdit: boolean;
}) {
  const [rows, setRows] = useState<Boundary[]>([]);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const query = useQuery({
    queryKey: ["component-assignment", repository],
    enabled: repository !== "ALL",
    queryFn: () =>
      api<Assignment>(
        `/repositories/${encodeURIComponent(repository)}/components`,
      ),
  });
  useLayoutEffect(() => {
    setRows(
      query.data?.configuration.components.map((row) => ({ ...row })) || [],
    );
  }, [repository, query.data]);
  useLayoutEffect(() => {
    setMessage("");
  }, [repository]);
  async function save() {
    if (!query.data) return;
    setBusy(true);
    setMessage("");
    try {
      await api(`/repositories/${encodeURIComponent(repository)}/components`, {
        version: query.data.version,
        configuration: { version: 1, components: rows },
      });
      await query.refetch();
      setMessage(
        "Saved. Component assignments apply to the next source import.",
      );
    } catch (error) {
      setMessage((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="settings-panel">
      <h3>Repository component boundaries</h3>
      <p>
        Package manifests and ProjectTrace configuration declare component
        folders. Administrators can correct their names and boundaries for
        future imports. Historical snapshots keep their captured assignments.
      </p>
      {repository === "ALL" ? (
        <p>Select a repository to review its component assignments.</p>
      ) : (
        <>
          <p>
            Assignment version {query.data?.version ?? "None"}. Use a
            repository-relative folder, or . for the repository root.
          </p>
          {query.isError && (
            <p role="alert">Component assignments could not be loaded.</p>
          )}
          {rows.map((row, index) => (
            <div className="filter-row" key={index}>
              <label>
                Folder boundary{" "}
                <input
                  aria-label={`Component folder ${index + 1}`}
                  maxLength={240}
                  value={row.root}
                  disabled={!canEdit || busy}
                  onChange={(event) =>
                    setRows(
                      rows.map((item, i) =>
                        i === index
                          ? { ...item, root: event.target.value }
                          : item,
                      ),
                    )
                  }
                />
              </label>
              <label>
                Component name{" "}
                <input
                  aria-label={`Component name ${index + 1}`}
                  maxLength={150}
                  value={row.name}
                  disabled={!canEdit || busy}
                  onChange={(event) =>
                    setRows(
                      rows.map((item, i) =>
                        i === index
                          ? { ...item, name: event.target.value }
                          : item,
                      ),
                    )
                  }
                />
              </label>
              {canEdit && (
                <button
                  className="secondary"
                  disabled={busy}
                  onClick={() => setRows(rows.filter((_, i) => i !== index))}
                >
                  Remove boundary
                </button>
              )}
            </div>
          ))}
          {canEdit && (
            <div className="filter-row">
              <button
                className="secondary"
                disabled={busy || rows.length >= 500 || !query.data}
                onClick={() => setRows([...rows, { root: "", name: "" }])}
              >
                Add boundary
              </button>
              <button
                className="primary"
                disabled={
                  busy ||
                  !query.data ||
                  rows.some((row) => !row.root.trim() || !row.name.trim())
                }
                onClick={save}
              >
                {busy ? "Saving…" : "Save component assignments"}
              </button>
            </div>
          )}
          {!rows.length && (
            <p>
              No manual overrides. Declared manifest and configuration
              boundaries apply.
            </p>
          )}
          {message && <p role="status">{message}</p>}
        </>
      )}
    </section>
  );
}
