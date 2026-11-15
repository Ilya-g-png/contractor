I now have complete evidence: the scanner's existing modules and tests, the golden harness, the fixtures, the Makefile contract, the schema pin, and the CD-3/CD-4 ADR precedents. The frozen spec is comprehensive and closed its five clarification questions; the remaining micro-decisions all have spec-grounded defaults, which I record below. Here is the implementation plan.

---

# Implementation Plan — CD-6: Validated Dogwatch Configuration and Common Report Contracts

## 1. Summary

CD-6 turns the CD-5 scanner bootstrap into the two contracts every later component binds to. First, the validated configuration model selected by the CD-3 ADR: `dogwatch.toml` grows from packages-only to the full AC-2 declaration surface — `[[python.packages]]`, `[python] exclude` globs (each of which must match at least one file, else `exclude-unmatched`), `[[python.rules]]` (`forbid` and `layers` kinds with syntax-validated selectors), and optional `[[openapi.contracts]]` — with every invalid config rejected before scanning by a diagnostic naming the offending TOML key path (FR-001–FR-009). Second, the common report model per the CD-4/CD-2 ADRs: the report envelope moves to schema `"0.2"`, gaining `status` (`pass`/`fail`/`inconclusive`, derived purely from contents per FR-011) and a `diagnostics` array alongside the existing provenance block and `findings`, with the normalized `Finding` (source, check_id, severity, message, fingerprint, waiver, locator) and `Diagnostic` (source, id, severity, message) entities, stable canonical JSON serialization, and a versioned JSON Schema pin (FR-010–FR-015). The CLI's exit code becomes a pure function of the run outcome — 0 pass, 1 fail, 2 config failure/inconclusive/usage/write error (FR-016–FR-018) — so a policy violation is never mistaken for infrastructure failure (AC-4). The approach extends the established CD-5 modules in place: `config.py` stays the orchestrator and gains three focused validation modules (`exclude.py`, `rules.py`, `contracts.py`); `report.py`/`diagnostics.py` grow the common model; `cli.py` gains a scan seam that produces no findings or diagnostics in this ticket (A-1) plus the status→exit mapping; one new golden fixture (`fixtures/full-surface/`) proves the whole AC-2 surface end-to-end (FR-019). No scan step, engine, adapter, waiver, or workflow-provenance field is added — those arrive with their consuming tickets (A-1, A-2, A-4, A-5, A-13, A-14).

## 2. Technical Context

| Dimension | Decision | Evidence |
|---|---|---|
| Language | Python ≥ 3.11 (supported 3.11–3.14), stdlib-only runtime — **no new dependencies** | `scanner/pyproject.toml` (`requires-python`, `dependencies = []`), `tests/test_isolation.py` enforces stdlib-or-dogwatch imports and zero runtime deps |
| Build/package | uv locked (`uv sync --locked`, `uv run --locked`), `uv_build` backend, console script `dogwatch` | `scanner/pyproject.toml`, root `Makefile` |
| Testing | pytest with the `golden` marker split: `make test-scanner` = `-m "not golden"`, `make test-fixtures` = `-m golden`; `jsonschema` (Draft 2020-12) is a dev-only dependency for schema tests | `Makefile`, `scanner/pyproject.toml` `[dependency-groups]`, `tests/golden/harness.py` |
| Lint/type | `ruff format --check` + `ruff check` (E,F,W,I,UP,B) + `mypy --strict` over `src` and `tests` | `Makefile lint-scanner`, `scanner/pyproject.toml` |
| Storage | None. Reads one TOML policy file (`tomllib`); writes one JSON report (atomic `os.replace`, or stdout mode) | `config.py`, `output.py` |
| Platform | CLI on macOS/Linux only (Windows unsupported); paths via `os.path` | `README.md` "Prerequisites" |
| Determinism | Byte-identical output across runs; harness varies TZ/LC_ALL/HOME/PYTHONHASHSEED and asserts no environment leakage; no wall-clock, random ids, host/user/cwd leakage | `tests/golden/harness.py` (`VARIANTS`, `STRIPPED_VARS`), `test_fixture_goldens.py` leak assertions, FR-014 |
| Performance | Peak child RSS ≤ 200 MB per check run; fixture-scale repositories; no network access at run time | `tests/test_resources.py`, `tests/test_trust_boundary.py` |
| Scale constraints | Static fixture projects; no remote services, no credentials | `README.md`, `fixtures/README.md` |

**Not applicable** (no AC or clarification answer calls for them; recorded so downstream stages do not invent them): auth/identity, migrations, background jobs, event/messaging contracts, rate limiting, observability/SLOs, deployment topology, secrets management, data retention, backup/DR. The only "API surface" in this ticket is the CLI + report JSON schema; the only "config management" is the `dogwatch.toml` contract itself.

**NEEDS CLARIFICATION**: none gating. The frozen spec closed all five clarification questions (`q-config-surface`, `q-ac4-triggerability`, `q-provenance-depth`, `q-selector-resolution`, `q-declaration-cardinalities`). The remaining micro-semantics the spec leaves open all have spec-grounded defaults, applied and recorded in §5 (Research Notes); the three an operator might still want to flip are listed in §9 (Open Questions) as non-gating recorded defaults.

## 3. Constitution Check

No formal constitution document was provided with this run; the active principles are the repo's established, test-enforced contracts (evidence cited per row). Every principle maps to a gate:

| Principle | Gate | Evidence & plan conformance |
|---|---|---|
| Determinism — byte-identical reports; no wall-clock/random/env-dependent values | **PASS** | `report.py:serialize_canonical` (sort_keys, indent=2, ensure_ascii=False, trailing newline), golden harness env variants. Plan keeps `serialize_canonical` untouched (FR-014); new fields (`status`, `diagnostics`) are content-derived only; goldens regenerate once via `make regen-fixtures` (FR-019, US-5). |
| Scanner isolation — stdlib-only imports, zero runtime dependencies | **PASS** | `tests/test_isolation.py`, `pyproject.toml dependencies=[]`. The FR-004 glob matcher is hand-rolled (decision D-1); no `pathspec`/`wcmatch`/`fnmatch`-across-separator shortcut is introduced. |
| Trust boundary — never import or execute scanned code; config-time tree walk lists names only | **PASS** | `tests/test_trust_boundary.py`, `test_config.py` trust tests. The exclusion-validation walk uses `os.scandir` name/type entries only, never opens file contents under package roots (spec: Edge Cases "Trust boundary"). The existing tests are updated to the spec-authorized narrowed invariant; the "never import user code" guarantee is absolute and unchanged. |
| Golden discipline — goldens change only via `make regen-fixtures`; fixtures are static data, never installed/imported/executed | **PASS** | `fixtures/README.md` rules, `Makefile regen-fixtures`. The new fixture is static data; its golden is generated by the regeneration command, never hand-edited; existing fixtures keep configs and layouts (FR-019). |
| Makefile as the single task contract — each recipe runs in one area directory, calling only that area's toolchain | **PASS** | Root `Makefile` header ("Root task contract (IC-2)"). No Makefile changes are needed; all verification runs through existing targets. |
| Fail-closed gate semantics — exit 2 is never a pass; precedence inconclusive > fail > pass | **PASS** | FR-011, FR-016, A-6, CD-4 ADR ("0 pass · 1 gate failed · 2 inconclusive; CI must never treat 2 as a pass"). Exit mapping is a pure function; mode tests assert all four (report, exit) pairs (SC-002). |
| Versioned schema pin — every report the CLI writes validates against a schema shipped in the repo | **PASS** | FR-015, `scanner/schemas/report-0.1.schema.json`, `tests/test_schema.py`. Plan ships `report-0.2.schema.json` per the existing naming convention (A-8) and removes the unreferenced 0.1 file (decision D-8). |
| Stable entity names across stages | **PASS** | The frozen spec's Key Entities names are used verbatim: `DogwatchConfig`, `PackageDecl`, `ExclusionDecl`, `RuleDecl`, `OpenApiContractDecl`, `Report`, `Finding`, `Diagnostic`, `Status`, `ExitCode`. The one rename (`PolicyConfig` → `DogwatchConfig`) is spec-mandated (Key Entities) and called out in §6. |

No EXCEPTIONs, no ERRORs. The plan proceeds.

## 4. Project Structure

All changes are inside `scanner/` and `fixtures/` — the CD-6 delta per the frozen spec's Overview. `api/`, `web/`, and the root `Makefile` are untouched (verified: nothing outside `scanner/` references the report shape or schema).

```
scanner/
  schemas/
    report-0.2.schema.json          NEW    — schema pin for version "0.2" (FR-015, A-8)
    report-0.1.schema.json          REMOVED — dead pin after the 0.2 cutover (D-8)
  src/dogwatch/
    __init__.py                     unchanged
    __main__.py                     unchanged
    diagnostics.py                  CHANGED — Diagnostic gains source+severity; EXIT_GATE_FAILED
                                             mapped; render_diagnostics extracted (FR-013, FR-016, FR-018)
    config.py                       CHANGED — PolicyConfig → DogwatchConfig + new fields; validation
                                             orchestration; extended unknown-key surface; packages
                                             keyword tightening (FR-003, FR-009, Key Entities)
    exclude.py                      NEW    — ExclusionDecl, glob syntax validation, glob matcher,
                                             package-tree walk for the match check (FR-004)
    rules.py                        NEW    — RuleDecl, selector syntax validation, forbid/layers
                                             constraints (FR-005–FR-007)
    contracts.py                    NEW    — OpenApiContractDecl, contract path validation (FR-008)
    report.py                       CHANGED — envelope "0.2" with status+diagnostics; Finding, Locator,
                                             Status, derive_status, exit_code_for_status;
                                             serialize_canonical unchanged (FR-010–FR-014)
    cli.py                          CHANGED — scan seam (empty in CD-6), status→exit mapping,
                                             scan-time diagnostic stderr wiring (FR-016–FR-018, A-1)
    output.py                       unchanged (A-12)
  tests/
    conftest.py                     CHANGED — make_config gains file-creation support
    test_diagnostics.py             CHANGED — new Diagnostic shape, render, exit constants
    test_config.py                  CHANGED — file/packages cases kept; keyword case added; unknown-key
                                             cases updated to the new surface; narrowed load_policy
                                             trust invariant; os-call whitelist grows os.scandir
    test_exclude.py                 NEW    — FR-004 + exclusion edge cases
    test_rules.py                   NEW    — FR-005–FR-007 + rules edge cases
    test_contracts.py               NEW    — FR-008 + contracts edge cases
    test_report.py                  CHANGED — 0.2 envelope, status derivation, Finding/Locator
    test_schema.py                  CHANGED — 0.2 schema, finding/diagnostic item shapes
    test_cli.py                     CHANGED — 0.2 expected report; four-mode tests at the scan seam;
                                             exit contract 0/1/2
    test_trust_boundary.py          CHANGED — narrowed invariant + exclusions variant
    test_isolation.py               unchanged
    test_resources.py                unchanged
    golden/
      harness.py                    unchanged
      regenerate.py                 unchanged
      test_fixture_goldens.py       CHANGED — schema path 0.2; status/diagnostics assertions
fixtures/
  README.md                         CHANGED — documents the new fixture
  minimal/                          config unchanged (still valid per A-3); golden regenerated
  full-surface/                     NEW    — dogwatch.toml (all four AC-2 surfaces), source tree,
                                              api/ spec file, expected-report.json (via regen)
```

## 5. Research Notes

The frozen spec closed its five clarification questions; no NEEDS CLARIFICATION item remains gating. The decisions below resolve the micro-semantics the spec leaves at the "at minimum" level. Each records the decision, rationale, and rejected alternatives. Papers consulted: CD-3 policy ADR (`/Users/iliaglushkov/Documents/sandbox/contractor/.am/reports/7ee72c98-20e3-41ff-9321-386775b7a72e-research-paper.md` — exclusion glob precedent, rule semantics), CD-4 adapter ADR (`/Users/iliaglushkov/Documents/sandbox/contractor/.am/reports/5b28548a-4c88-4600-b7cc-a6df1df95c7b-research-paper.md` — normalized finding/locator/fingerprint shape, exit semantics). CD-2's report-lifecycle content enters via the spec's A-4/FR-010 (provenance depth deferred), which the plan takes as given.

- **D-1 — Exclusion glob semantics (FR-004).** *Decision:* patterns are `/`-separated, anchored at the config file's directory, and matched against the **full** config-dir-relative path of each file (no suffix matching). A path segment that is exactly `**` matches zero or more whole segments; every other `*` occurrence (including several in one segment, e.g. `a*b`, `a**b`) matches within its segment only. Only `*` is a wildcard: `?`, `[`, `\` are rejected at validation; absolute patterns and `.`/`..`/empty segments are rejected; matching is case-sensitive. The matchable set is **regular files under the declared package directories** (`<config_dir>/<root>/<name>/`); symlinks are neither traversed nor counted (`DirEntry.is_file(follow_symlinks=False)`); a pattern matching only directories or only files outside package directories fails with `exclude-unmatched`. *Rationale:* FR-004's wording plus gitignore/tach precedent (CD-3 §2.7: exclude paths are always globs; regex removed); A-11's justification ("because exclusions act only on source files") requires the domain to be where sources live — CD-3 defines sources as files under `root/name/`, and FR-003's "root directory exists and is a directory" describes the existing check on `<root>/<name>`, so "declared package root" reads as the package directory. *Rejected:* `fnmatch` (not path-aware — `*` crosses separators); `pathlib.PurePath.full_match` (Python 3.13+ only; project supports 3.11); a `pathspec`/`wcmatch` dependency (violates the stdlib-only isolation test); matching against the `root` field subtree instead of the package directory (would let patterns that can never exclude a source pass validation, defeating the check's stated purpose). *Flagged for operator confirmation in §9 (non-gating).*
- **D-2 — "Valid Python identifier" excludes keywords (FR-003, FR-006, FR-007).** *Decision:* package `name` and every selector segment must satisfy `s.isidentifier() and not keyword.iskeyword(s)`. *Rationale:* the spec's Edge Cases list "keyword" among invalid package names, and FR-003/006/007 use the same phrase ("Python identifier") for selectors — keywords are not identifiers in Python's grammar, and a keyword module name could never be imported, so a keyword selector segment would be silently dead. *Rejected:* `isidentifier()` alone (accepts `import`, contradicting the edge case; asymmetric with packages).
- **D-3 — Contract path syntax (FR-008).** *Decision:* `path` must be `/`-separated, relative, with non-empty segments, no `.` or `..` segments, no absolute paths, no backslashes, and extension `.yaml`/`.yml`/`.json`; unique across contracts. *Rationale:* the spec lists `..`/absolute/backslash; rejecting `.` segments is the minimal rule that makes textual uniqueness (FR-008) imply file uniqueness (`./api/x.yaml` and `api/x.yaml` would otherwise alias). *Rejected:* normalize-then-compare (more machinery, same outcome).
- **D-4 — One unified Diagnostic entity (Key Entities, FR-013).** *Decision:* the single `Diagnostic` dataclass carries `(source, id, severity, message)`; pre-scan config-failure diagnostics are constructed with `source="dogwatch"`, `severity="error"`; the stderr render uses `id` and `message` only, format unchanged. *Rationale:* the spec defines one Diagnostic entity with four fields; config failures are produced by the scanner. *Rejected:* separate config/report diagnostic types (entity drift from Key Entities).
- **D-5 — Scan seam in the CLI (A-1, A-5, FR-018, SC-002).** *Decision:* `cli.py` gains a module-level `scan(cfg) -> tuple[tuple[Finding, ...], tuple[Diagnostic, ...]]` returning `((), ())` in CD-6; the CLI renders the returned diagnostics to stderr after the report write and maps the derived status to the exit code. *Rationale:* the spec's lifecycle step 3 exists but produces nothing in this ticket; the seam makes FR-018's wiring and the exit-1/exit-2 mode paths real, testable code (SC-002 asserts full (report, exit) pairs through the actual CLI path) without adding a scan step. *Rejected:* pure model-level construction only (leaves FR-018 wiring and the fail/inconclusive exit paths unexercised in the CLI).
- **D-6 — Validation staging and aggregation (FR-002).** *Decision:* keep the established two-phase pattern, extended: (1) file load — fail-fast; (2) document validation (unknown keys collected across the whole surface, sorted, first reported — existing behavior — then a fixed-order walk: `python` table type → packages → `exclude` → rules → `openapi` table → contracts) — fail-fast; (3) package filesystem structure — aggregate, existing order; (4) exclusion match walk — aggregate unmatched patterns in config order. A failing stage stops the run; later stages never run. *Rationale:* matches the tested CD-5 behavior (`test_stages_stop_at_first_failure`, `test_v4_reports_every_failure_in_contract_order`); FR-002 requires precision, not aggregation. *Rejected:* aggregating everything (changes established tested behavior for no requirement).
- **D-7 — Module split for the config surface.** *Decision:* `config.py` remains the orchestrator (file loading, orchestration, packages, top-level unknown-key surface); `exclude.py`, `rules.py`, `contracts.py` own their declaration's validation (including per-entry unknown keys, with rule-kind awareness). *Rationale:* the three validation domains are independent; the split keeps files cohesive and gives downstream decomposition clean write scopes. *Rejected:* one monolithic `config.py` (size, cohesion, parallel write-scope conflicts).
- **D-8 — Schema 0.1 file removed.** *Decision:* `report-0.2.schema.json` is added and `report-0.1.schema.json` deleted in the same change; all three referencing test files update their `SCHEMA_PATH`. *Rationale:* grep-verified that only `scanner/tests/{test_cli,test_schema,golden/test_fixture_goldens}.py` reference the 0.1 file; after the 0.2 cutover and golden regeneration no 0.1 report exists in the repo, so the file is a dead pin; git history preserves it. *Rejected:* keeping both (an unreferenced schema invites drift).
- **D-9 — New fixture named `full-surface`.** *Decision:* `fixtures/full-surface/` per the kebab naming convention, describing FR-019's "full AC-2 config surface". *Rationale:* `fixtures/README.md` layout rules; any convention-conforming name works; this one is self-describing next to `minimal`.
- **D-10 — `waiver` pinned null-only in schema 0.2.** *Decision:* the schema pins `"waiver": {"type": "null"}`; the model field exists (always `None`). *Rationale:* FR-012 "always `null` in this version; the field exists so the later engine can populate it without a model change"; the engine ticket relaxes the schema with a version bump per the A-4 pattern. *Rejected:* allowing the future waiver object now (nothing defines its shape yet; would weaken the 0.2 pin).
- **D-11 — Locator logical-location keys.** *Decision:* the locator is a flat object: `path` (required), optional `line`/`column` (integers ≥ 1), optional `source_module`/`target_module` (Python findings' logical location per FR-012); `additionalProperties: false`. *Rationale:* FR-012 names "the source and target module names" for Python findings; a flat locator matches the CD-4 ADR's locator style; adapter-specific extensions (OpenAPI's `method`/`json_pointer`/provenance) arrive with their tickets and bump the schema (A-13). *Rejected:* a nested `logical` object (no spec basis); open `additionalProperties` (weakens the pin).
- **D-12 — FR-018 render scope and ordering.** *Decision:* **all** scan-time diagnostics carried in the report (any severity) render to stderr, one `dogwatch:<id>: <message>` line each, after the report write succeeds and before the exit code is returned; a write failure keeps the existing `dogwatch: error: …` path. *Rationale:* FR-018 says diagnostics "carried in the report" are rendered — all of them; warning/info diagnostics never change status (FR-011) but must be visible; write-first ordering keeps the write-failure message last on stderr. With empty scan results (all CD-6 runs) stderr stays empty, preserving the golden contract.
- **D-13 — Exclusion walk runs only when `exclude` is non-empty.** *Decision:* with an absent or empty `exclude` list, no tree walk happens. *Rationale:* FR-004's check is vacuous with zero patterns; keeps `fixtures/minimal` (packages-only) behavior — including the existing strict no-listing trust assertion for no-exclusion configs — unchanged.

## 6. Data Model

Entity names are the frozen spec's Key Entities, verbatim. All declaration and model dataclasses are frozen (immutable), matching the existing `PackageDecl`/`PolicyConfig` style.

### Config entities (produced only by successful validation)

**DogwatchConfig** (replaces `PolicyConfig`; the rename is spec-mandated by Key Entities and is the only entity rename in this plan):
- `path_arg: str` — as given on the CLI
- `raw: bytes` — the config file's raw bytes (digest input)
- `packages: tuple[PackageDecl, ...]` — ≥ 1 (FR-003)
- `exclusions: tuple[ExclusionDecl, ...]` — may be empty (A-3)
- `rules: tuple[RuleDecl, ...]` — may be empty (FR-005, A-3)
- `contracts: tuple[OpenApiContractDecl, ...]` — may be empty (FR-008, A-3)

**PackageDecl** (existing): `name: str`, `root: str`.

**ExclusionDecl** (new): `pattern: str` — validated per D-1.

**RuleDecl** (new; one entity, kind-discriminated per Key Entities):
- `id: str` — `^[a-z][a-z0-9]*(-[a-z0-9]+)*$`, ≤ 64 chars, unique across rules
- `kind: Literal["forbid", "layers"]`
- `reason: str` — non-empty (A-10)
- forbid fields: `targets: tuple[str, ...]` (required, non-empty), `sources: tuple[str, ...]` (empty ⇒ default scope = all scanned packages, FR-006), `except_sources: tuple[str, ...]`, `except_targets: tuple[str, ...]` (each entry, when present, a non-empty list; every `except_sources` entry a strict descendant of some `sources` entry, every `except_targets` entry a strict descendant of some `targets` entry)
- layers fields: `layers: tuple[str, ...]` (required, non-empty, ordered, no duplicates, no entry a dotted-prefix of another), `container: str | None`, `exhaustive: bool = False` (`exhaustive=true` ⇒ `container` required and every `layers` entry a strict descendant of `container`, the container itself not qualifying)

Selector syntax (both kinds): dot-separated, every segment a valid Python identifier excluding keywords (D-2); syntax-only in this version — a selector matching no module is **not** a config error (A-14, deliberately asymmetric with exclusion globs). "Strict descendant" = proper dotted-prefix extension (`X != Y` and `X` starts with `Y + "."`).

**OpenApiContractDecl** (new): `id: str` (same rules as rule ids, unique across contracts), `path: str` (per D-3; file existence **not** checked at validation time — FR-008).

### Validation rules and staging (FR-001–FR-009, per D-6)

1. **File load** (existing, kept): missing path → `config-not-found`; directory/unreadable/non-UTF-8/invalid TOML → `config-invalid` with the TOML line number for syntax errors. Empty file parses as an empty document → "requires at least one `[[python.packages]]` entry".
2. **Document validation** (fail-fast; unknown keys collected across the whole surface, sorted, first reported — existing behavior): accepted surface is exactly `[[python.packages]]` (`name`, `root`), `[python] exclude`, `[[python.rules]]` (per-kind key sets: forbid = `id, kind, reason, targets, sources, except_sources, except_targets`; layers = `id, kind, reason, layers, container, exhaustive`), `[[openapi.contracts]]` (`id`, `path`) — and nothing else; the later-ticket ADR keys (`[python] type_checking`, `clock`, `max_waiver_days`, `[[python.waivers]]`, baseline file, `[openapi]` settings/severity/waiver keys) are rejected as unsupported (FR-009, A-2). Within a rule entry: `kind` validity → per-kind unknown keys → field types/required → value constraints. Package `name` gains keyword rejection (D-2).
3. **Package structure** (aggregate, existing order and messages): root directory exists/is a directory, no duplicate names, no split across roots, no nesting.
4. **Exclusion walk** (aggregate, config order): each pattern must match ≥ 1 regular file under a declared package directory (D-1, D-13), else `exclude-unmatched`. The walk lists directory entries under package directories only, never reads file contents, never follows symlinks, never imports or executes scanned code (Edge Cases "Trust boundary").

Every validation diagnostic names the offending TOML key path (e.g. `python.rules[1].targets[0]`, `openapi.contracts[0].path`) and states the violated constraint (FR-002, SC-001).

### Report entities

**Report** (envelope, all fields always present — FR-010): `schema_version: "0.2"`, `status: Status`, `scanner: {name: "dogwatch", version}`, `policy: {path: basename(path_arg), digest: {sha256: sha256(raw)}}`, `findings: list[Finding]`, `diagnostics: list[Diagnostic]`. Provenance depth is `scanner` + `policy` only in 0.2 (A-4); the CD-2 workflow fields stay forbidden (existing `test_schema.py` FORBIDDEN_FIELDS test keeps guarding this).

**Status** (enum): `pass | fail | inconclusive`. **Derivation (FR-011, pure function):** any diagnostic with severity `error` → `inconclusive`; else any finding with severity `error` and `waiver is None` → `fail`; else `pass`. Warning/info never change status; an error finding plus an error diagnostic → `inconclusive` (fail-closed, Edge Cases "Report and exit").

**Finding** (new, frozen; FR-012): `source: str` (producing adapter's name), `check_id: str` (violated rule id), `severity: Severity`, `message: str` (display-only), `fingerprint: str` (stable identity derived from rule/source/target — never line numbers, message text, or timestamps; the derivation algorithm is per-adapter and arrives with the engine/adapter tickets — in CD-6 the field is model+schema only), `waiver: None` (always null in 0.2, D-10), `locator: Locator`.

**Locator** (new, frozen; D-11): `path: str` (file path relative to the config file's directory, A-9), `line: int | None`, `column: int | None`, `source_module: str | None`, `target_module: str | None` (Python findings' logical location).

**Diagnostic** (updated, frozen; FR-013, D-4): `source: str` (scanner or adapter), `id: str` (kebab-case, `dogwatch` namespace — the `dogwatch:` prefix appears in the stderr render, the JSON `id` is bare kebab-case), `severity: Severity`, `message: str`. Diagnostics are scanner/adapter events, never policy violations. Scanner-known ids: `config-not-found`, `config-invalid`, `exclude-unmatched` (pre-scan; never in a report, A-7), `source-syntax-invalid` (scan-time, FR-013/FR-017); adapters use their own ids within the class (e.g. the CD-4 OpenAPI tool-failure ids).

**Severity** (enum): `error | warning | info`. **ExitCode** (constants, existing names): `EXIT_OK=0`, `EXIT_GATE_FAILED=1` (defined and mapped in CD-6, no longer merely reserved), `EXIT_ERROR=2`.

### State transitions (run lifecycle, from the spec)

1. config file → *load* → parsed document (failure ⇒ pre-scan failure: diagnostic on stderr, **no report**, exit 2 — A-7)
2. parsed document → *validate* (stages 2–4 above) → `DogwatchConfig`
3. `DogwatchConfig` → *scan* → findings + diagnostics (**empty in CD-6** — A-1; the seam exists per D-5)
4. findings + diagnostics → *derive status* (FR-011)
5. status → *map exit* (FR-016) and → *serialize + write report* (FR-014; scan-time diagnostics also render to stderr per FR-018/D-12)

Relationships: one `DogwatchConfig` produces one Report per run; findings reference rule ids declared in the config; diagnostics reference component names, never rule ids as violations.

## 7. Interface Contracts

These are the binding agreements between areas and stages. All commands run in this workspace.

### 7.1 CLI contract (AC-4, FR-016–FR-018, A-12)

- **Command:** `dogwatch check --config <PATH> --output <PATH|->` (defaults `./dogwatch.toml`, `./dogwatch-report.json`; `-` = stdout). `dogwatch --version` prints `dogwatch <semver>`. No new subcommands or flags (P-2 is a proposal and is not built).
- **Exit codes (pure function of outcome):**

| Outcome | Report written | Exit | Stderr |
|---|---|---|---|
| status `pass` | yes | 0 | empty (no scan-time diagnostics in CD-6) |
| status `fail` | yes | 1 | scan-time diagnostic lines, if any |
| status `inconclusive` | yes | 2 | scan-time diagnostic lines |
| pre-scan config failure | **no** | 2 | `dogwatch:<config-not-found\|config-invalid\|exclude-unmatched>: <message>` lines |
| usage error | no | 2 | `usage: dogwatch …` + `dogwatch: error: <message>` |
| report-write failure | no (atomic; no partial file) | 2 | `dogwatch: error: cannot write report to <path>: <reason>` |

- **Report bytes:** canonical JSON (sorted keys, 2-space indent, non-ASCII literal, trailing newline), written atomically or to stdout; byte-identical across runs (FR-014, SC-003). Preserved behaviors: same-file guard (`--output` == `--config` ⇒ exit 2 before write), stdout broken-pipe handling, atomic replace, `--version` (A-12).
- **Processing order:** load → same-file guard → scan → build → write → render scan-time diagnostics → exit (updates the existing `test_processing_order…` contract).

### 7.2 Report JSON Schema 0.2 (FR-015, A-8) — `scanner/schemas/report-0.2.schema.json`

Draft 2020-12, `$id: urn:dogwatch:schema:report:0.2`, top level `additionalProperties: false`, `required: [schema_version, status, scanner, policy, findings, diagnostics]`:

- `schema_version`: `{"const": "0.2"}`
- `status`: `{"enum": ["pass", "fail", "inconclusive"]}`
- `scanner`: unchanged from 0.1 (`name` const `dogwatch`; `version` semver pattern)
- `policy`: unchanged from 0.1 (`path` base-name pattern; `digest.sha256` 64-hex)
- `findings`: array of items (replacing 0.1's `items: false`): object, `additionalProperties: false`, `required: [source, check_id, severity, message, fingerprint, waiver, locator]`; `source`/`check_id`/`fingerprint` strings `minLength 1`; `severity` enum `[error, warning, info]`; `message` string; `waiver` `{"type": "null"}` (D-10); `locator`: object, `additionalProperties: false`, `required: [path]`, properties `path` (string, `minLength 1`), `line`/`column` (integer, `minimum 1`), `source_module`/`target_module` (string, `minLength 1`) (D-11)
- `diagnostics`: array of items: object, `additionalProperties: false`, `required: [source, id, severity, message]`; `source` string `minLength 1`; `id` string `{"pattern": "^[a-z][a-z0-9]*(-[a-z0-9]+)*$"}`; `severity` enum `[error, warning, info]`; `message` string

Every report the CLI writes validates against this schema; constructed-mode reports (SC-002) validate too (SC-005). The 0.1 schema file is removed (D-8).

### 7.3 Config file contract (`dogwatch.toml`) — the accepted surface (FR-003–FR-009, A-2, A-3)

```toml
[python]
exclude = ["<glob>", ...]              # optional; each must match ≥1 file (FR-004)

[[python.packages]]                     # ≥1 required (FR-003)
name = "<identifier>"                   # single top-level identifier, not a keyword
root = "<dir>"                          # relative to the config file's directory

[[python.rules]]                        # 0..n (FR-005)
id = "<kebab ≤64>"                      # unique
kind = "forbid"                         # or "layers"
reason = "<non-empty>"
targets = ["<selector>", ...]           # forbid: required, non-empty
sources = [...]                         # forbid: optional, non-empty
except_sources = [...]                   # forbid: optional; strict descendants of sources
except_targets = [...]                   # forbid: optional; strict descendants of targets

[[python.rules]]
kind = "layers"
layers = ["<selector>", ...]            # required, non-empty, ordered, unique, unambiguous
container = "<selector>"                # optional; required when exhaustive = true
exhaustive = false                      # optional bool

[[openapi.contracts]]                   # 0..n (FR-008)
id = "<kebab ≤64>"                      # unique across contracts
path = "<relative .yaml/.yml/.json>"    # unique; existence NOT checked at validation
```

Every key outside this surface — including `[python] type_checking`, `clock`, `max_waiver_days`, `[[python.waivers]]`, the baseline file, and `[openapi]` settings/severity/waiver keys — is rejected with a `config-invalid` diagnostic naming the key (FR-009, A-2). Cardinalities: ≥1 package; 0 exclusions, 0 rules, 0 contracts all valid (A-3, US-6).

### 7.4 Python module contracts (the seams between areas)

| Symbol | Contract |
|---|---|
| `dogwatch.config.load_policy(config_arg: str) -> DogwatchConfig` | Raises `DogwatchError` carrying `(config-not-found \| config-invalid \| exclude-unmatched)` diagnostics on any pre-scan failure (FR-001–FR-009). Name kept — "policy" is the spec's own vocabulary. |
| `dogwatch.config.DogwatchConfig` | Fields per §6; frozen. |
| `dogwatch.diagnostics.Diagnostic(source: str, id: str, severity: Severity, message: str)` | Frozen; config-failure constructors use `source="dogwatch"`, `severity="error"` (D-4). |
| `dogwatch.diagnostics.render_diagnostics(diagnostics: Sequence[Diagnostic]) -> str` | One `dogwatch:<id>: <message>` line each + trailing newline; `render(err)` delegates to it (format unchanged — FR-018). |
| `dogwatch.diagnostics.{EXIT_OK, EXIT_GATE_FAILED, EXIT_ERROR}` | `0 / 1 / 2`; `EXIT_GATE_FAILED` is now emitted (FR-016). |
| `dogwatch.report.build_report(cfg: DogwatchConfig, version: str, findings: Sequence[Finding] = (), diagnostics: Sequence[Diagnostic] = ()) -> dict[str, Any]` | Builds the 0.2 envelope; derives `status` internally (FR-010, FR-011). |
| `dogwatch.report.derive_status(findings, diagnostics) -> Status` | Pure; FR-011 precedence inconclusive > fail > pass. |
| `dogwatch.report.exit_code_for_status(status: Status) -> int` | Pure; pass→0, fail→1, inconclusive→2 (FR-016). |
| `dogwatch.report.serialize_canonical(obj) -> bytes` | Unchanged (FR-014). |
| `dogwatch.cli.scan(cfg: DogwatchConfig) -> tuple[tuple[Finding, ...], tuple[Diagnostic, ...]]` | Returns `((), ())` in CD-6 (D-5); the engine ticket replaces the body. |
| `dogwatch.output.write_report(data: bytes, output_arg: str)` | Unchanged (A-12). |

### 7.5 Error taxonomy (AC-1, AC-4, FR-017)

Four mutually distinguishable modes, each a unique (report, exit) pair: **policy violation** → error-severity finding in report, `status: "fail"`, exit 1; **malformed config** → config diagnostic on stderr (`config-not-found`/`config-invalid`/`exclude-unmatched`), no report, exit 2; **invalid source syntax** → `source-syntax-invalid` error diagnostic in report, `status: "inconclusive"`, exit 2; **adapter failure** → adapter error diagnostic in report (distinct `source` and id), `status: "inconclusive"`, exit 2. Config failure vs. inconclusive are distinguished by report presence (A-6). Per A-5, all four are satisfied at contract level in this ticket (tests construct each mode and assert the full pair; only malformed config is additionally triggerable end-to-end through the real CLI without test seams).

## 8. Parallelization Strategy

`team_work=True`, `max_concurrency=3`. Four work packages: one small serial foundation, two parallel, one finalizing. Write scopes are disjoint within each wave; every wave lands green on `make test-scanner` and `make lint-scanner`.

### Ownership areas

**F0 — Shared model seam (serial; blocks F1 and F2).**
Scope: `diagnostics.py` (Diagnostic gains `source`+`severity`; `render_diagnostics` extracted, `render` delegates; `EXIT_GATE_FAILED` comment updated), `config.py` (**only**: `PolicyConfig` → `DogwatchConfig` rename + new fields, populated as empty tuples; Diagnostic construction sites updated to the new shape), `test_diagnostics.py`, and the construction sites in `test_config.py`, `test_report.py`, `test_schema.py`. No behavior change: 0.1 envelope, packages-only validation, goldens untouched. *Gate:* `make test-scanner && make lint-scanner && make test-fixtures` all green (CP0).

**F1 — Config validation surface (parallel with F2).**
Scope: `config.py` (orchestration, extended unknown-key surface, keyword tightening), `exclude.py`, `rules.py`, `contracts.py`, `conftest.py`, `test_config.py`, `test_exclude.py`, `test_rules.py`, `test_contracts.py`. Delivers FR-001–FR-009, the config-file/packages/exclusions/rules/contracts edge-case groups, the narrowed `load_policy` trust invariant and the `os.scandir` whitelist addition (Edge Cases "Trust boundary"), SC-001. *Gate:* CP1 — all three make targets green (CLI output still 0.1-shaped, so goldens still pass).

**F2 — Report model, schema & CLI (parallel with F1).**
Scope: `report.py`, `schemas/report-0.2.schema.json` (add; remove 0.1 — D-8), `cli.py` (scan seam, status→exit, FR-018 wiring), `test_report.py`, `test_schema.py`, `test_diagnostics.py`, `test_cli.py`. Delivers FR-010–FR-018, SC-002 (four-mode tests at the scan seam + malformed-config end-to-end), SC-003 (unit level), SC-005. CLI-level config-failure tests use only file-load failures (no F1 dependency); `exclude-unmatched` is tested at `load_policy` level in F1 — the (no report, exit 2) pair is covered generically by F2's CLI tests. *Gate:* CP2 — `make test-scanner && make lint-scanner` green; **`make test-fixtures` is red by design at this checkpoint** (goldens are still 0.1 while CLI output is 0.2) — the transition US-5 anticipates; resolved by F3. Flagged so the reviewer is not surprised.

**F3 — Fixtures & trust boundary (after F1 + F2).**
Scope: `fixtures/full-surface/**` (new), `fixtures/README.md`, `fixtures/minimal/expected-report.json` (regenerated), `tests/golden/test_fixture_goldens.py` (0.2 schema path; `status == "pass"`, `diagnostics == []` assertions), `test_trust_boundary.py` (narrowed invariant + an exclusions-present variant). Delivers FR-019, the CLI-level trust-boundary edge case, SC-003 (golden level). The fixture declares all four AC-2 surfaces: ≥1 package, ≥1 exclusion pattern matching ≥1 real file under the package directory, ≥1 `forbid` and ≥1 `layers` rule (selectors need not resolve — A-14), 1 OpenAPI contract with a checked-in static spec file (e.g. `api/shop-api.yaml`; nothing parses it in CD-6); its golden is generated only via `make regen-fixtures`. *Gate:* CP3 — final SC-004 gate: `make test-scanner && make lint-scanner && make test-fixtures` all green.

### Dependency graph

```
F0 ──► F1 ──┐
 │          ├──► F3
 └──► F2 ──┘
```

F1 ∥ F2 (disjoint write scopes; both depend only on F0's pinned seams from §7.4). F3 depends on F1 (validation accepts the fixture config; walk behavior for trust tests) and F2 (0.2 output shape, schema, CLI). Golden regeneration is exclusively F3's and always last.

### Integration seams other workers must honor

- The §7.4 module contracts are frozen once F0 lands; F1/F2 code against them, not against each other's internals.
- `fixtures/**` and `tests/golden/**` are F3-exclusive; no other area writes goldens (golden discipline).
- `diagnostics.py` is F0-exclusive; after CP0 it is stable for the rest of the run.
- The red `make test-fixtures` window between CP2 and CP3 is expected and must not be "fixed" by hand-editing goldens — only `make regen-fixtures` (F3) resolves it.

### Verification matrix (all commands run in this workspace; nothing depends on PRs, merges, remote CI, or deployments)

| Requirement | Verification | Owner |
|---|---|---|
| AC-1, FR-001–FR-002 (pre-scan failure, precise diagnostics) | `make test-scanner` — `test_config.py` file cases; `test_exclude/test_rules/test_contracts` path-naming diagnostics | F1 |
| AC-2, FR-003–FR-008 (full config surface) | `make test-scanner` — per-module positive/negative cases incl. US-1/US-6 configs, zero-cardinalities, selector-no-match validity (A-14) | F1 |
| FR-009 (unknown keys, incl. later-ticket ADR keys) | `make test-scanner` — `test_config.py` unknown-key cases across the surface | F1 |
| SC-001 (100% of enumerated edge cases → diagnostic naming the config path) | `make test-scanner` — one test per enumerated case across the four config test files; report/exit/CLI groups in F2's files | F1 + F2 |
| AC-3, FR-010–FR-014 (envelope, status, models, serialization) | `make test-scanner` — `test_report.py`, `test_diagnostics.py` (byte-stability, non-ASCII, fail-closed precedence) | F2 |
| FR-015, SC-005 (schema 0.2 pin) | `make test-scanner` — `test_schema.py` over golden and constructed-mode reports | F2 |
| AC-4, FR-016–FR-017, SC-002 (four distinguishable modes) | `make test-scanner` — `test_cli.py` mode tests at the scan seam (assert full (report, stderr, exit) pairs; 4/4, zero identical pairs) + malformed-config end-to-end | F2 |
| FR-018 (stderr render of scan-time diagnostics) | `make test-scanner` — `test_diagnostics.py` render tests + `test_cli.py` seam wiring | F2 |
| FR-019, US-5 (full-surface fixture; goldens regenerate once, verify forever) | `make regen-fixtures` then `make test-fixtures` — byte-exact goldens incl. the new fixture | F3 |
| SC-003 (byte-stability end-to-end) | `make test-fixtures` — golden match, repeated-runs-identical, TZ/locale/HOME/PYTHONHASHSEED variants, leak assertions | F3 |
| Trust boundary (narrowed invariant; never import user code) | `make test-scanner` — `test_config.py` (load_policy) + `test_trust_boundary.py` (CLI, with and without exclusions) | F1 + F3 |
| A-12 (preserved CLI behavior), isolation, resource budget | `make test-scanner` — existing `test_cli`/`test_output`/`test_isolation`/`test_resources` stay green unchanged | F2 (keeps them green) |
| SC-004 (all quality gates) | `make test-scanner && make lint-scanner && make test-fixtures` — final gate at CP3 | F3 |

**Explicitly not built** (spec Proposals P-1–P-4): example policy configs, a `dogwatch validate` subcommand, a config-file JSON Schema, and rule metadata in the report. No requirement in this plan depends on them.

## 9. Open Questions

No gating open questions remain — the frozen spec closed all five clarification questions, and every micro-decision above has a spec-grounded default (recorded in §5). Three recorded defaults are surfaced here for operator confirmation because the spec's letter admits a second reading; none blocks execution, and flipping any of them changes one localized implementation point plus its tests:

1. **Exclusion match domain (D-1):** the plan reads "under a declared package root" as *under the package directory* `<root>/<name>/` (where sources live, per A-11's justification and FR-003's use of "root directory" for the existing `<root>/<name>` existence check). The alternative reading — the `root` field subtree — would let patterns matching only non-source files under `root` pass validation. Default applied: package directory.
2. **Selector keyword segments (D-2):** the plan applies "valid Python identifier" uniformly (packages and selector segments reject keywords). The spec's edge cases list "keyword" only for package names; the uniform reading prevents silently-dead selectors. Default applied: keywords rejected in both.
3. **Contract `.` segments (D-3):** the plan rejects `.` segments so textual path uniqueness implies file uniqueness. The spec lists only `..` for contracts. Default applied: `.` rejected.

One expectation to set for the reviewer (not a question): between F2 landing and F3 completing, `make test-fixtures` is red by design (goldens awaiting regeneration for the 0.2 shape, per US-5); the branch is fully green at CP3, which is the SC-004 acceptance point.
