## Overview

The OpenAPI adapter compares each configured YAML or JSON candidate contract with the contract at the identical relative path from an explicit baseline Git ref, using a fixed oasdiff release. It gives maintainers trustworthy compatibility findings while keeping malformed inputs, unavailable baselines, and tool faults distinct from actual compatibility-policy failures. This draft reuses the current Dogwatch contract declarations and report status model, and incorporates the prior research at `.am/reports/5b28548a-4c88-4600-b7cc-a6df1df95c7b-research-paper.md`.

## User Scenarios

### P1 — Compare a configured contract

A maintainer runs Dogwatch with an explicit baseline Git ref to identify compatibility changes in a configured OpenAPI contract.

- Given a configured candidate contract and an explicit baseline Git ref that contains the same relative path, when the adapter completes successfully, then it reports every detected OpenAPI compatibility finding in the standard report.

- Given a configured candidate contract, when the contract is unchanged from its baseline counterpart, then the report contains no OpenAPI findings or OpenAPI diagnostics and the OpenAPI comparison succeeds.

### P1 — Receive an actionable compatibility finding

A maintainer reviews a reported compatibility break and can identify what changed and the two contract versions compared.

- Given an oasdiff-detected compatibility change, when the adapter emits its finding, then the finding includes severity, check ID, locator, human message, fingerprint, and base/candidate provenance.

- Given multiple findings from one comparison, when the report is serialized, then each finding remains individually identifiable by its fingerprint and locator.

### P1 — Distinguish execution problems from policy failures

A maintainer can tell whether a scan found a compatibility failure or could not reliably compare the contracts.

- Given an invalid candidate or baseline contract, a missing baseline contract, an unavailable baseline ref, or an oasdiff failure, when the adapter cannot complete a valid comparison, then it emits an OpenAPI diagnostic and does not emit a compatibility-policy finding for that condition.

- Given an OpenAPI diagnostic with error severity, when the report status is derived, then the status is `inconclusive`, not `fail`.

### P2 — Govern a finding without hiding it

A policy owner can reclassify or waive a known finding through the Dogwatch policy, while preserving an auditable result.

- Given a configured severity reclassification for an oasdiff check, when that check is found, then the finding reports the effective configured severity.

- Given a configured waiver that exactly matches an OpenAPI finding, when that finding is reported, then the finding remains present with waiver information and does not cause a failed policy gate.

### P2 — Maintain regression coverage

A contributor can verify the adapter’s behavior against a controlled compatibility-fixture matrix.

- Given the fixture matrix, when the automated adapter tests run, then each scenario is compared with its pinned expected output.

- Given an update to the oasdiff pin or finding normalization rules, when the fixture outputs change, then the changed expected outputs require deliberate review rather than being regenerated implicitly.

## Functional Requirements

1. **FR-001 — Baseline comparison. [AC-1]** The adapter compares the configured candidate contract with the same path from an explicit baseline Git ref. The baseline ref is required for every OpenAPI comparison and has no inferred default.

2. **FR-002 — Candidate contract scope. [Added: existing `openapi.contracts` declarations accept relative `.yaml`, `.yml`, and `.json` paths.]** Each configured OpenAPI contract is identified by its existing unique contract ID and relative path. The candidate input is the regular file at that path in the candidate checkout; the baseline input is the regular file at the byte-identical relative path in the resolved baseline commit.

3. **FR-003 — Supported contract inputs. [Added: the adapter needs an explicit, testable support boundary.] [Q: q-contract-size-limit]** The adapter accepts single-file OpenAPI 3.0.x, 3.1.x, and 3.2.x documents in YAML or JSON, each with a raw size of at most 5 MiB independently for candidate and baseline inputs. It rejects Swagger/OpenAPI 2.0, unsupported OpenAPI major versions, non-file inputs, oversized inputs, and documents containing external `$ref` values with OpenAPI diagnostics.

4. **FR-004 — Fixed tool release. [AC-2] [Q: q-oasdiff-artifact-pin]** oasdiff invocation uses an argv list, pinned version, read-only temporary files, timeout/output limits, and disabled external reference loading. The selected release is oasdiff `v1.39.0`; the adapter executes the official release binary for its supported platform and verifies its archive against a pinned checksum.

5. **FR-005 — Safe execution outcome. [AC-2]** The adapter invokes oasdiff without a command interpreter, exposes only read-only comparison inputs to the tool, disables external reference loading, and enforces a 60-second execution limit, a 16 MiB standard-output limit, and a 1 MiB standard-error limit.

6. **FR-006 — No-change behavior. [AC-3]** No-change contracts yield a successful report with no OpenAPI findings. A successful no-change comparison produces neither an OpenAPI finding nor an OpenAPI diagnostic.

7. **FR-007 — Diagnostic behavior. [AC-3]** Invalid/missing inputs and tool failures yield diagnostics rather than false policy failures. The affected comparison produces no compatibility finding for the failed condition, and an error diagnostic makes the report `inconclusive`.

8. **FR-008 — Finding shape. [AC-4] [Q: q-report-schema-evolution]** Every OpenAPI finding includes severity, check ID, locator, human message, fingerprint, and base/candidate provenance. The standard report publishes a new versioned schema carrying the required OpenAPI provenance and waiver information for every OpenAPI finding.

9. **FR-009 — Finding normalization. [Added: current reports require deterministic, schema-validated findings.]** Each OpenAPI finding uses the existing Dogwatch severity vocabulary (`error`, `warning`, or `info`), has source `openapi`, and carries a stable fingerprint derived from its contract ID, check ID, normalized operation locator, and oasdiff finding identity. The human message is not part of the fingerprint.

10. **FR-010 — Provenance. [AC-4]** Each OpenAPI finding’s base provenance includes the supplied baseline ref, the resolved baseline commit, contract path, and raw-content SHA-256. Its candidate provenance includes the contract path and raw-content SHA-256. Both provenance objects identify the compared contract bytes.

11. **FR-011 — Severity and waiver ownership. [Added: the ticket requires ignored/reclassified fixture coverage; prior CD-4 research assigns policy ownership to Dogwatch.] [Q: q-openapi-policy-scope]** A repository-wide OpenAPI policy, rather than oasdiff ignore options, owns severity reclassification and waivers. A waiver applies only when it exactly matches the contract ID, check ID, normalized operation locator, fingerprint, and baseline raw-content SHA-256; waived findings remain in the report.

12. **FR-012 — Fixture matrix. [AC-5] [Q: q-history-fixture-layout]** The researched fixture matrix is covered by automated tests using pinned expected outputs. It includes no change, removed operation, optional-to-required field, enum or constraint break, invalid spec, missing baseline, timeout or tool failure, and ignored or reclassified finding. Tests materialize `base` and `candidate` inputs into a temporary Git repository to create the controlled explicit baseline revision for each fixture.

13. **FR-013 — Test isolation. [Added: AC-2 and AC-5 require safe, reproducible proof.]** Automated timeout and tool-failure cases use a controlled test substitute and must not depend on a live external service, external `$ref`, network access, or a mutable oasdiff release.

## Key Entities

- **OpenAPI Contract Declaration**
  - Attributes: `id`, relative `path`.
  - Relationship: one declaration identifies one candidate contract and its same-path baseline counterpart.

- **Baseline Reference**
  - Attributes: supplied Git ref, resolved commit identifier.
  - Relationship: supplies the immutable baseline revision for every OpenAPI Contract Declaration comparison.

- **OpenAPI Comparison**
  - States: `completed`, `no-change`, `policy-failed`, `inconclusive`.
  - Transitions:
    - valid inputs and no findings → `no-change`;
    - valid inputs and unwaived error findings → `policy-failed`;
    - valid inputs and only non-error or waived findings → `completed`;
    - invalid input, missing baseline, unavailable ref, timeout, output-limit breach, or tool failure → `inconclusive`.

- **OpenAPI Finding**
  - Attributes: source, severity, check ID, locator, message, fingerprint, waiver state, base provenance, candidate provenance.
  - Relationship: belongs to one OpenAPI Comparison.

- **OpenAPI Diagnostic**
  - Attributes: source, diagnostic ID, severity, message.
  - Relationship: belongs to one OpenAPI Comparison and explains why a reliable finding result was unavailable.

- **Policy Reclassification / Waiver**
  - Attributes: target check ID, effective severity or waiver identity, reason, and expiry where applicable.
  - Relationship: is declared in the repository-wide OpenAPI policy and applies to matching OpenAPI Findings; a waiver is bound to the baseline content hash and contract ID.

- **Fixture Case**
  - Attributes: named scenario, controlled baseline revision, candidate input, expected report output.
  - Relationship: materializes `base` and `candidate` inputs into a temporary Git repository and verifies one or more OpenAPI Comparison outcomes.

## Success Criteria

1. **SC-001 — Matrix coverage.** Automated tests pass for 100% of the eight required fixture categories in FR-012. Measurement: the workspace test command reports one passing assertion set for each named category.

2. **SC-002 — Required finding content.** 100% of OpenAPI findings in pinned fixture outputs include all six AC-4 fields. Measurement: schema and fixture assertions validate severity, check ID, locator, message, fingerprint, base provenance, and candidate provenance for every emitted finding.

3. **SC-003 — Safe invocation behavior.** 100% of adapter execution-path tests confirm direct argument-vector invocation, disabled external references, read-only inputs, the fixed timeout, and both output limits. Measurement: automated tests inspect the controlled invocation record and exercise timeout and output-limit failures.

4. **SC-004 — Correct failure classification.** 100% of invalid-spec, missing-baseline, unavailable-baseline, timeout, and tool-failure fixtures produce diagnostics and no compatibility-policy finding for the failed condition. Measurement: expected reports assert diagnostic IDs and `inconclusive` status.

5. **SC-005 — Deterministic expected outputs.** Two consecutive runs of every fixture produce byte-identical expected report output. Measurement: the fixture harness compares serialized reports from repeated runs.

## Edge Cases

- The configured candidate path does not exist, is not a regular file, or exceeds the 5 MiB raw input-size limit.
- The baseline ref cannot be resolved locally, including a shallow or partial checkout without the needed commit or blob.
- The baseline commit exists but does not contain the configured path.
- The baseline entry is not a regular YAML or JSON contract file.
- Either contract is malformed YAML or JSON, lacks a supported OpenAPI version, or contains an unresolved internal reference.
- Either contract contains a local, remote, URI-like, or otherwise non-internal `$ref`.
- oasdiff exits unsuccessfully, exceeds the timeout, exceeds either output cap, or returns malformed output.
- A finding has no operation-level location; its locator still identifies the configured contract and available document location.
- Two findings share visible locator and message fields; their fingerprints must remain distinct when oasdiff identifies them as distinct changes.
- A reclassification affects a finding’s severity but not its identity.
- A waiver’s baseline hash no longer matches the resolved baseline; it must not suppress the finding.
- Other scanner domains may independently affect the overall report; a no-change OpenAPI comparison itself contributes no OpenAPI failure.

## Assumptions

- The adapter reads baseline objects from the local repository only; it does not fetch refs, clone repositories, or alter checkout state.
- The candidate contract is checked into the candidate checkout. Consumer request/response fixture validation is explicitly outside this deliverable.
- The selected oasdiff version is `v1.39.0` because upstream released it on 2026-11-17 and its release material includes external-reference hardening introduced after the prior CD-4 paper’s `v1.33.0` selection.
- The current report’s `error` diagnostic behavior remains authoritative: an error diagnostic yields `inconclusive`; unwaived error findings yield `fail`.
- The existing `openapi.contracts` ID and relative-path conventions remain stable.
- The adapter executes official oasdiff `v1.39.0` release binaries verified against pinned archive checksums.
- Baseline-history fixtures use `base` and `candidate` inputs materialized into a temporary Git repository by the test harness.

## Clarification Decisions

- q-oasdiff-artifact-pin → Official release binaries with pinned archive checksums.
- q-report-schema-evolution → Publish a new versioned report schema with the OpenAPI fields required.
- q-openapi-policy-scope → Repository-wide OpenAPI policy, with waivers explicitly matching a contract ID.
- q-history-fixture-layout → `base` and `candidate` inputs materialized into a temporary Git repository by the test harness.
- q-contract-size-limit → 5 MiB.
