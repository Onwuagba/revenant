import { useEffect, useState } from "react";
import type { RunEvent } from "../api";

const NAMES = ["stage", "log", "kiro_event", "validator", "done"];

/** Subscribes to the compile-run SSE stream; returns events received so far. */
export function useRunEvents(runId: string | null) {
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [done, setDone] = useState(false);
  useEffect(() => {
    setEvents([]); setDone(false);
    if (!runId) return;
    const es = new EventSource(`/api/v1/compile-runs/${runId}/events`);
    NAMES.forEach(n => es.addEventListener(n, (e: MessageEvent) => {
      setEvents(prev => [...prev, { event: n, data: JSON.parse(e.data), t: Date.now() / 1000 }]);
      if (n === "done") { setDone(true); es.close(); }
    }));
    es.onerror = () => es.close();
    return () => es.close();
  }, [runId]);
  return { events, done };
}
