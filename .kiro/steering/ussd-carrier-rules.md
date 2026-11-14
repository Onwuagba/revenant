---
inclusion: always
---
# USSD carrier rules (also copied to every headless run dir as carrier-rules.md)

Source: `docs/PLATFORM_FACTS.md`, ADR-009, ADR-010, ADR-011. Items marked UNVERIFIED are design assumptions.

## Screen budget
- A screen is at most **182 characters measured on the FULL response string including the `CON ` or `END ` prefix** (4 chars). Body budget is therefore 178.
- Profiles: `standard = 182`, `conservative = 160` (operators differ; AT enforcement UNVERIFIED U4/U7). Always read the limit from `carrier_profile.max_chars`; never hard-code 182 in logic except as the `standard` default.
- `worst_case_len = static_len + sum(slot max_len) + 4` must be <= `max_chars`. Validate with the worst-case slot fill, not a sample.
- Charset: **GSM-7 only**. Transliterate everything else (accents, emoji, curly quotes). A label that cannot be transliterated is refused (`R_NON_GSM7`). No control characters; newlines only where the template places them. UCS-2 is out (UNVERIFIED U8).

## Keys and navigation
- `0` = back, `00` = home (root). Numbered items 1-9. Item `8` is `More` ONLY on paginated menus (5 items per page).
- `*` is the AT separator and `#` ends USSD: inputs containing `*` or `#` are invalid and never appear in labels or values.
- 3 invalid inputs on one state -> `ERROR_END`.
- Session step cap: default **8** inputs including menu, confirm and PIN steps (`max_steps`). Required params per flow <= 5.

## Timing (design targets; carrier facts from PLATFORM_FACTS)
- Safaricom/Equitel: 180 s total session, 30 s customer response. Airtel: 180 s total, 60 s customer, 15 s application, 10 s USSD-to-application connection.
- Our upstream deadline is 3 s (our budget, not a platform fact). Slow, long or async results become `END` "Details sent by SMS" plus an SMS job.

## Writing labels
- Menu labels <= 20 chars, operation titles <= 24 chars. Verb first. No trailing punctuation. No duplicate labels in one menu.
- The runtime adds `CON `/`END `; templates never include them. Sanitise slot values (strip control chars, collapse newlines, truncate to slot budget).

## PIN
- PIN is the LAST input before the action, the response is `END`, and the digits are never rendered. See `security-pin-secrets.md`.

## SMS
- GSM-7; single segment 160 septets, concatenated segments 153 each. Compile-time worst case must fit the segment budget (lossless) or refuse with an `R_...` code.
