---
inclusion: always
---
# Revenant: product and claim rules

Revenant compiles an OpenAPI 3.0/3.1 spec or an MCP server (tools/list over streamable HTTP) into a verified USSD + SMS app for feature phones. It is developer infrastructure: a compiler plus verifier, not an app builder, not a client, not a prompt-to-USSD generator.

## Honest claims (binding on code comments, docs, UI copy, commit messages)
- Say "behavioural evidence", "verified against stated invariants", "checked by validators". NEVER say "proof", "proven", "guaranteed", or "compiles any API".
- The supported subset is small and documented in `architecture/IR_AND_TYPE_SUBSET.md`. Unsupported shapes are REFUSED with a code and reason, never guessed or silently dropped.
- Never state a number (coverage, pass counts, latency, example counts) that a real run did not produce. Report Hypothesis seed and `max_examples` as printed by the run.
- Always say which annotator ran (`kiro-cli`, `deterministic`, or `cached`) and whether the result was cached. Never imply a fresh Kiro run when it was cached or a fallback.
- Anything marked UNVERIFIED in `docs/PLATFORM_FACTS.md` is a configurable assumption, not a fact. Do not turn it into a claim.
- Real-handset: USSD is shown in the Africa's Talking simulator and our emulator, labelled "simulated handset". Do not imply USSD ran on a real handset unless it did.
- Competitor statements are limited to what `docs/PRD.md` section 3 already says ("per selection doc").

## Theme (UI copy only)
Console = "The Crypt". Stages: Exhume (ingest), Reanimate (annotate/compile), Last Rites (validate), Rise (deploy). Refused operations are "Buried". API, code, tests and docs use neutral names: `ingest`, `annotate`, `validate`, `deploy`.

## Category
Primary: Resurrection. Skeleton Crew is a decision for 1 Dec; do not assume either in copy.
