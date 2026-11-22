# IR and supported type subset

## 1. Pipeline artefacts
`source (OpenAPI|MCP)` -> **Ingest** -> `ir.draft.json` + `refusals.json` -> **Annotate** (Kiro headless or deterministic) -> `annotations.json` -> **Merge** -> `ir.json` -> **Plan** -> `machine.json` (states, transitions) -> **Render** -> `screens.json` -> **Validate** -> `report.json` -> **Emit** -> `bundle.json` (+ generated app folder).

All artefacts are canonical JSON (sorted keys, stable ordering by operation id) so `bundle_hash` is deterministic (PBT P6).

## 2. IR (semantic, source-independent)
```
App        { slug, title, locale, carrier_profile{max_chars,max_steps,sms_segments,charset}, operations[], flows[] }
Operation  { id, source_ref, kind: read|write, title(<=24ch), params[], result, async: bool, risk: low|money|identity }
Param      { name, label(<=20ch), type, required, constraints{enum,min,max,max_len,pattern}, secret: none|pin,
             options_from?: {op_id, value_path, label_path}, default_from?: caller_msisdn }
Result     { shape: scalar|record|list|text, fields[{path,label,max_len}], template, sms_template }
Flow       { id, title, entry_op, steps[param names in order], confirm: bool }
Refusal    { op_id, path, code, message, hint }
```
OpenAPI maps: `operationId` -> Operation; path/query/header/body scalar params -> Param; `GET` -> read, others -> write (override by annotation). MCP maps: tool -> Operation; `inputSchema` -> Params; `outputSchema` if present -> Result, else `shape: text` (SMS path). `annotations.readOnlyHint`/`destructiveHint` (MCP tool annotations, when present) seed `kind`/`risk`; treat as untrusted hints.

## 3. Supported type subset (v1)
| Input type | Handling | Screen |
|---|---|---|
| `boolean` | yes/no | `1 Yes 2 No` |
| `string` + `enum` (<=36 values) | paginated menu, 5 per page, `8 More`, `0 Back` | menu |
| `integer`/`number` with `minimum`+`maximum` (<=9 digits) | numeric entry, range-checked | prompt with range |
| `string` with `pattern` or `maxLength<=20` and charset `[A-Za-z0-9 -]` | typed token (ids, codes) | prompt |
| `string` format `phone` or annotated `default_from: caller_msisdn` | prefilled from session MSISDN, confirm only | confirm |
| `string` format `date` + annotation `x-revenant-date-window: N` (N<=7) | day picker from "today + 0..N-1" | menu |
| secret `x-revenant-secret: pin` (4-6 digits) | masked-by-protocol: never echoed; last input before action | prompt |
| dynamic choice `x-revenant-options-from` (list op returning flat records) | options fetched at runtime, cached, paginated | menu |
| flat object (one level, <=6 scalar props) | flattened into sequential prompts | prompts |
| required params per flow | <=5 (step cap 8 includes menu, confirm, PIN) | |

| Output shape | Handling |
|---|---|
| scalar / flat record | one `label: value` line per field; each field needs a bound (`maxLength`, `enum`, number, boolean or a fixed-width format); fits -> `END`; else SMS |
| list of flat records | needs `maxItems` and bounded fields; whole list on one screen if it fits, else the whole list by SMS (no on-screen paging in v1) |
| MCP text content / scalar | short -> screen; long -> SMS, cut to the segment budget with a trailing `...` (the only lossy path) |
| 202 / `async` / upstream > deadline | `END` "We will SMS you" + job |

Result sizing is checked by V7 at compile time with the same formatter the runtime uses: the worst case (every field full, `maxItems` rows, two-septet characters) must fit `carrier_profile.sms_segments`. A list without `maxItems` or a field without a bound is a V7 violation (no refusal code fits it, so none is added). At runtime an upstream that returns more than `maxItems` rows is cut to `maxItems` and a warning is logged.

## 4. Refusal codes (always reported, never silently dropped)
| Code | Trigger |
|---|---|
| `R_NESTED_OBJECT` | object inside object, or array of objects as input |
| `R_POLYMORPHIC` | `oneOf`/`anyOf`/`allOf` with differing shapes, `discriminator` |
| `R_FREE_TEXT` | string without enum/pattern/`maxLength<=20` and no `x-revenant-interpret` |
| `R_DATETIME` | `date-time`, `time`, `duration`, or `date` without window annotation |
| `R_UNBOUNDED_NUMBER` | number/integer without min and max |
| `R_TOO_MANY_PARAMS` | would exceed step cap |
| `R_BINARY` | `format: binary/byte`, multipart |
| `R_AUTH_SCHEME` | per-user OAuth/OIDC flows (only server-held API key or bearer supported) |
| `R_CALLBACK` | webhooks/callbacks/streaming |
| `R_NON_GSM7` | label/enum values that cannot be transliterated to GSM-7 |
| `R_REF_UNRESOLVED` | remote `$ref` blocked (SSRF policy) or missing |
| `R_RECURSIVE` | cyclic schema |

A refused operation is excluded from the bundle; its menu entry is not generated. The report shows count compiled vs refused. If every operation is refused the compile fails with exit code 2.

## 5. Annotation layer (light, optional)
`x-revenant-*` vendor extensions in OpenAPI; for MCP, a sidecar `revenant.yaml` keyed by tool name (MCP schemas have no extension slot we can rely on). Supported keys: `label`, `secret`, `date-window`, `options-from`, `interpret`, `risk`, `hide`, `sms-only`. The Kiro annotator proposes these; a human or the compiler can override. Only these keys are accepted from the annotator (JSON Schema, `additionalProperties: false`).

## 6. State machine (bundle)
State kinds: `MENU`, `INPUT`, `CONFIRM`, `PIN`, `ACTION` (internal, no screen), `RESULT_END`, `RESULT_CON` (result with `0 Back`), `SMS_END`, `ERROR_END`.
Global keys: `0` back, `00` home (root), `*`-less (the `*` is AT's separator and never appears in input; inputs containing `*` or `#` are invalid). Menus number items 1-9; item 8 is `More` only on paginated menus.
Retry: 3 invalid inputs on one state -> `ERROR_END`.
Screen record: `{state_id, kind, template, slots[{name,max_len}], static_len, worst_case_len, transitions{key->state}}`; `worst_case_len = static_len + sum(slot max_len) + prefix(4)` must be <= `max_chars`.

Example (clinic):
```
root MENU -> 1 -> clinic MENU(options_from list_clinics) -> day MENU(date window 5)
 -> slot MENU(options_from list_slots[clinic,day]) -> pin PIN -> ACTION book_appointment
 -> RESULT: record fits? END "Booked KX42 Sat 14:30. SMS sent." : SMS_END
```
Longest path = root, clinic, day, slot, pin = 5 inputs (<= 8).
