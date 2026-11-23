## 1. Summary

Implement the OpenAPI adapter in the Python scanner: resolve each declared contract against an explicit local Git baseline, preflight both single-file documents, invoke verified oasdiff `v1.39.0` through a bounded argv-only runner, normalize results into report schema `0.3`, and apply repository-wide reclassification and exact-match waiver policy. The adapter will use controlled Git-history fixtures and pinned golden reports; timeout and failure cases use a substitute executable.

## 2. Technical Context

- Language/framework: CPython `>=3.11`; existing `argparse`, `tomllib`, `pytest`, `jsonschema`, and deterministic JSON serialization.
- New runtime dependency: a YAML parser using safe loading, added to `scanner/pyproject.toml` and locked in `scanner/uv.lock`. It is required by FR-003 because YAML contracts must be parsed before oasdiff runs.
- Storage: no service or database. Baseline objects come only from the local Git repository. Per-comparison input copies live in a private temporary directory and are read-only.
- Tool delivery: add a verified local oasdiff installer/cache. The fixed v1.39.0 archive map is:
  - macOS: `oasdiff_1.39.0_darwin_all.tar.gz`, SHA-256 `fe88d9950324d3b0ebeaf8e0d3a210b64cb099a0f55fce5ee5a22b276df0eac4`
  - Linux amd64: `oasdiff_1.39.0_linux_amd64.tar.gz`, SHA-256 `71a85930728f367a2086077b7ae1411319421549d18473a3e8258b6451520433`
  - Linux arm64: `oasdiff_1.39.0_linux_arm64.tar.gz`, SHA-256 `481db7d891d916f13df277b2ef8bbb95477702827710e49fe22cef69c359c780`

  These match the official v1.39.0 release assets. [oasdiff v1.39.0 release](https://github.com/oasdiff/oasdiff/releases/tag/v1.39.0)
- Target platforms: macOS and Linux, matching the existing workspace prerequisites; Windows remains unsupported.
- Limits: 5 MiB per raw contract, 60-second tool wall timeout, 16 MiB stdout cap, 1 MiB stderr cap.
- Testing: unit tests for parsing, Git and process boundaries; schema tests; a dedicated OpenAPI fixture harness with pinned expected reports; `make test-scanner`, `make test-fixtures`, and `make lint-scanner`.
- Scale constraint: one independent bounded comparison per configured OpenAPI Contract Declaration; no network, checkout mutation, ref fetching, or external reference resolution during scanning.
- NEEDS CLARIFICATION: none. The verified release metadata resolves the artifact-checksum detail left implicit by FR-004.

## 3. Constitution Check

| Gate | Result | Evidence |
|---|---|---|
| Workspace-only operation | PASS | FR-001, FR-010, and Assumptions require local Git baseline reads only; no remote fetch, clone, or checkout mutation is planned. |
| Safe external-tool execution | PASS | FR-004 and FR-005 require a pinned verified binary, argv invocation, read-only inputs, disabled external references, and explicit limits. |
| Deterministic, versioned output | PASS | FR-008, FR-009, SC-002, and SC-005 require a new versioned schema, stable fingerprints, canonical serialization, and byte-identical fixture outputs. |
| Diagnostics remain distinct from policy findings | PASS | FR-007 and SC-004 require error diagnostics to produce `inconclusive`, with no policy finding for failed comparisons. Existing `derive_status` already implements this status precedence. |
| DevOps bundle boundary | PASS | Changes stay within scanner tooling, release verification, local execution safety, test harnesses, and CI-compatible Make targets; API and web areas are untouched. |
| Project constitution | PASS | No repository constitution document was found in the workspace; the frozen specification and scope borders are the applicable constraints. |

## 4. Project Structure

```text
scanner/
  pyproject.toml                         # YAML runtime dependency
  uv.lock                                # locked dependency resolution
  schemas/
    report-0.2.schema.json               # retained for historical validation
    report-0.3.schema.json               # new OpenAPI-capable report contract
  src/dogwatch/
    cli.py                               # --baseline-ref and scan wiring
    config.py                            # parse repository-wide OpenAPI policy
    contracts.py                         # retain declaration validation
    report.py                            # schema 0.3 projection and sorting
    openapi.py                           # comparison orchestration
    openapi_git.py                       # local baseline resolution and blob read
    openapi_validate.py                  # input preflight and reference checks
    openapi_tool.py                      # release manifest, installer, bounded runner
    openapi_policy.py                    # reclassification and waiver matching
  tests/
    test_config.py                       # OpenAPI policy validation
    test_report.py                       # schema 0.3 projection/status behavior
    test_schema.py                       # report 0.3 validation
    test_cli.py                          # baseline argument and report behavior
    openapi/
      test_git.py
      test_validate.py
      test_tool.py
      test_policy.py
      test_fixtures.py
      harness.py
      regenerate.py
      fake_oasdiff.py
  scripts/
    install_oasdiff.py                   # download, checksum-verify, safely extract
fixtures/
  openapi/
    <fixture-case>/
      base/
      candidate/
      expected-report.json
      expected-invocation.json
Makefile                                # install-oasdiff and fixture-test wiring
README.md                               # tool bootstrap and baseline usage
fixtures/README.md                      # controlled Git-history fixture layout
.gitignore                              # local verified-tool cache
```

The existing `fixtures/*/dogwatch.toml` golden harness remains for scanner-wide pass fixtures. OpenAPI compatibility fixtures are separate because they require a temporary Git repository, may intentionally yield `fail` or `inconclusive`, and must capture invocation safety evidence.

## 5. Research Notes

- CD-4 was reviewed at `.am/reports/5b28548a-4c88-4600-b7cc-a6df1df95c7b-research-paper.md`. Its baseline-isolation, direct-process, and normalized-finding guidance is supporting context only; requirements come from the frozen specification.
- Current repository evidence: `scanner/src/dogwatch/report.py` already makes error diagnostics take precedence as `inconclusive`, while `scanner/schemas/report-0.2.schema.json` rejects provenance and structured waiver fields. Therefore FR-008 requires `report-0.3.schema.json`, not an additive 0.2 change.
- The prior fixture layout gap recorded in `fixtures/README.md` is resolved by FR-012: each fixture materializes `base` and `candidate` into a temporary Git repository.
- Three release-metadata searches were performed and cross-checked against the official upstream release. The v1.39.0 release supplies the macOS universal, Linux amd64, and Linux arm64 archives and the checksums recorded above. The release also confirms that pinning is material because v1.39.0 changes compatibility findings. [Official release metadata](https://github.com/oasdiff/oasdiff/releases/tag/v1.39.0)
- Decision: `make install-oasdiff` downloads only the fixed release URL for the detected supported platform, verifies the pinned SHA-256 before extraction, rejects unsafe archive paths, atomically installs the executable into an ignored local cache, and verifies `oasdiff --version` reports `1.39.0`. Scans never download tools; an absent or invalid cached tool produces an OpenAPI error diagnostic.
- Decision: policy expiry is optional metadata. When supplied, an expired waiver cannot match and yields an OpenAPI policy diagnostic; tests inject the evaluation date rather than depending on wall-clock time. This implements the Key Entities requirement for expiry “where applicable” without adding a new CLI surface.

## 6. Data Model

| Entity | Fields and validation |
|---|---|
| OpenAPI Contract Declaration | Existing `id` and relative `path`; retain unique kebab-case ID and `.yaml`, `.yml`, or `.json` path validation from FR-002. |
| Baseline Reference | `supplied_ref: str`, `resolved_commit: str`. The supplied ref is mandatory whenever at least one OpenAPI Contract Declaration is scanned; resolve once and use only the immutable commit thereafter. |
| OpenAPI Comparison | `contract_id`, `baseline`, `candidate`, `state`. States are `no-change`, `completed`, `policy-failed`, and `inconclusive`; map `policy-failed` to report status `fail`. |
| Contract Provenance | Base: `ref`, `commit`, `path`, `sha256`; candidate: `path`, `sha256`. Paths are repository-relative and hashes are lowercase SHA-256 of raw input bytes. |
| OpenAPI Finding | `source="openapi"`, `severity`, `check_id`, `locator`, `message`, `fingerprint`, `waiver`, `provenance`. Severity is only `error`, `warning`, or `info`. |
| Locator | `path` is the configured contract path; optional `operation` is normalized as `METHOD /openapi/path`; optional `json_pointer` is RFC 6901. Document-level findings retain `path` and use `operation="document"`. |
| OpenAPI Diagnostic | Existing generic shape: `source="openapi"`, `id`, `severity`, `message`. Error diagnostics always make the aggregate report `inconclusive`. |
| Policy Reclassification | `check_id`, effective `severity`, `reason`. It changes effective severity only, never identity. `off` is invalid because FR-009 permits only Dogwatch’s three output severities. |
| Waiver | `contract_id`, `check_id`, normalized `operation`, `fingerprint`, `baseline_sha256`, `reason`, optional `expires`. Match all identity fields exactly. A matched waiver remains attached to the finding and removes only its gate effect. |
| Fixture Case | Named category, `base` tree, `candidate` tree, expected canonical report, expected exit code, and—where applicable—expected controlled invocation record. |

Fingerprint contract:

```text
openapi/v1:<sha256 of canonical JSON(
  contract_id,
  check_id,
  normalized locator,
  oasdiff finding identity
)>
```

The oasdiff finding identity is required in accepted tool JSON. The message is excluded. Missing or malformed required tool fields are an `openapi-tool-failed` diagnostic, never a fabricated finding.

Comparison transitions:

```text
validated inputs + [] findings                    -> no-change
validated inputs + only warning/info/waived error -> completed
validated inputs + unwaived error                 -> policy-failed
input/Git/tool/output failure                     -> inconclusive
```

## 7. Interface Contracts

### Scanner command

| Method | Request | Response | Errors |
|---|---|---|---|
| `dogwatch check` | Existing `--config PATH`, `--output PATH`; add `--baseline-ref REF`. `REF` is required when the loaded policy declares one or more OpenAPI contracts. | Canonical report schema `0.3`; exit `0` for `pass`, `1` for `fail`, `2` for `inconclusive`. | Missing/invalid baseline input, Git failure, contract failure, or tool failure is emitted as an OpenAPI diagnostic in the report and exits `2`. |

### Policy TOML

```toml
[openapi]

[[openapi.contracts]]
id = "public-api"
path = "api/openapi.yaml"

[[openapi.severity]]
check_id = "request-property-became-required"
severity = "warning"
reason = "Compatibility allowance is documented."

[[openapi.waivers]]
contract_id = "public-api"
check_id = "request-property-became-required"
operation = "POST /pets"
fingerprint = "openapi/v1:..."
baseline_sha256 = "..."
reason = "Migration window is approved."
expires = "2027-01-31"
```

Unknown fields, duplicate policy targets, unsupported severities, malformed hashes, invalid dates, and malformed operation locators are configuration errors. No oasdiff ignore option is exposed.

### Git baseline protocol

| Method | Request | Response | Errors |
|---|---|---|---|
| Local Git argv calls | Resolved repository root, explicit baseline ref, configured repository-relative path. | Immutable commit, regular-file blob bytes, raw SHA-256. | `openapi-baseline-ref-unavailable`, `openapi-baseline-invalid`, or `openapi-git-failed`. |

Use argv-only `git rev-parse`, `git ls-tree`, and `git cat-file`; disable prompts, lazy fetch, replacement objects, and optional locks. Do not use `git show`, checkout, fetch, clone, LFS, or oasdiff Git-revision input syntax.

### oasdiff invocation

```text
<verified-oasdiff>
  changelog
  --format=json
  --level=INFO
  --allow-external-refs=false
  --
  <readonly-baseline-file>
  <readonly-candidate-file>
```

The runner uses `subprocess` with an argv sequence, `stdin=DEVNULL`, an empty private working directory, a controlled environment, concurrent capped stdout/stderr collection, and process termination on cap or timeout. No command interpreter is involved.

| Condition | Diagnostic ID |
|---|---|
| Missing/unverified installed release | `openapi-tool-unavailable` |
| 60-second timeout | `openapi-tool-timeout` |
| stdout cap exceeded | `openapi-tool-stdout-limit-exceeded` |
| stderr cap exceeded | `openapi-tool-stderr-limit-exceeded` |
| Non-zero exit, malformed output, or invalid finding shape | `openapi-tool-failed` |

### Report schema 0.3

`schema_version` becomes `"0.3"` and retains the existing envelope. A finding with `source: "openapi"` requires:

```json
{
  "source": "openapi",
  "check_id": "string",
  "severity": "error | warning | info",
  "message": "string",
  "fingerprint": "openapi/v1:<hex>",
  "waiver": null,
  "locator": {
    "path": "api/openapi.yaml",
    "operation": "GET /pets/{id}",
    "json_pointer": "/paths/~1pets/get"
  },
  "provenance": {
    "base": {
      "ref": "refs/heads/main",
      "commit": "<full git object id>",
      "path": "api/openapi.yaml",
      "sha256": "<64 lowercase hex>"
    },
    "candidate": {
      "path": "api/openapi.yaml",
      "sha256": "<64 lowercase hex>"
    }
  }
}
```

A waived finding replaces `waiver: null` with an object containing `matched: true`, `reason`, and optional `expires`; it remains present. Non-OpenAPI findings retain their current shape. There are no HTTP endpoints, events, or queues in this deliverable.

## 8. Parallelization Strategy

| Stream | Ownership and write scope | Depends on | Integration checkpoint |
|---|---|---|---|
| A — Shared contracts | `config.py`, `contracts.py`, `openapi_policy.py`, `report.py`, `report-0.3.schema.json`, and their direct tests | None | Freeze TOML grammar, report 0.3 projection, waiver shape, and schema validation before integration. |
| B — Safe comparison engine | `openapi.py`, `openapi_git.py`, `openapi_validate.py`, `openapi_tool.py`, installer script, and unit tests | Stream A’s dataclass and diagnostic contracts | Demonstrate local-only baseline reads, preflight rejection, invocation capture, limits, and normalized finding identity. |
| C — Fixture and verification lane | `fixtures/openapi/**`, OpenAPI harness/regenerator/tests, `Makefile`, `README.md`, `fixtures/README.md`, `.gitignore` | Frozen contracts from A; controlled runner seam from B | Materialize temporary Git histories; commit reviewed expected reports; make fixture tests self-contained after verified tool bootstrap. |

Dependency graph:

```text
A: config + report schema
 ├── B: Git/preflight/tool/normalization
 └── C: fixture harness + expected outputs
          └── final integration: CLI scan + complete matrix
```

Write-scope rules:

- Stream A owns shared schema and configuration files until its contract checkpoint is accepted.
- Stream B must not alter report schema or fixture goldens.
- Stream C must not change adapter normalization to make expected outputs pass; output differences are reviewed through the fixed oasdiff pin and explicit golden updates.
- CLI wiring occurs only after A and B agree on the comparison result interface.

Verification matrix:

| Requirement | Workspace proof |
|---|---|
| FR-001 / AC-1 | Temporary Git fixture proves the same configured path is read from an explicit baseline ref and resolved commit. |
| FR-003 | Unit cases cover YAML/JSON 3.0.x, 3.1.x, 3.2.x; unsupported versions, oversized/non-regular inputs, malformed documents, unresolved internal refs, and every external `$ref` form. |
| FR-004 / FR-005 / SC-003 | Captured process record asserts argv use, version/checksum-selected executable, read-only copied inputs, disabled external refs, timeout, and both output caps. |
| FR-006 | No-change fixture produces `pass`, no OpenAPI findings, and no OpenAPI diagnostics. |
| FR-007 / SC-004 | Invalid spec, missing baseline, unavailable ref, timeout, output-limit, and tool-failure fixtures assert diagnostics, no failed-condition finding, `inconclusive`, and exit `2`. |
| FR-008–FR-011 / SC-002 | Schema and golden assertions validate all required finding fields, provenance hashes, deterministic fingerprints, reclassification, and exact-match waiver preservation. |
| FR-012 / FR-013 / SC-001 / SC-005 | Named fixtures cover all eight required categories; repeated runs compare byte-identical serialized reports; timeout and tool-failure cases use the controlled substitute. |
| Regression | `make test-scanner`, `make test-fixtures`, and `make lint-scanner` pass from the repository root. |
