# Requirements: console and emulator

Source docs: `docs/ARCHITECTURE.md` sections 7, 8, 10, 11; `docs/PRD.md` sections 5, 9 (US1, US2, US9); ADR-014, ADR-015. Milestone: Thu 26 - Sat 28 Nov. Depends on the compiler, runtime and platform API. This is the LAST spec: the UI is a skin over a working core.

## Requirements

### Requirement 1: Console shell and theme
**User Story:** As a developer, I want a console that shows each pipeline stage, so that I can follow a compile.
#### Acceptance Criteria
1. THE console SHALL be a React + TypeScript + Vite app with a dark "Crypt" theme defined as CSS variables.
2. THE console SHALL name stages Exhume, Reanimate, Last Rites and Rise in UI text only.
3. THE console SHALL give every page loading, empty and error states.
4. THE console SHALL convey status by icon plus text, never colour alone.

### Requirement 2: Compile report pages
#### Acceptance Criteria
1. WHEN a compile finishes THE console SHALL show compiled operations, refused operations with codes (the "Buried" list), validator results, and the annotator used with a cached/fresh indicator.
2. WHEN a compile is running THE console SHALL stream stage events over SSE (`stage`, `log`, `kiro_event`, `validator`, `done`).

### Requirement 3: State graph and screen inspector
#### Acceptance Criteria
1. WHEN a bundle is loaded THE console SHALL render its state graph with React Flow, with a plain tree-list fallback.
2. WHEN a screen is selected THE console SHALL show its text, character count out of the profile limit, and worst-case count for dynamic slots.

### Requirement 4: Emulator
#### Acceptance Criteria
1. THE emulator at `/seance` SHALL be reachable without an account and SHALL list read-only sample projects.
2. WHEN a user presses keys THE emulator SHALL send input to the same runtime code path as the AT callback and show the returned screen.
3. THE emulator SHALL show an SMS inbox for the simulated MSISDN.
4. THE emulator SHALL label itself "simulated handset".
5. THE emulator screen SHALL be fixed-width monospace at the carrier max-char width and be keyboard operable, with the screen text in an `aria-live` region.

### Requirement 5: Judges page and honesty
#### Acceptance Criteria
1. THE `/judges` page SHALL explain what to try and link to evidence, using the claim wording in steering `product.md`.
2. THE console SHALL NOT display any metric that was not produced by a real run.

### Requirement 6: Access control
#### Acceptance Criteria
1. THE console SHALL use cookie sessions; viewers SHALL be read-only; sample projects SHALL be visible to all.
