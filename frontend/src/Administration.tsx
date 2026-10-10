import { useEffect, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router";
import { api, setCSRF } from "./api";
import type { AccessContext, Identity } from "./api";
import "./administration.css";

type Row = Record<string, unknown>;
type Page = {
  items: Row[];
  page?: { total: number; offset: number; limit: number; has_more: boolean };
  preview_limit?: number;
};
type Context = AccessContext & {
  permission_definitions: Record<string, string>;
  roles: { id: string; permissions: string[] }[];
  feature_catalog: { id: string; label: string; description: string }[];
  unavailable_controls: string[];
  active_job_policy: string;
};
type Field = {
  key: string;
  label: string;
  type?:
    "text" | "email" | "number" | "datetime-local" | "password" | "checkbox";
  options?: string[];
  required?: boolean;
  value?: string | number | boolean;
  lookup?: { path: string; versionKey?: string; exclusiveKeys?: string[] };
};
type Action = {
  title: string;
  path: string;
  base?: Row;
  fields?: Field[];
  explanation?: string;
  sensitive?: boolean;
};
const text = (value: unknown): string =>
  value == null
    ? "Unavailable"
    : typeof value === "object"
      ? Array.isArray(value)
        ? value.map(text).join(", ")
        : Object.entries(value as Row)
            .map(([k, v]) => `${k.replaceAll("_", " ")}: ${text(v)}`)
            .join(" · ")
      : String(value);
const version = (row: Row) => Number(row.version || 0);
const id = (row: Row) => String(row.id || row.user_id || "");
const command = () => crypto.randomUUID().replaceAll("-", "");
const caption = (value: string) =>
  value.replaceAll("_", " ").replaceAll(".", " / ");

function ErrorBox({ error, retry }: { error: unknown; retry?: () => void }) {
  return (
    <div role="alert" className="error">
      {error instanceof Error
        ? error.message
        : "The requested administration data is unavailable."}
      {retry && <button onClick={retry}>Retry</button>}
    </div>
  );
}

function Dialog({
  title,
  children,
  close,
}: {
  title: string;
  children: ReactNode;
  close: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement;
    ref.current?.focus();
    const handle = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
      if (event.key !== "Tab") return;
      const nodes = ref.current?.querySelectorAll<HTMLElement>(
        "button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),a[href]",
      );
      if (!nodes?.length) return;
      const first = nodes[0],
        last = nodes[nodes.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      }
      if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", handle);
    return () => {
      document.removeEventListener("keydown", handle);
      previous?.focus();
    };
  }, [close]);
  return (
    <div className="overlay">
      <div
        className="modal admin-dialog"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        ref={ref}
      >
        <div className="modal-head">
          <h2>{title}</h2>
          <button onClick={close} aria-label="Close administration dialog">
            Close
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

function Reauthenticate() {
  const [password, setPassword] = useState("");
  const [state, setState] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setState("");
    try {
      await api("/auth/reauthenticate", { password });
      setPassword("");
      setState(
        "Reauthenticated for five minutes. You can now retry the reviewed operation.",
      );
    } catch (error) {
      setState(
        error instanceof Error
          ? error.message
          : "Reauthentication unavailable.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <details className="admin-step-up">
      <summary>Sensitive operation verification</summary>
      <p>
        Local accounts verify their own password. OIDC-only accounts must sign
        in through their provider. Password verification does not claim MFA.
      </p>
      <form onSubmit={submit}>
        <label>
          Your password
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>
        <button disabled={busy}>
          {busy ? "Verifying…" : "Verify my identity"}
        </button>
        <p role="status">{state}</p>
      </form>
    </details>
  );
}

function RecordLookup({
  field,
  value,
  choose,
}: {
  field: Field;
  value: unknown;
  choose: (row?: Row) => void;
}) {
  const [search, setSearch] = useState("");
  const [submitted, setSubmitted] = useState("");
  const [offset, setOffset] = useState(0);
  const lookup = field.lookup!;
  const query = useQuery({
    queryKey: ["administration", "lookup", lookup.path, submitted, offset],
    queryFn: () =>
      api<Page>(
        `${lookup.path}?${new URLSearchParams({ search: submitted, offset: String(offset), limit: "25" })}`,
      ),
    retry: false,
  });
  return (
    <span className="admin-lookup">
      <input
        aria-label={`Search ${field.label}`}
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Search permitted records"
      />
      <button
        type="button"
        onClick={() => {
          setSubmitted(search);
          setOffset(0);
        }}
      >
        Search records
      </button>
      <select
        aria-label={field.label}
        required={field.required !== false}
        value={String(value || "")}
        onChange={(e) =>
          choose(query.data?.items.find((row) => id(row) === e.target.value))
        }
      >
        <option value="">Select…</option>
        {!!value && !query.data?.items.some((row) => id(row) === value) && (
          <option value={String(value)}>{String(value)}</option>
        )}
        {query.data?.items.map((row) => (
          <option key={id(row)} value={id(row)}>
            {String(row.display_name || row.email || row.name || id(row))} ·{" "}
            {id(row)}
          </option>
        ))}
      </select>
      {query.isLoading && <span role="status">Loading permitted records…</span>}
      {query.isError && (
        <ErrorBox error={query.error} retry={() => query.refetch()} />
      )}
      <span className="admin-lookup-pages">
        <button
          type="button"
          disabled={!offset || query.isFetching}
          onClick={() => setOffset(offset - 25)}
        >
          Previous choices
        </button>
        <button
          type="button"
          disabled={!query.data?.page?.has_more || query.isFetching}
          onClick={() => setOffset(offset + 25)}
        >
          More choices
        </button>
      </span>
    </span>
  );
}

function CommandDialog({
  action,
  close,
  changed,
}: {
  action: Action;
  close: () => void;
  changed: () => void;
}) {
  const [values, setValues] = useState<Row>(() =>
    Object.fromEntries(
      (action.fields || []).map((f) => [
        f.key,
        f.value ?? (f.type === "checkbox" ? false : ""),
      ]),
    ),
  );
  const [commandId, setCommandId] = useState(command);
  const [error, setError] = useState<unknown>();
  const [result, setResult] = useState<Row>();
  const [busy, setBusy] = useState(false);
  const [reason, setReason] = useState("");
  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(undefined);
    const normalized = { ...values };
    for (const field of action.fields || []) {
      if (field.type === "datetime-local")
        normalized[field.key] = values[field.key]
          ? new Date(String(values[field.key])).toISOString()
          : null;
      if (
        field.required === false &&
        field.type !== "checkbox" &&
        values[field.key] === ""
      )
        normalized[field.key] = null;
      if (field.type === "number")
        normalized[field.key] =
          values[field.key] === "" ? null : Number(values[field.key]);
    }
    try {
      const response = await api<Row>(action.path, {
        command_id: commandId,
        reason,
        expected_version: 0,
        ...action.base,
        ...normalized,
      });
      setResult(response);
      changed();
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog title={action.title} close={close}>
      {result ? (
        <div className="admin-command-result">
          <h3>{String(result.state || "Confirmed")}</h3>
          <p role="status">
            {result.replayed
              ? "Previously recorded operation returned safely."
              : "The server confirmed this operation."}
          </p>
          {result.audit_event_id ? (
            <p>
              Audit confirmation: <code>{String(result.audit_event_id)}</code>
            </p>
          ) : null}
          {result.invitation_token ? (
            <>
              <p>
                This invitation link is shown once. Share it only with the
                intended member using your approved process. Email delivery is
                not configured.
              </p>
              <input
                aria-label="One-time invitation link"
                readOnly
                value={`${window.location.origin}/invite#token=${encodeURIComponent(String(result.invitation_token))}`}
              />
            </>
          ) : null}
          {result.approval_id ? (
            <p>
              Approval request: <code>{String(result.approval_id)}</code>.
              Access stays unchanged until consent or approval completes.
            </p>
          ) : null}
          <button onClick={close}>Done</button>
        </div>
      ) : (
        <>
          <form className="admin-form" onSubmit={submit}>
            <p>
              {action.explanation ||
                "Review the selected scope and reason. The change takes effect only after the server confirms it."}
            </p>
            {(action.fields || []).map((field) => (
              <label key={field.key}>
                {field.label}
                {field.lookup ? (
                  <RecordLookup
                    field={field}
                    value={values[field.key]}
                    choose={(row) => {
                      setValues((v) => ({
                        ...v,
                        ...Object.fromEntries(
                          (field.lookup?.exclusiveKeys || []).map((key) => [
                            key,
                            "",
                          ]),
                        ),
                        [field.key]: row ? id(row) : "",
                        ...(row && field.lookup?.versionKey
                          ? { [field.lookup.versionKey]: version(row) }
                          : {}),
                      }));
                      setCommandId(command());
                    }}
                  />
                ) : field.options ? (
                  <select
                    aria-label={field.label}
                    value={String(values[field.key])}
                    required={field.required !== false}
                    onChange={(e) => {
                      setValues((v) => ({ ...v, [field.key]: e.target.value }));
                      setCommandId(command());
                    }}
                  >
                    <option value="">Select…</option>
                    {field.options.map((option) => (
                      <option key={option} value={option}>
                        {caption(option)}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    aria-label={field.label}
                    type={field.type || "text"}
                    value={
                      field.type === "checkbox"
                        ? undefined
                        : String(values[field.key] ?? "")
                    }
                    checked={
                      field.type === "checkbox"
                        ? !!values[field.key]
                        : undefined
                    }
                    min={field.type === "number" ? 0 : undefined}
                    required={
                      field.required !== false && field.type !== "checkbox"
                    }
                    onChange={(e) => {
                      setValues((v) => ({
                        ...v,
                        [field.key]:
                          field.type === "checkbox"
                            ? e.target.checked
                            : e.target.value,
                      }));
                      setCommandId(command());
                    }}
                  />
                )}
              </label>
            ))}
            <label>
              Reason
              <textarea
                value={reason}
                minLength={10}
                maxLength={500}
                required
                onChange={(e) => {
                  setReason(e.target.value);
                  setCommandId(command());
                }}
              />
            </label>
            <label className="admin-confirm">
              <input type="checkbox" required />I reviewed the target, scope and
              expected effect.
            </label>
            {!!error && <ErrorBox error={error} />}
            <button className="primary" disabled={busy}>
              {busy ? "Awaiting confirmation…" : "Confirm operation"}
            </button>
          </form>
          {action.sensitive && <Reauthenticate />}
        </>
      )}
    </Dialog>
  );
}

function DataSummary({ value }: { value: Row }) {
  return (
    <dl className="admin-summary">
      {Object.entries(value)
        .filter(
          ([key]) =>
            ![
              "items",
              "page",
              "limitations",
              "provenance",
              "organization_id",
            ].includes(key),
        )
        .map(([key, item]) => (
          <div key={key}>
            <dt>{caption(key)}</dt>
            <dd>{text(item)}</dd>
          </div>
        ))}
    </dl>
  );
}

function ReadView({ path }: { path: string }) {
  const data = useQuery({
    queryKey: ["administration", "summary", path],
    queryFn: () => api<Row>(path),
    retry: false,
  });
  if (data.isLoading)
    return <p role="status">Loading measured administration data…</p>;
  if (data.isError)
    return <ErrorBox error={data.error} retry={() => data.refetch()} />;
  if (!data.data) return null;
  const daily = data.data.daily_jobs as
    { day: string; jobs: number }[] | undefined;
  return (
    <section className="admin-panel">
      <DataSummary value={data.data} />
      {daily && (
        <>
          <h3>Analysis submissions by day</h3>
          {daily.length ? (
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Accepted jobs</th>
                </tr>
              </thead>
              <tbody>
                {daily.map((row) => (
                  <tr key={row.day}>
                    <td>{row.day}</td>
                    <td>
                      {row.jobs}
                      <meter
                        aria-label={`Jobs on ${row.day}`}
                        min={0}
                        max={Math.max(1, ...daily.map((d) => d.jobs))}
                        value={row.jobs}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p>No recorded submissions in this period.</p>
          )}
        </>
      )}
      {data.data.limitations ? (
        <p className="muted">{text(data.data.limitations)}</p>
      ) : null}
      {data.data.provenance ? (
        <p className="muted">{text(data.data.provenance)}</p>
      ) : null}
    </section>
  );
}

function PagedTable({
  path,
  columns,
  filterKey,
  actions,
  open,
  itemsKey = "items",
}: {
  path: string;
  columns: string[];
  filterKey?: string;
  actions?: (row: Row) => ReactNode;
  open?: (row: Row) => void;
  itemsKey?: string;
}) {
  const [offset, setOffset] = useState(0),
    [search, setSearch] = useState("");
  const params = new URLSearchParams({
    offset: String(offset),
    limit: "25",
    ...(filterKey && search ? { [filterKey]: search } : {}),
  });
  const data = useQuery({
    queryKey: ["administration", path, offset, search],
    queryFn: async () => {
      const result = await api<Page & Record<string, unknown>>(
        path + (path.includes("?") ? "&" : "?") + params,
      );
      return { ...result, items: result[itemsKey] as Row[] };
    },
    retry: false,
  });
  return (
    <section className="admin-panel">
      {filterKey && (
        <form
          className="filters"
          onSubmit={(event) => {
            event.preventDefault();
            const form = new FormData(event.currentTarget);
            setSearch(String(form.get("search") || ""));
            setOffset(0);
          }}
        >
          <label>
            Filter {caption(filterKey)}
            <input name="search" defaultValue={search} maxLength={120} />
          </label>
          <button>Search</button>
          {search && (
            <button
              type="button"
              onClick={() => {
                setSearch("");
                setOffset(0);
              }}
            >
              Clear filter
            </button>
          )}
        </form>
      )}
      {data.isLoading ? (
        <p role="status">Loading this page…</p>
      ) : data.isError ? (
        <ErrorBox error={data.error} retry={() => data.refetch()} />
      ) : (
        <>
          <div className="admin-table-scroll">
            <table>
              <thead>
                <tr>
                  {columns.map((column) => (
                    <th key={column}>{caption(column)}</th>
                  ))}
                  {(open || actions) && <th>Actions</th>}
                </tr>
              </thead>
              <tbody>
                {data.data?.items?.map((row, index) => (
                  <tr key={id(row) || index}>
                    {columns.map((column) => (
                      <td key={column}>{text(row[column])}</td>
                    ))}
                    {(open || actions) && (
                      <td className="admin-row-actions">
                        {open && (
                          <button onClick={() => open(row)}>Inspect</button>
                        )}
                        {actions?.(row)}
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!data.data?.items.length && (
            <p>No records in this authorized scope.</p>
          )}
          <div className="admin-pagination">
            <span>
              {data.data?.page
                ? `${data.data.page.total} records · ${offset + 1}–${offset + (data.data.items.length || 0)}`
                : `Bounded preview: at most ${data.data?.preview_limit || 100}`}
            </span>
            <button
              disabled={!offset}
              onClick={() => setOffset(Math.max(0, offset - 25))}
            >
              Previous page
            </button>
            <button
              disabled={!data.data?.page?.has_more}
              onClick={() => setOffset(offset + 25)}
            >
              Next page
            </button>
          </div>
        </>
      )}
    </section>
  );
}

function Detail({
  path,
  close,
  children,
}: {
  path: string;
  close: () => void;
  children?: (row: Row) => ReactNode;
}) {
  const data = useQuery({
    queryKey: ["administration", "detail", path],
    queryFn: () => api<Row>(path),
    retry: false,
  });
  return (
    <Dialog title="Administration record details" close={close}>
      {data.isLoading ? (
        <p role="status">Loading authorized details…</p>
      ) : data.isError ? (
        <ErrorBox error={data.error} retry={() => data.refetch()} />
      ) : (
        data.data && (
          <>
            <DataSummary value={data.data} />
            {Array.isArray(data.data.items) && (
              <PagedTable
                path={path}
                columns={Object.keys(
                  (data.data.items as Row[])[0] || { id: "", name: "" },
                ).slice(0, 8)}
              />
            )}
            {Array.isArray(data.data.members) && (
              <PagedTable
                path={path}
                itemsKey="members"
                columns={["id", "email", "role"]}
              />
            )}
            {children?.(data.data)}
          </>
        )
      )}
    </Dialog>
  );
}

type Policy = Row & {
  id: string;
  feature: string;
  version: number;
  decision: string;
  mandatory: boolean;
  allow_user_exceptions: boolean;
  expires_at?: string | null;
};
type FeatureResponse = Page & {
  effective?: Record<string, { allowed: boolean; reason: string }> | null;
};
function FeatureEditor({
  context,
  scope,
  target,
  feature,
  policy,
  close,
  changed,
  restore,
}: {
  context: Context;
  scope: string;
  target: string;
  feature: string;
  policy?: Policy;
  close: () => void;
  changed: () => void;
  restore?: Policy;
}) {
  const initial = restore || policy;
  const [decision, setDecision] = useState(
    String(initial?.decision || "INHERIT"),
  );
  const [mandatory, setMandatory] = useState(!!initial?.mandatory);
  const [exceptions, setExceptions] = useState(
    !!initial?.allow_user_exceptions,
  );
  const [expires, setExpires] = useState(
    initial?.expires_at
      ? new Date(initial.expires_at).toISOString().slice(0, 16)
      : "",
  );
  const [reason, setReason] = useState("");
  const [preview, setPreview] = useState<Row>();
  const [result, setResult] = useState<Row>();
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState(false);
  const [commandId, setCommandId] = useState(command);
  function edit() {
    setPreview(undefined);
    setCommandId(command());
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(undefined);
    const payload = {
      command_id: commandId,
      expected_version: policy?.version || 0,
      scope_type: scope,
      target_id: target,
      feature,
      decision,
      mandatory,
      allow_user_exceptions: exceptions,
      expires_at: expires ? new Date(expires + "Z").toISOString() : null,
      reason,
    };
    try {
      if (!preview)
        setPreview(await api<Row>("/admin/features/preview", payload));
      else {
        const saved = await api<Row>("/admin/features", {
          ...payload,
          preview_id: preview.preview_id,
        });
        setResult(saved);
        changed();
      }
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog
      title={`Feature access: ${context.feature_catalog.find((f) => f.id === feature)?.label || feature}`}
      close={close}
    >
      {result ? (
        <>
          <h3>{String(result.state)}</h3>
          <p role="status">
            {result.state === "APPLIED"
              ? "Policy confirmed. Existing snapshots and findings remain retained."
              : "The proposal awaits a separate operator. Effective access has not changed."}
          </p>
          <p>
            Audit confirmation: <code>{String(result.audit_event_id)}</code>
          </p>
          <button onClick={close}>Done</button>
        </>
      ) : (
        <>
          <form className="admin-form" onSubmit={submit}>
            <p>
              Scope: <strong>{caption(scope)}</strong> · Target:{" "}
              <code>{target}</code>. Existing version: {policy?.version || 0}.
            </p>
            <label>
              Decision
              <select
                aria-label="Decision"
                value={decision}
                onChange={(e) => {
                  setDecision(e.target.value);
                  edit();
                }}
              >
                <option>INHERIT</option>
                <option>ALLOW</option>
                <option>DENY</option>
              </select>
            </label>
            {["ORGANIZATION", "PLATFORM"].includes(scope) && (
              <label>
                <input
                  type="checkbox"
                  checked={mandatory}
                  onChange={(e) => {
                    setMandatory(e.target.checked);
                    edit();
                  }}
                />
                Mandatory restriction
              </label>
            )}
            {scope === "ORGANIZATION" && (
              <label>
                <input
                  type="checkbox"
                  checked={exceptions}
                  onChange={(e) => {
                    setExceptions(e.target.checked);
                    edit();
                  }}
                />
                Permit explicit expiring user exceptions to ordinary defaults
              </label>
            )}
            <label>
              Expiration (local time, optional; required for individual grants)
              <input
                type="datetime-local"
                value={expires}
                onChange={(e) => {
                  setExpires(e.target.value);
                  edit();
                }}
              />
            </label>
            <label>
              Reason
              <textarea
                required
                minLength={10}
                maxLength={500}
                value={reason}
                onChange={(e) => {
                  setReason(e.target.value);
                  edit();
                }}
              />
            </label>
            {preview && (
              <section className="admin-preview">
                <h3>Policy preview</h3>
                <p>
                  {String(preview.candidate_memberships)} memberships in this
                  scope. Exact changed-access count is not calculated; up to ten
                  effective decisions are sampled.
                </p>
                <ul>
                  {(
                    preview.sample as {
                      user_id: string;
                      before: { allowed: boolean };
                      after: { allowed: boolean };
                    }[]
                  ).map((sample) => (
                    <li key={sample.user_id}>
                      {sample.user_id}:{" "}
                      {sample.before.allowed ? "Available" : "Restricted"} →{" "}
                      {sample.after.allowed ? "Available" : "Restricted"}
                    </li>
                  ))}
                </ul>
                <p>{String(preview.active_job_policy)}</p>
                {preview.approval_required ? (
                  <p>
                    A second operator must approve lifting a global restriction.
                  </p>
                ) : null}
                <label>
                  <input type="checkbox" required />I reviewed the preview and
                  affected scope.
                </label>
              </section>
            )}
            {!!error && <ErrorBox error={error} />}
            <button className="primary" disabled={busy}>
              {busy
                ? "Awaiting confirmation…"
                : preview
                  ? "Confirm reviewed policy"
                  : "Preview effective access"}
            </button>
          </form>
          {scope === "PLATFORM" && <Reauthenticate />}
        </>
      )}
    </Dialog>
  );
}

function Features({
  context,
  changed,
}: {
  context: Context;
  changed: () => void;
}) {
  const [params] = useSearchParams();
  const orgManage = context.permissions.includes("features.manage");
  const scopes = [
    ...(orgManage
      ? ["ORGANIZATION", "TEAM", "USER", "ROLE"]
      : context.administered_team_ids.length
        ? ["TEAM"]
        : []),
    ...(context.platform_permissions.includes("platform.safety")
      ? ["PLATFORM"]
      : []),
  ];
  const [scope, setScope] = useState(
    scopes.includes(params.get("scope") || "")
      ? params.get("scope")!
      : scopes[0],
  );
  const [target, setTarget] = useState(
    params.get("target") ||
      (scope === "ORGANIZATION"
        ? context.organization_id
        : scope === "PLATFORM"
          ? "PLATFORM"
          : context.administered_team_ids[0] || ""),
  );
  const [selected, setSelected] = useState<{
    feature: string;
    policy?: Policy;
    restore?: Policy;
  }>();
  const [history, setHistory] = useState<Policy>();
  const data = useQuery({
    queryKey: ["administration", "feature-policies", scope, target],
    queryFn: () =>
      api<FeatureResponse>(
        `/admin/features?scope_type=${encodeURIComponent(scope)}&target_id=${encodeURIComponent(target)}&limit=100`,
      ),
    enabled: !!scope && !!target,
    retry: false,
  });
  return (
    <section className="admin-panel">
      <div className="filters">
        <label>
          Policy scope
          <select
            value={scope}
            onChange={(e) => {
              const value = e.target.value;
              setScope(value);
              setTarget(
                value === "ORGANIZATION"
                  ? context.organization_id
                  : value === "PLATFORM"
                    ? "PLATFORM"
                    : value === "TEAM"
                      ? context.administered_team_ids[0] || ""
                      : "",
              );
            }}
          >
            {scopes.map((value) => (
              <option key={value}>{value}</option>
            ))}
          </select>
        </label>
        <label>
          Target{" "}
          {scope === "ROLE" ? (
            <select value={target} onChange={(e) => setTarget(e.target.value)}>
              <option value="">Select role…</option>
              {context.roles.map((role) => (
                <option key={role.id}>{role.id}</option>
              ))}
            </select>
          ) : scope === "TEAM" && !orgManage ? (
            <select value={target} onChange={(e) => setTarget(e.target.value)}>
              {context.administered_team_ids.map((team) => (
                <option key={team}>{team}</option>
              ))}
            </select>
          ) : (
            <input
              aria-label="Feature policy target"
              value={target}
              disabled={["ORGANIZATION", "PLATFORM"].includes(scope)}
              maxLength={80}
              onChange={(e) => setTarget(e.target.value)}
            />
          )}
        </label>
      </div>
      <p>
        Use the user or team identifier from its details. Inherit removes this
        scope’s explicit decision. Mandatory platform and organization
        restrictions always win.
      </p>
      {data.isLoading ? (
        <p role="status">Loading feature policies…</p>
      ) : data.isError ? (
        <ErrorBox error={data.error} retry={() => data.refetch()} />
      ) : (
        target && (
          <div className="admin-table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Feature</th>
                  <th>Scope policy</th>
                  <th>Effective access</th>
                  <th>Expiration</th>
                  <th>Controls</th>
                </tr>
              </thead>
              <tbody>
                {context.feature_catalog.map((feature) => {
                  const policy = data.data?.items?.find(
                    (row) => row.feature === feature.id,
                  ) as Policy | undefined;
                  const effective = data.data?.effective?.[feature.id];
                  return (
                    <tr key={feature.id}>
                      <td>
                        <strong>{feature.label}</strong>
                        <small>{feature.description}</small>
                      </td>
                      <td>
                        {policy?.decision || "INHERIT"}
                        {policy?.mandatory ? " · Mandatory" : ""}
                      </td>
                      <td>
                        {effective
                          ? `${effective.allowed ? "Available" : "Restricted"} · ${caption(effective.reason)}`
                          : "Preview individual decisions before saving"}
                      </td>
                      <td>{text(policy?.expires_at)}</td>
                      <td>
                        <button
                          onClick={() =>
                            setSelected({ feature: feature.id, policy })
                          }
                        >
                          Review change
                        </button>
                        {policy && (
                          <button onClick={() => setHistory(policy)}>
                            History
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )
      )}
      <p className="muted">{context.active_job_policy}</p>
      {selected && (
        <FeatureEditor
          context={context}
          scope={scope}
          target={target}
          {...selected}
          close={() => setSelected(undefined)}
          changed={changed}
        />
      )}
      {history && (
        <Detail
          path={`/admin/features/${history.id}/history`}
          close={() => setHistory(undefined)}
        >
          {(row) => (
            <ul>
              {(
                row.items as { id: string; version: number; policy: Policy }[]
              ).map((revision) => (
                <li key={revision.id}>
                  Version {revision.version} · {revision.policy.decision} ·{" "}
                  {text(revision.policy.reason)}
                  <button
                    onClick={() => {
                      setSelected({
                        feature: history.feature,
                        policy: history,
                        restore: revision.policy,
                      });
                      setHistory(undefined);
                    }}
                  >
                    Restore through new preview
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Detail>
      )}
    </section>
  );
}

export default function Administration({
  identity,
  changed,
}: {
  identity: Identity;
  changed: () => void;
}) {
  const client = useQueryClient();
  const [params, setParams] = useSearchParams();
  const [action, setAction] = useState<Action>();
  const [detail, setDetail] = useState<string>();
  const [days, setDays] = useState(30);
  const [rangeEnd, setRangeEnd] = useState(() => new Date());
  const [customRange, setCustomRange] = useState<{
    start: string;
    end: string;
  }>();
  const context = useQuery({
    queryKey: ["administration", "context", identity.organization_id],
    queryFn: () => api<Context>("/admin/context"),
    retry: false,
  });
  function refresh() {
    setRangeEnd(new Date());
    client.invalidateQueries({ queryKey: ["administration"] });
    changed();
  }
  if (context.isLoading)
    return <p role="status">Loading administration permissions…</p>;
  if (context.isError)
    return <ErrorBox error={context.error} retry={() => context.refetch()} />;
  if (!context.data) return null;
  if (identity.access?.admin_available === false)
    return (
      <p className="error" role="alert">
        Administration is no longer available to this account.
      </p>
    );
  const c = context.data,
    can = (permission: string) => c.permissions.includes(permission),
    platform = (permission: string) =>
      c.platform_permissions.includes(permission);
  const sections = [
    ["Dashboard", can("usage.read")],
    ["Users", can("users.read")],
    ["Invitations", can("users.invite")],
    ["Teams", can("teams.read")],
    [
      "Team Operations",
      !!c.administered_team_ids.length ||
        (can("usage.read") && can("teams.read")),
    ],
    [
      "Feature Access",
      can("features.manage") ||
        !!c.administered_team_ids.length ||
        platform("platform.safety"),
    ],
    ["Repositories", can("repositories.read")],
    ["Analysis Jobs", can("analyses.read")],
    ["Usage & Analytics", can("usage.read")],
    ["Activity Explorer", can("activity.read")],
    ["Audit Trail", can("audit.read")],
    ["Quotas & Policies", can("usage.read")],
    ["Security Center", can("security.investigate")],
    ["System Health", can("analyses.read")],
    ["Notifications", true],
    ["Roles & Permissions", true],
    ["Settings", can("organization.settings.manage")],
    ["Organizations", platform("platform.organizations")],
    ["Platform Accounts", platform("platform.accounts")],
    ["Platform Operators", platform("platform.operators")],
    ["Platform Approvals", platform("platform.safety")],
    ["Operator Approvals", platform("platform.operators")],
    ["Platform Audit", platform("platform.audit")],
    ["Platform Health", platform("platform.health")],
  ]
    .filter(([, allowed]) => allowed)
    .map(([name]) => String(name));
  const section = sections.includes(params.get("section") || "")
    ? params.get("section")!
    : sections[0];
  const base = (row: Row) => ({ expected_version: version(row) });
  const button = (
    title: string,
    path: string,
    row: Row,
    values: Row = {},
    explanation?: string,
    fields?: Field[],
    sensitive = false,
  ) => (
    <button
      key={title}
      onClick={() =>
        setAction({
          title,
          path,
          base: { ...base(row), ...values },
          explanation,
          fields,
          sensitive,
        })
      }
    >
      {title}
    </button>
  );
  const timeRange = new URLSearchParams(
    customRange || {
      start: new Date(rangeEnd.getTime() - days * 86400000).toISOString(),
      end: rangeEnd.toISOString(),
    },
  );
  return (
    <div className="administration">
      <div className="admin-scope">
        <strong>{identity.organization || "Current organization"}</strong>
        <span>
          {caption(c.role)}
          {c.platform_role ? ` · ${caption(c.platform_role)}` : ""}
        </span>
        <p>
          Administration observes operational metadata. Repository source and
          evidence require separate grants.
        </p>
      </div>
      <nav className="admin-tabs" aria-label="Administration sections">
        {sections.map((name) => (
          <button
            key={name}
            aria-current={section === name ? "page" : undefined}
            className={section === name ? "active" : ""}
            onClick={() => {
              setParams({ section: name });
              setDetail(undefined);
            }}
          >
            {name}
          </button>
        ))}
      </nav>
      <div className="admin-section-heading">
        <h2>{section}</h2>
        {[
          "Dashboard",
          "Usage & Analytics",
          "Activity Explorer",
          "Audit Trail",
          "Team Operations",
        ].includes(section) && (
          <label>
            Period
            <select
              value={days}
              onChange={(e) => {
                setDays(Number(e.target.value));
                setCustomRange(undefined);
              }}
            >
              <option value={1}>Day</option>
              <option value={7}>Week</option>
              <option value={30}>Month</option>
              <option value={90}>90 days</option>
            </select>
          </label>
        )}
        <button onClick={refresh}>Refresh records</button>
      </div>
      {[
        "Dashboard",
        "Usage & Analytics",
        "Activity Explorer",
        "Audit Trail",
        "Team Operations",
      ].includes(section) && <CustomRange change={setCustomRange} />}
      {section === "Dashboard" && (
        <ReadView path={`/admin/dashboard?${timeRange}`} />
      )}
      {section === "Users" && (
        <PagedTable
          key={section}
          path="/admin/users"
          columns={[
            "email",
            "display_name",
            "role",
            "state",
            "teams",
            "direct_repository_grants",
            "measured_analysis_submissions",
          ]}
          filterKey="search"
          open={(row) => setDetail(`/admin/users/${id(row)}`)}
          actions={(row) => (
            <>
              {can("users.roles.manage") &&
                id(row) !== c.user_id &&
                row.role !== "ORG_OWNER" &&
                button(
                  "Change role",
                  `/admin/users/${id(row)}`,
                  row,
                  { action: "ROLE" },
                  "Change this member's role only in the selected organization.",
                  [
                    {
                      key: "role",
                      label: "Organization role",
                      options: [
                        "ENGINEER",
                        "VIEWER",
                        "REVIEWER",
                        "SECURITY_REVIEWER",
                        "AUDITOR",
                        "TEAM_ADMIN",
                        ...(c.role === "ORG_OWNER"
                          ? ["ADMIN", "SECURITY_ADMIN"]
                          : []),
                      ],
                    },
                  ],
                  true,
                )}
              {can("users.suspend") &&
                id(row) !== c.user_id &&
                row.role !== "ORG_OWNER" &&
                row.state !== "REMOVED" &&
                button(
                  row.state === "SUSPENDED" ? "Reactivate" : "Suspend",
                  `/admin/users/${id(row)}`,
                  row,
                  {
                    action:
                      row.state === "SUSPENDED" ? "REACTIVATE" : "SUSPEND",
                  },
                  "Affects this organization membership. Published work and other organization memberships remain retained.",
                  row.state === "SUSPENDED"
                    ? []
                    : [
                        {
                          key: "expires_at",
                          label: "Restriction expiration",
                          type: "datetime-local",
                          required: false,
                        },
                      ],
                )}
              {can("sessions.revoke") &&
                button(
                  "Revoke sessions",
                  `/admin/users/${id(row)}`,
                  row,
                  { action: "REVOKE_SESSIONS" },
                  "Revokes this member's sessions in the selected organization. Other organization sessions remain scoped separately.",
                  [],
                  row.role === "ORG_OWNER",
                )}
              {can("users.remove") &&
                id(row) !== c.user_id &&
                row.role !== "ORG_OWNER" &&
                row.state !== "REMOVED" &&
                button(
                  "Remove membership",
                  `/admin/users/${id(row)}`,
                  row,
                  { action: "REMOVE" },
                  "Removes this organization's membership and grants. Authored evidence and audit history remain retained. Team ownership must be transferred first.",
                )}
              {can("features.manage") && (
                <button
                  onClick={() =>
                    setParams({
                      section: "Feature Access",
                      scope: "USER",
                      target: id(row),
                    })
                  }
                >
                  Feature access
                </button>
              )}
              {can("organization.ownership.transfer") &&
                id(row) !== c.user_id &&
                row.role !== "ORG_OWNER" &&
                button(
                  "Request ownership transfer",
                  "/auth/ownership/requests",
                  { version: c.membership_version || 1 },
                  { target_user_id: id(row), target_version: version(row) },
                  "The current owner requests a transfer; the selected active member must separately consent after fresh authentication.",
                  [],
                  true,
                )}
            </>
          )}
        />
      )}
      {section === "Invitations" && (
        <>
          <button
            className="primary"
            onClick={() =>
              setAction({
                title: "Invite organization member",
                path: "/admin/invitations",
                fields: [
                  { key: "email", label: "Member email", type: "email" },
                  {
                    key: "role",
                    label: "Organization role",
                    options: [
                      "ENGINEER",
                      "VIEWER",
                      "REVIEWER",
                      "SECURITY_REVIEWER",
                      "AUDITOR",
                      "TEAM_ADMIN",
                      ...(c.role === "ORG_OWNER"
                        ? ["ADMIN", "SECURITY_ADMIN"]
                        : []),
                    ],
                  },
                ],
                sensitive: true,
              })
            }
          >
            Invite member
          </button>
          <PagedTable
            key={section}
            path="/admin/invitations"
            columns={["email", "role", "state", "expires_at", "version"]}
            actions={(row) =>
              row.state === "PENDING" && (
                <>
                  {button(
                    "Resend invitation",
                    `/admin/invitations/${id(row)}/resend`,
                    row,
                    {},
                    "Generates a replacement one-time link and invalidates the old link.",
                  )}
                  {button(
                    "Cancel invitation",
                    `/admin/invitations/${id(row)}/cancel`,
                    row,
                    {},
                  )}
                </>
              )
            }
          />
        </>
      )}
      {section === "Teams" && (
        <>
          {can("teams.create") && (
            <button
              className="primary"
              onClick={() =>
                setAction({
                  title: "Create team",
                  path: "/admin/teams",
                  fields: [{ key: "name", label: "Team name" }],
                })
              }
            >
              Create team
            </button>
          )}
          <PagedTable
            key={section}
            path="/admin/teams"
            columns={[
              "name",
              "owner_id",
              "archived",
              "members",
              "repositories",
              "version",
            ]}
            filterKey="search"
            open={(row) => setDetail(`/admin/teams/${id(row)}`)}
            actions={(row) =>
              (can("teams.manage") ||
                c.administered_team_ids.includes(id(row))) && (
                <>
                  {button(
                    "Rename team",
                    `/admin/teams/${id(row)}`,
                    row,
                    { action: "RENAME" },
                    undefined,
                    [
                      {
                        key: "name",
                        label: "Team name",
                        value: String(row.name),
                      },
                    ],
                  )}
                  {button(
                    row.archived ? "Restore team" : "Archive team",
                    `/admin/teams/${id(row)}`,
                    row,
                    { action: row.archived ? "RESTORE" : "ARCHIVE" },
                    "Archiving removes inherited repository access while retaining historical membership and activity.",
                  )}
                  {button(
                    "Manage member",
                    `/admin/teams/${id(row)}/members`,
                    row,
                    {},
                    "A member must already belong to this organization. Team administrators can change only their delegated teams.",
                    [
                      {
                        key: "user_id",
                        label: "Organization member identifier",
                        lookup: { path: `/admin/teams/${id(row)}/candidates` },
                      },
                      {
                        key: "action",
                        label: "Action",
                        options: ["ADD", "REMOVE"],
                      },
                      {
                        key: "role",
                        label: "Team role",
                        options: ["MEMBER", "ADMIN"],
                        value: "MEMBER",
                      },
                    ],
                  )}
                  {button(
                    "Transfer team ownership",
                    `/admin/teams/${id(row)}`,
                    row,
                    { action: "TRANSFER_OWNER" },
                    undefined,
                    [
                      {
                        key: "owner_id",
                        label: "New active owner",
                        lookup: { path: `/admin/teams/${id(row)}/candidates` },
                      },
                    ],
                  )}
                  <button
                    onClick={() =>
                      setParams({
                        section: "Feature Access",
                        scope: "TEAM",
                        target: id(row),
                      })
                    }
                  >
                    Feature defaults
                  </button>
                </>
              )
            }
          />
        </>
      )}
      {section === "Feature Access" && (
        <Features
          key={`${c.organization_id}:${params.get("scope")}:${params.get("target")}`}
          context={c}
          changed={refresh}
        />
      )}
      {section === "Team Operations" && (
        <TeamOperations range={String(timeRange)} open={setDetail} />
      )}
      {section === "Repositories" && (
        <PagedTable
          key={section}
          path="/admin/repositories"
          columns={[
            "name",
            "provider",
            "owner",
            "archived",
            "analysis_paused",
            "version",
          ]}
          filterKey="search"
          open={(row) => setDetail(`/admin/repositories/${id(row)}/access`)}
          actions={(row) => (
            <>
              {can("repositories.manage") && (
                <>
                  {button(
                    row.archived ? "Restore repository" : "Archive repository",
                    `/admin/repositories/${id(row)}`,
                    row,
                    { action: row.archived ? "RESTORE" : "ARCHIVE" },
                    "Preserves source, snapshots and evidence; new analyses are restricted while archived.",
                  )}
                  {button(
                    row.analysis_paused
                      ? "Resume new analyses"
                      : "Pause new analyses",
                    `/admin/repositories/${id(row)}`,
                    row,
                    { action: row.analysis_paused ? "RESUME" : "PAUSE" },
                  )}
                </>
              )}
              {can("repositories.access.grant") &&
                button(
                  "Manage access",
                  `/admin/repositories/${id(row)}/access`,
                  row,
                  {},
                  "A direct grant does not override an explicit repository denial.",
                  [
                    {
                      key: "user_id",
                      label:
                        "Organization member identifier (choose one subject)",
                      required: false,
                      lookup: {
                        path: "/admin/users",
                        versionKey: "expected_version",
                        exclusiveKeys: ["team_id"],
                      },
                    },
                    {
                      key: "team_id",
                      label: "Team identifier (choose one subject)",
                      required: false,
                      lookup: {
                        path: "/admin/teams",
                        versionKey: "expected_version",
                        exclusiveKeys: ["user_id"],
                      },
                    },
                    {
                      key: "action",
                      label: "Access action",
                      options: ["GRANT", "REVOKE", "DENY", "CLEAR_DENIAL"],
                    },
                  ],
                )}
            </>
          )}
        />
      )}
      {section === "Analysis Jobs" && (
        <PagedTable
          key={section}
          path="/admin/jobs"
          columns={[
            "id",
            "repository_id",
            "state",
            "stage",
            "source",
            "user_id",
            "duration_ms",
            "error_code",
          ]}
          filterKey="state"
          open={(row) => setDetail(`/admin/jobs/${id(row)}`)}
          actions={(row) => (
            <>
              {can("analyses.cancel") &&
                !["COMPLETED", "COMPLETED_NO_FINDINGS", "CANCELLED"].includes(
                  String(row.state),
                ) &&
                button(
                  "Cancel job",
                  `/admin/jobs/${id(row)}/cancel`,
                  row,
                  {},
                  "Uses the existing cancellation fence. Published evidence stays retained; a running transaction may delay acknowledgement.",
                )}
              {can("analyses.retry") &&
                ["FAILED", "PARTIAL", "QUEUED"].includes(String(row.state)) &&
                button(
                  "Retry job",
                  `/admin/jobs/${id(row)}/retry`,
                  row,
                  {},
                  "Rechecks the original submitting identity, source grants, feature policies, retained input and the existing finite retry limit.",
                )}
            </>
          )}
        />
      )}
      {section === "Usage & Analytics" && (
        <>
          <ReadView path={`/admin/usage?${timeRange}`} />
          <h3>Recorded usage by submitting account</h3>
          <PagedTable
            key={`actors:${timeRange}`}
            path={`/admin/usage/actors?${timeRange}`}
            columns={[
              "user_id",
              "jobs",
              "duration_samples",
              "recorded_duration_ms",
            ]}
          />
        </>
      )}
      {section === "Activity Explorer" && (
        <ActivityExplorer
          key={String(timeRange)}
          range={String(timeRange)}
          exportAllowed={can("audit.export") && c.features.exports.allowed}
        />
      )}
      {section === "Audit Trail" && (
        <>
          <PagedTable
            key={`${section}:${days}`}
            path={`/admin/audit?${timeRange}`}
            columns={[
              "created_at",
              "actor",
              "action",
              "target_id",
              "sequence",
              "digest",
              "data",
            ]}
            filterKey="action"
          />
          {can("audit.export") && c.features.exports.allowed && (
            <AuditExport range={timeRange.toString()} />
          )}
        </>
      )}
      {section === "Quotas & Policies" && (
        <>
          {can("quotas.manage") && (
            <button
              onClick={() =>
                setAction({
                  title: "Set admission quota",
                  path: "/admin/quotas",
                  explanation:
                    "This quota cannot raise technical resource caps. Removing a quota requires its current version and an empty limit.",
                  fields: [
                    {
                      key: "scope_type",
                      label: "Scope",
                      options: ["ORGANIZATION", "TEAM", "USER"],
                    },
                    {
                      key: "target_id",
                      label: "Scope identifier",
                      value: c.organization_id,
                    },
                    {
                      key: "metric",
                      label: "Measured capacity",
                      options: ["pending_jobs", "daily_jobs"],
                    },
                    {
                      key: "limit",
                      label: "Limit (empty removes current quota)",
                      type: "number",
                      required: false,
                    },
                    {
                      key: "expected_version",
                      label: "Current quota version (zero creates)",
                      type: "number",
                      value: 0,
                    },
                  ],
                })
              }
            >
              Review quota change
            </button>
          )}
          <PagedTable
            key={section}
            path="/admin/quotas"
            columns={[
              "scope_type",
              "target_id",
              "metric",
              "limit",
              "consumption",
              "version",
            ]}
          />
          <p>
            Daily jobs count distinct accepted jobs by UTC day. Team usage is
            attributed at submission after this release; earlier team
            consumption is unknown. Technical execution, memory, input and queue
            limits remain enforced independently.
          </p>
        </>
      )}
      {section === "Security Center" && <ReadView path="/admin/security" />}
      {section === "System Health" && <ReadView path="/admin/health" />}
      {section === "Notifications" && (
        <PagedTable
          key={section}
          path="/notifications"
          columns={["created_at", "message", "severity", "read_at"]}
          actions={(row) =>
            !row.read_at && (
              <button
                onClick={async () => {
                  await api(`/notifications/${id(row)}/read`, {});
                  refresh();
                }}
              >
                Mark read
              </button>
            )
          }
        />
      )}
      {section === "Roles & Permissions" && (
        <section className="admin-panel">
          <h3>Effective permissions</h3>
          <ul>
            {c.permissions.map((permission) => (
              <li key={permission}>
                <strong>{permission}</strong> —{" "}
                {c.permission_definitions[permission]}
              </li>
            ))}
          </ul>
          <h3>Organization roles</h3>
          {c.roles.map((role) => (
            <details key={role.id}>
              <summary>{caption(role.id)}</summary>
              <ul>
                {role.permissions.map((permission) => (
                  <li key={permission}>{permission}</li>
                ))}
              </ul>
            </details>
          ))}
          <h3>Explicitly unavailable controls</h3>
          <ul>
            {c.unavailable_controls.map((control) => (
              <li key={control}>{control}</li>
            ))}
          </ul>
        </section>
      )}
      {section === "Settings" && (
        <section className="admin-panel">
          <p>
            Organization integrations and existing analysis profiles remain in
            their current verified configuration workflows.
          </p>
          <a href="/settings/connections">Connections and OIDC</a>
          <p>
            <a href="/settings">Existing workspace settings</a>
          </p>
          <p>
            Account deletion, organization erasure and customer-content support
            elevation require a separately designed retention and consent
            workflow and are unavailable here.
          </p>
          <Reauthenticate />
        </section>
      )}
      {section === "Organizations" && (
        <PagedTable
          key={section}
          path="/admin/platform/organizations"
          columns={["id", "name", "state", "repositories", "version"]}
          filterKey="search"
          actions={(row) =>
            platform("platform.safety") &&
            button(
              row.state === "SUSPENDED"
                ? "Reactivate organization"
                : "Suspend organization",
              `/admin/platform/organizations/${id(row)}`,
              row,
              { state: row.state === "SUSPENDED" ? "ACTIVE" : "SUSPENDED" },
              "Restricts tenant access and new worker starts. Source and audit history remain retained.",
              [],
              true,
            )
          }
        />
      )}
      {section === "Platform Accounts" && (
        <PagedTable
          key={section}
          path="/admin/platform/accounts"
          columns={[
            "id",
            "primary_organization_id",
            "identity_enabled",
            "restriction",
            "expires_at",
            "version",
          ]}
          filterKey="user_id"
          actions={(row) =>
            button(
              row.restriction === "SUSPENDED"
                ? "Reactivate account"
                : "Suspend account",
              `/admin/platform/accounts/${id(row)}`,
              row,
              {
                state: row.restriction === "SUSPENDED" ? "ACTIVE" : "SUSPENDED",
              },
              "Platform suspension affects all memberships and revokes every session. Self-restriction and removal of the last super operator are blocked.",
              row.restriction === "SUSPENDED"
                ? []
                : [
                    {
                      key: "expires_at",
                      label: "Expiration",
                      type: "datetime-local",
                      required: false,
                    },
                  ],
              true,
            )
          }
        />
      )}
      {section === "Platform Operators" && (
        <>
          <p>
            Enter an existing account identifier to request an operator role.
          </p>
          <OperatorRequest setAction={setAction} />
          <PagedTable
            key={section}
            path="/admin/platform/operators"
            columns={["user_id", "role", "enabled", "version"]}
            actions={(row) =>
              button(
                "Revoke operator",
                `/admin/platform/operators/${id(row)}`,
                row,
                { role: row.role, enabled: false },
                "Requires another authorized operator; the last unrestricted super administrator cannot be removed.",
                [],
                true,
              )
            }
          />
        </>
      )}
      {section === "Platform Approvals" && (
        <PagedTable
          key={section}
          path="/admin/platform/approvals"
          columns={["id", "requested_by", "state", "expires_at", "data"]}
          actions={(row) =>
            row.state === "PENDING" &&
            button(
              "Approve global policy release",
              `/admin/platform/approvals/${id(row)}/approve`,
              row,
              {},
              "A distinct current super operator verifies this reviewed request; stale policy versions are rejected.",
              [],
              true,
            )
          }
        />
      )}
      {section === "Operator Approvals" && (
        <PagedTable
          key={section}
          path="/admin/platform/operator-requests"
          columns={["id", "requested_by", "state", "expires_at", "data"]}
          actions={(row) =>
            row.state === "PENDING" &&
            button(
              "Approve operator request",
              `/admin/platform/operator-requests/${id(row)}/approve`,
              row,
              {},
              "A distinct current super operator must approve. This does not grant tenant source access.",
              [],
              true,
            )
          }
        />
      )}
      {section === "Platform Audit" && (
        <PagedTable
          key={section}
          path="/admin/platform/audit"
          columns={[
            "id",
            "organization_id",
            "actor",
            "action",
            "target",
            "created_at",
          ]}
        />
      )}
      {section === "Platform Health" && (
        <ReadView path="/admin/platform/health" />
      )}
      {detail && !action && (
        <Detail path={detail} close={() => setDetail(undefined)}>
          {(row) =>
            row.member && can("sessions.revoke") ? (
              <ul>
                {(row.sessions as Row[]).map((session) => (
                  <li key={id(session)}>
                    Session {id(session)} · {text(session.assurance)} · expires{" "}
                    {text(session.expires_at)}
                    {button(
                      "Revoke this session",
                      `/admin/users/${id(row.member as Row)}/sessions/${id(session)}/revoke`,
                      row.member as Row,
                      {},
                      undefined,
                      [],
                      (row.member as Row).role === "ORG_OWNER",
                    )}
                  </li>
                ))}
              </ul>
            ) : null
          }
        </Detail>
      )}
      {action && (
        <CommandDialog
          key={action.title + action.path}
          action={action}
          close={() => setAction(undefined)}
          changed={refresh}
        />
      )}
    </div>
  );
}

function OperatorRequest({
  setAction,
}: {
  setAction: (value: Action) => void;
}) {
  const [target, setTarget] = useState("");
  return (
    <form
      className="filters"
      onSubmit={(event) => {
        event.preventDefault();
        setAction({
          title: "Request platform operator grant",
          path: `/admin/platform/operators/${encodeURIComponent(target)}`,
          explanation:
            "The proposal requires approval from a distinct existing super administrator.",
          fields: [
            {
              key: "role",
              label: "Platform role",
              options: [
                "PLATFORM_SUPER_ADMIN",
                "PLATFORM_SUPPORT_ADMIN",
                "PLATFORM_AUDITOR",
              ],
            },
            {
              key: "expected_version",
              label: "Current operator version (zero creates)",
              type: "number",
              value: 0,
            },
          ],
          sensitive: true,
        });
      }}
    >
      <label>
        Existing account identifier
        <input
          value={target}
          onChange={(e) => setTarget(e.target.value)}
          required
          maxLength={80}
        />
      </label>
      <button>Review operator request</button>
    </form>
  );
}

function CustomRange({
  change,
}: {
  change: (range: { start: string; end: string }) => void;
}) {
  const [error, setError] = useState("");
  return (
    <details>
      <summary>Custom period (maximum 90 days)</summary>
      <form
        className="filters"
        onSubmit={(event) => {
          event.preventDefault();
          const form = new FormData(event.currentTarget);
          const start = new Date(String(form.get("start"))),
            end = new Date(String(form.get("end")));
          if (
            !Number.isFinite(start.getTime()) ||
            !Number.isFinite(end.getTime()) ||
            start >= end ||
            end.getTime() - start.getTime() > 90 * 86400000 ||
            end.getTime() > Date.now() + 300000
          ) {
            setError(
              "Choose an ordered period of at most 90 days ending no later than now.",
            );
            return;
          }
          setError("");
          change({ start: start.toISOString(), end: end.toISOString() });
        }}
      >
        <label>
          Start (local time)
          <input type="datetime-local" name="start" required />
        </label>
        <label>
          End (local time)
          <input type="datetime-local" name="end" required />
        </label>
        <button>Apply period</button>
        {error && <p role="alert">{error}</p>}
      </form>
    </details>
  );
}

function TeamOperations({
  range,
  open,
}: {
  range: string;
  open: (path: string) => void;
}) {
  const [team, setTeam] = useState("");
  const query = team ? `${range}&team_id=${encodeURIComponent(team)}` : "";
  return (
    <>
      <label>
        Permitted team
        <RecordLookup
          field={{
            key: "team_id",
            label: "Permitted team",
            lookup: { path: "/admin/teams" },
          }}
          value={team}
          choose={(row) => setTeam(row ? id(row) : "")}
        />
      </label>
      {team ? (
        <>
          <ReadView path={`/admin/usage?${query}`} />
          <h3>Team analysis jobs</h3>
          <PagedTable
            key={`jobs:${query}`}
            path={`/admin/jobs?team_id=${encodeURIComponent(team)}`}
            columns={["id", "state", "stage", "user_id", "duration_ms"]}
            open={(row) =>
              open(`/admin/jobs/${id(row)}?team_id=${encodeURIComponent(team)}`)
            }
          />
          <h3>Team activity</h3>
          <ActivityExplorer key={query} range={query} exportAllowed={false} />
        </>
      ) : (
        <p>
          Select a permitted team to inspect its measured usage, jobs and
          activity.
        </p>
      )}
    </>
  );
}

function ActivityExplorer({
  range,
  exportAllowed,
}: {
  range: string;
  exportAllowed: boolean;
}) {
  const [filters, setFilters] = useState("");
  const [detail, setDetail] = useState<string>();
  const query = `${range}${filters ? `&${filters}` : ""}`;
  return (
    <>
      <form
        className="filters"
        onSubmit={(event) => {
          event.preventDefault();
          const form = new FormData(event.currentTarget);
          const params = new URLSearchParams();
          for (const [key, value] of form.entries())
            if (String(value).trim()) params.set(key, String(value).trim());
          setFilters(String(params));
        }}
      >
        {[
          "actor_id",
          "repository_id",
          "action",
          "category",
          "outcome",
          "correlation_id",
          "target_id",
        ].map((key) => (
          <label key={key}>
            {caption(key)}
            <input name={key} maxLength={key.includes("id") ? 100 : 30} />
          </label>
        ))}
        <button>Apply activity filters</button>
        <button type="reset" onClick={() => setFilters("")}>
          Clear activity filters
        </button>
      </form>
      <PagedTable
        key={query}
        path={`/admin/activity?${query}`}
        open={row => setDetail(`/admin/activity/${id(row)}?${range}`)}
        columns={[
          "created_at",
          "actor_id",
          "action",
          "category",
          "outcome",
          "repository_id",
          "target_id",
          "correlation_id",
        ]}
      />
      {detail && <Detail path={detail} close={() => setDetail(undefined)} />}
      {exportAllowed && <AuditExport range={query} kind="activity" />}
    </>
  );
}

function AuditExport({
  range,
  kind = "audit",
}: {
  range: string;
  kind?: "audit" | "activity";
}) {
  const [error, setError] = useState<unknown>(),
    [busy, setBusy] = useState(false);
  async function download() {
    setBusy(true);
    setError(undefined);
    try {
      const page = await api<Page>(
        `/admin/${kind}?${range}&export=true&offset=0&limit=100`,
      );
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(page, null, 2)], { type: "application/json" }),
      );
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `projecttrace-${kind}-first-100.json`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div>
      <p>
        Exports the first 100 sanitized records in this period. The file
        includes pagination; it is not a complete audit archive.
      </p>
      <button disabled={busy} onClick={download}>
        {busy ? "Preparing page…" : `Export first ${kind} page`}
      </button>
      {!!error && <ErrorBox error={error} />}
      <Reauthenticate />
    </div>
  );
}

type Organizations = {
  items: {
    id: string;
    name: string;
    role: string;
    state: string;
    available: boolean;
    selected: boolean;
  }[];
  page: { has_more: boolean };
  csrf: string;
};
export function WorkspaceSelector({
  identity,
  selected,
}: {
  identity?: Identity | null;
  selected: (identity: Identity) => void;
}) {
  const [offset, setOffset] = useState(0),
    [error, setError] = useState<unknown>(),
    [busy, setBusy] = useState(false);
  const data = useQuery({
    queryKey: ["organizations", identity?.organization_id, offset],
    queryFn: () =>
      api<Organizations>(`/auth/organizations?offset=${offset}&limit=25`),
    retry: false,
  });
  async function select(organization_id: string) {
    if (!data.data) return;
    setBusy(true);
    setError(undefined);
    setCSRF(data.data.csrf);
    try {
      const next = await api<Identity>("/auth/organization", {
        organization_id,
      });
      setCSRF(next.csrf);
      selected(await api<Identity>("/auth/me"));
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="admin-workspace-selector">
      <label>
        Organization workspace
        <select
          aria-label="Organization workspace"
          value={data.data?.items?.find((org) => org.selected)?.id || ""}
          disabled={busy || data.isLoading || data.isError}
          onChange={(e) => select(e.target.value)}
        >
          <option value="">
            {busy
              ? "Switching workspace…"
              : identity?.organization || "Choose permitted workspace"}
          </option>
          {data.data?.items?.map((org) => (
            <option key={org.id} value={org.id} disabled={!org.available}>
              {org.name}
              {org.available ? "" : " · Restricted"}
            </option>
          ))}
        </select>
      </label>
      {data.isError && (
        <ErrorBox error={data.error} retry={() => data.refetch()} />
      )}
      {!!error && <ErrorBox error={error} />}
      {(offset > 0 || data.data?.page?.has_more) && (
        <div>
          <button
            disabled={!offset || busy}
            onClick={() => setOffset(Math.max(0, offset - 25))}
          >
            Previous workspaces
          </button>
          <button
            disabled={!data.data?.page?.has_more || busy}
            onClick={() => setOffset(offset + 25)}
          >
            More workspaces
          </button>
        </div>
      )}
    </div>
  );
}

export function OwnNotifications() {
  const [offset, setOffset] = useState(0);
  const client = useQueryClient();
  const [error, setError] = useState<unknown>();
  const notices = useQuery({ queryKey: ["administration", "own-notices", offset], queryFn: () => api<Page>(`/notifications?offset=${offset}&limit=25`), retry: false });
  return <section className="admin-panel"><h2>Your account notices</h2>
    {notices.isLoading ? <p role="status">Loading your notices…</p> : notices.isError ? <ErrorBox error={notices.error} retry={() => notices.refetch()} /> : <>
      {notices.data?.items?.length ? <ul>{notices.data.items.map(row => <li key={id(row)}><p>{String(row.message)}</p><small>{String(row.created_at)} · {String(row.severity)}</small>{!row.read_at && <button onClick={async () => { try { await api(`/notifications/${id(row)}/read`, {}); client.invalidateQueries({ queryKey: ["administration", "own-notices"] }); } catch (failure) { setError(failure); } }}>Mark as read</button>}</li>)}</ul> : <p>No recorded notices for your selected organization.</p>}
      <button disabled={!offset} onClick={() => setOffset(offset - 25)}>Previous notices</button><button disabled={!notices.data?.page?.has_more} onClick={() => setOffset(offset + 25)}>More notices</button>
    </>}{!!error && <ErrorBox error={error} />}</section>;
}

export function OwnershipNotices({
  changed,
  userId,
}: {
  changed: () => void;
  userId: string;
}) {
  const client = useQueryClient();
  const [action, setAction] = useState<Action>();
  const data = useQuery({
    queryKey: ["administration", "own-ownership"],
    queryFn: () => api<Page>("/auth/ownership/requests"),
    retry: false,
  });
  return (
    <>
      {data.data?.items
        ?.filter(
          (row) => row.state === "PENDING" && row.target_user_id === userId,
        )
        .map((row) => (
          <div className="admin-preview" key={id(row)}>
            Ownership transfer request · {id(row)}
            <button
              onClick={() =>
                setAction({
                  title: "Accept organization ownership",
                  path: `/auth/ownership/requests/${id(row)}/accept`,
                  base: { expected_version: version(row) },
                  explanation:
                    "Only the designated member can consent. The requesting owner becomes an organization administrator; source grants remain independent.",
                  sensitive: true,
                })
              }
            >
              Review consent
            </button>
          </div>
        ))}
      {action && (
        <CommandDialog
          action={action}
          close={() => setAction(undefined)}
          changed={() => {
            client.invalidateQueries({ queryKey: ["administration"] });
            changed();
          }}
        />
      )}
    </>
  );
}
