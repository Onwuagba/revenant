# Start here: building Revenant in Kiro

Written for someone who has not used Kiro before. Follow the steps in order. Every step ends with a check; do not move on until it passes.

## 0. How to use this guide
The hackathon scores how well Kiro is used. Run the specs in this folder in Kiro, task by task, and keep the build log in section 9 up to date.

## 1. What is in `.kiro/`
- `steering/` - 8 rule files Kiro reads automatically (honest claims, supported types, 182-char screens, no LLM at runtime, PIN rules).
- `specs/` - 6 specs, each with `requirements.md`, `design.md`, `tasks.md`.
- `hooks/` - 4 automation hooks (JSON).
- `agents/` - 2 custom agents (`ussd-annotator` for the headless compile step, `compiler-reviewer` for dev reviews) plus their prompts.
- `settings/mcp.json` - the `revenant-validator` MCP server.
- `evidence/README.md` - table to fill with real Kiro run records.

Do NOT add `.kiro` to any `.gitignore`. The judges need to see it.

## 2. Open the project
1. Install and open the Kiro IDE (kiro.dev). Sign in.
2. File > Open Folder > choose the `revenant` folder (the one containing this file and `.kiro/`).
3. Check: open the Kiro panel (ghost icon). Under Steering you should see 8 files. If not, you opened the wrong folder.
4. Also install Python 3.12 and run `git init` in the folder if it is not a repo yet. Commit now (`git add -A && git commit -m "Add .kiro config"`) so the first commit shows steering.

## 3. Check steering is working
1. In a Kiro chat, ask: "What is the maximum screen length and what does it include?"
2. Check: the answer says 182 characters including the `CON `/`END ` prefix. If it does not, steering is not loaded: re-open the folder.

## 4. Run the specs in this order
Open each spec (Kiro panel > Specs > the spec name). The files already exist, so do NOT click "create new spec". Read `requirements.md` and `design.md` once; they are the contract. Open `tasks.md` and click **Start task** next to ONE task at a time. Do not use "Run all tasks": the tasks are written to be reviewed one by one.

| Order | Spec | What it produces | Check after finishing it |
|---|---|---|---|
| 1 | `ir-type-subset` | IR models, classifier, 12 refusal codes, P7 and P13 stub | `pytest tests/unit tests/pbt -q` passes; `pytest -m pbt --hypothesis-profile=dev` passes; the printed seed is noted |
| 2 | `ingestion` (tasks 1-7 now, 8-10 on 22 Nov) | URL guard, safe parsing, OpenAPI ingest, clinic and unsupported example specs | Unsupported demo spec lists nested/date-time/free-text refusals; no test opens a network socket for remote refs |
| 3 | `state-machine-validators` | planner, renderer, gsm7, validators V1-V8, mutation tests, P1-P6, P10 | Every mutation is flagged by exactly one validator; run the `ci` profile and write down the real counts |
| 4 | `runtime-sms` | callback route, replay, dedupe, PIN safety, SMS outbox | Canary PIN test green; duplicate callback causes one upstream call; integration suite passes with LLM env vars unset |
| 5 | `kiro-compile-step` | annotation schema, fallback, validator MCP, headless runner | Failure-injection tests pass; compile works with no Kiro key (deterministic fallback) |
| 6 | `console-emulator` | React console and emulator | `npm run build` passes; emulator books a clinic appointment; screen shows "simulated handset" |

Rules while running tasks:
- After each task: read the diff, run the tests the task names, commit with a message naming the task.
- If a test fails, ask Kiro to fix the code. Never let it loosen a validator or property to get green.
- If Kiro proposes something outside the supported subset or adds an unlisted refusal code, say no (steering covers this).
- Tasks marked KEY need a Kiro API key. Skip them if you have none, and note it in section 9.

## 5. Hooks
The hook files use the documented JSON shape but have not been confirmed in the IDE (see section 8).
1. Open the Kiro panel > Agent Hooks. Check the 4 hooks are listed: `pbt-on-compiler-save`, `verify-on-spec-change`, `pin-leak-guard`, `docs-drift`.
2. If any is missing or shows an error, create it through the IDE hook UI instead, with the same trigger, file pattern and command, then commit what the IDE writes.
3. Per Kiro docs, file-event hooks may fire only for changes made by the agent, not for your own manual saves. To test: ask Kiro to make a small edit under `backend/src/revenant/compiler/`.
4. Check: the PBT hook runs. Paste a short log excerpt into `.kiro/evidence/README.md` and later `docs/KIRO_EVIDENCE.md`.
5. `verify-on-spec-change` and the CLI commands need `revenant verify` to exist (spec `state-machine-validators` / `kiro-compile-step`); before that the hook will fail. Set `"enabled": false` on that hook until then.

## 6. Custom agents and MCP (needed from spec 5)
1. MCP: Kiro panel > MCP Servers. `revenant-validator` should be listed. It only starts working after the `kiro-compile-step` task 5 creates `python -m revenant.mcp_validator`. Until then it will show an error; that is expected.
2. Agents are used by `kiro-cli` (the terminal tool): install it, run `kiro-cli login` (or set `KIRO_API_KEY` in your shell, never in a file), then from the repo root check the agent exists with `kiro-cli agent list` (command name from CLI docs; verify with `kiro-cli --help` if it differs).
3. Day-1 gates (from `docs/PLATFORM_FACTS.md`): can you log in from Nigeria, can headless run in the worker container, does your plan allow an API key (docs say paid plans only). If headless is not possible, tell the write-up the truth: local runs, cached results, labelled as cached.
4. After spec 5 task 12/13: save each real transcript in `.kiro/evidence/` and fill the table there.

## 7. Before you submit
- `git status` shows `.kiro/` tracked. `git check-ignore .kiro` prints nothing.
- Secret scan clean; only `.env.example` with empty values committed.
- Fill `docs/KIRO_EVIDENCE.md` (create it then) from `.kiro/evidence/`.
- Section 9 is complete and matches the git history.

## 8. What is verified and what is not
Checked on kiro.dev on 2026-11-14:
- Steering: `.kiro/steering/*.md`, YAML front matter, modes `always`, `fileMatch` (`fileMatchPattern` string or array), `manual`, `auto` (needs `name` and `description`). Custom agents do not auto-load steering, so the agent files list steering in `resources`.
- Spec folder `.kiro/specs/<name>/` with `requirements.md`, `design.md`, `tasks.md`; EARS wording "WHEN ... THE SYSTEM SHALL ...".
- Hooks: JSON files in `.kiro/hooks/` with `version: "v1"` and a `hooks` array (`name`, `trigger`, `matcher`, `action.type` of `command` or `agent`, `timeout`, `enabled`).
- Custom agents: JSON in `.kiro/agents/` with `name`, `description`, `prompt` (`file://`, relative to the agent file), `tools`, `mcpServers`, `resources`, `includeMcpJson`, and `permissions.rules` entries of `capability`, `match`, `effect`, optional `exclude`.
- MCP: workspace `.kiro/settings/mcp.json`, `mcpServers` map with `command`, `args`, `env`, `disabled`, `autoApprove`.

NOT verified (use with care):
1. **Hook trigger spelling.** The schema example shows `PostFileSave`; the trigger table shows display names like `File Save`. I used `PostFileSave`. If the IDE rejects it, recreate via the hook UI. The `matcher` for file triggers is a regex per the schema page, but its exact semantics are not documented.
2. **IDE hook file format.** Older IDE builds may write `.kiro.hook` files instead (noted in `docs/PLATFORM_FACTS.md` U9). Prefer whatever the IDE writes and commit that.
3. **`tasks.md` checkbox syntax.** The docs do not show it. I used the usual `- [ ] 1. Title` with sub-bullets and `_Requirements: x.y_` references, and `- [ ]*` for the optional task. Kiro may normalise this on first open.
4. **Correctness-properties format in `design.md`.** Docs describe properties and PBT tasks only at a high level. Properties are listed as a verbatim table; the IDE spec-to-PBT UX is unverified (U9). Tell Kiro "turn these properties into Hypothesis tests" in the relevant task if it does not offer it itself.
5. **Agent permission details.** The capability names `fs_read`, `fs_write`, `shell`, `mcp` and the `server/tool` match form are from docs examples, but I did not confirm the `fs_write` match is relative to the run directory, nor a `web` capability. Web is excluded by omitting `web` from `tools`. Confirm with a deliberate denied-action test on Day 1.
6. **Agent `resources` path.** `ussd-annotator` loads `.kiro/steering/ussd-carrier-rules.md`, resolved from where the CLI is started. The worker runs in `runs/<id>/`, which also holds a copy as `carrier-rules.md` that the prompt reads. If the resource path fails to resolve there, remove the entry and rely on the copy.
7. `kiro-cli` agent-list command name, `--trust-tools` ids for write limited to the run dir (ARCHITECTURE section 4: confirm Day 1), and whether hackathon credits unlock `KIRO_API_KEY` (U1).
8. The `pin-leak-guard` grep is a coarse heuristic that can miss leaks and false-positive; the canary-PIN test is the real control. The `docs/KIRO_EVIDENCE.md` file is not created yet.

## 9. Build log (fill in as you go)
| Date | Work item | Tool (Kiro IDE spec task / Kiro chat / kiro-cli headless / by hand) | Evidence (commit, transcript, screenshot) | Notes (what needed fixing by hand) |
|---|---|---|---|---|
| 2026-11-15 | Spec 4 runtime-sms: service, store, worker, actions, clinic mock, Alembic | By hand (an AI coding assistant in the terminal, not the Kiro IDE) | commits `Spec 4 ...` | Planner/runtime gaps found: no wildcard input, unreachable menu options 2-5 (fixed) |
| 2026-11-15 | Spec 5 kiro-compile-step: schema, merge, deterministic annotator, validator MCP, headless runner, cache, repair | By hand (an AI coding assistant in the terminal, not the Kiro IDE) | commit `Spec 5 ...`; fake-kiro tests only | No real Kiro run: no kiro-cli/key available. Tasks 12-13 (KEY) not done |
| 2026-11-15 | Platform API, console, emulator, CLI, deploy files | By hand (an AI coding assistant in the terminal, not the Kiro IDE) | commits; Playwright smoke 7/7 | Hooks not confirmed in IDE |
| 2026-11-16 | Real headless runs: clinic smoke, farmer-prices, adversarial injection | kiro-cli headless | `.kiro/evidence/smoke-20261116T072917Z/`, `farmer-prices-*`, `adversarial2-*` (result.json) | See `docs/KIRO_EVIDENCE.md`; no model id in the stream |
| 2026-11-21 | Ticked kiro-compile-step tasks 12 and 13 against the 16 Nov evidence | By hand (an AI coding assistant in the terminal, not the Kiro IDE) | commit `Tick kiro-compile-step tasks 12 and 13 ...` | Ticked only after checking the evidence folders |
| 2026-11-21 | runtime-sms `tasks.md` reformatted to Kiro spec format | Not recorded (the commit does not say which tool) | commit `Reformat runtime-sms tasks.md ...` | Confirm before the write-up |
| 2026-11-21 | Task 17 runtime-sms: stateful key-press property test | Kiro IDE spec task ("Start task") | commit `Task 17 (runtime-sms) ...` (message says written by the Kiro IDE agent) | |
| 2026-11-21 | "Step 3": lint, strict typing, live MCP ingest, verification on generated folders, regression tests | Not recorded (the commit does not say which tool) | commit `Step 3: fix lint ...` | Confirm before the write-up |
| 2026-11-22 | Deploy: Dockerfile builds console + API, API serves the console, `render.yaml`, tests (5 new) | By hand (an AI coding assistant in the terminal, not the Kiro IDE) | `Dockerfile`, `render.yaml`, `tests/integration/test_console_serving.py`; image built and 7/7 Playwright passed against it | Found and fixed a bug that would have blanked the console (assets were blocked) |
| 2026-11-22 | Fresh headless run + agent permission denied-action tests | kiro-cli headless | `.kiro/evidence/smoke-20261122T122007Z/`, `denied-action-*` (result.json, excerpt.json) | MCP start-up was too slow under load on two attempts; the forced write was blocked by the `fs_write` deny rule |

Write-up checklist: which specs were run in Kiro; which hooks really fired; which headless runs were real vs cached vs fallback; what Kiro could not do; what you wrote by hand.
