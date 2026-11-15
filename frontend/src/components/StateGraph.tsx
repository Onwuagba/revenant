import { useMemo, useState } from "react";
import { Background, Controls, ReactFlow, type Edge, type Node } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { Bundle } from "../api";

/** Layered layout by BFS depth from root; 0/00 (back/home) edges are omitted to keep it readable. */
function layout(b: Bundle) {
  const { root, states } = b.machine;
  const depth: Record<string, number> = { [root]: 0 };
  const queue = [root];
  while (queue.length) {
    const id = queue.shift()!;
    for (const [k, dest] of Object.entries(states[id]?.transitions ?? {})) {
      if (k === "0" || k === "00" || !(dest in states) || dest in depth) continue;
      depth[dest] = depth[id] + 1; queue.push(dest);
    }
  }
  const rows: Record<number, string[]> = {};
  for (const id of Object.keys(states)) (rows[depth[id] ?? 99] ||= []).push(id);
  const nodes: Node[] = []; const edges: Edge[] = [];
  Object.entries(rows).forEach(([d, ids]) => ids.sort().forEach((id, i) => {
    nodes.push({ id, position: { x: Number(d) * 230, y: i * 80 }, data: { label: `${id}\n(${states[id].kind})` },
      style: { background: "#1b212b", color: "#e6e9ee", border: "1px solid #2a3340", fontSize: 11, whiteSpace: "pre", width: 200 } });
  }));
  for (const [id, s] of Object.entries(states)) for (const [k, dest] of Object.entries(s.transitions)) {
    if (k === "0" || k === "00" || !(dest in states)) continue;
    edges.push({ id: `${id}-${k}-${dest}`, source: id, target: dest, label: k === "*" ? "input" : k, style: { stroke: "#7fd1b9" }, labelStyle: { fill: "#9aa5b4", fontSize: 10 } });
  }
  return { nodes, edges, depth };
}

export default function StateGraph({ bundle, onSelect }: { bundle: Bundle; onSelect: (id: string) => void }) {
  const [asList, setAsList] = useState(false);
  const g = useMemo(() => layout(bundle), [bundle]);
  const states = bundle.machine.states;
  return (
    <section aria-labelledby="graph-h">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h3 id="graph-h">State graph</h3>
        <button onClick={() => setAsList(v => !v)} aria-pressed={asList}>{asList ? "Show graph" : "Show tree list"}</button>
      </div>
      {asList ? (
        <ul className="tree" aria-label="State tree">
          {Object.keys(states).sort((a, b) => (g.depth[a] ?? 99) - (g.depth[b] ?? 99) || a.localeCompare(b)).map(id => (
            <li key={id}>
              <button onClick={() => onSelect(id)} style={{ border: 0, padding: 0, background: "none", color: "var(--accent)", cursor: "pointer" }}>{id}</button>
              {" "}<span className="muted">{states[id].kind}</span>
              {Object.entries(states[id].transitions).map(([k, d]) => <div key={k} className="muted" style={{ paddingLeft: 16 }}>{k} → {d}</div>)}
            </li>
          ))}
        </ul>
      ) : (
        <div style={{ height: 420, border: "1px solid var(--line)", borderRadius: 8 }} aria-label="State graph canvas">
          <ReactFlow nodes={g.nodes} edges={g.edges} fitView onNodeClick={(_, n) => onSelect(n.id)} nodesDraggable={false}>
            <Background /><Controls showInteractive={false} />
          </ReactFlow>
        </div>
      )}
    </section>
  );
}
