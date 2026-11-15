import { Route, Routes } from "react-router-dom";
import AppShell from "./components/AppShell";
import Landing from "./pages/Landing";
import Login from "./pages/Login";
import Crypt from "./pages/Crypt";
import Project from "./pages/Project";
import Seance from "./pages/Seance";
import Judges from "./pages/Judges";
import Settings from "./pages/Settings";
import NotFound from "./pages/NotFound";

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/" element={<Landing />} />
        <Route path="/login" element={<Login />} />
        <Route path="/crypt" element={<Crypt />} />
        <Route path="/crypt/:slug" element={<Project />} />
        <Route path="/seance" element={<Seance />} />
        <Route path="/seance/:slug" element={<Seance />} />
        <Route path="/judges" element={<Judges />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/404" element={<NotFound />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
