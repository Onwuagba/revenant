// Typed client for /api/v1. Cookie session + CSRF header on state-changing calls.
export interface User { id: string; email: string; role: "owner" | "viewer"; csrf: string }
export interface Project { id: string; slug: string; title: string; is_public_sample: boolean }
export interface RunSummary { id: string; status: string; stage: string; annotator: string; bundle_id: string | null }
export interface BundleSummary { id: string; version: number; status: string; bundle_hash: string }
export interface ProjectDetail extends Project { runs: RunSummary[]; bundles: BundleSummary[] }
export interface RunEvent { event: string; data: Record<string, unknown>; t: number }
export interface RunRefusal { op_id: string; path: string; code: string; message: string }
export interface Run extends RunSummary { error: string; log: RunEvent[]; refusals?: RunRefusal[] }
export interface State {
  id: string; kind: string; op_id: string; title: string; transitions: Record<string, string>;
  template: string; static_len: number; worst_case_len: number; options: string[];
}
export interface Screen {
  state_id: string; kind: string; template: string; static_len: number; worst_case_len: number;
  slots: { name: string; max_len: number }[]; transitions: Record<string, string>;
}
export interface Bundle {
  id: string; status: string; version: number; bundle_hash: string;
  ir: { operations: { id: string; title: string; kind: string; risk: string }[]; carrier_profile?: { max_chars: number } };
  machine: { root: string; states: Record<string, State>; carrier_profile: { max_chars: number } };
  screens: Record<string, Screen>;
}
export interface Violation { state_id: string; message: string; measured: number | null }
export interface Report {
  validators: { validator: string; passed: boolean; violations: Violation[] }[];
  all_passed: boolean;
  refusals: { op_id: string; path: string; code: string; message: string; hint?: string }[];
  annotation: {
    annotator: string; cached: boolean; fallback_reason: string; kiro_model: string;
    transcript_path: string; exit_code: number | null; repair_attempts: number;
  };
}

let csrf = "";
export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET" && csrf) headers["X-CSRF-Token"] = csrf;
  const res = await fetch(`/api/v1${path}`, { method, headers, credentials: "same-origin",
    body: body === undefined ? undefined : JSON.stringify(body) });
  if (!res.ok) {
    let msg = res.statusText;
    try { const p = await res.json(); msg = p.detail ?? p.title ?? msg; } catch { /* keep statusText */ }
    throw new ApiError(res.status, msg);
  }
  return (await res.json()) as T;
}

export const api = {
  me: async () => { const u = await call<User>("GET", "/me"); csrf = u.csrf; return u; },
  login: async (email: string, password: string) => { const u = await call<User>("POST", "/auth/login", { email, password }); csrf = u.csrf; return u; },
  register: async (email: string, password: string) => { const u = await call<User>("POST", "/auth/register", { email, password }); csrf = u.csrf; return u; },
  logout: () => call<{ ok: boolean }>("POST", "/auth/logout", {}),
  projects: () => call<Project[]>("GET", "/projects"),
  project: (id: string) => call<ProjectDetail>("GET", `/projects/${id}`),
  createProject: (title: string, slug: string) => call<Project>("POST", "/projects", { title, slug }),
  addSource: (pid: string, kind: "openapi" | "mcp", v: string) =>
    call<{ id: string }>("POST", `/projects/${pid}/sources`, kind === "openapi" ? { kind, content: v } : { kind, url: v }),
  compile: (pid: string, annotator: string, fresh: boolean) => call<{ id: string }>("POST", `/projects/${pid}/compile`, { annotator, fresh }),
  run: (id: string) => call<Run>("GET", `/compile-runs/${id}`),
  bundle: (id: string) => call<Bundle>("GET", `/bundles/${id}`),
  report: (id: string) => call<Report>("GET", `/bundles/${id}/report`),
  deploy: (bid: string, upstream_base: string, sms_provider: string) =>
    call<{ id: string; callback_url: string }>("POST", `/bundles/${bid}/deployments`, { upstream_base, sms_provider }),
  putCredentials: (pid: string, api_key: string) => call<{ stored: boolean }>("PUT", `/projects/${pid}/credentials`, { api_key }),
  emuStart: (bundle_id: string, msisdn: string) => call<{ session_id: string; label: string; max_chars: number }>("POST", "/emulator/sessions", { bundle_id, msisdn }),
  emuInput: (sid: string, text: string) => call<{ type: "CON" | "END"; text: string }>("POST", `/emulator/sessions/${sid}/input`, { text }),
  emuInbox: (msisdn: string) => call<{ body: string }[]>("GET", `/emulator/inbox/${encodeURIComponent(msisdn)}`),
};
