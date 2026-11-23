# Summary

Decompose CD-9 into five scanner-owned units: first establish the strict policy/report contract, then build independent input/Git and tool-execution boundaries, integrate them through the coordinator and CLI, and finally add the pinned end-to-end fixture matrix. This follows the existing `scanner/src/dogwatch`, schema, unit-test, and golden-fixture conventions while isolating shared seams and making the coordinator the only integration point.

# Implementation Units

## `openapi-policy-report-contract`

- **Title:** Add OpenAPI policy declarations and report schema 0.3
- **Ticket requirements served:** [AC-4]
- **Frozen-spec sections satisfied:** FR-002, FR-008, FR-009, FR-010, FR-011; SC-002.
- **Architecture components touched:** Policy and configuration extension; OpenAPI policy applier contract; Versioned report builder; Data Model: OpenAPI Contract Declaration, Policy Reclassification / Waiver, OpenAPI Finding, OpenAPI Diagnostic, Report Schema 0.3.
- **Files owned:**
  - `scanner/src/dogwatch/config.py` — extend strict TOML key validation and `DogwatchConfig` with ordered OpenAPI severity and waiver declarations; preserve relative contract path resolution from the policy-file directory.
  - `scanner/src/dogwatch/contracts.py` — retain and validate declaration invariants needed by policy references.
  - `scanner/src/dogwatch/report.py` — evolve the report model/projection, finding sort key, locator projection, waiver representation, and canonical serialization to schema 0.3 without changing non-OpenAPI finding shape.
  - `scanner/schemas/report-0.3.schema.json` — add `urn:dogwatch:schema:report:0.3`; retain `report-0.2.schema.json` untouched for historical validation.
  - `scanner/tests/test_config.py`, `scanner/tests/test_contracts.py`, `scanner/tests/test_report.py`, `scanner/tests/test_schema.py` — contract and regression coverage.
  - `scanner/tests/golden/harness.py`, `scanner/tests/golden/test_fixture_goldens.py`, `fixtures/*/expected-report.json` — update existing non-OpenAPI golden/schema expectations to 0.3 if required by the schema-version change.
- **Write-scope hints:** Own the public config and report data-model seam. Do not add comparison orchestration, Git access, subprocess execution, or OpenAPI fixtures here. Export stable declaration/report types for downstream units rather than having them inspect TOML or construct report dictionaries directly.
- **Success criteria:**
  - Strict loader accepts only `[[openapi.contracts]]`, `[[openapi.severity]]`, and `[[openapi.waivers]]` shapes defined by the contracts; invalid targets, duplicate targets, invalid locator/hash/date/severity values, and unknown keys are configuration diagnostics.
  - Schema 0.3 validates every OpenAPI finding only when it has source, effective severity, check ID, locator, message, `openapi/v1:` fingerprint, base/candidate provenance, and either `null` or a structured waiver; schema 0.2 remains available.
  - Report status continues to give error diagnostics priority over unwaived error findings, and canonical output remains deterministic.
  - `cd scanner && uv run --locked pytest tests/test_config.py tests/test_contracts.py tests/test_report.py tests/test_schema.py` passes, as do `cd scanner && uv run --locked ruff format --check . && uv run --locked ruff check . && uv run --locked mypy` and the existing golden suite.

## `openapi-input-baseline`

- **Title:** Implement contract preflight and local Git baseline retrieval
- **Ticket requirements served:** [AC-1], [AC-3]
- **Frozen-spec sections satisfied:** FR-001, FR-002, FR-003, FR-007, FR-010; SC-004.
- **Architecture components touched:** Candidate reader and preflight validator; Local Git baseline reader; Baseline Reference; Validated Contract Input; Comparison coordinator input boundary.
- **Files owned:**
  - `scanner/src/dogwatch/openapi/__init__.py` — package boundary only.
  - `scanner/src/dogwatch/openapi/model.py` — immutable validated-input, baseline-reference, and diagnostic-result types shared with coordinator/normalizer.
  - `scanner/src/dogwatch/openapi/preflight.py` — regular-file eligibility, 5 MiB raw-byte cap, YAML/JSON parsing, OpenAPI-version validation, internal-reference resolution, canonical JSON, and raw SHA-256.
  - `scanner/src/dogwatch/openapi/git.py` — argv-only local Git ref resolution and exact same-path blob reads.
  - `scanner/pyproject.toml`, `scanner/uv.lock` — one selected pinned YAML parser/runtime dependency, once the unresolved dependency decision is supplied.
  - `scanner/tests/openapi/test_preflight.py`, `scanner/tests/openapi/test_git.py`, `scanner/tests/openapi/__init__.py` — isolated validation and Git-plumbing tests.
- **Write-scope hints:** This unit owns only raw input retrieval and validation. It returns typed outcomes/diagnostics; it neither invokes oasdiff nor creates findings. All Git calls must remain local, argv-only, and read-only; do not modify checkout state, fetch, clone, invoke LFS, or pass revision syntax to a later tool.
- **Success criteria:**
  - Candidate and baseline accept only regular `.yaml`, `.yml`, or `.json` files at the declaration’s byte-identical relative path, independently enforce the 5 MiB cap, retain raw-byte SHA-256, and pass only deterministic canonical JSON onward.
  - Preflight emits error OpenAPI diagnostics and no findings for missing/non-regular/oversize input, malformed YAML/JSON, unsupported OpenAPI versions, external `$ref`, or unresolved internal `$ref`.
  - The supplied baseline ref is resolved once to a local immutable commit; unavailable refs, absent/invalid baseline entries, and Git/object faults use the contracted diagnostic IDs without a network or checkout side effect.
  - Tests prove no runner-ready result is produced unless both validation conditions are met, and prove same-path baseline retrieval rather than path substitution.
  - `cd scanner && uv run --locked pytest tests/openapi/test_preflight.py tests/openapi/test_git.py` passes, as do `cd scanner && uv run --locked ruff format --check . && uv run --locked ruff check . && uv run --locked mypy`.

## `openapi-verified-runner`

- **Title:** Provide archive-verified oasdiff and bounded restricted execution
- **Ticket requirements served:** [AC-2], [AC-3]
- **Frozen-spec sections satisfied:** FR-004, FR-005, FR-007, FR-013; SC-003, SC-004.
- **Architecture components touched:** Verified tool provider and restricted oasdiff runner; Cross-Cutting Concerns: Trust boundary, Integrity and supply chain, Resource control.
- **Files owned:**
  - `scanner/src/dogwatch/openapi/tool.py` — v1.39.0 supported-platform manifest, archive checksum verification, safe archive handling, cache inspection, executable-version verification, and `openapi-tool-unavailable` outcomes.
  - `scanner/src/dogwatch/openapi/runner.py` — private temporary directory, read-only canonical inputs, exact argv construction, disconnected stdin, concurrent bounded stream collection, timeout/cap termination, and JSON output decoding.
  - `scanner/tests/openapi/test_tool.py`, `scanner/tests/openapi/test_runner.py` — manifest, archive/cache, argv, permissions, timeout, output-limit, non-zero-exit, and malformed-output coverage.
  - `scanner/tests/openapi/support.py` — controlled executable/test-record helpers used solely by runner tests and later fixture tests.
- **Write-scope hints:** Own all subprocess and local tool-cache behavior. Use the exact command profile in `architecture_contracts.md`; expose successful structured records or a diagnostic outcome only. Do not normalize records, apply policy, read Git, or edit report/config/schema files.
- **Success criteria:**
  - Provider selects only the macOS, Linux amd64, or Linux arm64 v1.39.0 archive and the exact pinned SHA-256 from the architecture contract; unsupported/missing/checksum-invalid/unsafe/wrong-version binaries produce `openapi-tool-unavailable` and never trigger a download during scan.
  - Runner invokes only an argv sequence containing `changelog`, `--format=json`, `--level=INFO`, exactly one `--allow-external-refs=false`, `--`, and adapter-created paths; no shell or inherited candidate/Git path reaches the tool.
  - At launch, canonical files are under a private temporary directory and read-only. Timeout is 60 seconds; stdout and stderr caps are 16 MiB and 1 MiB; timeout, cap, startup/non-zero, and malformed-output outcomes are contracted diagnostics with no partial records returned.
  - Controlled tests record all fixed invocation properties and prove no external service, mutable release, or external reference is needed for timeout and failure cases.
  - `cd scanner && uv run --locked pytest tests/openapi/test_tool.py tests/openapi/test_runner.py` passes, as do `cd scanner && uv run --locked ruff format --check . && uv run --locked ruff check . && uv run --locked mypy`.

## `openapi-comparison-integration`

- **Title:** Coordinate comparisons, normalize findings, apply policy, and wire CLI
- **Ticket requirements served:** [AC-1], [AC-3], [AC-4]
- **Frozen-spec sections satisfied:** FR-001, FR-006, FR-007, FR-008, FR-009, FR-010, FR-011; SC-002, SC-004.
- **Architecture components touched:** Scanner CLI and baseline-input resolver; OpenAPI comparison coordinator; Finding normalizer; OpenAPI policy applier; Versioned report builder; OpenAPI Comparison state machine.
- **Files owned:**
  - `scanner/src/dogwatch/openapi/coordinator.py` — one baseline resolution per scan, one comparison per declaration, state transitions, and aggregate result construction.
  - `scanner/src/dogwatch/openapi/normalize.py` — accepted-record validation, locator normalization, deterministic ordering, and `openapi/v1` fingerprint construction.
  - `scanner/src/dogwatch/openapi/policy.py` — post-normalization severity reclassification and exact, unexpired waiver matching.
  - `scanner/src/dogwatch/cli.py` — `--baseline-ref` behavior, candidate-root handoff, OpenAPI diagnostics in normal report output, and scan integration.
  - `scanner/tests/openapi/test_coordinator.py`, `scanner/tests/openapi/test_normalize.py`, `scanner/tests/openapi/test_policy.py`, `scanner/tests/test_cli.py` — integration and public-command coverage.
- **Write-scope hints:** This is the only unit permitted to compose policy/report types with preflight, Git, and runner interfaces. Depend on their typed result contracts; do not duplicate their parsing, Git, tool, or schema logic. CLI omission with configured contracts must generate a report diagnostic and exit 2, not an argument-parser-only error.
- **Success criteria:**
  - With no OpenAPI declarations, existing command behavior remains compatible; with declarations, an explicit `--baseline-ref` is mandatory and a successful resolution is shared by every comparison.
  - Valid no-change results add neither OpenAPI finding nor OpenAPI diagnostic. Failed input/Git/tool/normalization stages produce an error diagnostic, zero policy findings for that failed comparison, and aggregate `inconclusive` status.
  - Every accepted tool change becomes a deterministic `source: openapi` finding with required locator/provenance data. The fingerprint includes contract ID, check ID, normalized locator, and tool identity, but not message or effective severity; distinct tool identities remain distinct.
  - Policy reclassification changes only effective severity. A waiver remains visible and applies only on exact contract ID, check ID, normalized operation locator, fingerprint, baseline raw SHA-256, and non-expiry; it never removes the finding.
  - `cd scanner && uv run --locked pytest tests/openapi/test_coordinator.py tests/openapi/test_normalize.py tests/openapi/test_policy.py tests/test_cli.py` passes, as do `cd scanner && uv run --locked ruff format --check . && uv run --locked ruff check . && uv run --locked mypy`.

## `openapi-fixture-matrix`

- **Title:** Add pinned OpenAPI comparison fixtures and deterministic acceptance harness
- **Ticket requirements served:** [AC-5], plus [AC-1]–[AC-4] as end-to-end evidence.
- **Frozen-spec sections satisfied:** FR-012, FR-013; SC-001, SC-002, SC-003, SC-004, SC-005.
- **Architecture components touched:** Fixture Case; Fixture harness → temporary Git repository and controlled runner substitute; all coordinator integration seams.
- **Files owned:**
  - `scanner/tests/openapi/fixtures/` — named `base`/`candidate` fixture trees, policy inputs, runner descriptors where needed, and reviewed canonical expected reports.
  - `scanner/tests/openapi/test_fixture_matrix.py` — temporary-repository materialization, explicit baseline commit creation, command/invocation assertions, schema validation, report byte comparisons, and two-run determinism checks.
  - `scanner/tests/openapi/fixture_harness.py` — fixture discovery/materialization and pinned-output comparison utilities.
  - `scanner/tests/openapi/expected/` — one deliberately reviewed expected report artifact per scenario.
  - `scanner/tests/openapi/support.py` — may extend only its fixture-facing controlled-executable API in coordination with `openapi-verified-runner`.
- **Write-scope hints:** Own OpenAPI-specific fixtures only; do not regenerate fixture outputs implicitly and do not alter existing non-OpenAPI fixture semantics. Integration seams are the public CLI/report schema and controlled runner interface.
- **Success criteria:**
  - The suite has named, pinned cases for: no change; removed operation; optional-to-required field; enum or constraint break; invalid spec; missing baseline; timeout or tool failure; and ignored or reclassified finding.
  - Every case materializes `base` and `candidate` at the same relative path in a temporary local Git repository and supplies the baseline commit through `--baseline-ref`.
  - Expected reports validate against report schema 0.3; all emitted OpenAPI findings assert all AC-4 fields; error cases assert exact diagnostic IDs, no corresponding policy finding, and `inconclusive`/exit 2.
  - Execution-path fixtures assert the argv profile, disabled external references, read-only temporary inputs, fixed timeout, and both output limits. Timeout/tool-failure cases use controlled local substitutes only.
  - Each case is run twice and its canonical bytes match the checked-in expected bytes and each other; no test path silently rewrites expected outputs.
  - `cd scanner && uv run --locked pytest tests/openapi/test_fixture_matrix.py` passes, followed by `cd scanner && uv run --locked pytest` and `cd scanner && uv run --locked ruff format --check . && uv run --locked ruff check . && uv run --locked mypy`.

# Dependency Graph

- `openapi-policy-report-contract` → `openapi-comparison-integration` **(blocking):** coordinator requires stable policy declarations, report 0.3 types, finding projection, and schema contract.
- `openapi-input-baseline` → `openapi-comparison-integration` **(blocking):** coordinator consumes validated inputs, the resolved baseline, and diagnostic outcomes.
- `openapi-verified-runner` → `openapi-comparison-integration` **(blocking):** coordinator must use the runner’s typed success/failure boundary.
- `openapi-comparison-integration` → `openapi-fixture-matrix` **(blocking):** fixture tests verify the user-visible scanner behavior, states, report bytes, and exits.
- `openapi-verified-runner` → `openapi-fixture-matrix` **(blocking):** fixture harness needs the controlled runner-substitute seam and invocation record.
- `openapi-policy-report-contract` → `openapi-fixture-matrix` **(blocking):** pinned outputs and schema validation require report 0.3 and policy grammar.
- `openapi-input-baseline` → `openapi-fixture-matrix` **(advisory):** fixture layout can be authored early, but baseline-materialization assertions should wait for the final reader diagnostics.

# Parallelization Plan

**Wave 1 (concurrent):**

- `openapi-policy-report-contract` owns only existing config/report/schema/golden surfaces.
- `openapi-input-baseline` owns the new `dogwatch.openapi` input and Git modules plus their isolated tests; it may add the pinned YAML dependency after the parser decision is closed.
- `openapi-verified-runner` owns the new tool/runner modules, their cache boundary, and controlled-executable test support.

These three units have no overlapping production-file ownership. The only shared future package namespace is allocated up front: input/Git owns `model.py`, `preflight.py`, and `git.py`; tool execution owns `tool.py` and `runner.py`.

**Integration checkpoint:** merge and type-check the exported config/report, input/Git, and runner result contracts before starting `openapi-comparison-integration`. Confirm exact diagnostic IDs, canonical input/result types, and the one-time baseline-resolution interface.

**Wave 2:**

- `openapi-comparison-integration` runs after all three blocking Wave 1 units land. It is the sole owner of `cli.py` and composition logic.

**Final verification checkpoint:** after command integration, `openapi-fixture-matrix` adds fixture data and acceptance harness without modifying integration code except an agreed test-support extension. Run the complete scanner test, lint, type-check, and fixture commands before accepting the batch.

# Risks & Open Questions

- **Pinned YAML parser remains unresolved.** The architecture explicitly leaves the YAML library/version and duplicate-key, alias-expansion, and nesting controls undecided. `openapi-input-baseline` cannot safely implement FR-003 until this is selected and added to the lockfile.

- **Tool provisioning lifecycle is incomplete.** The contracts define cache verification and say scans do not download replacements, but do not specify where verified archives are installed or how a user invokes installation. The provider can return `openapi-tool-unavailable`; an installation command/package workflow requires an explicit decision.

- **Official v1.39.0 output evidence needs verification.** The architecture fixes the command profile and requires a structured change identity, but the frozen materials do not include a reviewed sample/schema from this release. The normalizer’s accepted record fields and fixture expected check IDs must be confirmed against the pinned binary before implementation is accepted.

- **Git hardening detail is underspecified by the current contracts.** They require local argv-only plumbing and prohibit fetch/clone/checkout/LFS, but do not prescribe Git version support, environment hardening, or exact plumbing commands. The baseline unit must either receive an approved profile or limit itself strictly to the stated invariants and record the residual security review risk.

- **Path resolution is clear for policy-relative candidates, but repository discovery is not fully named.** Contracts say candidate paths resolve from the policy-file directory; they do not state how the local repository root/Git directory is selected when the policy directory is nested. The CLI/coordinator needs this compatibility detail before baseline retrieval is wired.

- **Ticket coverage is complete.** AC-1 is served by `openapi-input-baseline` and `openapi-comparison-integration`; AC-2 by `openapi-verified-runner`; AC-3 by those three execution units; AC-4 by `openapi-policy-report-contract` and `openapi-comparison-integration`; and AC-5 by `openapi-fixture-matrix`.
