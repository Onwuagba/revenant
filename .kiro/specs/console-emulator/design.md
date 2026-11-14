# Design: console and emulator

## Components (`frontend/`)
Per `docs/ARCHITECTURE.md` section 10: `AppShell`, `SignalBars`, pages `Landing`, `Crypt`, `Project` (tabs Exhume/Reanimate/Last Rites/Rise), `Seance`, `Judges`, `Settings`. Shared: typed API client, SSE hook, a11y helpers. Data fetching with TanStack Query. Graph with React Flow, fallback tree list.

## Data flow
UI -> `/api/v1` REST + SSE; emulator -> `/api/v1/emulator/sessions/{sid}/input` which calls the runtime's step function (same code path as AT).

## Theme
Phosphor green on near-black, monospace screens, signal-bars motif for validation health. Contrast checked; focus rings visible; reduced-motion respected.

## Error handling
RFC 7807 problem JSON is mapped to inline messages; SSE reconnect with backoff.

## Testing strategy
Typecheck + build in CI; one Playwright smoke: upload sample -> compile (deterministic annotator) -> graph renders -> emulator books an appointment. Accessibility checks on emulator and graph fallback.

## Correctness properties
None from TESTING.md are owned by the UI. Screen text shown in the inspector must come from `screens.json`, never be recomputed in the browser.
