import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { Badge, ErrorBox, Query } from "../components/ui";

export default function Crypt() {
  const projects = useQuery({ queryKey: ["projects"], queryFn: api.projects });
  const me = useQuery({ queryKey: ["me"], queryFn: api.me });
  const qc = useQueryClient();
  const [title, setTitle] = useState(""); const [slug, setSlug] = useState("");
  const create = useMutation({
    mutationFn: () => api.createProject(title, slug),
    onSuccess: () => { setTitle(""); setSlug(""); qc.invalidateQueries({ queryKey: ["projects"] }); },
  });
  const onSubmit = (e: FormEvent) => { e.preventDefault(); create.mutate(); };
  const owner = me.data?.role === "owner";
  return (
    <>
      <h2>The Crypt</h2>
      <p className="muted">Sample projects are read-only. Sign in to bury your own.</p>
      <Query q={projects} what="Opening the Crypt" empty={d => d.length === 0}>
        {list => (
          <div className="grid">
            {list.map(p => (
              <Link key={p.id} to={`/crypt/${p.slug}`} className="card" style={{ textDecoration: "none", color: "inherit" }}>
                <h3>{p.title}</h3>
                <Badge kind={p.is_public_sample ? "idle" : "ok"}>{p.is_public_sample ? "Sample (read-only)" : "Yours"}</Badge>
                <div className="muted" style={{ marginTop: 8 }}>{p.slug}</div>
              </Link>
            ))}
          </div>
        )}
      </Query>
      {owner ? (
        <form className="card" onSubmit={onSubmit} aria-labelledby="np-h">
          <h3 id="np-h">New project</h3>
          <div className="row">
            <div><label htmlFor="pt">Title</label><input id="pt" required value={title} onChange={e => setTitle(e.target.value)} /></div>
            <div><label htmlFor="ps">Slug</label><input id="ps" required pattern="[a-z0-9][a-z0-9\-]{1,62}" value={slug} onChange={e => setSlug(e.target.value)} /></div>
            <button className="primary" disabled={create.isPending} style={{ alignSelf: "end" }}>Create</button>
          </div>
          {create.isError ? <ErrorBox error={create.error} /> : null}
        </form>
      ) : null}
    </>
  );
}
