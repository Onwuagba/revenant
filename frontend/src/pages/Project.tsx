import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Bundle, type Report } from "../api";
import { Badge, Empty, ErrorBox, Loading, Query } from "../components/ui";
import StateGraph from "../components/StateGraph";
import ScreenInspector from "../components/ScreenInspector";
import { useRunEvents } from "../components/useRunEvents";

const TABS = ["Exhume", "Reanimate", "Last Rites", "Rise"] as const;
type Tab = typeof TABS[number];

export default function Project() {
  const { slug = "" } = useParams();
  const [tab, setTab] = useState<Tab>("Exhume");
  const [runId, setRunId] = useState<string | null>(null);
  const qc = useQueryClient();
  const project = useQuery({ queryKey: ["project", slug], queryFn: () => api.project(slug) });
  const me = useQuery({ queryKey: ["me"], queryFn: api.me });
  const canEdit = !!me.data && me.data.role === "owner" && project.data?.is_public_sample === false;
  return (
    <Query q={project} what="Unearthing project">
      {p => {
        const latest = p.bundles[0] ?? null;
        return (
          <>
            <h2>{p.title}</h2>
            <p className="muted">{p.slug} {p.is_public_sample ? <Badge kind="idle">Sample (read-only)</Badge> : null}</p>
            <div className="tabs" role="tablist" aria-label="Pipeline stages">
              {TABS.map(t => <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)}>{t}</button>)}
            </div>
            {tab === "Exhume" && <Exhume pid={p.id} runs={p.runs} canEdit={canEdit}
              onStarted={id => { setRunId(id); setTab("Reanimate"); qc.invalidateQueries({ queryKey: ["project", slug] }); }} />}
            {tab === "Reanimate" && <Reanimate runId={runId ?? p.runs[0]?.id ?? null} live={runId !== null}
              bundleId={latest?.id ?? null} onDone={() => qc.invalidateQueries({ queryKey: ["project", slug] })} />}
            {tab === "Last Rites" && (latest ? <LastRites bundleId={latest.id} /> : <Empty>No bundle yet. Compile first.</Empty>)}
            {tab === "Rise" && (latest ? <Rise bundleId={latest.id} canEdit={canEdit} slug={p.slug} /> : <Empty>No verified bundle to deploy.</Empty>)}
          </>
        );
      }}
    </Query>
  );
}

function Exhume({ pid, runs, canEdit, onStarted }: { pid: string; runs: { id: string }[]; canEdit: boolean; onStarted: (id: string) => void }) {
  const [kind, setKind] = useState<"openapi" | "mcp">("openapi");
  const [value, setValue] = useState(""); const [annotator, setAnnotator] = useState("auto"); const [fresh, setFresh] = useState(false);
  const start = useMutation({
    mutationFn: async () => { if (value) await api.addSource(pid, kind, value); return api.compile(pid, annotator, fresh); },
    onSuccess: r => onStarted(r.id),
  });
  const latestRun = runs[0]?.id ?? null;
  const run = useQuery({ queryKey: ["run", latestRun], queryFn: () => api.run(latestRun!), enabled: !!latestRun });
  const report = useQuery({
    queryKey: ["report-of-run", run.data?.bundle_id], queryFn: () => api.report(run.data!.bundle_id!), enabled: !!run.data?.bundle_id,
  });
  // A run that refused every operation has no bundle (so no report); fall back to the refusals stored with the run.
  const refusals: { op_id: string; path: string; code: string; message?: string; hint?: string }[] =
    report.data?.refusals ?? run.data?.refusals ?? [];
  return (
    <>
      {canEdit ? (
        <form className="card" aria-labelledby="ex-h" onSubmit={e => { e.preventDefault(); start.mutate(); }}>
          <h3 id="ex-h">Exhume: read your spec</h3>
          <div className="row">
            <label><input type="radio" checked={kind === "openapi"} onChange={() => setKind("openapi")} /> OpenAPI (JSON/YAML)</label>
            <label><input type="radio" checked={kind === "mcp"} onChange={() => setKind("mcp")} /> MCP server URL</label>
          </div>
          {kind === "openapi"
            ? <textarea aria-label="OpenAPI document" value={value} onChange={e => setValue(e.target.value)} placeholder="Paste an OpenAPI 3.0/3.1 document (max 2 MB)" />
            : <input aria-label="MCP URL" style={{ width: "100%" }} value={value} onChange={e => setValue(e.target.value)} placeholder="https://example.com/mcp" />}
          <div className="row" style={{ marginTop: 8 }}>
            <label>Annotator <select value={annotator} onChange={e => setAnnotator(e.target.value)}>
              <option value="auto">auto</option><option value="kiro">kiro</option><option value="deterministic">deterministic</option></select></label>
            <label><input type="checkbox" checked={fresh} onChange={e => setFresh(e.target.checked)} /> Ignore cache</label>
            <button className="primary" disabled={start.isPending}>Compile</button>
          </div>
          {start.isError ? <ErrorBox error={start.error} /> : null}
        </form>
      ) : <p className="muted">This project is read-only for your account.</p>}
      <div className="card">
        <h3>Buried</h3>
        {!latestRun ? <Empty>No compile has run yet.</Empty> : report.isLoading || run.isLoading ? <Loading /> :
          run.data?.status === "refused" || refusals.length ? (
            <table><thead><tr><th>Operation</th><th>Code</th><th>Reason</th></tr></thead>
              <tbody>{refusals.map((r, i) => <tr key={i}><td>{r.op_id}<div className="muted">{r.path}</div></td><td><code>{r.code}</code></td><td>{r.message}{r.hint ? <div className="muted">{r.hint}</div> : null}</td></tr>)}</tbody></table>
          ) : <p>Nothing was refused in the latest run.</p>}
        {run.data?.status === "refused" ? <p>Every operation was refused; no bundle was produced.</p> : null}
      </div>
    </>
  );
}

function Reanimate({ runId, live, bundleId, onDone }: { runId: string | null; live: boolean; bundleId: string | null; onDone: () => void }) {
  const stream = useRunEvents(live ? runId : null);
  const saved = useQuery({ queryKey: ["run", runId], queryFn: () => api.run(runId!), enabled: !!runId && !live });
  useEffect(() => { if (stream.done) onDone(); }, [stream.done]); // eslint-disable-line react-hooks/exhaustive-deps
  const events = live ? stream.events : saved.data?.log ?? [];
  const bundle = useQuery({ queryKey: ["bundle", bundleId], queryFn: () => api.bundle(bundleId!), enabled: !!bundleId && (!live || stream.done) });
  const report = useQuery({ queryKey: ["report", bundleId], queryFn: () => api.report(bundleId!), enabled: !!bundleId && (!live || stream.done) });
  const [sel, setSel] = useState<string | null>(null);
  if (!runId) return <Empty>No run yet. Start one from Exhume.</Empty>;
  if (!live && saved.isLoading) return <Loading />;
  const ann = report.data?.annotation;
  return (
    <>
      <div className="card">
        <h3>Reanimate</h3>
        {ann ? (
          <p>Annotator: <strong>{ann.annotator}</strong> <Badge kind={ann.cached ? "warn" : "ok"}>{ann.cached ? "Cached result" : "Fresh result"}</Badge>
            {ann.kiro_model ? <> · model {ann.kiro_model}</> : null}</p>
        ) : <p className="muted">Annotator is reported when the run finishes.</p>}
        <div className="log" role="log" aria-live="polite" aria-label="Compile log">
          {events.length === 0 ? <span className="muted">Waiting for events…</span> : events.map((e, i) => (
            <div key={i}><span className="muted">[{e.event}]</span> {summary(e.data)}</div>
          ))}
        </div>
        {live && !stream.done ? <Badge kind="idle">Running</Badge> : null}
      </div>
      {bundle.data ? (
        <div className="split">
          <StateGraph bundle={bundle.data} onSelect={setSel} />
          <ScreenInspector bundle={bundle.data} stateId={sel} />
        </div>
      ) : bundle.isError ? <ErrorBox error={bundle.error} /> : null}
    </>
  );
}
const summary = (d: Record<string, unknown>) => Object.entries(d).filter(([, v]) => v !== "" && v !== null).map(([k, v]) => `${k}=${typeof v === "object" ? JSON.stringify(v) : String(v)}`).join(" ");

function LastRites({ bundleId }: { bundleId: string }) {
  const report = useQuery({ queryKey: ["report", bundleId], queryFn: () => api.report(bundleId) });
  const bundle = useQuery({ queryKey: ["bundle", bundleId], queryFn: () => api.bundle(bundleId) });
  return (
    <Query q={report} what="Reading the rites">
      {(r: Report) => {
        const passed = r.validators.filter(v => v.passed).length;
        return (
          <>
            <div className="card">
              <h3>Last Rites</h3>
              <p>{passed} of {r.validators.length} validators passed. <Badge kind={r.all_passed ? "ok" : "bad"}>{r.all_passed ? "Verified against stated invariants" : "Violations found"}</Badge></p>
              <table><thead><tr><th>Validator</th><th>Result</th><th>Violations</th></tr></thead>
                <tbody>{r.validators.map(v => (
                  <tr key={v.validator}><td>{v.validator}</td><td><Badge kind={v.passed ? "ok" : "bad"}>{v.passed ? "Passed" : "Failed"}</Badge></td>
                    <td>{v.violations.length === 0 ? "none" : v.violations.map((x, i) => <div key={i}><code>{x.state_id}</code> {x.message}{x.measured !== null ? ` (${x.measured})` : ""}</div>)}</td></tr>
                ))}</tbody></table>
            </div>
            {bundle.data ? <WorstCase b={bundle.data} /> : null}
          </>
        );
      }}
    </Query>
  );
}

function WorstCase({ b }: { b: Bundle }) {
  const limit = b.machine.carrier_profile?.max_chars ?? 182;
  const rows = Object.values(b.screens).sort((x, y) => y.worst_case_len - x.worst_case_len).slice(0, 8);
  return (
    <div className="card"><h3>Worst-case screen lengths</h3>
      <table><thead><tr><th>Screen</th><th>Worst case</th><th>Limit</th></tr></thead>
        <tbody>{rows.map(s => <tr key={s.state_id}><td>{s.state_id}</td><td className={`counter ${s.worst_case_len > limit ? "over" : ""}`}>{s.worst_case_len}</td><td>{limit}</td></tr>)}</tbody></table>
    </div>
  );
}

function Rise({ bundleId, canEdit, slug }: { bundleId: string; canEdit: boolean; slug: string }) {
  const [upstream, setUpstream] = useState(slug === "clinic-booking" ? "mock://clinic" : ""); const [sms, setSms] = useState("emulator");
  const dep = useMutation({ mutationFn: () => api.deploy(bundleId, upstream, sms) });
  return (
    <div className="card">
      <h3>Rise: deploy</h3>
      {!canEdit ? <p className="muted">Deployment is available to project owners. Samples run in the <a href="/seance">simulated handset</a>.</p> : (
        <form onSubmit={e => { e.preventDefault(); dep.mutate(); }}>
          <div className="row">
            <div><label htmlFor="up">Upstream base URL</label><input id="up" value={upstream} onChange={e => setUpstream(e.target.value)} placeholder="https://api.example.com" /></div>
            <div><label htmlFor="sp">SMS provider</label><select id="sp" value={sms} onChange={e => setSms(e.target.value)}><option value="emulator">Emulator</option><option value="africastalking">Africa's Talking</option></select></div>
            <button className="primary" disabled={dep.isPending} style={{ alignSelf: "end" }}>Create deployment</button>
          </div>
        </form>
      )}
      {dep.isError ? <ErrorBox error={dep.error} /> : null}
      {dep.data ? (
        <div role="status">
          <p><Badge kind="ok">Deployment created</Badge></p>
          <p>Callback URL (shown once; only its hash is stored):</p>
          <pre>{dep.data.callback_url}</pre>
        </div>
      ) : null}
      <h3 style={{ marginTop: 16 }}>Africa's Talking channel</h3>
      <ol className="muted">
        <li>Create a USSD channel in the Africa's Talking sandbox.</li>
        <li>Paste the callback URL above as the channel callback.</li>
        <li>Dial the sandbox code in the Africa's Talking simulator. This is a simulator, not a real handset.</li>
      </ol>
    </div>
  );
}
