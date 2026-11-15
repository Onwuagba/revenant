import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";

export default function AppShell() {
  const me = useQuery({ queryKey: ["me"], queryFn: api.me });
  const qc = useQueryClient();
  const nav = useNavigate();
  const signOut = async () => { await api.logout(); qc.clear(); nav("/"); };
  return (
    <div className="shell">
      <nav className="nav" aria-label="Main">
        <h1>Revenant</h1>
        <NavLink to="/" end>Home</NavLink>
        <NavLink to="/crypt">The Crypt</NavLink>
        <NavLink to="/seance">Séance</NavLink>
        <NavLink to="/judges">Judges</NavLink>
        <NavLink to="/settings">Settings</NavLink>
        <div className="spacer" />
        {me.data ? (
          <>
            <span className="muted" style={{ fontSize: 12 }}>{me.data.email} ({me.data.role})</span>
            <button onClick={signOut}>Sign out</button>
          </>
        ) : (
          <NavLink to="/login">Sign in</NavLink>
        )}
      </nav>
      <main><Outlet /></main>
    </div>
  );
}
