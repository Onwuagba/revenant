import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { ErrorBox } from "../components/ui";

export default function Login() {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState(""); const [password, setPassword] = useState("");
  const [err, setErr] = useState<unknown>(null); const [busy, setBusy] = useState(false);
  const nav = useNavigate(); const qc = useQueryClient();
  const submit = async (e: FormEvent) => {
    e.preventDefault(); setBusy(true); setErr(null);
    try {
      await (mode === "login" ? api.login : api.register)(email, password);
      await qc.invalidateQueries(); nav("/crypt");
    } catch (x) { setErr(x); } finally { setBusy(false); }
  };
  return (
    <form className="card" onSubmit={submit} style={{ maxWidth: 380 }} aria-labelledby="auth-h">
      <h2 id="auth-h">{mode === "login" ? "Sign in" : "Create account"}</h2>
      <label htmlFor="email">Email</label>
      <input id="email" type="email" required value={email} onChange={e => setEmail(e.target.value)} style={{ width: "100%" }} />
      <label htmlFor="pw" style={{ marginTop: 8 }}>Password (8+ characters)</label>
      <input id="pw" type="password" required minLength={8} value={password} onChange={e => setPassword(e.target.value)} style={{ width: "100%" }} />
      {err ? <ErrorBox error={err} /> : null}
      <div className="row" style={{ marginTop: 12 }}>
        <button className="primary" disabled={busy}>{mode === "login" ? "Sign in" : "Register"}</button>
        <button type="button" onClick={() => setMode(mode === "login" ? "register" : "login")}>
          {mode === "login" ? "Need an account?" : "Have an account?"}
        </button>
      </div>
    </form>
  );
}
