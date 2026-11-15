import type { ReactNode } from "react";
import type { UseQueryResult } from "@tanstack/react-query";

/** Status is always icon + text, never colour alone. */
export function Badge({ kind, children }: { kind: "ok" | "bad" | "warn" | "idle"; children: ReactNode }) {
  const icon = { ok: "✓", bad: "✗", warn: "!", idle: "…" }[kind];
  return (
    <span className={`badge ${kind}`}>
      <span aria-hidden="true">{icon}</span>
      <span>{children}</span>
    </span>
  );
}

export const Loading = ({ what = "Loading" }: { what?: string }) => (
  <div className="state" role="status">{what}…</div>
);
export const Empty = ({ children }: { children: ReactNode }) => <div className="state">{children}</div>;
export const ErrorBox = ({ error }: { error: unknown }) => (
  <div className="state err" role="alert">✗ {error instanceof Error ? error.message : "Something went wrong"}</div>
);

/** Loading / error / empty / data in one place so every page has all four states. */
export function Query<T>({ q, empty, what, children }: {
  q: UseQueryResult<T>; empty?: (d: T) => boolean; what?: string; children: (d: T) => ReactNode;
}) {
  if (q.isLoading) return <Loading what={what} />;
  if (q.isError) return <ErrorBox error={q.error} />;
  if (q.data === undefined) return <Empty>Nothing here.</Empty>;
  if (empty && empty(q.data)) return <Empty>Nothing here yet.</Empty>;
  return <>{children(q.data)}</>;
}
