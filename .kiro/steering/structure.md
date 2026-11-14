---
inclusion: always
---
# Repository layout (from docs/ARCHITECTURE.md section 3)

```
.kiro/                          specs, steering, hooks, agents, settings, evidence
backend/src/revenant/
  compiler/   ingest_openapi.py ingest_mcp.py ir.py subset.py refusals.py planner.py render.py gsm7.py
              validators/ (reachability, exits, back, steps, length, pin, sms)
              annotate/ (kiro_headless, deterministic, schema)
              emit.py cli.py
  runtime/    app.py machine.py session.py actions.py sms.py redact.py
  platform/   api/ models/ services/ worker.py auth.py settings.py
  mcp_validator/ server.py      MCP server exposing validators (used by the Kiro agent)
backend/alembic/
frontend/                       React + TS + Vite
examples/   specs/ (clinic.openapi.yaml, unsupported-demo.openapi.yaml)  clinic_api/  farmer_prices_mcp/
generated/  clinic-booking/  farmer-prices/    committed emitter output
infrastructure/ docker-compose.yml Dockerfile.api Dockerfile.worker Caddyfile
tests/      unit/ pbt/ integration/ e2e/       (pbt regressions in tests/pbt/regressions/)
scripts/    probe_at.py kiro_smoke.sh seed.py
docs/  architecture/                           design docs, the source of truth
```

## Conventions
- One concern per module. Compiler and runtime never import from `platform/`.
- The runtime library is shared: the platform and every generated app use the same `runtime/` code.
- Source of truth for behaviour: `docs/*.md` and `architecture/*.md`. If code and docs disagree, stop and flag it; do not silently change either.
- Before creating a file, check the layout above; do not invent new top-level folders.
- Tests live under `tests/`, mirroring module names. Mark property tests `@pytest.mark.pbt`.
