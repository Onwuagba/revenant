# Requirements: IR and type subset

Source docs: `architecture/IR_AND_TYPE_SUBSET.md`, `docs/PRD.md` (goal 4, US3), `docs/TESTING.md` (P7, P13). Milestone: Mon 16 - Tue 17 Nov. This spec is the compiler core and is built FIRST.

## Introduction
The IR is a source-independent description of operations, parameters and results. The classifier maps every JSON Schema to a supported Param or a typed Refusal. Refused operations never reach the bundle.

## Requirements

### Requirement 1: Canonical IR models
**User Story:** As a developer, I want a single typed IR, so that OpenAPI and MCP inputs compile through the same pipeline.
#### Acceptance Criteria
1. THE IR module SHALL define typed models for App, Operation, Param, Result, Flow and Refusal with the fields in `IR_AND_TYPE_SUBSET.md` section 2.
2. WHEN an IR object is serialised THE SYSTEM SHALL emit canonical JSON with sorted keys and operations ordered by operation id.
3. WHEN two IRs differ only in operation order or JSON key order THE SYSTEM SHALL serialise them to identical bytes.
4. IF a model field violates its length limit (Operation title > 24 chars, Param label > 20 chars) THEN THE SYSTEM SHALL reject it with a validation error naming the field.

### Requirement 2: Type classification (supported subset)
**User Story:** As a developer, I want each schema element classified, so that I know exactly what compiles.
#### Acceptance Criteria
1. WHEN a schema is `boolean` THE SYSTEM SHALL classify it as a yes/no Param.
2. WHEN a schema is `string` with `enum` of at most 36 values THE SYSTEM SHALL classify it as a paginated menu Param.
3. WHEN a schema is `integer` or `number` with both `minimum` and `maximum` and at most 9 digits THE SYSTEM SHALL classify it as a range-checked numeric Param.
4. WHEN a schema is `string` with `pattern`, or `maxLength` <= 20 and charset `[A-Za-z0-9 -]` THE SYSTEM SHALL classify it as a typed-token Param.
5. WHEN a schema carries `x-revenant-secret: pin` with 4 to 6 digits THE SYSTEM SHALL classify it as a PIN Param with `secret = pin`.
6. WHEN a schema is `string` format `date` with `x-revenant-date-window` N where N <= 7 THE SYSTEM SHALL classify it as a day-picker Param.
7. WHEN a schema is a flat object of at most 6 scalar properties THE SYSTEM SHALL flatten it into sequential Params.
8. WHEN a schema carries `x-revenant-options-from` THE SYSTEM SHALL classify it as a dynamic-choice Param with `options_from`.

### Requirement 3: Refusal with codes
**User Story:** As a developer, I want unsupported shapes refused with a reason, so that nothing is guessed.
#### Acceptance Criteria
1. WHEN a schema matches an unsupported shape THE SYSTEM SHALL return a Refusal with exactly one code from: R_NESTED_OBJECT, R_POLYMORPHIC, R_FREE_TEXT, R_DATETIME, R_UNBOUNDED_NUMBER, R_TOO_MANY_PARAMS, R_BINARY, R_AUTH_SCHEME, R_CALLBACK, R_NON_GSM7, R_REF_UNRESOLVED, R_RECURSIVE.
2. WHEN a Refusal is produced THE SYSTEM SHALL include `op_id`, a JSON pointer `path`, a message and a hint.
3. THE classifier SHALL NOT raise an exception for any JSON Schema input, including empty, cyclic, deeply nested or malformed schemas.
4. WHEN an Operation contains any refused Param THE SYSTEM SHALL exclude the whole Operation from the IR operations list and record every Refusal.
5. WHEN every Operation is refused THE SYSTEM SHALL signal compile failure with exit code 2.
6. THE SYSTEM SHALL NOT execute a schema `pattern` at compile time.

### Requirement 4: Refusal report
**User Story:** As a developer, I want a compiled-vs-refused summary, so that the Buried report is accurate.
#### Acceptance Criteria
1. WHEN classification finishes THE SYSTEM SHALL produce `refusals.json` listing every Refusal and counts of compiled and refused operations.
2. THE report SHALL NOT present a single coverage percentage without the per-code table.
