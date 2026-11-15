import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { Badge, Empty, ErrorBox, Query } from "../components/ui";

const MSISDN = "+2348000000000";
const LIMIT = 182;

export default function Seance() {
  const { slug } = useParams();
  const projects = useQuery({ queryKey: ["projects"], queryFn: api.projects });
  return (
    <>
      <h2>Séance</h2>
      <p className="muted">Dial a compiled app on a <strong>simulated handset</strong>. It uses the same runtime code path as the Africa's Talking callback. It is not a real phone.</p>
      <Query q={projects} what="Summoning samples" empty={d => d.filter(p => p.is_public_sample).length === 0}>
        {list => (
          <>
            <div className="row" role="navigation" aria-label="Sample apps" style={{ marginBottom: 16 }}>
              {list.filter(p => p.is_public_sample).map(p => (
                <Link key={p.id} className="btn" aria-current={slug === p.slug ? "page" : undefined} to={`/seance/${p.slug}`}>{p.title}</Link>
              ))}
            </div>
            {slug ? <Handset key={slug} slug={slug} /> : <Empty>Pick a sample above to start dialling.</Empty>}
          </>
        )}
      </Query>
    </>
  );
}

function Handset({ slug }: { slug: string }) {
  const project = useQuery({ queryKey: ["project", slug], queryFn: () => api.project(slug) });
  const bundleId = project.data?.bundles.find(b => b.status !== "failed")?.id;
  const [sid, setSid] = useState<string | null>(null);
  const [cumulative, setCumulative] = useState("");
  const [buffer, setBuffer] = useState("");
  const [screen, setScreen] = useState<{ type: "CON" | "END"; text: string } | null>(null);
  const [inbox, setInbox] = useState<string[]>([]);
  const input = useRef<HTMLInputElement>(null);

  const refreshInbox = async () => setInbox((await api.emuInbox(MSISDN)).map(m => m.body));

  const dial = useMutation({
    mutationFn: async () => {
      const s = await api.emuStart(bundleId!, MSISDN);
      const first = await api.emuInput(s.session_id, "");
      return { s, first };
    },
    onSuccess: ({ s, first }) => { setSid(s.session_id); setCumulative(""); setBuffer(""); setScreen(first); input.current?.focus(); },
  });
  const send = useMutation({
    mutationFn: async () => {
      const next = cumulative ? `${cumulative}*${buffer}` : buffer;
      const out = await api.emuInput(sid!, next);
      return { next, out };
    },
    onSuccess: async ({ next, out }) => { setCumulative(next); setBuffer(""); setScreen(out); await refreshInbox(); input.current?.focus(); },
  });

  useEffect(() => { refreshInbox().catch(() => undefined); }, []);
  const ended = screen?.type === "END";
  const canSend = !!sid && !ended && buffer !== "" && !send.isPending;
  const text = screen ? `${screen.type} ${screen.text}` : "Press Dial to start.";

  return (
    <Query q={project} what="Preparing handset">
      {() => !bundleId ? <Empty>This project has no compiled bundle yet.</Empty> : (
        <div className="split">
          <div className="phone" role="group" aria-label="Simulated handset">
            <div className="label">Simulated handset</div>
            <div className="lcd" style={{ width: "30ch", margin: "0 auto" }} role="status" aria-live="polite" aria-label="Handset screen" data-testid="lcd">{text}</div>
            <div className="muted" style={{ fontSize: 12, textAlign: "center", marginTop: 4 }}>
              {screen ? `${text.length} / ${LIMIT} characters` : ""}
            </div>
            <form onSubmit={e => { e.preventDefault(); if (canSend) send.mutate(); }}>
              <label htmlFor="keys" style={{ marginTop: 8 }}>Your input</label>
              <input id="keys" ref={input} autoComplete="off" disabled={!sid || ended} value={buffer}
                onChange={e => setBuffer(e.target.value.replace(/[*#]/g, ""))} style={{ width: "100%" }} inputMode="text" />
              <div className="keypad" aria-label="Keypad">
                {["1", "2", "3", "4", "5", "6", "7", "8", "9"].map(k => <button type="button" key={k} disabled={!sid || ended} onClick={() => setBuffer(b => b + k)}>{k}</button>)}
                <button type="button" aria-label="Delete" disabled={!sid || ended} onClick={() => setBuffer(b => b.slice(0, -1))}>⌫</button>
                <button type="button" disabled={!sid || ended} onClick={() => setBuffer(b => b + "0")}>0</button>
                <button type="submit" className="primary" disabled={!canSend}>Send</button>
              </div>
              <div className="row" style={{ marginTop: 12, justifyContent: "center" }}>
                <button type="button" className="primary" disabled={dial.isPending} onClick={() => dial.mutate()}>{sid ? "Redial" : "Dial"}</button>
              </div>
            </form>
            {dial.isError ? <ErrorBox error={dial.error} /> : null}
            {send.isError ? <ErrorBox error={send.error} /> : null}
            {ended ? <p style={{ textAlign: "center" }}><Badge kind="idle">Session ended</Badge></p> : null}
          </div>
          <section className="card" aria-labelledby="inbox-h">
            <h3 id="inbox-h">SMS inbox <span className="muted" style={{ fontSize: 12 }}>({MSISDN})</span></h3>
            {inbox.length === 0 ? <p className="muted">No messages.</p> : inbox.map((b, i) => <div className="sms" key={i}>{b}</div>)}
            <button onClick={() => refreshInbox()}>Refresh</button>
            <p className="muted" style={{ marginTop: 12 }}>Clinic demo PIN: <code>2468</code> (checked by a mock upstream).</p>
          </section>
        </div>
      )}
    </Query>
  );
}
