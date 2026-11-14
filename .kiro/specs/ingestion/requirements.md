# Requirements: ingestion (OpenAPI + MCP) and SSRF policy

Source docs: `docs/ARCHITECTURE.md` sections 4, 9; `docs/SECURITY.md` T6, T7, T9; ADR-005, ADR-012. Milestone: Mon 16 - Tue 17 Nov (OpenAPI), Sun 22 Nov (MCP). Depends on spec `ir-type-subset`.

## Requirements

### Requirement 1: OpenAPI ingest
**User Story:** As a developer, I want to upload an OpenAPI file, so that its operations become draft IR.
#### Acceptance Criteria
1. WHEN a JSON or YAML OpenAPI 3.0 or 3.1 document of at most 2 MB is supplied THE SYSTEM SHALL produce `ir.draft.json` and `refusals.json`.
2. WHEN an operation has an `operationId` THE SYSTEM SHALL use it as the Operation id.
3. IF an operation lacks an `operationId` THEN THE SYSTEM SHALL generate one from method and path and flag it in the report.
4. WHEN the method is GET THE SYSTEM SHALL set kind to read, and otherwise to write.
5. IF the document exceeds 2 MB THEN THE SYSTEM SHALL reject it before parsing.

### Requirement 2: Safe parsing and `$ref` resolution
#### Acceptance Criteria
1. THE SYSTEM SHALL parse YAML with a safe loader that limits aliases and nesting depth.
2. WHEN a `$ref` is local (`#/...`) THE SYSTEM SHALL resolve it using the project's own resolver.
3. WHEN a `$ref` is remote and the host is not on the allowlist THE SYSTEM SHALL record `R_REF_UNRESOLVED` and SHALL NOT make a network request.
4. WHEN a `$ref` cycle is found THE SYSTEM SHALL record `R_RECURSIVE` and terminate.
5. IF schema depth exceeds the configured cap THEN THE SYSTEM SHALL refuse the affected operation with a code, not raise.

### Requirement 3: URL guard (SSRF policy)
#### Acceptance Criteria
1. WHEN a URL is requested for an MCP server or allowlisted `$ref` THE SYSTEM SHALL permit https only.
2. WHEN the URL host resolves to a private, loopback, link-local or cloud-metadata address THE SYSTEM SHALL reject the request.
3. WHEN a redirect is followed THE SYSTEM SHALL re-run the guard on the new target.
4. THE SYSTEM SHALL enforce response size and time caps on every guarded fetch.

### Requirement 4: MCP ingest
#### Acceptance Criteria
1. WHEN a streamable-HTTP MCP URL passes the URL guard THE SYSTEM SHALL call `initialize` and `tools/list` and map each tool to a draft Operation.
2. WHEN a tool has `outputSchema` THE SYSTEM SHALL map it to Result, and otherwise SHALL set result shape to text.
3. WHEN tool annotations `readOnlyHint` or `destructiveHint` are present THE SYSTEM SHALL use them only as untrusted seeds for kind and risk.
4. IF a user supplies a stdio command THEN THE SYSTEM SHALL reject it; stdio transports SHALL be accepted only from the server-side registry of bundled samples.
5. THE SYSTEM SHALL treat tool descriptions and server responses as data and never as instructions.

### Requirement 5: Adversarial inputs
#### Acceptance Criteria
1. WHEN given a YAML alias bomb, a deeply nested schema or a catastrophic-backtracking `pattern` THE SYSTEM SHALL finish within its caps without crashing.
