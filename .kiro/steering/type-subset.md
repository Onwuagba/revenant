---
inclusion: fileMatch
fileMatchPattern: ["backend/src/revenant/compiler/**", "tests/unit/**", "tests/pbt/**"]
---
# Supported type subset and refusal codes (v1)

Source of truth: `architecture/IR_AND_TYPE_SUBSET.md`. Keep this file in sync with it (the `docs-drift` hook reminds you).

## Supported inputs
| Input | Handling |
|---|---|
| `boolean` | `1 Yes 2 No` |
| `string` + `enum` (<=36 values) | paginated menu, 5 per page, `8 More`, `0 Back` |
| `integer`/`number` with `minimum` AND `maximum` (<=9 digits) | numeric entry, range-checked |
| `string` with `pattern`, or `maxLength<=20` and charset `[A-Za-z0-9 -]` | typed token |
| `string` format `phone` or annotation `default_from: caller_msisdn` | prefilled from session MSISDN, confirm only |
| `string` format `date` + annotation `x-revenant-date-window: N` (N<=7) | day picker, today + 0..N-1 |
| secret `x-revenant-secret: pin` (4-6 digits) | never echoed; last input before action |
| dynamic choice `x-revenant-options-from` (list op returning flat records) | fetched at runtime, cached, paginated |
| flat object (one level, <=6 scalar props) | flattened into sequential prompts |
| required params per flow | <=5 |

Outputs: scalar/flat record -> `label: value` lines, every field bounded (maxLength/enum/number/boolean/fixed format), fits -> END else SMS; list of flat records -> needs `maxItems`, whole list on screen if it fits else by SMS (no on-screen paging in v1); MCP text -> short on screen, long via SMS cut to the segment budget with `...`; 202/async/slow -> END "We will SMS you" + job. V7 checks the worst case against `sms_segments`; an unbounded list or field is a V7 violation, not a new refusal code.

## Refusal codes (always reported, never silently dropped)
`R_NESTED_OBJECT` object in object or array of objects as input | `R_POLYMORPHIC` oneOf/anyOf/allOf with differing shapes, discriminator | `R_FREE_TEXT` string without enum/pattern/maxLength<=20 and no `x-revenant-interpret` | `R_DATETIME` date-time, time, duration, or date without window | `R_UNBOUNDED_NUMBER` number without min and max | `R_TOO_MANY_PARAMS` exceeds step cap | `R_BINARY` binary/byte/multipart | `R_AUTH_SCHEME` per-user OAuth/OIDC | `R_CALLBACK` webhooks/callbacks/streaming | `R_NON_GSM7` cannot transliterate | `R_REF_UNRESOLVED` remote `$ref` blocked or missing | `R_RECURSIVE` cyclic schema.

## Rules
- Do not invent new refusal codes without updating `architecture/IR_AND_TYPE_SUBSET.md` first.
- A refused op is excluded from the bundle: no menu entry, no screen, no transition (P13). If every op is refused, compile fails with exit code 2.
- Annotation keys accepted from the annotator: `label`, `secret`, `date-window`, `options-from`, `interpret`, `risk`, `hide`, `sms-only`. Nothing else.
- Classification is a total function: never raise on odd schemas (P7). Do not execute `pattern` at compile time.
