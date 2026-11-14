# Kiro usage plan

Goal: judges (Technological Implementation = how well Kiro is used) can see real, load-bearing use of specs, steering, hooks, a custom agent, MCP, PBT, and the headless CLI. Everything below is created under repo-root `.kiro/` (committed, never in `.gitignore`). Design phase: none of these files exist yet.

Unverified items (PLATFORM_FACTS U9): exact hook JSON schema and the IDE spec-to-PBT UX. Create hooks through the IDE's hook UI and commit the generated files rather than hand-writing the schema.

## 1. Files to create

### Specs (EARS requirements, design with correctness properties, tasks)
Each folder holds `requirements.md`, `design.md`, `tasks.md`.
1. `.kiro/specs/ir-type-subset/` : IR, subset rules, refusal codes (P7, P13)
2. `.kiro/specs/ingestion/` : OpenAPI + MCP ingest, SSRF policy
3. `.kiro/specs/state-machine-validators/` : planner, renderer, V1-V8 (P1-P6, P10)
4. `.kiro/specs/runtime-sms/` : AT callback, replay, PIN safety, SMS fallback (P8, P9, P11)
5. `.kiro/specs/kiro-compile-step/` : headless stage, schema, fallback, cache (P12)
6. `.kiro/specs/console-emulator/` : pages, graph, emulator, accessibility

Design.md in specs 1, 3, 4 lists the correctness properties verbatim from TESTING.md so tasks map to Hypothesis tests.

### Steering (`.kiro/steering/*.md`, with inclusion mode in front matter)
- `product.md` (always): positioning, claim boundary, evidence wording
- `tech.md` (always): stack, versions, no-Redis, no-LLM-at-runtime rule
- `structure.md` (always): repo layout from ARCHITECTURE section 3
- `ussd-carrier-rules.md` (always; also copied into every headless run dir): 182 char budget incl. prefix, GSM-7 only, key conventions, step cap, session timing from PLATFORM_FACTS
- `type-subset.md` (fileMatch `backend/src/revenant/compiler/**`): subset table and refusal codes
- `security-pin-secrets.md` (fileMatch `backend/src/revenant/runtime/**`): PIN never logged/echoed/stored, redaction rules
- `copy-voice.md` (manual): short labels, verbs first, local-language-safe transliteration table, the Crypt voice for console copy
- `testing.md` (fileMatch `tests/**`): PBT conventions, seeds, profiles

### Hooks (`.kiro/hooks/`, created via IDE UI)
- `pbt-on-compiler-save` : on file save `backend/src/revenant/compiler/**/*.py` run `pytest -m pbt --hypothesis-profile=dev -x`
- `verify-on-spec-change` : on save/create `examples/specs/**` run `revenant verify examples/specs` (the "upstream API changed, re-verify" story)
- `pin-leak-guard` : on save `backend/src/revenant/runtime/**` run grep/AST check forbidding logging of `text`, `pin`; fails loudly
- `docs-drift` : on save `architecture/IR_AND_TYPE_SUBSET.md` remind to update subset steering/tests (agent prompt hook)
Evidence: a short `docs/KIRO_EVIDENCE.md` with a log excerpt of each hook firing (to be written during build).

### Custom agents (`.kiro/agents/*.json` + `.kiro/agents/prompts/*.md`)
- `ussd-annotator.json` : the headless compile agent. `prompt: file://./prompts/ussd-annotator.md`; `tools: ["read","write","@revenant-validator"]`; `permissions.rules` deny shell and web; `resources: ["file://.kiro/steering/ussd-carrier-rules.md"]`; `mcpServers` references the validator server. Output contract: write only `annotations.json` conforming to `annotations.schema.json`.
- `compiler-reviewer.json` : dev-time agent that reviews compiler diffs against the invariants (used in the IDE and in a CI-less pre-push check).
Use `permissions` not `allowedTools` (V3 ignores legacy fields).

### MCP (`.kiro/settings/mcp.json`)
- `revenant-validator` : stdio server `python -m revenant.mcp_validator` exposing `validate_draft`, `explain_violation`, `list_limits`. Used by the headless agent so Kiro iterates against the real validators.
- Optional `fetch`-style docs server for AT docs lookups during dev (dev only, not enabled for the headless agent).

### Evidence (`.kiro/evidence/`, not a Kiro-defined folder)
- `headless-run-<id>.jsonl` : stream-json transcripts of real runs (clinic, farmer-prices, adversarial spec)
- `README.md` : command line used, kiro-cli version, date, exit code, whether cached.

## 2. Headless invocation (what is verified)
`kiro-cli chat --no-interactive --v3 --agent ussd-annotator --trust-tools=<minimal> --output-format stream-json --require-mcp-startup "<instruction>"` with `KIRO_API_KEY` set. Verified from docs today: `--no-interactive`, positional/stdin instruction, `--agent`, `--trust-tools`/`--trust-all-tools`, `--output-format stream-json`, `--require-mcp-startup` exit 3, agent-missing exit 4, `--sandbox`, `--v2/--v3`. API-key auth only for Pro/Pro+/Pro Max/Power: hackathon credits may not unlock it (U1). Not claimed: that Crew or cloud mode is used.

## 3. Usage story for the write-up
Specs drove the compiler's requirements and its 13 properties (count from TESTING.md); steering held carrier rules so every IDE session and every headless run obeyed the same constraints; hooks re-ran PBT and re-verified specs on change; the custom agent is a runtime step of the compile pipeline, not a dev-only helper; MCP gives the agent the real validator; PBT checks the compiler that the agent feeds. Include honest notes: what Kiro could not do, fallback behaviour, cached vs fresh runs.

## 4. Day-1 Kiro checklist
Install kiro-cli; confirm login in Nigeria (U3); create API key if the plan permits (U1); run headless hello in the worker Dockerfile (U2); submit credits form; commit empty `.kiro/` tree with steering first so every later commit shows steering use.
