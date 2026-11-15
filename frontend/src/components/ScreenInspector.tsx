import type { Bundle } from "../api";
import { Badge } from "./ui";

/** Shows a screen's text with character count out of the carrier limit and the worst case for slots. */
export default function ScreenInspector({ bundle, stateId }: { bundle: Bundle; stateId: string | null }) {
  const limit = bundle.machine.carrier_profile?.max_chars ?? 182;
  if (!stateId) return <div className="card"><h3>Screen inspector</h3><p className="muted">Select a state to inspect its screen.</p></div>;
  const st = bundle.machine.states[stateId]; const screen = bundle.screens[stateId];
  if (!st) return null;
  if (!screen) return <div className="card"><h3>{stateId}</h3><p className="muted">{st.kind} states do not render a screen.</p></div>;
  const worst = screen.worst_case_len; const over = worst > limit;
  return (
    <div className="card" aria-live="polite">
      <h3>{stateId}</h3>
      <div className="muted">{screen.kind}</div>
      <pre aria-label="Screen text">{screen.template}</pre>
      <p className={`counter ${over ? "over" : ""}`}>
        Static {screen.static_len} · worst case {worst} / {limit}{" "}
        <Badge kind={over ? "bad" : "ok"}>{over ? "Over the limit" : "Fits"}</Badge>
      </p>
      {screen.slots.length ? (
        <table><thead><tr><th>Slot</th><th>Max length</th></tr></thead>
          <tbody>{screen.slots.map(s => <tr key={s.name}><td>{s.name}</td><td>{s.max_len}</td></tr>)}</tbody></table>
      ) : <p className="muted">No dynamic slots.</p>}
      <p className="muted">Counts include the 4-character CON/END prefix in the worst case.</p>
    </div>
  );
}
