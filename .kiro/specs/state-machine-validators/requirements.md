# Requirements: planner, renderer, validators V1-V8

Source docs: `architecture/IR_AND_TYPE_SUBSET.md` sections 6; `docs/TESTING.md` (P1-P6, P10, validator self-test); `docs/PRD.md` goal 2, 3, US2, US6; ADR-009, ADR-010, ADR-011. Milestone: Wed 18 - Fri 20 Nov. Depends on `ir-type-subset`.

## Requirements

### Requirement 1: Planner
**User Story:** As a developer, I want a navigable state machine derived from the IR, so that no hand-drawn flows are needed.
#### Acceptance Criteria
1. WHEN an IR with compiled operations is planned THE SYSTEM SHALL produce `machine.json` with states of kinds MENU, INPUT, CONFIRM, PIN, ACTION, RESULT_END, RESULT_CON, SMS_END and ERROR_END.
2. THE SYSTEM SHALL create a ROOT menu with at most 7 entries, using the numbered keys 1-9.
3. WHEN a menu has more than 5 items THE SYSTEM SHALL paginate 5 per page with `8 More` and `0 Back`.
4. WHEN an operation is a write THE SYSTEM SHALL insert a CONFIRM state before its ACTION.
5. WHEN an operation has a PIN Param THE SYSTEM SHALL place the PIN state last, immediately before the ACTION, followed only by a terminal state.
6. WHEN the same IR is planned twice THE SYSTEM SHALL produce identical `machine.json`, regardless of operation order.
7. THE SYSTEM SHALL map key `0` to the previous state and `00` to ROOT on every non-root state.
8. WHEN 3 invalid inputs occur on one state THE machine SHALL transition to ERROR_END.

### Requirement 2: Renderer and GSM-7
#### Acceptance Criteria
1. WHEN screens are rendered THE SYSTEM SHALL produce, per screen, `template`, `slots[{name,max_len}]`, `static_len`, `worst_case_len` and `transitions`.
2. THE SYSTEM SHALL compute `worst_case_len = static_len + sum(slot max_len) + 4` and require it to be <= `carrier_profile.max_chars`.
3. THE gsm7 module SHALL transliterate non-GSM-7 characters, report characters it cannot map, and strip control characters.
4. WHEN a slot value is substituted THE SYSTEM SHALL sanitise it (strip control chars, collapse newlines, transliterate, truncate to slot budget) and SHALL NOT allow `CON ` or `END ` to alter the prefix.
5. WHEN a list result exceeds one screen THE SYSTEM SHALL paginate it so every item appears exactly once and each page fits the budget.

### Requirement 3: Validators V1-V8
Each validator returns a machine-readable result `{validator, passed, violations[]}`.
#### Acceptance Criteria
1. V1 reachability: WHEN any state is not reachable from ROOT THE SYSTEM SHALL report a violation naming the state.
2. V2 exit paths: WHEN any state has no path to a terminal state, or invalid-input retries are unbounded, THE SYSTEM SHALL report a violation.
3. V3 back navigation: WHEN `0` from a non-root INPUT or MENU state does not lead to the previous state with earlier params preserved, or `00` does not reach ROOT, THE SYSTEM SHALL report a violation.
4. V4 step limit: WHEN the longest shortest path from ROOT to a terminal exceeds `max_steps` THE SYSTEM SHALL report a violation.
5. V5 length and charset: WHEN any screen's worst case exceeds `max_chars`, contains non-GSM-7 or control characters THE SYSTEM SHALL report a violation with the measured length.
6. V6 PIN safety: WHEN a PIN state is followed by anything other than ACTION then a terminal, or a PIN value reaches a screen slot or stored param, THE SYSTEM SHALL report a violation.
7. V7 SMS fallback: WHEN a result's `sms_template` worst case exceeds the segment budget or omits a declared result field THE SYSTEM SHALL report a violation, or the compile SHALL refuse with an `R_...` code.
8. V8 refusal soundness: WHEN a refused operation appears in the machine or screens THE SYSTEM SHALL report a violation.
9. THE SYSTEM SHALL run all validators and return all results, not stop at the first failure.

### Requirement 4: Validator self-test
#### Acceptance Criteria
1. THE test suite SHALL include mutation fixtures that each break exactly one thing in a valid bundle: delete an edge, orphan a state, use a 200-char label, add an echo slot to a PIN state, make back loop to self, add a 12-step chain.
2. WHEN a mutation is applied THE SYSTEM SHALL flag it with exactly the intended validator and no unrelated validator.

### Requirement 5: Determinism
1. WHEN a bundle is compiled twice from the same input THE SYSTEM SHALL produce an identical `bundle_hash`, invariant under operation order permutation and JSON key order.
