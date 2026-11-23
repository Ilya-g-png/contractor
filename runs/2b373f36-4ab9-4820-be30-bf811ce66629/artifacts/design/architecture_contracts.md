# Interface Contracts

All interfaces are local, synchronous scanner interfaces. There are no HTTP endpoints. Traces: architecture *Component Decomposition* and *Interaction Topology*; FR-001–FR-013.

| Surface | Verb / path | Request schema | Response schema | Error codes / behavior | Idempotency |
|---|---|---|---|---|---|
| Scanner command | `EXEC dogwatch check` | `--config PATH` and `--output PATH` retain current semantics. `--baseline-ref REF` is required iff the loaded policy declares at least one OpenAPI contract. | Canonical report schema `0.3` written to `PATH` or stdout. Exit: `0` for `pass`, `1` for `fail`, `2` for `inconclusive`. | Missing required baseline input produces an error OpenAPI diagnostic in the report and exit `2`; it is not an argument-parser-only failure. Configuration parse errors retain existing `dogwatch/config-invalid` behavior. | Repeating with identical checkout, policy, local Git objects, verified tool, and baseline ref produces byte-identical output. The command does not fetch, clone, check out, or mutate Git state. |
| Policy loader | `RPC LoadPolicy(config_path)` | UTF-8 TOML policy. Existing `[[openapi.contracts]]`; repository-wide `[[openapi.severity]]` and `[[openapi.waivers]]`. Relative contract paths resolve from the policy file directory, matching existing configuration resolution. | Immutable `DogwatchConfig`, including ordered contract declarations and OpenAPI policy declarations. | Unknown keys, malformed declaration fields, invalid policy targets, malformed hashes/dates/operation locators, duplicate policy targets, or unsupported output severities produce configuration diagnostics. No oasdiff ignore-file setting is accepted. | Read-only and deterministic for identical policy bytes and filesystem state. |
| Comparison coordinator | `RPC CompareOpenApiContracts(config, baseline_ref, candidate_root)` | One resolved baseline reference, all configured declarations, and policy. The coordinator resolves `baseline_ref` once before reading a contract. | One `OpenAPI Comparison` per declaration; aggregate findings and diagnostics. A comparison state is `no-change`, `completed`, `policy-failed`, or `inconclusive`. | Any input, Git, validation, runner, or normalization failure yields diagnostics for that comparison and no compatibility finding for the failed condition. | Each declaration is independent; no retry, cache, or side effect is permitted. |
| Local Git baseline reader | `RPC ReadBaseline(resolved_commit, relative_path)` | Immutable commit object ID and configured relative POSIX path. The supplied ref must first be resolved locally using argv-only Git plumbing. | Exact baseline blob bytes, byte size, raw SHA-256, and resolved commit; or a diagnostic outcome. | `openapi-baseline-ref-unavailable` for an unresolved supplied ref; `openapi-baseline-invalid` when same-path input is not an eligible regular contract file; `openapi-git-failed` for local Git/object failures. Missing baseline path is an input diagnostic, not a finding. No network recovery is attempted. | Byte-exact and read-only. It must use only local objects and must not fetch, clone, check out, invoke LFS, or pass a Git-revision input to oasdiff. |
| Candidate reader and preflight | `RPC ValidateContract(side, declaration, raw_bytes)` | `side ∈ {base,candidate}`, declared `.yaml`, `.yml`, or `.json` path, and bytes from an eligible regular file. | Canonical deterministic JSON bytes for the runner, plus raw-byte SHA-256 and validated document metadata. | Missing/non-regular/oversize candidate and malformed, unsupported, unresolved-internal-reference, or external-reference documents yield an OpenAPI error diagnostic. The runner is not called. | Pure for identical input bytes and declaration. |
| Verified tool provider | `RPC ResolveVerifiedOasdiff(platform)` | Supported platform triple and local tool cache. Release is fixed to `v1.39.0`; manifest selects the approved archive and SHA-256. | Absolute executable path only after archive checksum verification and executable version verification. | Missing, unsupported-platform, checksum-invalid, unsafe-extraction, or wrong-version tool returns `openapi-tool-unavailable`; the scan does not download a replacement. | Scan-time resolution is read-only. Explicit installation is atomic and repeatable: an already verified matching cache entry is retained. |
| Restricted runner | `RPC RunOasdiff(executable, base_json, candidate_json)` | Adapter-created, read-only canonical inputs in a private temporary directory; fixed argv: `executable`, `changelog`, `--format=json`, `--level=INFO`, `--allow-external-refs=false`, `--`, base path, candidate path. Standard input is disconnected. | Successful stdout is a structured JSON sequence of declared changes, retained only when process exit is zero and output validates. | `openapi-tool-timeout` after 60 seconds; `openapi-tool-stdout-limit-exceeded` above 16 MiB; `openapi-tool-stderr-limit-exceeded` above 1 MiB; `openapi-tool-failed` for startup error, non-zero exit, malformed JSON, or malformed change record. No partial output is normalized. | One bounded child-process execution per call. Temporary inputs are removed after completion; no external network or reference loading is allowed. |
| Finding normalizer | `RPC NormalizeOpenApiChanges(contract, tool_records, provenance)` | Successful structured tool records; contract ID; validated base/candidate provenance. Each accepted record must carry the tool identity required to distinguish changes. | Deterministically ordered OpenAPI findings with normalized severity, locator, message, and `openapi/v1` fingerprint. | An unknown or incomplete record is `openapi-tool-failed`, with no fabricated finding. | Pure and deterministic; human message changes alone cannot change fingerprint. |
| OpenAPI policy applier | `RPC ApplyOpenApiPolicy(finding, policy, evaluation_date)` | Normalized finding and repository-wide reclassification/waiver declarations. | Same finding with effective severity and either `waiver: null` or a matched waiver object. | Invalid policy is a configuration diagnostic. A nonmatching, expired, or baseline-hash-mismatched waiver never suppresses a finding; expiry handling emits the policy diagnostic specified by the configuration implementation. | Pure. Reapplication to an already policy-processed finding is prohibited; policy applies exactly once after normalization. |
| Report builder | `RPC BuildReport(config, findings, diagnostics)` | Current scanner findings/diagnostics plus OpenAPI results. | Canonical JSON report conforming to `report-0.3.schema.json`. | Any error diagnostic determines `inconclusive`; otherwise any unwaived error finding determines `fail`; otherwise `pass`. | Deterministic sort and serialization. It has no external side effects. |

The verified-tool manifest is part of the tool-provider interface:

| Platform | Archive | Required archive SHA-256 |
|---|---|---|
| macOS | `oasdiff_1.39.0_darwin_all.tar.gz` | `fe88d9950324d3b0ebeaf8e0d3a210b64cb099a0f55fce5ee5a22b276df0eac4` |
| Linux amd64 | `oasdiff_1.39.0_linux_amd64.tar.gz` | `71a85930728f367a2086077b7ae1411319421549d18473a3e8258b6451520433` |
| Linux arm64 | `oasdiff_1.39.0_linux_arm64.tar.gz` | `481db7d891d916f13df277b2ef8bbb95477702827710e49fe22cef69c359c780` |

# Event & Queue Contracts

No event, queue, topic, background worker, retry loop, or asynchronous delivery surface exists in this deliverable. Comparisons are synchronous local scanner work; therefore producer, consumer, delivery guarantee, and retry policy are not applicable. Trace: architecture *Technology Choices* and *Interaction Topology*; FR-001, FR-005, FR-012, and FR-013.

# Data Contracts

## OpenAPI Contract Declaration

| Field | Type | Nullable | Validation | Source of truth |
|---|---|---:|---|---|
| `id` | string | no | Unique across declarations; kebab case; existing maximum-length rule applies. | Policy loader / `[[openapi.contracts]]` |
| `path` | relative POSIX path string | no | No absolute path, empty segment, `.`, `..`, or backslash; suffix is `.yaml`, `.yml`, or `.json`; unique across declarations. | Policy loader / `[[openapi.contracts]]` |

## Baseline Reference and Validated Contract Input

| Field | Type | Nullable | Validation | Source of truth |
|---|---|---:|---|---|
| `supplied_ref` | string | no | Explicit CLI value; no inferred default; must resolve locally to a commit before any contract read. | Scanner command |
| `resolved_commit` | Git object ID string | no after successful resolution | Immutable commit ID returned by local Git; one value is used for every configured comparison. | Local Git baseline reader |
| `side` | enum: `base`, `candidate` | no | Identifies input being validated. | Comparison coordinator |
| `raw_bytes` | bytes | no on successful read | Source bytes are preserved only for hashing/preflight; size is at most `5_242_880` bytes independently per side. | Candidate reader or Git baseline reader |
| `raw_sha256` | 64-character lowercase hexadecimal string | no on successful read | SHA-256 of `raw_bytes` before canonicalization. | Candidate reader / Git baseline reader |
| `canonical_json` | bytes | no on successful validation | Deterministic JSON generated after YAML/JSON parsing, supported-version validation, and reference validation; this is the only contract content passed to oasdiff. | Preflight validator |
| `openapi_version` | string | no on successful validation | Matches `3.0.x`, `3.1.x`, or `3.2.x`; Swagger/OpenAPI 2.0 and other major versions are rejected. | Preflight validator |

A valid input is a regular single file only. Every `$ref` is a string starting with `#`, and each internal reference resolves within that same document. Non-internal `$ref`, malformed input, unresolved internal reference, and over-limit input are diagnostics, not findings. Trace: FR-002, FR-003, FR-005, and FR-007.

## Repository-wide OpenAPI Policy

| Field | Type | Nullable | Validation | Source of truth |
|---|---|---:|---|---|
| `severity[].check_id` | string | no | Targets one OpenAPI check ID; duplicate targets are invalid. | `[[openapi.severity]]` |
| `severity[].severity` | enum: `error`, `warning`, `info` | no | `off` and all other values are invalid because findings use only the Dogwatch output vocabulary. | `[[openapi.severity]]` |
| `severity[].reason` | string | no | Required explanatory text; no additional length rule is frozen. | `[[openapi.severity]]` |
| `waivers[].contract_id` | string | no | Exact configured contract ID. | `[[openapi.waivers]]` |
| `waivers[].check_id` | string | no | Exact normalized finding check ID. | `[[openapi.waivers]]` |
| `waivers[].operation` | normalized operation locator string | no | Exact normalized locator, including method and OpenAPI path; malformed locators are configuration errors. | `[[openapi.waivers]]` |
| `waivers[].fingerprint` | string | no | Exact `openapi/v1:` finding fingerprint. | `[[openapi.waivers]]` |
| `waivers[].baseline_sha256` | 64-character lowercase hexadecimal string | no | Exact baseline raw-content hash. | `[[openapi.waivers]]` |
| `waivers[].reason` | string | no | Required explanatory text. | `[[openapi.waivers]]` |
| `waivers[].expires` | ISO-8601 calendar-date string | yes | If supplied, evaluated against injected evaluation date; an expired waiver cannot match. | `[[openapi.waivers]]` |

## OpenAPI Comparison

| Field | Type | Nullable | Validation | Source of truth |
|---|---|---:|---|---|
| `contract_id` | string | no | Equals one configured declaration ID. | Comparison coordinator |
| `baseline` | Baseline Reference | no once resolution succeeds | Shared resolved commit; same configured path is read from it. | Comparison coordinator |
| `state` | enum: `no-change`, `completed`, `policy-failed`, `inconclusive` | no | State transition rules are defined in Boundary Invariants. | Comparison coordinator |
| `findings` | ordered array of OpenAPI Finding | no | Empty for no-change and failed-comparison conditions. | Finding normalizer / policy applier |
| `diagnostics` | ordered array of OpenAPI Diagnostic | no | Error diagnostics make the aggregate report inconclusive. | All comparison stages |

## OpenAPI Finding

| Field | Type | Nullable | Validation | Source of truth |
|---|---|---:|---|---|
| `source` | literal string `openapi` | no | Must equal `openapi`. | Finding normalizer |
| `check_id` | string | no | Declared by accepted tool output. | Finding normalizer |
| `severity` | enum: `error`, `warning`, `info` | no | Effective severity after repository policy; reclassification changes this field only. | Policy applier |
| `message` | string | no | Human-readable tool-derived text; it is not fingerprint input. | Finding normalizer |
| `fingerprint` | string | no | `openapi/v1:` plus deterministic hash of canonical identity: contract ID, check ID, normalized operation locator, and oasdiff finding identity. | Finding normalizer |
| `locator` | Locator object | no | Identifies an operation when one exists; otherwise identifies the configured contract and available document location. | Finding normalizer |
| `waiver` | `null` or Waiver Result object | yes | A non-null waiver must exactly match contract ID, check ID, normalized locator, fingerprint, and baseline hash. | Policy applier |
| `provenance` | Provenance object | no | Contains both base and candidate provenance below. | Comparison coordinator |

### Locator

| Field | Type | Nullable | Validation | Source of truth |
|---|---|---:|---|---|
| `path` | relative POSIX path string | no | Equals the configured contract path. | Contract declaration |
| `operation` | string | yes | Normalized `METHOD /openapi/path`; method is uppercase. Document-level records use `document`. | Finding normalizer |
| `json_pointer` | RFC 6901 string | yes | When derivable, points to the related OpenAPI document location; otherwise omitted/null. | Finding normalizer |

### Provenance

| Field | Type | Nullable | Validation | Source of truth |
|---|---|---:|---|---|
| `provenance.base.ref` | string | no | Exact CLI-supplied baseline ref. | Scanner command |
| `provenance.base.commit` | Git object ID string | no | Exact locally resolved commit used for this comparison. | Git baseline reader |
| `provenance.base.path` | relative POSIX path string | no | Equals configured declaration path. | Contract declaration |
| `provenance.base.sha256` | 64-character lowercase hexadecimal string | no | Hash of raw baseline bytes. | Preflight input record |
| `provenance.candidate.path` | relative POSIX path string | no | Equals configured declaration path. | Contract declaration |
| `provenance.candidate.sha256` | 64-character lowercase hexadecimal string | no | Hash of raw candidate bytes. | Preflight input record |

### Waiver Result

| Field | Type | Nullable | Validation | Source of truth |
|---|---|---:|---|---|
| `matched` | literal boolean `true` | no | Present only for an exact, unexpired policy match. | Policy applier |
| `reason` | string | no | Copied from matched waiver. | Policy loader |
| `expires` | calendar-date string | yes | Copied when configured. | Policy loader |

## OpenAPI Diagnostic

| Field | Type | Nullable | Validation | Source of truth |
|---|---|---:|---|---|
| `source` | literal string `openapi` | no | Must equal `openapi`. | Producing comparison stage |
| `id` | string | no | Stable diagnostic ID. Tool IDs are `openapi-tool-unavailable`, `openapi-tool-timeout`, `openapi-tool-stdout-limit-exceeded`, `openapi-tool-stderr-limit-exceeded`, and `openapi-tool-failed`; Git IDs are `openapi-baseline-ref-unavailable`, `openapi-baseline-invalid`, and `openapi-git-failed`. | Producing comparison stage |
| `severity` | enum: `error`, `warning`, `info` | no | Failed comparison conditions required by FR-007 are `error`. | Producing comparison stage |
| `message` | string | no | Human-readable bounded diagnostic text; tool stderr included only in bounded form. | Producing comparison stage |

## Report Schema 0.3

| Field | Type | Nullable | Validation | Source of truth |
|---|---|---:|---|---|
| `schema_version` | literal string `0.3` | no | Must match report schema 0.3. | Report builder |
| `status` | enum: `pass`, `fail`, `inconclusive` | no | Derived, never directly configured. | Report builder |
| `scanner.name` | literal string `dogwatch` | no | Existing scanner identity. | Report builder |
| `scanner.version` | semantic-version string | no | Current scanner version. | Package metadata |
| `policy.path` | filename string | no | Existing policy report contract. | Policy loader |
| `policy.digest.sha256` | 64-character lowercase hexadecimal string | no | Hash of raw policy bytes. | Policy loader |
| `findings` | array | no | Every `source: openapi` item must satisfy the OpenAPI Finding contract; non-OpenAPI findings retain their established shape. | Report builder |
| `diagnostics` | array | no | Each item has the Diagnostic contract. | Report builder |

## Fixture Case

| Field | Type | Nullable | Validation | Source of truth |
|---|---|---:|---|---|
| `name` | string | no | Identifies a named FR-012 matrix scenario. | Fixture harness |
| `base` | fixture tree | no | Materialized and committed into a temporary local Git repository. | Fixture source |
| `candidate` | fixture tree | no | Materialized as candidate checkout content at the same declared path. | Fixture source |
| `baseline_ref` | string | no | Explicit ref to the temporary baseline commit. | Fixture harness |
| `expected_report` | canonical JSON bytes | no | Pinned; validates against report schema 0.3. | Reviewed fixture artifact |
| `expected_exit_code` | integer `0`, `1`, or `2` | no | Matches expected report status. | Reviewed fixture artifact |
| `expected_invocation` | structured record | yes | Required for execution-path fixtures; proves argv, disabled external references, read-only inputs, timeout, and both output bounds. | Fixture harness |
| `runner_substitute` | controlled executable descriptor | yes | Used only for timeout/tool-failure cases; never a live upstream failure. | Fixture harness |

# Boundary Invariants

1. For every configured declaration `d`, a comparison starts only if `baseline_ref` is explicit; `d.path` is read from both candidate input and `resolved_commit` without path substitution.

2. `count(distinct resolved_commit per scan) = 1` whenever the policy contains one or more OpenAPI declarations and baseline resolution succeeds.

3. For every accepted input `x`, `len(x.raw_bytes) <= 5_242_880`, `sha256(x.raw_bytes) = x.raw_sha256`, and `x.canonical_json` is the only contract body passed to the runner.

4. A runner invocation occurs only when both inputs passed preflight. Formally, `runner_called ⇒ base.valid ∧ candidate.valid`.

5. For every `$ref` found in an accepted input, `isinstance(ref, string) ∧ ref.startswith('#') ∧ resolves_json_pointer(ref, document)`.

6. Every oasdiff execution uses an argv sequence, never a command string or command interpreter; argv contains exactly one `--allow-external-refs=false` element and adapter-created input paths only.

7. At tool start, both runner input files are read-only and located below a private temporary directory; no candidate checkout path or Git object path is supplied to oasdiff.

8. For every tool execution, `elapsed_seconds <= 60` or the outcome is `openapi-tool-timeout`; `stdout_bytes <= 16 MiB` or the outcome is `openapi-tool-stdout-limit-exceeded`; `stderr_bytes <= 1 MiB` or the outcome is `openapi-tool-stderr-limit-exceeded`.

9. `nonzero_tool_exit ∨ malformed_tool_output ∨ malformed_tool_record ⇒ normalized_findings_for_that_execution = []` and produces `openapi-tool-failed`.

10. Invalid/missing input, unavailable baseline, timeout, output-limit breach, unavailable/invalid tool, or tool failure implies `comparison.state = inconclusive` and emits no compatibility-policy finding for that failed condition.

11. `comparison.state = no-change` iff both inputs and runner output are valid and the normalized finding array is empty; such a comparison contributes neither OpenAPI finding nor OpenAPI diagnostic.

12. `comparison.state = policy-failed` iff valid completed comparison results contain at least one unwaived finding whose effective severity is `error`.

13. `report.status = inconclusive` iff at least one diagnostic severity is `error`; otherwise `report.status = fail` iff at least one unwaived finding severity is `error`; otherwise `report.status = pass`.

14. For every normalized finding `f`, changing only `f.message` or applying a severity reclassification leaves `f.fingerprint` unchanged.

15. A waiver applies iff all five exact equalities hold: contract ID, check ID, normalized operation locator, fingerprint, and baseline raw SHA-256. A matching waiver annotates the finding; it does not remove it.

16. `waiver.baseline_sha256 != finding.provenance.base.sha256 ⇒ finding.waiver = null`.

17. Every OpenAPI finding has non-null severity, check ID, locator, message, fingerprint, `provenance.base`, and `provenance.candidate` fields.

18. Every base provenance commit equals the scan-wide resolved commit, and each provenance hash equals the raw bytes actually preflighted for that side.

19. Repeating each fixture twice under identical inputs produces identical canonical report bytes: `serialize(run_1) = serialize(run_2)`.

20. Fixture timeout and tool-failure tests use a controlled substitute and make no external service, mutable release, or external-reference request.

# Versioning & Compatibility

- The public report schema version for this capability is `0.3`, represented by `report-0.3.schema.json` and schema identifier `urn:dogwatch:schema:report:0.3`. Schema `0.2` remains available for historical validation but is not the output contract for an OpenAPI-capable scan.

- Schema 0.3 preserves the report envelope, status values, scanner metadata, policy digest, diagnostics, and non-OpenAPI finding shape. It adds mandatory OpenAPI provenance and structured waiver support only when `finding.source = "openapi"`. Consumers must select behavior by `schema_version`; a consumer that validates only 0.2 is not forward-compatible with 0.3.

- OpenAPI finding identity is independently versioned as `openapi/v1`. Any change to its canonical identity fields, hashing representation, locator normalization, or tool-identity interpretation requires a new fingerprint prefix. Message text and effective severity are explicitly outside the identity contract.

- oasdiff compatibility is pinned to official `v1.39.0` archives and the manifest checksums in Interface Contracts. There is no automatic update, fallback release, or unverified executable path. Changing the release, archive digest, command profile, or normalized output interpretation is a deliberate contract change requiring fixture expected-output review.

- The policy grammar is strict: unsupported or unknown fields are configuration errors. Existing declarations with no OpenAPI contracts remain compatible with `dogwatch check` without `--baseline-ref`. Once any OpenAPI contract is declared, omission of the explicit baseline ref is incompatible and yields a report diagnostic with exit `2`.

- No deprecation window is specified for report 0.2 output or policy syntax. Therefore neither may be silently removed or reinterpreted by this work; any later removal requires a separately versioned, explicitly announced compatibility change. Trace: FR-001, FR-004, FR-008–FR-013; architecture *Data Model*, *Cross-Cutting Concerns*, and *Open Questions* resolved by the implementation plan.
