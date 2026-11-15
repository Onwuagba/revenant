import { Link } from "react-router-dom";

const STAGES = [
  ["Exhume", "Reads an OpenAPI 3.x spec or an MCP server and classifies every operation against the supported subset."],
  ["Reanimate", "Proposes short labels and a menu structure. Kiro runs headless when a key is available; otherwise a deterministic annotator runs and the report says so."],
  ["Last Rites", "Checks the state machine with validators V1-V8 against stated invariants (screen length, GSM-7, back/home, PIN handling)."],
  ["Rise", "Deploys a callback URL for Africa's Talking USSD and an SMS fallback for results that do not fit a screen."],
];

export default function Landing() {
  return (
    <>
      <h2>Revenant</h2>
      <p>Compile an API into a verified USSD + SMS app for feature phones. Operations outside the supported subset are refused with a code and a reason, never guessed.</p>
      <div className="row" style={{ marginBottom: 24 }}>
        <Link className="btn primary" to="/seance">Try the simulated handset</Link>
        <Link className="btn" to="/crypt">Open the Crypt</Link>
      </div>
      <div className="grid">
        {STAGES.map(([name, text]) => (
          <section className="card" key={name}><h3>{name}</h3><p className="muted">{text}</p></section>
        ))}
      </div>
    </>
  );
}
