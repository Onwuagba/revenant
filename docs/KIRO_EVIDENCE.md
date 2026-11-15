# Kiro evidence

This file records what was actually run. Nothing here is claimed beyond that.

## Real Kiro runs
**None yet.** No `kiro-cli` binary or `KIRO_API_KEY` was available in the environment where the pipeline was built.
`scripts/kiro_smoke.sh` runs the real headless command and writes its transcript to `.kiro/evidence/`; it skips
cleanly without a key. Until it has run, `.kiro/evidence/` contains no transcript and no real-run claim should be made.

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
1. `scripts/kiro_smoke.sh` on the clinic draft; commit the transcript and fill `.kiro/evidence/README.md`.
2. Run the adversarial spec through the real path (spec `kiro-compile-step`, task 13).
3. Confirm hook triggers and the agent permission rules with a deliberate denied-action test.
