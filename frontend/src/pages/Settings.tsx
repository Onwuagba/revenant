import { useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { Badge, ErrorBox, Query } from "../components/ui";

export default function Settings() {
  const me = useQuery({ queryKey: ["me"], queryFn: api.me });
  const projects = useQuery({ queryKey: ["projects"], queryFn: api.projects });
  const [pid, setPid] = useState(""); const [key, setKey] = useState("");
  const [state, setState] = useState<"idle" | "saved" | { error: unknown }>("idle");
  const save = async (e: FormEvent) => {
    e.preventDefault();
    try { await api.putCredentials(pid, key); setKey(""); setState("saved"); } catch (error) { setState({ error }); }
  };
  return (
    <>
      <h2>Settings</h2>
      <Query q={me} what="Checking session">
        {u => u.role !== "owner" ? <div className="state">This account is read-only.</div> : (
          <form className="card" onSubmit={save} aria-labelledby="cr-h">
            <h3 id="cr-h">Upstream API key</h3>
            <p className="muted">Write-only. The key is encrypted at rest and never shown again or placed in a bundle.</p>
            <Query q={projects} empty={d => d.filter(p => !p.is_public_sample).length === 0}>
              {list => (
                <div className="row">
                  <div><label htmlFor="proj">Project</label>
                    <select id="proj" required value={pid} onChange={e => setPid(e.target.value)}>
                      <option value="">Choose…</option>
                      {list.filter(p => !p.is_public_sample).map(p => <option key={p.id} value={p.id}>{p.title}</option>)}
                    </select></div>
                  <div><label htmlFor="k">API key</label><input id="k" type="password" autoComplete="off" required value={key} onChange={e => setKey(e.target.value)} /></div>
                  <button className="primary" style={{ alignSelf: "end" }}>Store</button>
                </div>
              )}
            </Query>
            {state === "saved" ? <Badge kind="ok">Stored (not displayed)</Badge> : null}
            {typeof state === "object" ? <ErrorBox error={state.error} /> : null}
          </form>
        )}
      </Query>
    </>
  );
}
