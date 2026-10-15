import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";
import type { Identity, Item, Repository } from "./api";

type Resource = { id: string; title: string; topic: string; explanation: string; status: string; confidence: string; evidence_ids: string[]; path?: string };
type Knowledge = { snapshot_id: string; status: string; branch: string; resources: Resource[]; limitations: string[]; maximum_records_per_kind: number };
type Objective = Resource & { record_id: string; question: string; version: number; state: string; gap_basis: string; score?: number; assessment?: { answer: string; evidence_ids: string[] } };
type Journey = { id: string; version: number; mode: string; role: string; state: string; revision: number; snapshot_id: string; repository_id: string; source_repository_id?: string; participant_id: string; mentor_id: string; manager_id: string; viewer: string; can_complete: boolean; expires_at: string; retention_expired: boolean; refresh_required: boolean; objectives: Objective[]; progress: { approved: number; total: number }; skills: string[]; comparison?: { shared_observed_technologies: string[]; target_observed_technologies: string[] }; reviews: { id: string; kind: string; decision: string; notes?: string }[]; completion_records: { revision: number; snapshot_id: string; at: string; basis: string }[] };
type Member = { id: string; email: string; role: string };
type Summary = Pick<Journey, "id" | "mode" | "role" | "state" | "repository_id" | "participant_id">;

export default function Learning({ repository, repositories, identity, onOpen }: {
  repository: string; repositories: Repository[]; identity: Identity; onOpen: (item: Item) => void;
}) {
  const queryClient = useQueryClient();
  const tenantKey = `${identity.organization_id || identity.access?.organization_id || ""}:${identity.access?.user_id || identity.email}:${identity.access?.decision_version || ""}`;
  const currentScope = useRef(tenantKey);
  currentScope.current = tenantKey;
  const [target, setTarget] = useState(repository === "ALL" ? "" : repository);
  const [selected, setSelected] = useState("");
  const [pathOffset, setPathOffset] = useState(0);
  const [mode, setMode] = useState("NEW_HIRE");
  const [role, setRole] = useState("GENERAL");
  const [source, setSource] = useState("");
  const [participant, setParticipant] = useState("");
  const [mentor, setMentor] = useState("");
  const [skills, setSkills] = useState("");
  const [team, setTeam] = useState("");
  const [retentionDays, setRetentionDays] = useState("90");
  const [memberSearch, setMemberSearch] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [scores, setScores] = useState<Record<string, string>>({});
  const [managerNotes, setManagerNotes] = useState("");
  const requestKey = useRef(crypto.randomUUID());
  const canManage = identity.access?.permissions.includes("learning.manage") || !!identity.access?.administered_team_ids?.length;
  const accountId = identity.access?.user_id;
  const teams = useQuery({ queryKey: ["learning-teams", tenantKey], enabled: !!canManage,
    queryFn: () => api<{ items: { id: string; name: string }[]; page?: { has_more: boolean } }>("/admin/teams?limit=100") });
  useEffect(() => { setTarget(repository === "ALL" ? "" : repository); }, [repository]);
  useEffect(() => { setSelected(""); setTarget(repository === "ALL" ? "" : repository); setPathOffset(0); setAnswers({}); setNotes({}); setScores({}); setManagerNotes(""); setMessage(""); setTeam(""); setSource(""); setParticipant(""); setMentor(""); setSkills(""); setMemberSearch(""); requestKey.current = crypto.randomUUID(); }, [tenantKey]);
  const knowledge = useQuery({ queryKey: ["learning-knowledge", tenantKey, target], enabled: !!target,
    queryFn: () => api<Knowledge>(`/learning/knowledge/${encodeURIComponent(target)}`) });
  const members = useQuery({ queryKey: ["learning-members", tenantKey, target, team, memberSearch], enabled: !!target && !!canManage,
    queryFn: () => api<{ items: Member[]; has_more: boolean }>("/learning/members?" + new URLSearchParams({ repository_id: target, search: memberSearch, ...(team ? { team_id: team } : {}) })) });
  const list = useQuery({ queryKey: ["learning-journeys", tenantKey, pathOffset], queryFn: () => api<{ items: Summary[]; has_more: boolean }>("/learning/journeys?offset=" + pathOffset) });
  const detail = useQuery({ queryKey: ["learning-journey", tenantKey, selected], enabled: !!selected,
    queryFn: () => api<Journey>(`/learning/journeys/${encodeURIComponent(selected)}`) });
  const journey = detail.data;

  async function perform(path: string, body: unknown) {
    setBusy(true); setMessage("");
    try {
      const result = await api<Journey>(path, body);
      if (currentScope.current !== tenantKey) return false;
      queryClient.setQueryData(["learning-journey", tenantKey, result.id], result);
      setSelected(result.id);
      await queryClient.invalidateQueries({ queryKey: ["learning-journeys", tenantKey] });
      setMessage("Learning record saved.");
      return true;
    } catch (error) { setMessage(error instanceof Error ? error.message : "The learning operation failed."); return false; }
    finally { setBusy(false); }
  }

  async function assign(event: FormEvent) {
    event.preventDefault();
    const saved = await perform("/learning/journeys", { repository_id: target, source_repository_id: mode === "INTERNAL_TRANSFER" ? source : null,
      participant_id: participant, mentor_id: mentor, manager_id: accountId, team_id: team || null, mode, role,
      skills: skills.split(",").map(s => s.trim()).filter(Boolean), request_key: requestKey.current, retention_days: Number(retentionDays) });
    if (saved) requestKey.current = crypto.randomUUID();
  }

  async function inspect(id: string) {
    try { onOpen(await api<Item>(`/record/${encodeURIComponent(id)}`)); }
    catch (error) { setMessage(error instanceof Error ? error.message : "Captured evidence is unavailable."); }
  }

  return <div className="quality-module learning-module">
    <section className="settings-panel">
      <h2>Project knowledge</h2>
      <p>Learn from published architecture, engineering claims and source evidence. Static knowledge and declared skills require human assessment.</p>
      <label>Knowledge project<select aria-label="Knowledge project" value={target} onChange={e => setTarget(e.target.value)}>
        <option value="">Choose an authorized project</option>{repositories.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
      </select></label>
      {knowledge.isPending && target && <p role="status">Loading captured project knowledge…</p>}
      {knowledge.isError && <p role="alert">{knowledge.error.message} <button onClick={() => knowledge.refetch()}>Retry knowledge</button></p>}
      {knowledge.data && <>
        <p>Snapshot <code>{knowledge.data.snapshot_id}</code> · {knowledge.data.branch} · {knowledge.data.status}. Knowledge preview is bounded to {knowledge.data.maximum_records_per_kind} records per kind.</p>
        <div className="learning-knowledge-grid">{knowledge.data.resources.slice(0, 12).map(r => <article key={r.id} className="settings-panel">
          <p className="eyebrow">{r.topic} · {r.status}</p><h3>{r.title}</h3><p>{r.explanation}</p>
          <p>Confidence: {r.confidence}{r.path ? ` · ${r.path}` : ""}</p><button onClick={() => inspect(r.id)}>Inspect captured knowledge</button>
        </article>)}</div>
      </>}
    </section>
    {message && <p role="status" className="learning-message">{message}</p>}
    <section className="settings-panel">
      <h2>Learning paths and reviews</h2>
      {list.isPending && <p role="status">Loading your learning assignments…</p>}
      {list.isError && <p role="alert">{list.error.message} <button onClick={() => list.refetch()}>Retry assignments</button></p>}
      {list.data?.items.length === 0 && <p>No learning paths are assigned to you yet.</p>}
      <div className="learning-path-list">{list.data?.items.map(item => <button key={item.id} className={selected === item.id ? "active" : ""} onClick={() => setSelected(item.id)}>
        {item.mode === "NEW_HIRE" ? "New employee" : "Internal transfer"} · {item.role} · {item.state}
      </button>)}</div>
      <div className="learning-path-list"><button disabled={!pathOffset || list.isFetching} onClick={() => setPathOffset(Math.max(0, pathOffset - 25))}>Previous learning paths</button><button disabled={!list.data?.has_more || list.isFetching} onClick={() => setPathOffset(pathOffset + 25)}>Next learning paths</button></div>
    </section>
    {canManage && <section className="settings-panel"><h2>Assign a learning path</h2>
      <form onSubmit={assign} className="learning-assignment">
        <label>Onboarding mode<select value={mode} onChange={e => setMode(e.target.value)}><option value="NEW_HIRE">New employee</option><option value="INTERNAL_TRANSFER">Internal project transfer</option></select></label>
        {mode === "INTERNAL_TRANSFER" && <label>Previous project<select required value={source} onChange={e => setSource(e.target.value)}><option value="">Choose a previous project</option>{repositories.filter(r => r.id !== target).map(r => <option key={r.id} value={r.id}>{r.name}</option>)}</select></label>}
        <label>Learning role<select value={role} onChange={e => setRole(e.target.value)}>{["GENERAL", "BACKEND", "FRONTEND", "SECURITY", "PLATFORM"].map(r => <option key={r}>{r}</option>)}</select></label>
        <label>Team<select value={team} onChange={e => setTeam(e.target.value)}><option value="">{identity.access?.permissions.includes("learning.manage") ? "Organization assignment" : "Choose an administered team"}</option>{teams.data?.items.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}</select></label>
        {teams.isError && <p role="alert">Team choices could not be loaded. <button type="button" onClick={() => teams.refetch()}>Retry team choices</button></p>}
        {teams.data?.page?.has_more && <p>Showing the first 100 administered team choices.</p>}
        <label>Response retention<select value={retentionDays} onChange={e => setRetentionDays(e.target.value)}>{[7, 30, 90, 180].map(days => <option key={days} value={days}>{days} days</option>)}</select></label>
        <label>Find participants and mentors<input value={memberSearch} onChange={e => setMemberSearch(e.target.value)} maxLength={100} /></label>
        {members.data?.has_more && <p>More members match. Narrow the search by email or member ID.</p>}
        {members.isError && <p role="alert">{members.error.message}</p>}
        <label>Participant<select required value={participant} onChange={e => setParticipant(e.target.value)}><option value="">Choose a participant</option>{members.data?.items.filter(m => m.id !== accountId).map(m => <option key={m.id} value={m.id}>{m.email}</option>)}</select></label>
        <label>Mentor<select required value={mentor} onChange={e => setMentor(e.target.value)}><option value="">Choose a mentor</option>{members.data?.items.filter(m => m.id !== accountId && m.id !== participant).map(m => <option key={m.id} value={m.id}>{m.email}</option>)}</select></label>
        <label>Existing skills (comma separated)<input value={skills} onChange={e => setSkills(e.target.value)} maxLength={1000} /></label>
        <p>You are the accountable manager. Participant, mentor and manager require project access; transfer paths also require previous-project access.</p>
        <button disabled={busy || !target || !knowledge.data || !accountId}>Assign evidence-backed path</button>
      </form></section>}
    {detail.isError && <p role="alert">{detail.error.message} <button onClick={() => detail.refetch()}>Reload learning path</button></p>}
    {journey && <section className="settings-panel">
      <h2>{journey.mode === "NEW_HIRE" ? "New employee onboarding" : "Internal knowledge transfer"}</h2>
      <p>{journey.role} · {journey.state} · Revision {journey.revision} · {journey.viewer.toLowerCase()} view</p>
      <p>Captured snapshot: <code>{journey.snapshot_id}</code>. {journey.progress.approved} of {journey.progress.total} objectives approved.</p>
      <progress aria-label="Approved learning objectives" value={journey.progress.approved} max={journey.progress.total || 1} />
      <p>Declared skills: {journey.skills.join(", ") || "None declared"}. Private responses are encrypted and withheld after {new Date(journey.expires_at).toLocaleDateString()}.</p>
      {journey.viewer === "PARTICIPANT" && journey.state !== "COMPLETED" && !journey.retention_expired && <form onSubmit={e => { e.preventDefault(); perform(`/learning/journeys/${journey.id}/skills`, { version: journey.version, skills: skills.split(",").map(s => s.trim()).filter(Boolean) }); }}><label>Declare your existing skills<input value={skills} onChange={e => setSkills(e.target.value)} maxLength={1000} /></label><button disabled={busy}>Save skill declaration</button><p>Your declaration informs learning gaps; assessments remain required.</p></form>}
      {journey.comparison && <div><h3>Project comparison</h3><p>Shared observed technologies: {journey.comparison.shared_observed_technologies.join(", ") || "None in this bounded preview"}.</p><p>Target-project technologies: {journey.comparison.target_observed_technologies.join(", ") || "None in this bounded preview"}. Observations do not prove prior competence.</p></div>}
      {journey.refresh_required && <p role="status">Source changed. Manager-approved refresh is required before completion.</p>}
      {journey.viewer === "MANAGER" && journey.refresh_required && <button disabled={busy || journey.retention_expired || !journey.can_complete} onClick={() => perform(`/learning/journeys/${journey.id}/refresh`, { version: journey.version })}>Refresh learning after source change</button>}
      {journey.retention_expired && <p role="status">The retention window expired. Private assessment responses are withheld.</p>}
      <ol className="learning-objectives">{journey.objectives.map(objective => <li key={objective.id} className="settings-panel">
        <h3>{objective.title}</h3><p>{objective.question}</p><p>{objective.state} · {objective.gap_basis.replaceAll("_", " ")} {objective.score !== undefined ? `· Mentor score ${objective.score}/4` : ""}</p>
        <button onClick={() => inspect(objective.record_id)}>Inspect objective knowledge</button>
        {objective.evidence_ids.map(id => <button key={id} onClick={() => inspect(id)}>Inspect source evidence</button>)}
        {objective.assessment && <blockquote><p>{objective.assessment.answer}</p><small>Submitted captured citations: {objective.assessment.evidence_ids.length}</small></blockquote>}
        {journey.viewer === "PARTICIPANT" && journey.state !== "COMPLETED" && !journey.retention_expired && objective.state !== "APPROVED" && <form onSubmit={e => { e.preventDefault(); perform(`/learning/journeys/${journey.id}/objectives/${objective.id}/submit`, { version: objective.version, answer: answers[objective.id] || "", evidence_ids: [objective.record_id] }); }}>
          <label>Evidence-backed explanation<textarea required minLength={30} maxLength={8000} value={answers[objective.id] || ""} onChange={e => setAnswers({ ...answers, [objective.id]: e.target.value })} /></label>
          <p>Your response cites the captured objective. A mentor evaluates the explanation; submission alone does not pass an assessment.</p><button disabled={busy}>Submit assessment</button>
        </form>}
        {journey.viewer === "MENTOR" && objective.state === "SUBMITTED" && !journey.retention_expired && <form onSubmit={e => { e.preventDefault(); perform(`/learning/journeys/${journey.id}/objectives/${objective.id}/review`, { version: objective.version, score: Number(scores[objective.id]), notes: notes[objective.id] || "" }); }}>
          <label>Assessment score<select required value={scores[objective.id] || ""} onChange={e => setScores({ ...scores, [objective.id]: e.target.value })}><option value="">Select a score</option>{[0, 1, 2, 3, 4].map(score => <option key={score} value={score}>{score} / 4{score >= 3 ? " — approve" : " — request changes"}</option>)}</select></label>
          <label>Mentor feedback<textarea required minLength={10} maxLength={2000} value={notes[objective.id] || ""} onChange={e => setNotes({ ...notes, [objective.id]: e.target.value })} /></label><button disabled={busy}>Submit mentor review</button>
        </form>}
      </li>)}</ol>
      {journey.viewer === "MANAGER" && journey.state !== "COMPLETED" && !journey.retention_expired && <form onSubmit={e => { e.preventDefault(); perform(`/learning/journeys/${journey.id}/complete`, { version: journey.version, notes: managerNotes }); }}>
        <label>Manager completion review<textarea required minLength={10} maxLength={2000} value={managerNotes} onChange={e => setManagerNotes(e.target.value)} /></label>
        <button disabled={busy || !journey.can_complete || journey.refresh_required || journey.progress.approved !== journey.progress.total}>Complete learning revision</button>
      </form>}
      <h3>Review history</h3>{journey.reviews.length === 0 && <p>No reviews recorded.</p>}{journey.reviews.map(r => <p key={r.id}>{r.kind} · {r.decision} · {r.notes || "Private feedback withheld"}</p>)}
      <h3>Completion records</h3>{journey.completion_records.length === 0 && <p>No revision has completed manager review.</p>}{journey.completion_records.map(record => <p key={record.revision}>Revision {record.revision} · {new Date(record.at).toLocaleDateString()} · Snapshot <code>{record.snapshot_id}</code> · Mentor assessments and manager review</p>)}
    </section>}
  </div>;
}
