import { Link } from "react-router-dom";

export default function Judges() {
  return (
    <>
      <h2>For judges</h2>
      <p className="muted">What to try, in order. Nothing on this page is a measured figure; run results appear in the Crypt, produced by real runs.</p>
      <ol>
        <li><Link to="/seance/clinic-booking">Séance: clinic booking</Link>. Dial the simulated handset, pick a clinic and slot, confirm, enter the demo PIN. This is a <strong>simulated handset</strong>, not a real phone.</li>
        <li><Link to="/crypt/clinic-booking">Crypt: clinic-booking</Link> (read-only). See the state graph, the screen inspector with character counts, and the Last Rites validator results.</li>
        <li><Link to="/crypt/unsupported-demo">Crypt: unsupported-demo</Link>. Operations outside the supported subset are listed as Buried, each with a refusal code and reason.</li>
        <li><Link to="/seance/farmer-prices">Séance: farmer prices</Link>, compiled from an MCP tool list.</li>
        <li>Open the Reanimate tab of any project. It states which annotator ran (<code>kiro-cli</code>, <code>deterministic</code>, or <code>cached</code>) and whether the result was cached. Samples at startup use the deterministic annotator.</li>
      </ol>
      <h3>How to read the claims</h3>
      <ul>
        <li>Bundles are <em>verified against stated invariants</em> by validators. This is behavioural evidence, not a proof.</li>
        <li>The supported subset is small and documented; anything else is refused, never guessed.</li>
        <li>The demo upstream is a mock; the demo PIN is checked by the mock, not by a real system.</li>
      </ul>
    </>
  );
}
