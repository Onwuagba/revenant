# Revenant

Compile an OpenAPI 3.x spec or an MCP server's tool list into a **verified USSD + SMS app** for feature phones.
Operations outside the documented subset are **refused with a code and a reason**, never guessed.

> Honest scope: bundles are *checked by validators against stated invariants* (behavioural evidence, not a proof).
> USSD runs in our emulator, labelled **simulated handset**. It has not been run on a real handset. The demo upstream
> and its PIN are a mock.

**Live demo:** https://revenant-st1d.onrender.com (free tier: the first load after idle takes 30-60 s; read-only samples, simulated handset)

## What is here
| Piece | Where |
|---|---|
| Compiler: ingest, type-subset classifier, planner, renderer, validators V1-V8 | `backend/src/revenant/compiler/` |
| Annotation stage: schema, deterministic annotator, Kiro headless runner, cache, repair loop | `backend/src/revenant/compiler/annotate/` |
| Validator MCP server (`validate_draft`, `explain_violation`, `list_limits`) | `backend/src/revenant/mcp_validator/` |
| Runtime: AT-shaped callback, replay, dedupe, PIN safety, lockout, SMS outbox + worker | `backend/src/revenant/runtime/` |
| Platform API (`/api/v1`): auth, projects, compile runs + SSE, bundles, deployments, emulator | `backend/src/revenant/api/` |
| Console ("The Crypt") + emulator ("Séance") | `frontend/` |
| Generated sample apps | `generated/clinic-booking`, `generated/farmer-prices` |
| Kiro specs, steering, hooks, agents | `.kiro/` (committed on purpose) |

## Run it (one command)
Needs Docker with Compose v2. From the repo root:
```bash
docker compose up --build
```
Open http://localhost:8000/seance/clinic-booking, press Dial, and book (clinic `c1`, slot `s1`, confirm `1`, demo PIN `2468`).
This starts PostgreSQL 16 and one app container (API, AT-shaped `/ussd` callback and the built console on one origin).
The three sample projects are compiled at start-up with the deterministic annotator. Data persists in a Docker volume;
`docker compose down -v` removes it. Optional settings go in `.env` (copy `.env.example`; empty values use the defaults).
The compose file is for local use: plain HTTP, no database password, cookies without `Secure`.

## Run it for development
```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -c backend/constraints.txt -e "backend[dev,web,mcp]"
REVENANT_INSECURE_COOKIES=1 uvicorn revenant.api.main:app --port 8765     # API + /ussd route (SQLite, in a temp file)
```
In a second terminal:
```bash
cd frontend && npm install && REVENANT_API=http://127.0.0.1:8765 npm run dev   # console on http://127.0.0.1:5173
```
`REVENANT_INSECURE_COOKIES=1` is for local HTTP only; production keeps `Secure` cookies.

CLI (in the venv):
```bash
revenant verify examples/specs                  # compile + validate; exit 1 on any violation
revenant compile examples/specs/clinic.openapi.yaml --out generated/clinic-booking
```

## Tests
```bash
pytest tests -q                                  # unit, property-based, integration (SQLite)
pytest -m pbt --hypothesis-profile=ci -q         # Hypothesis ci profile (seed and counts are printed by the run)
ruff check --config backend/pyproject.toml backend/src tests && (cd backend && mypy)   # lint, strict types
cd frontend && npm run build && npx playwright test   # typecheck, build, e2e smoke + axe a11y
```
Same suite on PostgreSQL 16 (each test gets a fresh database, dropped at the end):
```bash
docker run --rm -d --name revenant-pg -e POSTGRES_HOST_AUTH_METHOD=trust -p 127.0.0.1:5433:5432 postgres:16-alpine
REVENANT_TEST_PG_URL=postgresql+psycopg://postgres@127.0.0.1:5433/postgres pytest tests -q
docker stop revenant-pg
```
Playwright against the compose stack instead of a dev server: `E2E_BASE_URL=http://localhost:8000 npx playwright test`.

## Deploy (Render)
`render.yaml` is a Render Blueprint: one Docker web service. The `Dockerfile` builds the console and the API serves it
from the same origin (`REVENANT_CONSOLE_DIR`), so `/`, `/crypt`, `/seance/*`, `/judges`, `/api/v1/*` and the `/ussd` callback share one URL.
Free-plan notes: the instance sleeps when idle (the first request can take 30-60 s) and its disk is ephemeral, so the SQLite
file resets on restart; the three sample projects are re-seeded at start-up. The Kiro CLI is not in the image, so compiles on
the hosted app use the deterministic annotator and say so.

## Kiro
The annotation stage runs `kiro-cli` headless (agent `ussd-annotator`) when `KIRO_API_KEY` and the CLI are present.
Otherwise a deterministic annotator runs and the report says `deterministic(fallback: <reason>)`.
Every report states which annotator ran and whether the result was cached. See `docs/KIRO_EVIDENCE.md` for what has
and has not been run for real.

## Security notes
PINs are held in memory only and never logged, stored or rendered (canary-PIN test greps responses, logs and a DB dump).
MSISDNs are stored encrypted with an HMAC for lookups. Specs are untrusted data: URL guard against SSRF, safe YAML,
spec text reaches Kiro only as files. See `docs/SECURITY.md`.

## Licence
MIT. See `LICENSE`.
