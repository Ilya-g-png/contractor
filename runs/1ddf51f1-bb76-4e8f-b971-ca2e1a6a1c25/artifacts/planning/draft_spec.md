I now have a complete picture: the CD-5 bootstrap (scanner skeleton with minimal config/report/exit-code contracts), and the three ADRs CD-6 implements (CD-3 policy config semantics, CD-4 adapter/report finding shape, CD-2 provenance/report lifecycle). I've verified the existing code contracts (exit codes 0/1/2 with 1 reserved, canonical JSON serialization, golden-fixture determinism, config-dir anchoring, trust-boundary test). Now I'll write the draft specification.

---

# Draft Specification — CD-6: Validated Dogwatch Configuration and Common Report Contracts

## Overview

Dogwatch is a policy gate: it reads a `dogwatch.toml` policy file, checks a repository against it, and emits one deterministic JSON report whose exit code a CI pipeline can gate on. CD-6 delivers the two contracts every later component depends on: (1) the validated configuration model selected by the CD-3 policy ADR (`/Users/iliaglushkov/Documents/sandbox/contractor/.am/reports/7ee72c98-20e3-41ff-9321-386775b7a72e-research-paper.md`) — explicit scanned Python packages, exclusions, named rules, and optional OpenAPI contract paths, each rejected with a precise diagnostic before any scanning starts; and (2) the common report model shared by every adapter, per the CD-4 adapter ADR (`/Users/iliaglushkov/Documents/sandbox/contractor/.am/reports/5b28548a-4c88-4600-b7cc-a6df1df95c7b-research-paper.md`) and the CD-2 report-lifecycle ADR (`/Users/iliaglushkov/Documents/sandbox/contractor/.am/reports/9c37b285-b35d-4dc2-be1c-2347272422e0-research-paper.md`) — scan status, provenance, normalized findings, and diagnostics with stable JSON serialization. The core safety property, in the ticket's own words: "A report must distinguish a policy violation from scanner or adapter infrastructure failure" — a policy violation is a **finding** that fails the gate (exit 1); an infrastructure failure is a **diagnostic** that makes the run inconclusive (exit 2); a malformed config fails before scanning with no report (exit 2). This spec is the delta over the CD-5 bootstrap (`scanner/src/dogwatch/{config,report,diagnostics,cli,output}.py`, `scanner/schemas/report-0.1.schema.json`, `fixtures/minimal/`): the config surface grows from packages-only to the full AC-2 declaration set, and the report grows from an empty-findings stub to the common status/findings/diagnostics model.

## User Scenarios

### US-1 — Valid full-surface config scans cleanly (P1)
A developer runs the scanner on a repository whose policy declares everything AC-2 allows and gets a deterministic, machine-verifiable report.

- **Given** a repository with a `dogwatch.toml` declaring at least one `[[python.packages]]` entry, an `[python] exclude` list, one or more `[[python.rules]]`, and one `[[openapi.contracts]]` entry with a checked-in spec file, all structurally valid
- **When** the developer runs `dogwatch check`
- **Then** the CLI writes a report with `status: "pass"`, empty `findings` and `diagnostics` arrays, and exits 0
- **Given** the same repository and the same scanner version
- **When** the developer runs `dogwatch check` again
- **Then** the report bytes are identical to the first run (no wall-clock, random, or environment-dependent values)

### US-2 — Malformed config fails precisely, before scanning (P1)
A developer with a broken policy file learns exactly which key is wrong without the scanner touching the source tree as a scan.

- **Given** a `dogwatch.toml` with a structural defect (for example, a rule with a duplicate id, a `forbid` rule without `targets`, or an exclusion glob matching nothing)
- **When** the developer runs `dogwatch check`
- **Then** no report file is written, the exit code is 2, and stderr carries a diagnostic naming the offending config path (e.g. `python.rules[1].id`) and the violated constraint
- **Given** a config that is not valid TOML
- **When** the developer runs `dogwatch check`
- **Then** the diagnostic includes the TOML line number of the syntax error

### US-3 — Adapter implementers build on one shared contract (P1)
Engineers implementing the later Python policy engine and OpenAPI adapter produce findings and failures through the same report model, so their results are never confused.

- **Given** the shared report model from this ticket
- **When** an adapter records a policy violation, it emits a normalized **finding** (rule id, severity, locator, stable fingerprint)
- **And** when an adapter or the scanner cannot complete its work (tool crash, unparseable source), it emits a **diagnostic**, never a finding
- **Then** the CLI derives the exit code from the report alone: `fail` → 1, `inconclusive` → 2, so a policy violation is never mistaken for an infrastructure failure or vice versa

### US-4 — CI never treats an infrastructure failure as a pass (P2)
A CI pipeline consuming the exit code can gate correctly on all four failure modes of AC-4.

- **Given** a CI step running `dogwatch check`
- **When** the scan is inconclusive (an adapter failure or an invalid source file appears as an error-severity diagnostic)
- **Then** the report says `status: "inconclusive"` with the diagnostic present, the exit code is 2, and the pipeline fails — visibly distinct from a policy violation's `status: "fail"` and exit 1
- **Given** a config failure
- **When** the step runs
- **Then** no report exists, the config diagnostic is on stderr, and the exit code is 2 — distinguishable from an inconclusive scan by the absence of a report

### US-5 — Golden fixtures keep the contract honest (P2)
A fixture maintainer regenerates expected reports once and verifies byte-exactness forever after.

- **Given** the report model changes shape in this ticket (schema version 0.1 → 0.2)
- **When** the maintainer runs the fixture regeneration command
- **Then** existing fixtures' goldens are rewritten for the new shape without changing their configs, and a new fixture covering the full AC-2 config surface (packages, exclusions, rules, an OpenAPI contract) gains its golden
- **And** when the fixture test runs, every golden matches the scanner's output byte for byte

### US-6 — A Python-only repository needs no OpenAPI declaration (P3)
A repository with no API contracts is not forced to declare any.

- **Given** a `dogwatch.toml` with packages, exclusions and rules but no `[[openapi.contracts]]` entries
- **When** the developer runs `dogwatch check`
- **Then** the config is valid and the run proceeds exactly as US-1 (the OpenAPI declaration is optional per AC-2)

## Functional Requirements

### Configuration loading and validation (AC-1, AC-2)

**FR-001** [AC-1] Loading a config that does not exist, is not a readable regular file, is not valid UTF-8, or is not valid TOML fails before any scanning: no report is written, the exit code is 2, and a diagnostic identifies the file and — for TOML syntax errors — the line number. *(Existing CD-5 behavior, kept as the AC-1 floor.)*

**FR-002** [AC-1] Every config-validation failure emits at least one diagnostic that names the offending config path as a TOML key path (e.g. `python.packages[0].name`, `python.rules[1].targets[0]`, `openapi.contracts[0].path`) and states the violated constraint. Independent structural failures of the same kind may be reported together in one run; the requirement is precision, not aggregation.

**FR-003** [AC-2] A valid config declares at least one scanned Python package as `[[python.packages]]` entries with `name` (a single top-level Python identifier) and `root` (a directory path relative to the config file's directory). The existing package validations — root directory exists and is a directory, no duplicate package names, no package nested inside another, no dotted name split across roots — continue to reject invalid declarations with precise diagnostics before scanning. *(Existing; AC-2's "explicit scanned Python packages".)*

**FR-004** [AC-2] A valid config declares exclusions as `[python] exclude`, an array of glob patterns anchored at the config file's directory and written with `/`, where `*` matches within one path segment and `**` matches across segments; no other wildcard or regex syntax is accepted, matching is case-sensitive, and symlinks are not followed. Each pattern must match at least one file under a declared package root (exclusions act on source files only); a pattern that matches nothing fails before scanning with an `exclude-unmatched` diagnostic and exit 2. An absent or empty `exclude` list is valid.

**FR-005** [AC-2] A valid config declares named rules as `[[python.rules]]` entries. Each rule has a required `id` matching `^[a-z][a-z0-9]*(-[a-z0-9]+)*$` with at most 64 characters, unique across all rules; a required `kind` of `forbid` or `layers`; and a required non-empty `reason` string.

**FR-006** [AC-2] A `forbid` rule declares `targets` (required, non-empty, each entry a dot-separated selector whose every segment is a valid Python identifier) and optionally `sources`, `except_sources`, and `except_targets` (each, when present, a non-empty list of valid selectors). Every `except_sources` entry must be a strict descendant of some `sources` entry, and every `except_targets` entry a strict descendant of some `targets` entry; otherwise the config is invalid. When `sources` is absent, the rule's source scope defaults to all scanned packages.

**FR-007** [AC-2] A `layers` rule declares `layers` (required, non-empty, ordered, each entry a valid selector, no duplicates, and no entry a dotted-prefix of another so layer assignment is unambiguous) and optionally `container` (a valid selector) and `exhaustive` (boolean, default `false`). When `exhaustive` is `true`, `container` is required and every `layers` entry must be a strict descendant of `container`.

**FR-008** [AC-2] A valid config optionally declares OpenAPI contracts as `[[openapi.contracts]]` entries with `id` (unique across contracts, same ID rules as FR-005) and `path` (relative to the config file's directory, `/`-separated, extension `.yaml`, `.yml` or `.json`, no `..` segments, no absolute paths, unique across contracts). Zero contracts is valid. Contract file existence is not checked at validation time — a missing candidate contract is a runtime adapter diagnostic, not a config error.

**FR-009** [AC-1] Any config key outside the accepted surface — at the top level, under `[python]`, or inside a package, rule, or contract entry — fails validation with a diagnostic that names the unsupported key, before scanning. *(The established CD-5 "not supported in this version" pattern, extended to the new surface.)*

> **[NEEDS CLARIFICATION — accepted config surface]** AC-2 names packages, exclusions, named rules, and optional OpenAPI contract paths. The CD-3/CD-4 ADRs also define `[python] type_checking`, `clock`, `max_waiver_days`, `[[python.waivers]]`, the baseline file, and the `[openapi]` settings keys (`timeout_seconds`, `max_spec_bytes`, `stability_level`, `allow_missing_baseline`, `[[openapi.severity]]`, `[[openapi.waivers]]`) — keys whose semantics only take effect once the policy engine and adapters exist. Default applied (see A-2): the CD-6 validator accepts exactly the AC-2 declarations and their structural sub-keys and rejects every other key per FR-009. Confirm this, or instruct the validator to accept and structurally validate the full ADR surface now.

### Common report model (AC-3)

**FR-010** [AC-3] Every completed run produces exactly one report envelope with these fields, all always present: `schema_version` (`"0.2"`), `status`, `scanner` (`name`, `version`), `policy` (`path` — the config file's base name — and `digest.sha256` over the config's raw bytes), `findings` (array), and `diagnostics` (array). `scanner` and `policy` are the report's provenance block.

> **[NEEDS CLARIFICATION — provenance depth]** AC-3 requires "provenance" without naming fields. The CD-2 ADR's provenance schema adds repository identity, commit/ref/dirty, `base_sha`, `evaluation_date`, scan timestamps, and `report_id`. Several of those are git-derived (fixture projects are not git repositories; git-history fixtures are pending per `fixtures/README.md` OQ-8) or non-deterministic (wall-clock timestamps, a UUID `report_id`), which conflicts with the repo's byte-identical golden contract (`make -s run-scanner | diff - fixtures/minimal/expected-report.json`). Default applied (see A-4): provenance = `scanner` + `policy` only; the workflow fields arrive with their consuming tickets, each with a `schema_version` bump. Confirm this, or instruct the model to adopt the fuller CD-2 provenance now, which requires the golden harness to pin or normalize the volatile fields.

**FR-011** [AC-3] `status` is one of `pass`, `fail`, `inconclusive`, derived only from the report's contents: `inconclusive` if any diagnostic in the report has severity `error`; otherwise `fail` if any finding has severity `error` and is not waived; otherwise `pass`. Warning- and info-severity entries never change the status.

**FR-012** [AC-3] A normalized **finding** carries: `source` (the producing adapter's name), `check_id` (the rule id violated), `severity` (`error` | `warning` | `info`), `message` (display-only text), `fingerprint` (a stable identity derived deterministically from the finding's rule, source and target — never from line numbers, message text, or timestamps, so the same violation keeps its fingerprint across reformats), `waiver` (always `null` in this version; the field exists so the later engine can populate it without a model change), and a `locator` (at minimum the file path relative to the config file's directory; line and column where the adapter knows them; plus the adapter's logical location — for Python findings, the source and target module names).

**FR-013** [AC-3] A **diagnostic** carries: `source` (the producing component — the scanner or an adapter), `id` (kebab-case, in the reserved `dogwatch` namespace), `severity` (`error` | `warning` | `info`), and `message`. Diagnostics represent scanner and adapter events — never policy violations. This ticket names two scan-time diagnostic ids for the AC-4 modes: `source-syntax-invalid` (the scanner cannot parse a declared source file) and the adapter-failure class (an error diagnostic whose `source` is an adapter; adapters use their own specific ids within this class, e.g. the OpenAPI adapter's tool-failure ids from the CD-4 ADR).

**FR-014** [AC-3] Report serialization is stable: the report is serialized as UTF-8 JSON with sorted keys, two-space indentation, non-ASCII preserved literally, and a trailing newline (the established canonical form); identical inputs produce byte-identical output; the report contains no wall-clock timestamps, random identifiers, or environment-dependent values.

**FR-015** [AC-3] [Added: the repo already pins the report shape with a versioned JSON Schema and validates output against it (`scanner/schemas/report-0.1.schema.json`, `tests/test_schema.py`); keeping that pin is part of the contract, not new scope] The report's JSON shape is pinned by a versioned JSON Schema document shipped in the repo (following the existing `schemas/` naming convention for version `"0.2"`), and every report the CLI writes validates against it.

### CLI exit behavior (AC-4)

**FR-016** [AC-4] The CLI's exit code is a pure function of the run outcome, so it is testable without any adapter present: `0` when a report is written with status `pass`; `1` when a report is written with status `fail`; `2` for a pre-scan config failure (no report written), a report with status `inconclusive`, a usage error, or a report-write failure. *(The existing constants: 0 pass, 1 gate-failed — reserved in CD-5, defined and mapped here — 2 error.)*

**FR-017** [AC-4] The four modes of AC-4 are distinguishable by the report and CLI exit behavior, each producing a unique (report, exit) pair:
- **policy violation** → an error-severity finding in the report, `status: "fail"`, exit 1;
- **malformed config** → a config diagnostic on stderr (`config-not-found`, `config-invalid`, or `exclude-unmatched`), no report, exit 2;
- **invalid source syntax** → a `source-syntax-invalid` error diagnostic in the report, `status: "inconclusive"`, exit 2;
- **adapter failure** → an adapter error diagnostic in the report (distinct id and `source`), `status: "inconclusive"`, exit 2.

**FR-018** [AC-4] [Added: a failed run's cause must be visible in CI logs without parsing the report; extends the established stderr render format] Scan-time diagnostics carried in the report are also rendered to stderr in the established `dogwatch:<id>: <message>` format.

> **[NEEDS CLARIFICATION — end-to-end triggerability of AC-4's modes]** CD-6 delivers the contracts; the policy engine and adapters are later tickets, so of AC-4's four modes only "malformed config" can be triggered end-to-end through the CLI today. Default applied (see A-5): contract-level satisfaction — the report model and exit mapping represent all four modes, and tests construct each mode and assert its (report, exit) pair per FR-016/FR-017. Confirm this, or instruct CD-6 to add a minimal scan step (e.g. parsing declared, non-excluded sources) so "invalid source syntax" is also triggerable end-to-end.

### Fixtures — the end-to-end proof (added criterion)

**FR-019** [Added: the golden-fixture harness is this repo's established end-to-end verification (`make test-fixtures`, `make regen-fixtures`); AC-2's full config surface needs one end-to-end proof] The fixture set gains one new fixture directory whose `dogwatch.toml` declares all four AC-2 surfaces — packages, exclusions, named rules (at least one `forbid` and one `layers`), and an OpenAPI contract with a checked-in static spec file — and whose golden report (status `pass`, empty findings and diagnostics) is generated by the regeneration command and verified byte-identical by the fixture test. Existing fixtures keep their configs and layouts; their goldens regenerate for schema `"0.2"`.

## Key Entities

- **DogwatchConfig** (validated policy, immutable): `path_arg` (as given on the CLI), `raw` (config bytes), `packages` (tuple of PackageDecl), `exclusions` (tuple of ExclusionDecl), `rules` (tuple of RuleDecl), `contracts` (tuple of OpenApiContractDecl). Produced only by successful validation; a failed validation produces diagnostics instead.
- **PackageDecl**: `name` (top-level identifier), `root` (config-dir-relative directory).
- **ExclusionDecl**: `pattern` (glob, per FR-004).
- **RuleDecl**: `id`, `kind` (`forbid` | `layers`), `reason`; `forbid` adds `sources?`, `targets`, `except_sources?`, `except_targets?`; `layers` adds `layers` (ordered), `container?`, `exhaustive` (bool).
- **OpenApiContractDecl**: `id`, `path`.
- **Report**: `schema_version` ("0.2"), `status`, `scanner {name, version}`, `policy {path, digest {sha256}}`, `findings []`, `diagnostics []`.
- **Finding**: `source`, `check_id`, `severity`, `message`, `fingerprint`, `waiver`, `locator {path, line?, column?, logical location}`.
- **Diagnostic**: `source`, `id`, `severity`, `message`.
- **Status** (enum): `pass` | `fail` | `inconclusive`.
- **ExitCode** (enum): `0` pass · `1` fail · `2` error/inconclusive/config.

**Relationships**: one DogwatchConfig produces one Report per run; findings reference rule ids declared in the config; diagnostics reference scanner/adapter component names, never rule ids as violations.

**State transitions (run lifecycle)**:
1. config file → *load* → parsed document (failure here or below ⇒ pre-scan failure: diagnostic on stderr, no report, exit 2)
2. parsed document → *validate* (FR-003–FR-009) → DogwatchConfig
3. DogwatchConfig → *scan* (in this ticket: no findings or diagnostics are produced; rule evaluation arrives with the engine ticket) → findings + diagnostics
4. findings + diagnostics → *derive status* (FR-011: error diagnostic ⇒ inconclusive; else unwaived error finding ⇒ fail; else pass)
5. status → *map exit* (FR-016: pass ⇒ 0, fail ⇒ 1, inconclusive ⇒ 2) and → *serialize + write report* (FR-014)

## Success Criteria

- **SC-001**: Every invalid-config case enumerated under Edge Cases produces a diagnostic naming the offending config path. *Measured by*: the scanner test suite — one test per enumerated case asserting the diagnostic id and that the message contains the config path; target 100% of enumerated cases covered.
- **SC-002**: The four AC-4 modes produce four mutually distinguishable (report, exit-code) pairs. *Measured by*: tests that trigger or construct each mode and assert the full pair (status, findings/diagnostics present, exit code); 4 of 4 modes covered, zero identical pairs.
- **SC-003**: Report serialization is byte-stable. *Measured by*: running the CLI twice on the same fixture and comparing bytes (zero differences), plus the golden fixture test passing without regeneration.
- **SC-004**: All existing quality gates stay green. *Measured by*: `make test-scanner`, `make lint-scanner`, and `make test-fixtures` all exit 0 (these include strict type-checking, linting, and the full test suite).
- **SC-005**: Every report the CLI writes validates against the shipped JSON Schema. *Measured by*: the schema-validation test running over every golden fixture report and every constructed-mode report; 100% pass.

## Edge Cases

**Config file**: missing path; path is a directory; unreadable file; non-UTF-8 bytes; TOML syntax error (diagnostic carries line number); empty file (parses as empty document ⇒ "requires at least one `[[python.packages]]` entry"); zero packages.

**Packages**: non-string `name`/`root`; `name` not a single identifier (dotted, kebab, keyword); root directory missing; root is a file; duplicate names in the same root; same name split across roots; two packages nested one inside the other.

**Exclusions**: non-array `exclude`; non-string entry; empty pattern; absolute pattern; `..` or `.` segment; `?`, `[`, or `\` in a pattern (only `*`/`**` allowed); pattern matching only directories or only files outside declared package roots (⇒ `exclude-unmatched`); two patterns where one makes the other match nothing (each is checked independently).

**Rules**: missing `id`/`kind`/`reason`; id over 64 characters; id with uppercase, underscores, or colons; duplicate ids; unknown `kind`; `forbid` without `targets` or with an empty list; selector with an empty or non-identifier segment (`a..b`, `foo-bar`); `except_sources` entry not a strict descendant of any `sources` entry (same for `except_targets`); empty `sources`/`except_*` arrays; `layers` empty, containing duplicates, or with one entry a prefix of another (`a` and `a.b`); `exhaustive = true` without `container`; a `layers` entry not a strict descendant of `container` (including the container itself); unknown keys inside a rule entry.

**OpenAPI contracts**: missing `id`/`path`; duplicate ids; duplicate paths; extension other than `.yaml`/`.yml`/`.json`; absolute path; `..` segment; backslash separators; unknown keys inside a contract entry; a declared contract whose file does not exist (valid at config time per FR-008 — runtime adapter concern).

**Report and exit**: an error finding and an error diagnostic in the same report ⇒ status `inconclusive` (fail-closed: the scan cannot vouch, even though violations were also found); warning/info findings and diagnostics never change status; non-ASCII text in config or messages (digest is over raw bytes; JSON preserves non-ASCII literally); a `pass` report with warnings present.

**CLI**: `--output` path equal to the config path (existing guard, exit 2); unwritable output directory (exit 2, no partial report); stdout output mode with a broken pipe (existing handling); usage errors (exit 2, usage on stderr).

**Trust boundary**: the exclusion-validation tree walk lists directories under declared package roots but never reads file contents there and never imports or executes scanned code; the existing trust-boundary test is updated to this narrowed invariant (the "never import user code" guarantee is absolute and unchanged).

## Assumptions

- **A-1 (scope)**: This ticket delivers contracts only — the config parser/validator and the shared report models. Rule evaluation (the Python engine), the OpenAPI adapter run, waivers/baseline enforcement, and report upload are later tickets that consume these contracts. In CD-6 the scan step produces no findings or diagnostics for a valid config, so a valid config's report is `pass` with empty arrays; that is honest for the checks that exist and changes when the engine lands.
- **A-2 (config surface — default for clarification 1)**: The accepted config surface is exactly AC-2's four declarations plus their structural sub-keys (FR-003–FR-008). `type_checking`, `clock`, `max_waiver_days`, `[[python.waivers]]`, the baseline file, and the `[openapi]` settings/severity/waiver keys are rejected as unsupported until their consuming tickets, because their semantics (expiry vs evaluation date, unused-vs-findings) cannot be validated without an engine.
- **A-3 (cardinalities)**: At least one package is required (existing). Zero exclusions, zero rules, and zero OpenAPI contracts are all valid: AC-2 enumerates the declarable surface, and "optional" singles out OpenAPI as the declaration whose absence is normal for Python-only repos. This keeps the existing `fixtures/minimal` config (packages only) valid.
- **A-4 (provenance — default for clarification 2)**: Provenance is `scanner` + `policy` (the existing block, carried into the common model). CD-2's workflow provenance (repository, commit/ref/dirty, `base_sha`, `evaluation_date`, timestamps, `report_id`) arrives with the tickets that consume it, each bumping `schema_version` — preserving the byte-identical golden contract, which wall-clock timestamps and a random `report_id` would break.
- **A-5 (AC-4 verification — default for clarification 3)**: Contract-level satisfaction: the model and exit mapping represent all four modes and tests construct each mode. Only "malformed config" is additionally triggerable end-to-end today.
- **A-6 (exit mapping)**: 0/1/2 per the existing constants and the CD-4 ADR ("0 pass · 1 gate failed · 2 inconclusive; CI must never treat 2 as a pass"). Config failure and inconclusive share exit 2 and are distinguished by report presence plus diagnostics; status precedence is inconclusive > fail > pass.
- **A-7 (no report on pre-scan failure)**: A malformed config writes no report — it fails before scanning (AC-1), and a report describes a scan. This is the existing, tested CD-5 behavior.
- **A-8 (schema version)**: The report's `schema_version` moves `"0.1"` → `"0.2"`; the schema file naming follows the existing `schemas/` convention.
- **A-9 (anchoring)**: Package roots, exclusion globs, OpenAPI contract paths, and finding locator paths all resolve relative to the config file's directory — the existing in-repo convention (roots already do), which coincides with the ADRs' repo-relative wording for the normal root-level `dogwatch.toml`.
- **A-10 (rule reason)**: Non-empty string required (CD-3 requires a reason for rules; the ≥15-character minimum applies to waivers, which are out of scope here).
- **A-11 (exclusion match scope)**: "A glob that matches nothing" (CD-3 §2.7) is made precise as "matches no file under any declared package root", because exclusions act only on source files.
- **A-12 (preserved CLI behavior)**: `--config`/`--output` defaults, stdout output mode, atomic report writes, the same-file guard, `--version`, and the canonical serialization form are unchanged from CD-5.
- **A-13 (adapter-specific finding detail)**: The common finding carries the fields both adapters share (FR-012). Adapter-specific detail (e.g. the OpenAPI adapter's severity-override provenance or per-finding base/candidate provenance from the CD-4 ADR) extends the model in those adapters' tickets.

## Proposals (not requirements)

- **P-1**: Ship the CD-3 ADR's three example policies (layered package, two-package monorepo, banned third-party dependency) as documented example configs in the repo, so users can copy a known-good starting point.
- **P-2**: Add a `dogwatch validate` subcommand that runs config validation only and writes no report — fast feedback for editors and CI preflight without producing an artifact.
- **P-3**: Publish a JSON Schema for the `dogwatch.toml` config file itself, enabling editor validation and autocomplete of the AC-2 surface.
- **P-4**: Include the effective rule metadata (ids, reasons) in the report, as the CD-2 ADR's workflow envisions for dashboard context — deferred until the engine ticket can populate findings that reference it.
