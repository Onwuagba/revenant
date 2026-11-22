# Kiro evidence

This file records what was actually run. Nothing here is claimed beyond that.

## Real Kiro runs
**One attempt, which did not produce annotations.** On 2026-11-15, `kiro-cli` 3.3.0 (logged in via Google) was installed and
`scripts/kiro_smoke.sh` ran the real headless command on the clinic draft. After fixing agent discovery (the run dir now carries
a copy of `.kiro/agents/ussd-annotator`), the run started and the agent loaded, then failed on the account:
`UsageLimitReachedError: You've reached your monthly usage limit` (exit 1). The pipeline fell back to the deterministic annotator
and recorded the reason. The transcript is in `.kiro/evidence/smoke-20261115T172131Z/`. No annotations came from Kiro, so there is
no evidence yet of Kiro's output quality. A first attempt before the fix failed with exit 4 (agent not found in the run dir).

**Superseded below by the 2026-11-16 successful run.** (Earlier note, kept for history:) No `kiro-cli` binary or `KIRO_API_KEY` was available in the environment where the pipeline was built.
`scripts/kiro_smoke.sh` runs the real headless command and writes its transcript to `.kiro/evidence/`; it skips
cleanly without a key. Until it has run, `.kiro/evidence/` contains no transcript and no real-run claim should be made.

## Real Kiro run that succeeded (2026-11-16)
`scripts/kiro_smoke.sh` on the clinic draft, `kiro-cli` 3.3.0 logged in via Google (no API key): exit 0, fresh (not cached), 30.9 s,
annotator `kiro-cli`. The transcript shows Kiro reading the run-dir files, writing `annotations.json`, and calling
`@revenant-validator/validate_draft` once. Its labels were schema-valid; after merge the operation set was unchanged and V1-V8 passed.
Transcript: `.kiro/evidence/smoke-20261116T072917Z/`. Limits: one run, one spec. The stream did not report a model id.
### Runs 2 and 3 (2026-11-16)
Farmer-prices (MCP tools): exit 0, 17.2 s, fresh; one tool compiled (`get_crop_price`), `search_market` was refused with `R_FREE_TEXT` before Kiro ran. Annotations schema-valid, V1-V8 passed.
Adversarial: injection text (an instruction to add `evil_op`) was placed in an enum value, the path and the title of the draft. Exit 0, 18.8 s, fresh. Kiro wrote labels only; `evil_op` is absent from the annotations and the operation set is unchanged. An earlier variant with injection only in descriptions is weaker, because descriptions never reach the agent (titles are cut to 24 chars).
Limits: one run each, no model id in the stream. Merge cannot add operations regardless of what Kiro writes, so this shows Kiro did not try, not that it could not.
## Run 4: fresh headless run after the deploy work (2026-11-22)
`scripts/kiro_smoke.sh` on the clinic draft with `KIRO_REQUIRE_MCP_STARTUP_TIMEOUT_SECS=120`: exit 0, fresh (not cached),
annotator `kiro-cli`, 115.6 s, no repair attempts. Result: `.kiro/evidence/smoke-20261122T122007Z/result.json`.
Limit worth knowing: earlier the same day two other attempts failed at start-up because the validator MCP server
(`revenant-validator`) did not connect within Kiro's 30 s then 60 s wait, on a machine that was busy with a Docker build.
The server itself answers `initialize` in about 5 s when run alone, so the cause is slow start-up under load, not a broken
server. The compile stage falls back to the deterministic annotator (and says so) if Kiro does not start. The compile
stage does not pass `KIRO_REQUIRE_MCP_STARTUP_TIMEOUT_SECS` through, so on a slow host a fresh Kiro run may fall back.

## Agent permission rules: denied-action test (2026-11-22)
`scripts/kiro_denied_action.py` runs the real `kiro-cli` with the `ussd-annotator` agent and asks it to write a file other
than `annotations.json` and to run a shell command. Two runs, both kept:
1. Plain request (`denied-action-20261122T122219Z/`): the agent **declined on its own** (its prompt says to write only
   `annotations.json`, and it has no shell tool). It made no forbidden call, so this run does **not** exercise the
   permission rule. It wrote `annotations.json`, which is allowed. No forbidden file or shell output was created.
2. Forced request (`denied-action-forced-20261122T122403Z/`): the instruction told the agent to attempt one write to
   `forbidden.txt`. The write tool call **failed** with: `Blocked by a permission rule (deny fs_write matching "*"); the
   user did not reject it. Source: agent-profile.` No file was created. This is the rule in
   `.kiro/agents/ussd-annotator.json` doing its job. Excerpt: `denied-action-forced-20261122T122403Z/excerpt.json`.
Limits: one run each, `fs_write` deny only. The shell deny was not exercised (the agent has no shell tool, so there was
nothing to block). Raw transcripts are git-ignored; the excerpts have local paths removed.

## Tested with a fake `kiro-cli`
`tests/unit/test_annotate.py` puts a stub `kiro-cli` script on the path to test our side of the contract:
exact flags (no `--trust-all-tools`), constant instruction with no spec text, exit codes 1/3/4, timeout,
invalid JSON, schema violation, missing output, cache hit (`annotator = cached`), the bounded repair loop, and an
adversarial spec whose operation set stays unchanged. These tests prove our fallback and gating behave as designed.
They are **not** evidence that Kiro itself behaves well.

## How the project was built
The `.kiro/` specs, steering, hooks and agents are committed. Which tool did what, per the commit history and the
build log at the end of this file:
- Specs 4 and 5, the platform API and the console were written outside the Kiro IDE, with an AI coding assistant in the terminal (15 Nov).
- Kiro headless (`kiro-cli`) ran the compile-time annotation stage for real on 16 Nov (3 runs) and 22 Nov (1 fresh run, see below).
- Task 17 of runtime-sms (stateful key-press property test) was written by the Kiro IDE agent through "Start task"
  on 21 Nov (commit message records this).
- All 81 tasks across the 6 specs are now ticked. Tasks 12 and 13 of kiro-compile-step were ticked by hand (AI coding assistant)
  against the 16 Nov evidence, not by Kiro.
- Two 21 Nov commits do not record which tool made them (the runtime-sms `tasks.md` reformat and the lint/typing
  "Step 3" commit); they are listed as "not recorded" in the build log rather than guessed.
- Deploy files (Dockerfile, `render.yaml`, console served by the API) and the evidence scripts were written with an AI coding assistant in the terminal (22 Nov).
Hooks: the Kiro IDE log shows all 4 hook files load (`v2 hooks loaded 4 standalone hooks from .kiro/hooks/`), so the file
format and trigger names are accepted. On 22 Nov the IDE log recorded one hook invocation after a Kiro agent edit (see "Hook firing" below).
On 14 Nov the same log shows `hooks.v2.executionDisabledUntrustedWorkspace` (hooks do not run in an untrusted workspace).

## Still to do
1. ~~Clinic smoke run~~ done 2026-11-16 and again 2026-11-22 (see above). farmer-prices and adversarial runs done 2026-11-16.
2. ~~Adversarial spec through the real path~~ done (see Runs 2 and 3).
3. ~~Agent permission rules with a deliberate denied-action test~~ done for `fs_write` (see above). Shell deny not exercised.
4. ~~Confirm that a hook actually fires in the Kiro IDE~~ observed 2026-11-22 (see "Hook firing" below). Still open:
   observe the other three hooks.

## Hook firing (2026-11-22)
In a trusted workspace, the Kiro IDE agent (chat, Autopilot) edited the docstring of
`backend/src/revenant/compiler/gsm7.py` at 20:41:52. That path matches the `pbt-on-compiler-save` matcher. The IDE
log records `ContextualHookInvoked` at 20:42:32, 40 s later, and the hook result was returned to the agent. The log
does not name the hook. The Kiro chat names it: the screenshot `hook-firing-20261122/kiro-chat.png` shows the
agent's `gsm7.py` diff followed by a "Run Command Hook: pbt-on-compiler-save" card.
Neither the log nor the chat shows the hook's pytest output for that first run.

Second run, 21:08:22 WAT: the hook command was temporarily changed to append a timestamp and its pytest output to
a log file (now `runs/hook-debug.log`, git-ignored), and a second agent docstring edit to `gsm7.py` triggered it. The hook's own output reads
`32 passed, 340 deselected in 45.26s` (Python 3.12.12, pytest 9.2.0, Hypothesis 6.170.15, `dev` profile). Copy with
the local path removed: `hook-firing-20261122/hook-output-2108.log`. One run; this shows the hook runs the suite and
reports the result back to the agent, not that it catches regressions.
Before this run the hook command was changed from bare `pytest` (it resolved to a system Python that cannot import
`revenant`) to `.venv/bin/python -m pytest -m pbt --hypothesis-profile=dev -x`. Run by hand, that command gave
32 passed, 340 deselected in 34.78 s. Excerpt: `.kiro/evidence/hook-firing-20261122/ide-log-excerpt.txt`.

## Build log
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
| 2026-11-22 | Hook test: docstring edit to `compiler/gsm7.py` fired `pbt-on-compiler-save` | Kiro IDE agent (chat, Autopilot) | `.kiro/evidence/hook-firing-20261122/ide-log-excerpt.txt`, `kiro-chat.png` | Hook command fixed first to use `.venv` (by hand, AI coding assistant); Kiro chat shows "Run Command Hook: pbt-on-compiler-save" (`kiro-chat.png`); second run at 21:08 logged its output: 32 passed (`hook-output-2108.log`) |

Write-up checklist: which specs were run in Kiro; which hooks really fired; which headless runs were real vs cached vs fallback; what Kiro could not do; what you wrote by hand.
