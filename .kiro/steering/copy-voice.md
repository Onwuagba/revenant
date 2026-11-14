---
inclusion: manual
---
# Copy and voice (use with #copy-voice)

## USSD labels (hard limits come from ussd-carrier-rules)
- Short, verb first: "Book visit", "Check price", "Send money". Menu labels <= 20 chars.
- Plain words. No jargon, no brand puns on the handset. No emoji, no curly quotes.
- Confirmation text states the thing and the amount/target: "Pay 500 to Ada? 1 Yes 2 No".
- Errors are short and non-blaming: "Not valid. Try again." Never expose internals.

## Transliteration table (GSM-7 safe, local-language safe; extend only with verified mappings)
| From | To |
|---|---|
| a with acute/grave/circumflex/tilde/dot | a |
| e with acute/grave/circumflex/dot below | e |
| o with acute/grave/circumflex/dot below | o |
| u with acute/grave | u |
| s with dot below / sh digraph forms | s |
| n with tilde/acute | n |
| curly quotes | straight ' or " (use ' only) |
| en/em dash | - |
| ellipsis | ... (3 chars, count them) |
Hausa hooked letters and Yoruba tonal marks: transliterate to the base letter; if meaning becomes ambiguous, refuse with `R_NON_GSM7` rather than guess. Native-speaker review of any real local-language copy is required (cut-list item).

## The Crypt voice (console copy only, never on the handset)
Dry, calm, slightly gothic, never jokey about failure. Examples: "Exhume: reading your spec." "Buried: nested object at /body/address". "Last Rites: 7 of 7 validators passed." Status is never colour alone: always icon + text. Do not claim more than the data shows.
