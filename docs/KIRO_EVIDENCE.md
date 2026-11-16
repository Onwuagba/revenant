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
## Tested with a fake `kiro-cli`
`tests/unit/test_annotate.py` puts a stub `kiro-cli` script on the path to test our side of the contract:
exact flags (no `--trust-all-tools`), constant instruction with no spec text, exit codes 1/3/4, timeout,
invalid JSON, schema violation, missing output, cache hit (`annotator = cached`), the bounded repair loop, and an
adversarial spec whose operation set stays unchanged. These tests prove our fallback and gating behave as designed.
They are **not** evidence that Kiro itself behaves well.

## How the project was built
The `.kiro/` specs, steering, hooks and agents are committed. The implementation of specs 4-6 and the platform API
was written outside the Kiro IDE (see the build log in `KIRO_START_HERE.md`, section 9). Hooks have not been confirmed
to fire in the IDE.

## Still to do with a key
1. ~~Clinic smoke run~~ done 2026-11-16 (see above). farmer-prices and adversarial runs done the same day.
2. ~~Adversarial spec through the real path~~ done (see Runs 2 and 3).
3. Confirm hook triggers and the agent permission rules with a deliberate denied-action test.
