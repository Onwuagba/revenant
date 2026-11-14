# Requirements: runtime, replay, PIN safety, SMS fallback

Source docs: `docs/ARCHITECTURE.md` section 5; `docs/SECURITY.md` T1-T5, T10, T11; `docs/TESTING.md` P8, P9, P11, section 3; `docs/PLATFORM_FACTS.md` (AT callback format); ADR-003, ADR-011. Milestone: Sat 21 - Sun 22 Nov. Depends on `ir-type-subset` and `state-machine-validators`.

## Requirements

### Requirement 1: AT-shaped callback
**User Story:** As an end user on a feature phone, I want each key press answered with the next screen.
#### Acceptance Criteria
1. WHEN a form-encoded POST to `/ussd/{slug}/{token}` with `sessionId`, `serviceCode`, `phoneNumber`, `text` arrives THE SYSTEM SHALL return `text/plain` starting with `CON ` or `END `.
2. WHEN `text` is empty THE SYSTEM SHALL return the ROOT screen.
3. WHEN the token is wrong THE SYSTEM SHALL return HTTP 404.
4. IF the form is malformed THEN THE SYSTEM SHALL return HTTP 200 with a generic `END` message and SHALL NOT expose a stack trace.
5. THE runtime SHALL NOT call any LLM and SHALL pass its integration suite with all LLM environment variables unset.
6. WHEN a static screen is requested THE SYSTEM SHALL respond from precomputed templates with slot substitution only.

### Requirement 2: Replay from text and session cache
#### Acceptance Criteria
1. WHEN a callback arrives THE SYSTEM SHALL rebuild the machine state by replaying `text` split on `*`.
2. THE SYSTEM SHALL use stored session rows only as a cache and for fetched option lists.
3. WHEN the cached state and the replayed state differ THE SYSTEM SHALL use the replayed state.
4. WHEN a callback repeats an existing `(session_id, step_index)` THE SYSTEM SHALL return the stored response and SHALL NOT re-execute any action.

### Requirement 3: Actions and upstream calls
#### Acceptance Criteria
1. WHEN an ACTION state runs THE SYSTEM SHALL call the upstream with a 3 s deadline and an Idempotency-Key derived from hash(session, state, params).
2. WHEN the upstream times out, returns 202, or the result exceeds the screen budget THE SYSTEM SHALL insert an `sms_outbox` row and respond with `END` stating details are sent by SMS.
3. WHEN upstream data is placed in slots THE SYSTEM SHALL sanitise it.
4. THE SYSTEM SHALL cache fetched option lists with a default TTL of 60 s.

### Requirement 4: PIN safety
#### Acceptance Criteria
1. THE SYSTEM SHALL NOT include `text`, a PIN, or any input value in any log record, exception message, `session_events` row, `ussd_sessions` row or response body.
2. WHEN a PIN is entered THE SYSTEM SHALL treat it as the last input, hold it in memory only, pass it to the upstream, and respond with `END`.
3. WHEN 3 upstream auth failures occur for one MSISDN HMAC on one deployment THE SYSTEM SHALL lock it for 15 minutes.
4. WHEN a locked MSISDN tries again THE SYSTEM SHALL show a message identical to the bad-PIN message.
5. WHEN a canary PIN is run through a full flow THE SYSTEM SHALL leave the canary digits absent from responses, logs and a database dump.

### Requirement 5: SMS outbox and provider
#### Acceptance Criteria
1. THE SYSTEM SHALL define an `SmsProvider` interface with `AfricasTalkingSms`, `EmulatorSms` and a `ModemSms` stub.
2. WHEN an SMS job is claimed THE worker SHALL use `FOR UPDATE SKIP LOCKED` and retry with backoff up to a bounded attempt count.
3. THE SYSTEM SHALL send SMS only to the session's own MSISDN and enforce per-MSISDN and per-deployment rate limits and a daily cap.
4. WHEN an SMS body is built THE SYSTEM SHALL ensure it is GSM-7 and within the segment budget (160 single, 153 concatenated), containing all declared result fields, or the compile SHALL have refused.

### Requirement 6: Retention
1. THE SYSTEM SHALL purge expired sessions, and sent SMS rows after 24 hours.
