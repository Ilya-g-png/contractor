The CD-6 work splits into seven implementation units: a foundation unit, four units that can run in parallel, then config wiring and a final fixture unit. Every unit leaves all three scanner gates green, so the branch never goes red.

# Decomposition: CD-6, Validated Dogwatch Configuration and Common Report Contracts

## 1. Summary

**Scope.** CD-6 changes the CD-5 `dogwatch` scanner in place (`scanner/src/dogwatch/`, `scanner/schemas/`, `scanner/tests/`, `fixtures/`) to deliver two contracts that later tickets build on:
- **The validated `dogwatch.toml` model** (FR-001–FR-009; [AC-1], [AC-2]): packages, exclusion globs, named `forbid`/`layers` rules and optional OpenAPI contracts. Each invalid value is rejected before scanning with a diagnostic that names its key path.
- **The common report model, version 0.2** (FR-010–FR-018; [AC-3], [AC-4]): status, provenance, findings, diagnostics, canonical JSON and a versioned schema pin. The exit code is a pure function of the report, so the four AC-4 modes are always distinguishable.
- **One new end-to-end golden fixture** (FR-019).

**How the work is partitioned.** The partition follows the module DAG in ARCH §3 (`diagnostics` ← `_validate` ← {`exclude`, `rules`, `contracts`} ← `config` ← `report` ← `cli`). Each unit owns whole files.

1. **Foundation (`seam-foundation`).** Freezes every cross-unit seam: the `Diagnostic` shape, exit constants, the renamed `DogwatchConfig`, the `_validate.py` helpers, and the entity dataclasses for the three domain modules. It changes no behaviour.
2. **Four parallel units.** Each domain validator (`exclude`, `rules`, `contracts`) is a pure, separately tested module. The report/schema/CLI unit runs alongside them.
3. **Config wiring (`config-orchestration`).** Wires the validators into `load_policy`'s staged validation (stages 1–4).
4. **Fixture unit (`full-surface-fixture`).** Adds the full-surface fixture and the trust-boundary and module-structure checks, and runs the final SC-004 gate.

**Changes from the plan** (`plan.json` EPIC-001 to EPIC-004 and `implementation_plan.md` §8 F0–F3). Each change is called out where it applies:
- **EPIC-002 is split into four units.** It contains three independent pure modules plus the orchestration that wires them, which is too much for one session.
- **The foundation also creates `_validate.py`** (an ARCH §3 refinement) and entity-only stubs of the domain modules. Without these, the three validators cannot build in parallel against frozen types.
- **The plan's red `make test-fixtures` window between F2 and F3 is removed.** `report-cli-contract` deletes `report-0.1.schema.json`, and `tests/golden/test_fixture_goldens.py` pins that file (`SCHEMA_PATH`, line 25). So that unit also owns the golden test's switch to 0.2 and the regeneration of `fixtures/minimal/expected-report.json`, and the regeneration still goes only through `make regen-fixtures`. This satisfies the rule that every unit leaves the commands covering its files passing.

**Traceability.** Every task_id below maps to a plan epic. Every frozen-spec AC, FR and SC is served by at least one unit (see §2.8).

---

## 2. Implementation Units

Commands used throughout, all run from the repo root:
- `make test-scanner`: `pytest -m "not golden"`
- `make lint-scanner`: ruff format check, ruff check, `mypy --strict` over `src` and `tests`
- `make test-fixtures`: `pytest -m golden`
- `make regen-fixtures`: regenerates the goldens

**No unit may change** `scanner/pyproject.toml`, `scanner/uv.lock` or the `Makefile`. CD-6 adds no dependencies: `jsonschema` is already a dev-only dependency (INV-M2), and every target already exists.

---

### 2.1 `seam-foundation`: Shared model seam foundation *(plan EPIC-001 / F0)*

- **Requirements served:**
  - [AC-1] FR-002: key-path rendering and the `config_invalid` helper.
  - [AC-3] FR-013: the four-field `Diagnostic`.
  - [AC-4] FR-016: exit constants. FR-018: `render_diagnostics`.
  - Key Entities: the `DogwatchConfig` rename and the `ExclusionDecl`, `RuleDecl` and `OpenApiContractDecl` shapes.
  - Supports SC-001 and SC-004.
- **Architecture components:**
  - `diagnostics.py` (ARCH §3; IC-PY; DC-R2, DC-R5; IC-ERR-1, IC-ERR-2)
  - `_validate.py` (ARCH §3 refinement; IC-PY)
  - `config.py`: the rename and new fields only (DC-C1, DC-C2)
  - Entity stubs of `exclude.py`, `rules.py` and `contracts.py` (DC-C3, DC-C4, DC-C5)
- **Files it owns (write scope):**
  - `scanner/src/dogwatch/diagnostics.py` — this unit is the **only writer for the whole run**:
    - `Diagnostic(source, id, severity, message)`, with `id` widened to `str`.
    - The `Severity` literal.
    - The named `Final[str]` id constants `CONFIG_NOT_FOUND`, `CONFIG_INVALID`, `EXCLUDE_UNMATCHED` and `SOURCE_SYNTAX_INVALID`.
    - `render_diagnostics(seq) -> str`, with `render(err)` delegating to it.
    - `EXIT_OK=0`, `EXIT_GATE_FAILED=1` (comment changed from "reserved" to "emitted") and `EXIT_ERROR=2`.
  - `scanner/src/dogwatch/_validate.py` *(new)*:
    - key-path rendering, `config_invalid(message) -> DogwatchError`;
    - `is_identifier` (`isidentifier() and not iskeyword`), `is_kebab_id` (regex, at most 64 characters);
    - typed accessors (`require_str`, `optional_str_list`, …) that produce the existing "`<path> is required`" and "`<path> must be a string`" wording.
  - `scanner/src/dogwatch/exclude.py`, `rules.py`, `contracts.py` *(new)*: **only** the frozen dataclasses `ExclusionDecl`, `RuleDecl` (kind-discriminated, with the defaults from DC-C4) and `OpenApiContractDecl`. Parse functions are not added here.
  - `scanner/src/dogwatch/config.py`: rename `PolicyConfig` to `DogwatchConfig` with no alias, and add `exclusions`, `rules` and `contracts`, each populated as `()`. Update the `Diagnostic` construction sites to `source="dogwatch", severity="error"`. **No validation change.**
  - Tests:
    - `scanner/tests/test_validate.py` *(new)*.
    - `scanner/tests/test_diagnostics.py`.
    - Construction sites and imports in `scanner/tests/test_config.py`, `test_report.py` and `test_schema.py`.
    - The import allowlist in `test_config.py::test_config_module_restricts_imports_and_os_calls`, which must now admit `dogwatch.exclude`, `dogwatch.rules` and `dogwatch.contracts`.
- **Must not touch:** `report.py`, `cli.py`, `output.py`, `schemas/**`, `fixtures/**`, `tests/golden/**`, `conftest.py`.
- **Success criteria:**
  1. `Diagnostic` has exactly the fields `(source, id, severity, message)`, and every config-time constructor uses `source="dogwatch"` and `severity="error"` (INV-V4 holds for the existing cases).
  2. `render_diagnostics([])` returns `""`. `render_diagnostics(ds)` returns `"".join(f"dogwatch:{d.id}: {d.message}\n" for d in ds)`. `render(err) == render_diagnostics(err.diagnostics)`.
  3. `EXIT_OK`, `EXIT_GATE_FAILED` and `EXIT_ERROR` equal `0`, `1` and `2`.
  4. The `_validate` helpers behave as follows:
     - `is_kebab_id` accepts `a`, `no-db-in-domain` and a 64-character id. It rejects a 65-character id, `A`, `a_b`, `a:b`, `-a` and `a--b`.
     - `is_identifier` rejects `class`, `foo-bar` and `""`.
     - Key-path rendering produces `python.rules[1].targets[0]`.
  5. `load_policy` returns a `DogwatchConfig` with `exclusions == rules == contracts == ()`. Every existing `test_config.py` assertion still passes with unchanged messages.
  6. `_validate.py` imports only `dogwatch.diagnostics`. The three stub modules import only from the stdlib (the INV-M1 subset that applies at this point).
  7. **Zero behaviour change:** `make test-fixtures` passes with byte-identical 0.1 goldens.
  8. `make test-scanner`, `make lint-scanner` and `make test-fixtures` all exit 0 (checkpoint CP0).

---

### 2.2 `exclude-validation`: Exclusion glob syntax, matcher and package-tree walk *(plan EPIC-002, part)*

- **Requirements served:** [AC-1], [AC-2] FR-004 and FR-002 (key paths for `python.exclude[i]`); Edge Cases "Exclusions" and "Trust boundary"; contributes to SC-001.
- **Architecture components:** `exclude.py` (ARCH §2 glob row, §3, §5.1 stage 4); IC-CFG-2; IC-PY `parse_exclusions` and `check_matches`; INV-T1 and INV-T2 (unit level).
- **Files it owns:**
  - `scanner/src/dogwatch/exclude.py`, adding to the foundation's `ExclusionDecl`:
    - `parse_exclusions(value: object) -> tuple[ExclusionDecl, ...]`;
    - the segment-based matcher, where a `**` segment matches zero or more segments and `*` matches within one segment;
    - `check_matches(config_dir, packages, exclusions) -> None`, which walks with `os.scandir` using `is_file/is_dir(follow_symlinks=False)`, builds candidates with `posixpath.normpath("<root>/<name>/<rel>")`, and collects one `exclude-unmatched` per pattern in config order.
  - `scanner/tests/test_exclude.py` *(new)*.
- **Integration seam:** `check_matches` must not import `dogwatch.config` (INV-M1). Its `packages` parameter is typed against a module-local `typing.Protocol` with read-only `name: str` and `root: str`. `PackageDecl` satisfies it structurally, so callers pass `cfg.packages` unchanged (see R-1).
- **Must not touch:** `config.py`, `_validate.py`, `diagnostics.py`, `rules.py`, `contracts.py`, `conftest.py`, `test_config.py`, `fixtures/**`.
- **Success criteria:**
  1. **Syntax:** each Edge Case "Exclusions" syntax case raises `DogwatchError` with one `config-invalid` diagnostic whose message matches the IC-ERR-4 template and contains `python.exclude[i]`:
     - `exclude` not an array, or an entry that is not a string;
     - an empty pattern, a leading `/`, or a `.`, `..` or empty segment;
     - `?`, `[` or `\` in a pattern.
  2. **Matching:**
     - `src/shop/**/*.py` matches `src/shop/a.py` and `src/shop/x/y/b.py`.
     - `src/shop/*.py` does not match `src/shop/x/b.py`.
     - `a**b` behaves like `a*b`.
     - Matching is case-sensitive.
     - Patterns are independent: two overlapping patterns are each satisfied by the same file.
  3. **Walk:**
     - A pattern that matches only a directory, only a file outside `<root>/<name>/`, or only a symlink (to a file or to a directory) yields `exclude-unmatched` with the IC-ERR-4 message `python.exclude[i] '<v>' matches no file under a declared package directory` (INV-T2).
     - Several unmatched patterns yield one diagnostic each, in config order.
  4. **Trust surface:** with `open` and `os.scandir` instrumented, `check_matches` never calls `open`, and calls `os.scandir` only on paths whose `realpath` lies under some `realpath(<config_dir>/<root>/<name>)` (INV-T1, unit level).
  5. `exclude.py` imports only the stdlib, `dogwatch._validate` and `dogwatch.diagnostics`.
  6. `make test-scanner`, `make lint-scanner` and `make test-fixtures` exit 0. The functions are not yet wired, so the CLI behaves as before.

---

### 2.3 `rules-validation`: Named rule validation (`forbid` / `layers`) *(plan EPIC-002, part)*

- **Requirements served:** [AC-1], [AC-2] FR-005, FR-006 and FR-007; FR-009 (unknown keys inside a rule entry, per kind); FR-002; Edge Cases "Rules" and "Selector resolution"; A-10, A-14; contributes to SC-001.
- **Architecture components:** `rules.py` (ARCH §3, §4.1); IC-CFG-3 (selectors); IC-PY `parse_rules`; DC-C4; the rule rows of IC-ERR-4.
- **Files it owns:**
  - `scanner/src/dogwatch/rules.py`, adding `parse_rules(value: object) -> tuple[RuleDecl, ...]` to the foundation's `RuleDecl`. Checks run in the IC-CFG-1 stage-2b order: `kind` → per-kind unknown keys → required fields and types → `id` grammar → `id` uniqueness → `reason` non-empty → selector syntax → structural constraints.
  - `scanner/tests/test_rules.py` *(new)*.
- **Must not touch:** `config.py`, `_validate.py`, `diagnostics.py`, `exclude.py`, `contracts.py`, `conftest.py`, `test_config.py`, `fixtures/**`.
- **Success criteria:**
  1. Each Edge Case "Rules" case (missing `id`/`kind`/`reason` through unknown keys inside a rule) has **one test** that asserts:
     - `id == "config-invalid"`;
     - the message contains the exact key path (e.g. `python.rules[1].targets[0]`);
     - the message equals the IC-ERR-4 template.

     These cases cover the other kind's keys being rejected for each kind. They also cover `except_sources` given while `sources` is absent, which is rejected under the CQ-2 default.
  2. Valid inputs load:
     - a `forbid` rule with all optional keys;
     - a `forbid` rule with only `targets`, which gives `sources == ()`;
     - a `layers` rule with `exhaustive = true` and `container`;
     - a `layers` rule without `container`, which gives `exhaustive is False` and `container is None`.

     Fields that belong to the other kind keep their DC-C4 empty defaults.
  3. `parse_rules(None)` (key absent) and `parse_rules([])` both return `()`.
  4. A selector that names no existing module is accepted, and no filesystem access happens (A-14, INV-V9 at unit level).
  5. A document failure yields exactly one diagnostic (INV-V5, document stage).
  6. `rules.py` imports only the stdlib, `dogwatch._validate` and `dogwatch.diagnostics`.
  7. `make test-scanner`, `make lint-scanner` and `make test-fixtures` exit 0.

---

### 2.4 `contracts-validation`: OpenAPI contract declarations *(plan EPIC-002, part)*

- **Requirements served:** [AC-2] FR-008 (optional contracts), [AC-1] FR-002; Edge Cases "OpenAPI contracts"; US-6; contributes to SC-001.
- **Architecture components:** `contracts.py` (ARCH §3); IC-PY `parse_contracts`; DC-C5; the contract rows of IC-ERR-4.
- **Files it owns:**
  - `scanner/src/dogwatch/contracts.py`, adding `parse_contracts(value: object) -> tuple[OpenApiContractDecl, ...]`. It checks:
    - `id` presence, type and `is_kebab_id`, then `id` uniqueness;
    - `path` presence and type;
    - `path` syntax: relative; `/` separators; no `.`, `..` or empty segment; no `\`; extension `.yaml`, `.yml` or `.json` (case-sensitive);
    - `path` textual uniqueness.
  - `scanner/tests/test_contracts.py` *(new)*.
- **Ownership boundary:** unknown keys inside a contract entry are **not** checked here. They belong to stage 2a in `config.py` (ARCH §5.1) and so to `config-orchestration`.
- **Must not touch:** `config.py`, `_validate.py`, `diagnostics.py`, `exclude.py`, `rules.py`, `conftest.py`, `test_config.py`, `fixtures/**`.
- **Success criteria:**
  1. Each Edge Case "OpenAPI contracts" case except unknown keys gets one test. Each asserts `config-invalid`, a message containing `openapi.contracts[i]` (or `[j]` for duplicates), and the IC-ERR-4 template. The cases are:
     - missing `id`/`path`; duplicate id; duplicate path;
     - a bad extension, an absolute path, a `..` segment or backslashes;
     - a `.` segment (OQ-5 default).
  2. A contract whose file does not exist loads successfully, and the module does no filesystem access (INV-V10, unit level).
  3. `parse_contracts(None)` and `parse_contracts([])` return `()`.
  4. `contracts.py` imports only the stdlib, `dogwatch._validate` and `dogwatch.diagnostics`, and never `dogwatch.rules`.
  5. `make test-scanner`, `make lint-scanner` and `make test-fixtures` exit 0.

---

### 2.5 `config-orchestration`: Staged `load_policy` over the full accepted surface *(plan EPIC-002, completion)*

- **Requirements served:**
  - [AC-1] FR-001 (preserved), FR-002 and FR-009.
  - [AC-2] FR-003 (packages, plus keyword tightening D-2), and the wiring of FR-004–FR-008.
  - Edge Cases "Config file", "Packages" and "Trust boundary" (at the `load_policy` level).
  - A-2, A-3; SC-001.
- **Architecture components:** `config.py` as orchestrator (ARCH §3, §5.1); IC-CFG-1 (accepted key sets, staging, key-path rendering); IC-ERR-4; N-1 / CQ-1; INV-V1 to INV-V10 and INV-T1 at the `load_policy` level.
- **Files it owns:**
  - `scanner/src/dogwatch/config.py`, implementing the stages:
    - Stage 2a: unknown keys across the top level, `[python]`, `[openapi]`, package entries and contract entries. They are collected and sorted, and the first is reported (INV-V6).
    - Stage 2b: values in a fixed order. `python` type → packages (name now also rejects keywords) → `parse_exclusions` → `parse_rules` → `openapi` type → `parse_contracts`.
    - Stage 3: package filesystem checks, aggregated, with each message prefixed `python.packages[i]: ` (N-1, CQ-1 default).
    - Stage 4: `exclude.check_matches`, run only when `exclude` is non-empty (D-13).
  - `scanner/tests/conftest.py`.
  - `scanner/tests/test_config.py`, including the narrowed `load_policy` trust tests: an `os.scandir` allowlist entry and a variant with exclusions present.
- **Must not touch:** `diagnostics.py`, `_validate.py`, `exclude.py`, `rules.py`, `contracts.py` (consume only their IC-PY signatures; a defect found there is escalated to that unit's owner, not patched here), `report.py`, `cli.py`, `schemas/**`, `fixtures/**`, `tests/golden/**`.
- **Success criteria:**
  1. **Accepted surface (INV-V7):** `load_policy` succeeds on a full-surface config (packages, `exclude`, one `forbid` rule, one `layers` rule, one contract) built in `tmp_path`. It also succeeds on each variant without contracts, without rules, without `exclude`, and with packages only.
  2. **Unknown keys (FR-009):** each of these is rejected as `"<key path> is not supported in this version"`:
     - `python.type_checking`, `python.clock`, `python.max_waiver_days`, `python.waivers`;
     - a baseline key;
     - `openapi.severity`;
     - an unknown top-level key;
     - an unknown key in a package entry and in a contract entry.

     With several unknown keys present, the reported one is `sorted(K)[0]` (INV-V6).
  3. **Precision:** every Edge Case "Config file" and "Packages" case produces the IC-ERR-4 message. The preserved CD-5 texts are verbatim, and stage-3 messages carry the `python.packages[i]: ` prefix. A keyword package name (for example `class`) is rejected (INV-V3).
  4. **Fail-fast staging (INV-V5):**
     - An unknown key plus a missing package directory yields exactly one diagnostic, the unknown-key one.
     - A stage-3 defect plus an unmatched exclusion yields only stage-3 diagnostics.
     - Every document-stage failure yields `len == 1`.
  5. Every diagnostic `load_policy` raises satisfies INV-V4. Every returned `DogwatchConfig` satisfies the DC-C1 to DC-C5 predicates (INV-V8).
  6. **Trust (INV-T1):**
     - `open` is called only on `config_arg`.
     - `os.scandir` is called only under package directories.
     - `os.scandir` is called zero times when `exclude` is absent or empty.
     - The import and os-call restriction test for `config.py` is updated, and passes.
  7. **End to end through the CLI (INV-V2):** an `exclude-unmatched` config gives `exit 2`, no report and a matching stderr line. This proves the malformed-config mode through the real CLI.
  8. `make test-scanner`, `make lint-scanner` and `make test-fixtures` exit 0. `fixtures/minimal` is packages-only, so its golden still passes (checkpoint CP1).

---

### 2.6 `report-cli-contract`: Report model 0.2, schema pin, CLI exit behaviour, minimal golden *(plan EPIC-003 / F2, plus the minimal half of F3)*

- **Requirements served:** [AC-3] FR-010–FR-015; [AC-4] FR-016, FR-017 and FR-018; SC-002, SC-003 (unit level plus the minimal golden), SC-005; US-3, US-4, US-5 (the minimal regeneration); A-4 to A-8, A-12.
- **Architecture components:** `report.py`, `cli.py`, `schemas/` (ARCH §3, §4.2, §4.3, §5.2–§5.4); IC-CLI-1, IC-CLI-2; IC-PY (`derive_status`, `exit_code_for_status`, `build_report`, `scan`); IC-ERR-1, IC-ERR-3; DC-R1 to DC-R9; VC-1; INV-S1 to INV-S4, INV-E1 to INV-E5, INV-D1 to INV-D6, INV-O1 to INV-O3, INV-M3.
- **Files it owns:**
  - `scanner/src/dogwatch/report.py`:
    - `Finding`, `Locator`, `Status`;
    - `derive_status`, `exit_code_for_status`;
    - `build_report` with canonical sorting (DC-R8) and explicit per-entity JSON converters (DC-R6: omit `None` locator keys; always emit `waiver: null`);
    - `serialize_canonical`, unchanged.
  - `scanner/src/dogwatch/cli.py`:
    - module-level `scan(cfg) -> ((), ())`, looked up at call time so tests can monkeypatch it;
    - the IC-CLI-1 processing order;
    - render scan-time diagnostics after a successful write;
    - `return exit_code_for_status(status)`.
  - `scanner/schemas/report-0.2.schema.json` *(new; DC-R9)*. **Deletes** `scanner/schemas/report-0.1.schema.json` (D-8, VC-1).
  - Tests: `scanner/tests/test_report.py`, `test_schema.py`, `test_cli.py`, and the new FR-018 render tests appended to `test_diagnostics.py`.
  - `scanner/tests/golden/test_fixture_goldens.py`:
    - `SCHEMA_PATH` switched to 0.2;
    - assertions added that each golden has `status == "pass"` and `diagnostics == []`.
  - `fixtures/minimal/expected-report.json`, **regenerated only by `make regen-fixtures`, never edited by hand**.
- **Must not touch:** `diagnostics.py` (the render function and constants come from the foundation), `config.py`, `_validate.py`, `exclude.py`, `rules.py`, `contracts.py`, `conftest.py` (needed test helpers are defined locally in its own test files), `output.py`, `tests/golden/harness.py`, `tests/golden/regenerate.py`, `fixtures/minimal/dogwatch.toml`, `fixtures/minimal/src/**`, `fixtures/README.md`, `test_trust_boundary.py`.
- **Success criteria:**
  1. **Envelope (FR-010):** `build_report` returns exactly the keys `{schema_version: "0.2", status, scanner, policy, findings, diagnostics}`. The `FORBIDDEN_FIELDS` keys are absent (INV-D4), and INV-D5 provenance holds.
  2. **Status derivation (FR-011, INV-E4):**
     - An error diagnostic gives `inconclusive`.
     - Otherwise an error finding gives `fail`.
     - An error finding plus an error diagnostic gives `inconclusive`.
     - Warning and info entries alone give `pass`.
     - `exit_code_for_status` maps `pass`, `fail` and `inconclusive` to `0`, `1` and `2`.
  3. **Projection (DC-R6, INV-D6, INV-S1):**
     - Finding keys are exactly the DC-R3 set, and `waiver` is always `null`.
     - No `null` appears inside `locator`.
     - Diagnostic keys are exactly the DC-R5 set.
  4. **Determinism:**
     - INV-D2: canonical form, a trailing newline and literal non-ASCII.
     - INV-D3: any permutation of findings and diagnostics serializes to identical bytes.
     - Two serializations of the same input are byte-identical.
  5. **Schema (SC-005, INV-S2):** `report-0.2.schema.json` has `$id: urn:dogwatch:schema:report:0.2` and validates every constructed report: pass, fail, both inconclusive kinds, non-ASCII, warning/info, and all optional locator keys. It rejects a forbidden field, a non-null `waiver`, a `Finding` with an `id` key and a `Diagnostic` with a `check_id` key. `rg 'report-0\.1' scanner` finds no matches.
  6. **The four AC-4 modes (FR-017, SC-002, INV-E5):** `test_cli.py` produces each mode, the last end to end with a file-load failure, and asserts its full (report present?, status, exit, stderr) tuple:

     | Mode | How it is produced | Expected |
     |---|---|---|
     | Policy violation | monkeypatched `scan` returns an error finding | `(T, fail, 1)` |
     | Invalid source syntax | `scan` returns an error `source-syntax-invalid` diagnostic | `(T, inconclusive, 2)` |
     | Adapter failure | `scan` returns an error diagnostic with `source="openapi"` | `(T, inconclusive, 2, adapter source)` |
     | Malformed config | missing or invalid-TOML config | `(F, —, 2)` |

     The four tuples are pairwise distinct. INV-E1 to INV-E3 and INV-S3/INV-S4 hold for each written report, and each one validates against 0.2.
  7. **Stderr mirror (INV-O1):** stderr lines equal `dogwatch:<id>: <message>` for each report diagnostic, in report order, and stderr is empty when there are none.
  8. **Write failure and guard:**
     - INV-O2: on a write failure, no diagnostic lines appear, the last stderr line starts with `dogwatch: error: cannot write report to `, exit is `2`, and no temp file is left.
     - INV-O3: with the same-file guard triggered, `scan` is called zero times and the config is unchanged.
     - `--version`, stdout `-` mode and usage errors behave as before (A-12).
  9. **Seam signature (INV-M3):** `scan` has one parameter and `scan(cfg) == ((), ())`.
  10. **Minimal golden:** `make regen-fixtures` rewrites only `fixtures/minimal/expected-report.json`, to the 0.2 shape with `status: "pass"` and empty arrays. `make test-fixtures` then passes, including the repeated-run and TZ/LC_ALL/HOME/PYTHONHASHSEED variants (INV-D1).
  11. `make test-scanner`, `make lint-scanner` and `make test-fixtures` all exit 0, so there is **no red window** (checkpoint CP2).

---

### 2.7 `full-surface-fixture`: Full-surface golden fixture, trust boundary, module structure and final gate *(plan EPIC-004 / F3)*

- **Requirements served:** [AC-2] (end-to-end proof) FR-019; US-1, US-5, US-6; [AC-3] SC-003 (golden level) and SC-005 (golden reports); Edge Cases "Trust boundary" (CLI level); SC-004 (final gate).
- **Architecture components:** `fixtures/full-surface/` (ARCH §3; DC-F1, DC-F2); ARCH §6 trust boundary (INV-T1 to INV-T3); the module-structure boundary (INV-M1, INV-M2).
- **Files it owns:**
  - `fixtures/full-surface/` *(new)*. Static only, never imported, LF line endings. It contains:
    - `dogwatch.toml` with at least one package, at least one `exclude` pattern that matches at least one real regular file under `<root>/<name>/`, at least one `forbid` rule, at least one `layers` rule, and exactly one `[[openapi.contracts]]`;
    - the source tree;
    - a checked-in static spec file at the contract path (for example `api/shop-api.yaml`);
    - `expected-report.json`, generated only by `make regen-fixtures`.
  - `fixtures/README.md`: document the new fixture and fix the stale "V0-V4" wording if needed.
  - `scanner/tests/test_trust_boundary.py`: the narrowed invariant (directory listing only under package directories when exclusions are present; never opening, importing or executing scanned code), with variants with and without exclusions.
  - `scanner/tests/test_module_structure.py` *(new)*: the INV-M1 AST import-DAG test.
- **Must not touch:** all `scanner/src/**` (a defect found there is escalated to the owning unit), `fixtures/minimal/**` (its golden must come out byte-identical after regeneration), `tests/golden/**`, `scanner/schemas/**`, `conftest.py`, `test_config.py`, `test_cli.py`.
- **Success criteria:**
  1. `load_policy("fixtures/full-surface/dogwatch.toml")` succeeds. The config's exclusion matches at least one real file, it has a `forbid` and a `layers` rule, and it has one contract whose file exists.
  2. `make regen-fixtures` creates `fixtures/full-surface/expected-report.json` with `schema_version "0.2"`, `status "pass"`, `findings: []` and `diagnostics: []`. Afterwards `git diff --exit-code fixtures/minimal` is clean.
  3. `make test-fixtures` passes for both fixtures:
     - byte-exact goldens;
     - repeated runs identical;
     - TZ/LC_ALL/HOME/PYTHONHASHSEED variants, with no environment leakage (INV-D1, INV-D4);
     - schema 0.2 validation of every golden (SC-005).
  4. **Trust boundary, CLI level:**
     - On `fixtures/minimal` (no exclusions), `os.scandir`, `os.listdir` and `open` are never used on package directories.
     - On `fixtures/full-surface`, `os.scandir` is used only under package directories and no file there is opened.
     - In both cases no module named after a fixture package appears in `sys.modules`, and a fixture source file that raises on import does not change the outcome (INV-T1, INV-T3).
     - The network-disabled run still passes.
  5. **INV-M1:** `diagnostics` imports no `dogwatch.*` module; `_validate` imports only `diagnostics`; `exclude`, `rules` and `contracts` import only `_validate` and `diagnostics`, and never each other; `config` does not import `report` or `cli`; `report` does not import `cli`, `exclude`, `rules` or `contracts`; the graph is acyclic. **INV-M2:** the existing `test_isolation.py` stays green.
  6. **Final gate (SC-004):** `make test-scanner && make lint-scanner && make test-fixtures` pass in one run (checkpoint CP3). `make run-scanner` exits 0 with an empty stderr.

---

### 2.8 Traceability matrix

| Requirement | Units |
|---|---|
| [AC-1] FR-001, FR-002, FR-009, SC-001 | `seam-foundation` (helpers), `exclude-validation`, `rules-validation`, `contracts-validation`, `config-orchestration` |
| [AC-2] FR-003–FR-008 | `config-orchestration` (FR-003, wiring), `exclude-validation` (FR-004), `rules-validation` (FR-005–FR-007), `contracts-validation` (FR-008); end-to-end proof in `full-surface-fixture` (FR-019) |
| [AC-3] FR-010–FR-015, SC-003, SC-005 | `seam-foundation` (FR-013 shape), `report-cli-contract`, `full-surface-fixture` (golden level) |
| [AC-4] FR-016–FR-018, SC-002 | `seam-foundation` (constants, render), `report-cli-contract` (mapping, four modes), `config-orchestration` (`exclude-unmatched` through the CLI) |
| FR-019, US-5 | `report-cli-contract` (minimal regeneration), `full-surface-fixture` (new fixture) |
| SC-004 | Every unit holds the gates green; `full-surface-fixture` runs the final combined gate |

Every AC is served, and there is no orphaned ticket requirement. The proposals P-1 to P-4 are **not** built.

---

## 3. Dependency Graph

```
seam-foundation ──► exclude-validation ───┐
      │                                    │
      ├────────► rules-validation ────────┼──► config-orchestration ──┐
      │                                    │                           │
      ├────────► contracts-validation ────┘                           ├──► full-surface-fixture
      │                                                                │
      └────────► report-cli-contract ─────────────────────────────────┘
```

| Edge | Type | Reason |
|---|---|---|
| `seam-foundation` → `exclude-validation` | **blocking** | needs the `ExclusionDecl` stub, the `_validate` helpers and the `Diagnostic`/`EXCLUDE_UNMATCHED` constant |
| `seam-foundation` → `rules-validation` | **blocking** | needs the `RuleDecl` stub and `is_identifier`/`is_kebab_id`/accessors |
| `seam-foundation` → `contracts-validation` | **blocking** | needs the `OpenApiContractDecl` stub and `is_kebab_id` |
| `seam-foundation` → `report-cli-contract` | **blocking** | needs the four-field `Diagnostic`, `render_diagnostics`, the exit constants, the `DogwatchConfig` name and `SOURCE_SYNTAX_INVALID` |
| `exclude-validation` → `config-orchestration` | **blocking** | wires `parse_exclusions`/`check_matches` |
| `rules-validation` → `config-orchestration` | **blocking** | wires `parse_rules` |
| `contracts-validation` → `config-orchestration` | **blocking** | wires `parse_contracts` |
| `config-orchestration` → `full-surface-fixture` | **blocking** | the fixture config must validate, and the CLI trust test needs the real walk |
| `report-cli-contract` → `full-surface-fixture` | **blocking** | the golden must be 0.2-shaped, the golden test must target the 0.2 schema, and the regeneration must not collide with the minimal golden's ownership |
| `report-cli-contract` ↔ `config-orchestration` | **advisory, no edge** | Write scopes are disjoint and both code against foundation seams. `report-cli-contract`'s CLI config-failure tests use file-load failures only. The order in which they merge does not matter. |

---

## 4. Parallelization Plan

`team_work=True`, `max_concurrency=3`.

| Wave | Units | Notes |
|---|---|---|
| W0 (serial) | `seam-foundation` | Small and short. Ends at **CP0**: all three make targets green with goldens byte-identical. |
| W1 (parallel) | `rules-validation`, `exclude-validation`, `report-cli-contract`, then `contracts-validation` | Four units for three slots. Start the three longest (rules, exclude, report-cli) first, and schedule `contracts-validation`, the smallest, in the first freed slot. All write scopes are disjoint. |
| W2 | `config-orchestration` | Starts once all three validators have landed. It may overlap a still-running `report-cli-contract`. Ends at **CP1**. |
| W3 (serial) | `full-surface-fixture` | Starts after CP1 and **CP2** (`report-cli-contract` landed). Ends at **CP3**, the SC-004 final gate. |

**Critical path:** `seam-foundation` → `rules-validation` → `config-orchestration` → `full-surface-fixture`.

**Ownership boundaries (each file has one writer at a time; files with sequential handoffs are noted):**
- `diagnostics.py`, `_validate.py`: `seam-foundation` only, for the whole run.
- `exclude.py` / `rules.py` / `contracts.py`: `seam-foundation` writes the entity dataclasses, then the respective validator unit writes the rest. The entity fields are frozen at CP0, and validator units must not change them.
- `config.py`, `test_config.py`: `seam-foundation` (rename only), then `config-orchestration`.
- `conftest.py`: `config-orchestration` only.
- `report.py`, `cli.py`, `schemas/**`, `test_cli.py`, `test_schema.py`, `test_report.py`: `seam-foundation` changes only the rename and `Diagnostic` construction sites in the test files. After that, `report-cli-contract` owns them all.
- `test_diagnostics.py`: `seam-foundation` (shape), then `report-cli-contract` (render-wiring tests are appended only).
- `tests/golden/test_fixture_goldens.py`, `fixtures/minimal/expected-report.json`: `report-cli-contract` only.
- `fixtures/full-surface/**`, `fixtures/README.md`, `test_trust_boundary.py`, `test_module_structure.py`: `full-surface-fixture` only.

**Integration seams every worker must honour:**
1. The IC-PY signatures and the DC-C/DC-R entity fields are frozen at CP0. Code against them, not against another unit's internals.
2. Goldens change **only** through `make regen-fixtures`, never by hand (`fixtures/README.md` rules).
3. `dogwatch.cli.scan` is looked up at call time, which is the test seam for the four modes.
4. `exclude`, `rules` and `contracts` never import `dogwatch.config` or each other (INV-M1). See R-1 for the `PackageDecl` typing.
5. Config-time diagnostic ids and messages follow IC-ERR-4. Preserved CD-5 texts are verbatim, except for the stage-3 `python.packages[i]: ` prefix (N-1).

**Integration checkpoints:**

| Checkpoint | After | Must hold |
|---|---|---|
| CP0 | `seam-foundation` | all 3 make targets green; 0.1 goldens untouched |
| CP1 | `config-orchestration` | all 3 green; full accepted surface validates through `load_policy` |
| CP2 | `report-cli-contract` | all 3 green; 0.2 output; minimal golden regenerated |
| CP3 | `full-surface-fixture` | all 3 green in one run; `make run-scanner` clean |

---

## 5. Risks & Open Questions

- **R-1 (contract inconsistency, resolved here by default).** IC-PY types `exclude.check_matches(..., packages: tuple[PackageDecl, ...], ...)`, but `PackageDecl` lives in `config.py`, and INV-M1 forbids `exclude` from importing `config`. An import under `TYPE_CHECKING` would still fail the AST-based INV-M1 test.
  - *Default:* `exclude.py` declares a local `Protocol` (`name: str`, `root: str`) and types `packages` as `Sequence` of it. `PackageDecl` satisfies it structurally, and call sites pass `cfg.packages` unchanged.
  - *Alternative (operator):* move `PackageDecl` into `_validate.py` or a new entity module. That changes a frozen ownership line.
- **R-2 (change from the plan: golden ownership).** The plan reserves all golden regeneration for F3 and accepts a red `make test-fixtures` window after F2. This decomposition gives the minimal golden's regeneration, and the golden test's schema-path switch, to `report-cli-contract`. Two reasons: that unit deletes `report-0.1.schema.json`, which `test_fixture_goldens.py` pins, and no unit may leave its covering commands failing. Golden discipline is unchanged: regeneration still goes only through `make regen-fixtures`.
- **R-3 (OQ-1, carried, not resolved).** An unexpected exception in a future `scan` body exits with Python's default `1`, which CI would read as a policy violation. CD-6's `scan` cannot raise, so no CD-6 unit is affected, but the engine and adapter tickets inherit this. *Section to answer:* FR-016 / A-6.
- **R-4 (CQ-1, carried).** Stage-3 package messages gain a `python.packages[i]: ` prefix to satisfy FR-002/SC-001. This changes CD-5 assertions in `test_config.py`, which `config-orchestration` owns. If the operator keeps the verbatim CD-5 text instead, SC-001 is not met for the five package-structure cases.
- **R-5 (CQ-2, carried).** `except_sources` with no `sources` is rejected under the literal reading of FR-006, implemented in `rules-validation`. The alternative is to treat the package names as implicit `sources`.
- **R-6 (CQ-3 / CQ-4, carried).**
  - A whitespace-only `reason` is accepted (`len > 0`).
  - Multi-line diagnostic messages are not constrained. Every scanner-produced message is single-line. An adapter that emits a multi-line message would break INV-O1's one-line mirror; adapter tickets own that.
- **R-7 (OQ-2 to OQ-6, defaults applied).**
  - Adapter diagnostics use the adapter's own `source`, and tests use `"openapi"`.
  - The exclusion match domain is `<root>/<name>/`.
  - Keyword selector segments are rejected.
  - `.` segments in contract paths are rejected.
  - The fingerprint is an unpinned non-empty string.

  Each change is local to one unit plus its tests.
- **R-8 (schema-validity gap for adapters).** `build_report` does not validate adapter-supplied strings (INV-S2). A non-kebab id or an empty `source` produces a schema-invalid report. No CD-6 code path can produce one; the adapter tickets must test for it.
- **R-9 (AC-4 end-to-end coverage).** Only the malformed-config mode can be triggered end to end in CD-6 (A-5). The other three are proven at the `cli.scan` seam. This is the frozen spec's decision; it is noted here so a reviewer does not expect real source parsing.
- **Ticket coverage.** AC-1 to AC-4 are each served by at least one unit (§2.8). No acceptance criterion needs evidence from outside the workspace, and no unit needs a pull request, merge or remote CI.
