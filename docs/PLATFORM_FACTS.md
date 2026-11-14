# Platform facts: verified vs UNVERIFIED (checked 2026-11-14)

Rule: anything in other docs that depends on a row marked UNVERIFIED is a design assumption, configurable, and has a test or a go/no-go gate.

## Verified (source read today)

| Fact | Source | Design consequence |
|---|---|---|
| Kiro CLI headless: `kiro-cli chat --no-interactive "<instruction>"` (instruction positional or stdin, not both, non-empty). | kiro.dev/docs/cli/headless | Compile stage shells out to this. |
| Auth in headless: `KIRO_API_KEY` env var. API-key auth is available only to Kiro Pro, Pro+, Pro Max and Power subscribers. | same | **Hackathon credits may not enable API keys: see UNVERIFIED U1.** |
| Tool approval is pre-authorised: `--trust-all-tools` or `--trust-tools=<ids>` (supports `@server`, `@builtin`, globs in CLI >= 3.3.0). No mid-run user input. | same | Use `--trust-tools` with a minimal list, never `--trust-all-tools`. |
| `--output-format stream-json` (V2/V3) emits JSON Lines; `--agent <name>` selects agent (exit code 4 if unavailable); `--model`, `--effort`, `--sandbox`, `--require-mcp-startup` (exit 3 if MCP fails), `--v2/--v3` pick harness. | same | Pass `--v3` explicitly; store the JSONL as evidence; parse exit codes. |
| Custom agents are JSON in `.kiro/agents/`; fields incl. `name`, `description`, `prompt` (`file://`), `tools`, `mcpServers`, `resources`, `hooks`, `permissions`. `allowedTools`/`toolsSettings` are CLI 2.x legacy, ignored by V3. | kiro.dev/docs/custom-agents/configuration-reference | Use `permissions.rules`, not `allowedTools`. |
| Kiro Free tier is 50 credits/month; Pro is 1,000 credits. | search results (kiro.dev pricing/blog snippets, secondary) | Budget Kiro runs; cache by spec hash. |
| USSD screen limit is 182 characters (GSM 02.90 lineage); Clickatell recommends staying within 160 because operators differ. | Clickatell FAQ via search; ETSI 02.90 | Default max 182 measured on the full response string incl. `CON `/`END ` prefix (conservative); `conservative` profile = 160. |
| Kenyan telco session durations (via Africa's Talking help centre): Safaricom 180 s total, 30 s customer response; Equitel same; Airtel 180 s total, 60 s customer response, 15 s application response, 10 s USSD-to-application connection. | help.africastalking.com article 1284071 | Per-screen think-time design target 30 s; upstream deadline 3 s (our budget, not a platform fact); session step cap default 8. |
| AT callback: POST form-encoded `sessionId, serviceCode, phoneNumber, text` (+ `networkCode`); `text` is cumulative, `*`-separated, empty on first request; reply `text/plain` starting `CON ` or `END `. | third-party summaries (several, consistent) | Runtime parses these; replay-from-text design. |
| AT sandbox: channel code, public callback URL required (tunnel needed), browser simulator, max 2 USSD channels in sandbox, production needs a dedicated service code from AT. | third-party summary (AI-ML-Community skills file), tutorials | Two sandbox channels = exactly our two apps. Do not deploy a third. |

## UNVERIFIED (could not confirm from an official page)

| # | Item | Plan |
|---|---|---|
| U1 | Whether Kiroween's one-time 4,000 credits (or a free account) allow generating `KIRO_API_KEY` for headless. Docs say paid-plan only. | Day 1 go/no-go (see MILESTONES). Plan B: run headless locally with an interactive login, commit stream-json transcripts, hosted site serves cached results keyed by spec hash and labels them as cached. |
| U2 | `kiro-cli` installs and runs in a Linux container without a browser login (docs imply CI/CD support). | Test on Day 1 in the worker Dockerfile. |
| U3 | Kiro works from Nigeria (RISK_REGISTER #5). | Day 1 check. |
| U4 | Official AT docs for callback params, 182-char handling by AT (does AT truncate/reject?), any AT retry behaviour on callback failure, callback signing or source IPs. developers.africastalking.com returned HTTP 403 to the fetch tool. | Verify in a browser Day 1. Meanwhile: idempotent callbacks, secret path token, count prefix toward 182. |
| U5 | Whether AT sandbox SMS can reach a real handset (believed to be simulator-only), and Nigerian sender-ID / live SMS onboarding lead time. | Email AT support Day 1. Plan B: SMS to real handset via own GSM modem or Android SMS gateway behind the same `SmsProvider` interface. |
| U6 | Whether AT can lease a Nigerian (or Kenyan) shortcode before 3 Dec so USSD itself runs on a real handset. Likely no. | Ask Day 1; plan assumes no. Video shows SMS on handset + USSD in AT simulator and in our emulator, each labelled. |
| U7 | AT sandbox simulator behaviour with non-GSM-7 characters and whether the 182 limit is enforced in the simulator. | Test with a probe screen Day 1; record result in DECISIONS (ADR-009). |
| U8 | Carrier handling of UCS-2 (e.g. Yoruba/Hausa diacritics) in USSD. | Default: GSM-7 only, transliterate. |
| U9 | Kiro IDE spec "correctness properties" to PBT generation exact UX; hook file schema (`.kiro/hooks/*.kiro.hook`). | Create hooks via the IDE hook UI and commit what it writes; do not hand-author schema. |
| U10 | Kiroween category rule text for Resurrection vs Skeleton Crew (only compliance summary read). | Re-read rules in Chrome before 1 Dec. |
| U11 | Competitor feature claims (BlueKai, Buni AI, USSDly, Telerivet, RapidPro) beyond the selection PDF. | PRD marks them "per selection doc"; do not add claims. |
