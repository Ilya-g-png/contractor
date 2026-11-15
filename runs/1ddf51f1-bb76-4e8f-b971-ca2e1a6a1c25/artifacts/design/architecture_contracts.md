
# Architecture Contracts — CD-6: Validated Dogwatch Configuration and Common Report Contracts

**Inputs:** `artifacts/design/architecture.md` (cited as **ARCH §n**), `artifacts/planning/frozen_spec.md` (cited as **FR-/SC-/A-/US-**), and the implementation plan's decisions (cited as **D-n**, from `artifacts/planning/implementation_plan.md` §5–§7, which the architecture adopts).

**Code grounding:** checked against `scanner/src/dogwatch/{config,diagnostics,report,cli,output}.py`, `scanner/schemas/report-0.1.schema.json` and `scanner/tests/{test_config,test_schema,test_diagnostics}.py` as they stand at `b11da70`.

**Normative language:** "MUST" is binding. Every contract below carries an ID (`IC-*`, `DC-*`, `INV-*`, `VC-*`) so the decomposer can reference it.

**Shape of the system.** One synchronous, single-process, stdlib-only CLI. It has no HTTP API, no storage, no network and no message bus (ARCH §2, §5; A-1). Its external surfaces are:
- the `dogwatch` command line;
- the `dogwatch.toml` input file;
- the report JSON output;
- stderr.

Its internal surfaces are the in-process Python module seams that later tickets plug into.

---

## 1. Interface Contracts

### IC-CLI-1 — `dogwatch check` (the gate invocation)

| Aspect | Contract | Trace |
|---|---|---|
| **Verb / path** | `dogwatch check [--config PATH] [--output PATH\|-]`. This is the process entry point `dogwatch.cli.main(argv) -> int`. | ARCH §3 `cli.py`; A-12 |
| **Request (arguments)** | `--config`: default `./dogwatch.toml`. `--output`: default `./dogwatch-report.json`; `-` means stdout. **No new flags or subcommands.** `dogwatch validate` (P-2) is not built. | A-12; ARCH §6 "API surface" |
| **Request (file input)** | The `dogwatch.toml` document, per IC-CFG-1 / DC-C*. | FR-003–FR-009 |
| **Response (artifact)** | On a completed scan, exactly one report (DC-R1) written atomically to `--output`, or to stdout when `--output -`. The bytes MUST equal `serialize_canonical(build_report(...))`. | FR-010, FR-014, A-12 |
| **Response (stderr)** | The line grammar in IC-ERR-3. On a successful run (pass, fail or inconclusive) stderr contains exactly the scan-time diagnostic lines, in report order. Every CD-6 pass run therefore has empty stderr. | FR-018, D-12 |
| **Error codes** | Exit codes per IC-ERR-1. Diagnostic ids per IC-ERR-2. | FR-016, FR-017 |
| **Processing order (binding)** | `parse args` → `load_policy` → same-file guard → `scan(cfg)` → `build_report` → `serialize_canonical` → `write_report` → render scan-time diagnostics to stderr → `return exit_code_for_status(status)`. A failure at any step skips every later step. | ARCH §4.3, §5.2; plan §7.1 |
| **Idempotency** | Same config bytes, same source tree and same scanner version give byte-identical report bytes and the same exit code on every run (INV-D1). The atomic replace means a rerun never leaves a partial or mixed file. Pre-existing output is replaced only by a complete new report, and is left untouched on any pre-scan, guard or write failure. | FR-014, SC-003, A-12 |

**Outcome table (binding: FR-016, FR-017, plan §7.1):**

| Outcome | Report written? | Exit | Stderr content |
|---|---|---|---|
| `status: "pass"` | yes | `0` | scan-time diagnostic lines (none in CD-6) |
| `status: "fail"` | yes | `1` | scan-time diagnostic lines, if any |
| `status: "inconclusive"` | yes | `2` | scan-time diagnostic lines (at least one error line) |
| Pre-scan config failure | **no** | `2` | ≥ 1 `dogwatch:<config-not-found\|config-invalid\|exclude-unmatched>: <message>` line |
| Same-file guard (`--output` resolves to the config file) | no | `2` | `dogwatch: error: output path <out> is the same file as config <cfg>` |
| Usage error (argparse) | no | `2` | `usage: dogwatch …` line, then `dogwatch: error: <message>` |
| Report write failure (`OSError`) | no (no partial file) | `2` | `dogwatch: error: cannot write report to <out>: <reason>` as the **last** stderr line. Scan-time diagnostics are not rendered. |
| Broken pipe on stdout | — | unchanged CD-5 handling | unchanged |

### IC-CLI-2 — `dogwatch --version`

The `--version` flag is unchanged: it prints `dogwatch <semver>` to stdout and exits `0` (A-12).

### IC-CFG-1 — `dogwatch.toml` input contract (accepted surface)

The accepted surface is **exactly** the following (FR-003–FR-009, A-2, A-3, plan §7.3). All paths resolve relative to `dirname(--config)` (A-9).

```toml
[python]                                  # table; required (packages live in it)
exclude = ["<glob>", ...]                 # optional; 0..n; each MUST match ≥1 file (FR-004)

[[python.packages]]                       # 1..n REQUIRED (FR-003)
name = "<identifier, not a keyword>"
root = "<dir relative to config dir>"

[[python.rules]]                          # 0..n (FR-005)
id = "<kebab-case, ≤64>"                  # unique across rules
kind = "forbid"
reason = "<non-empty>"
targets = ["<selector>", ...]             # required, non-empty
sources = ["<selector>", ...]             # optional; non-empty when present
except_sources = ["<selector>", ...]      # optional; non-empty; each a strict descendant of a sources entry
except_targets = ["<selector>", ...]      # optional; non-empty; each a strict descendant of a targets entry

[[python.rules]]
id = "<kebab-case, ≤64>"
kind = "layers"
reason = "<non-empty>"
layers = ["<selector>", ...]              # required, non-empty, ordered, no duplicates, no entry a dotted prefix of another
container = "<selector>"                  # optional; required when exhaustive = true
exhaustive = false                        # optional bool, default false

[openapi]                                 # optional table
[[openapi.contracts]]                     # 0..n (FR-008)
id = "<kebab-case, ≤64>"                  # unique across contracts
path = "<relative/path.yaml|.yml|.json>"  # unique; existence NOT checked
```

**Accepted key sets.** Any other key is rejected with `config-invalid` "`<key path>` is not supported in this version" (FR-009):

| Table | Accepted keys |
|---|---|
| top level | `python`, `openapi` |
| `[python]` | `packages`, `exclude`, `rules` |
| `[[python.packages]]` entry | `name`, `root` |
| `[[python.rules]]` entry, `kind = "forbid"` | `id`, `kind`, `reason`, `targets`, `sources`, `except_sources`, `except_targets` |
| `[[python.rules]]` entry, `kind = "layers"` | `id`, `kind`, `reason`, `layers`, `container`, `exhaustive` |
| `[openapi]` | `contracts` |
| `[[openapi.contracts]]` entry | `id`, `path` |

These keys are explicitly rejected because they belong to later tickets (A-2): `python.type_checking`, `python.clock`, `python.max_waiver_days`, `python.waivers`, any baseline key, and any `[openapi]` key other than `contracts`.

**Validation staging (binding; ARCH §5.1, D-6).** A failing stage raises `DogwatchError`. No later stage runs.

| # | Stage | Failure mode | Order of checks / of reported diagnostics |
|---|---|---|---|
| 1 | File load: exists → regular readable file → UTF-8 → TOML | fail-fast, 1 diagnostic | as listed |
| 2a | Unknown keys across top level, `[python]`, `[openapi]`, package entries and contract entries. Only entries whose container is the right type are inspected. | fail-fast | All unknown key paths are collected and sorted lexicographically (Python `str` order). Only the **first** is reported. |
| 2b | Document values | fail-fast, 1 diagnostic | `python` presence and type → `python.packages` → `python.exclude` syntax → `python.rules` → `openapi` type → `openapi.contracts`. Within each array, entries go in index order. Within a rule entry: `kind` → per-kind unknown keys → required fields and types → `id` grammar → `id` uniqueness → `reason` non-empty → selector syntax → structural constraints (descendant, prefix, duplicate, container). |
| 3 | Package filesystem structure (existence, is-dir, duplicate, split, nested) | **aggregated**, then raised | The existing CD-5 order: per-package existence checks in declaration order, then pairwise conflicts in `(i, j>i)` order |
| 4 | Exclusion match walk. Runs **only if** `exclude` is non-empty (D-13). | **aggregated**, then raised | One `exclude-unmatched` per unmatched pattern, in config order |

**Key-path rendering (binding; FR-002, ARCH §3 `_validate.py`).** Paths are dotted table names with 0-based `[i]` array indices, for example `python.packages[0].name`, `python.rules[1].targets[0]`, `python.exclude[2]`, `openapi.contracts[0].path`.

**Glob matching contract (IC-CFG-2; FR-004, D-1, ARCH §2).**
- **Pattern syntax:** a non-empty string; not starting with `/`; split on `/` into segments.
  - Every segment MUST be non-empty and not `.` or `..`.
  - The characters `?`, `[` and `\` are forbidden anywhere.
- **Candidate set:** every regular file found by walking `<config_dir>/<root>/<name>/` recursively with `os.scandir`. Entries count only if `DirEntry.is_file(follow_symlinks=False)` is true. The walk descends only into entries where `DirEntry.is_dir(follow_symlinks=False)` is true. File contents are never opened.
- **Candidate path string:** `posixpath.normpath("<root>/<name>/<relative-path-inside-package>")`, using `/` separators and relative to the config directory. For example, root `./src` with name `shop` gives `src/shop/legacy/x.py`.
- **Match:** the pattern matches the **whole** candidate path, segment by segment.
  - A pattern segment that is exactly `**` matches zero or more whole path segments.
  - Any other pattern segment matches exactly one path segment. In such a segment, each `*` matches any run of characters (possibly empty) that contains no `/`, and every other character matches itself literally and case-sensitively. For example, `a**b` behaves like `a*b`.
- **Independence:** each pattern is evaluated against the full candidate set on its own, so one pattern can never "consume" another's matches (Edge Cases "Exclusions").

**Selector contract (IC-CFG-3; FR-006, FR-007, D-2, A-14).**
- A selector is a string split on `.`. Every segment `s` satisfies `s.isidentifier() and not keyword.iskeyword(s)`.
- "X is a strict descendant of Y" ⇔ `X != Y and X.startswith(Y + ".")`.
- Whether a selector resolves to a module is **never** checked.

### IC-PY — In-process module seams (cross-ticket API)

These are the contracts the engine and adapter tickets bind to (ARCH §3, plan §7.4). All entities are frozen dataclasses.

| Symbol | Request | Response | Errors | Idempotency / purity |
|---|---|---|---|---|
| `dogwatch.config.load_policy(config_arg: str) -> DogwatchConfig` | path string | a valid `DogwatchConfig` (DC-C1) | Raises `DogwatchError` with ≥ 1 `Diagnostic`. Each has `source="dogwatch"`, `severity="error"` and `id ∈ {config-not-found, config-invalid, exclude-unmatched}`. No other exception escapes for config defects. | Reads only the config file and the package-directory listings (INV-T1). Deterministic for the same filesystem state. |
| `dogwatch.config.DogwatchConfig`, `PackageDecl` | — | DC-C1, DC-C2 | — | Built **only** by `load_policy`. `PolicyConfig` is renamed to `DogwatchConfig` with no alias. |
| `dogwatch.exclude.parse_exclusions(value: object) -> tuple[ExclusionDecl, ...]` | the raw `python.exclude` value | in config order | `DogwatchError(config-invalid)` | pure |
| `dogwatch.exclude.check_matches(config_dir: str, packages: tuple[PackageDecl, ...], exclusions: tuple[ExclusionDecl, ...]) -> None` | validated packages and exclusions | `None` | `DogwatchError` carrying one `exclude-unmatched` per unmatched pattern, in config order | Directory listing only (INV-T1) |
| `dogwatch.rules.parse_rules(value: object) -> tuple[RuleDecl, ...]` | the raw `python.rules` value | in config order | `DogwatchError(config-invalid)` | pure, no I/O |
| `dogwatch.contracts.parse_contracts(value: object) -> tuple[OpenApiContractDecl, ...]` | the raw `openapi.contracts` value | in config order | `DogwatchError(config-invalid)` | pure, no I/O, no existence check |
| `dogwatch._validate` (private) | — | `config_invalid(message) -> DogwatchError`, key-path rendering, `is_identifier`, `is_kebab_id`, typed accessors | — | Private: may be imported only by `config`, `exclude`, `rules` and `contracts` |
| `dogwatch.diagnostics.Diagnostic(source: str, id: str, severity: Severity, message: str)` | — | DC-R5 | — | frozen |
| `dogwatch.diagnostics.DogwatchError(diagnostics: tuple[Diagnostic, ...])` | ≥ 1 diagnostic | `.diagnostics` | `ValueError` when given an empty tuple (existing) | — |
| `dogwatch.diagnostics.render_diagnostics(diagnostics: Sequence[Diagnostic]) -> str` | sequence | `"".join(f"dogwatch:{d.id}: {d.message}\n" for d in diagnostics)`, which is `""` for an empty sequence | — | Pure. The existing `render(err)` MUST return `render_diagnostics(err.diagnostics)`. |
| `dogwatch.diagnostics.EXIT_OK / EXIT_GATE_FAILED / EXIT_ERROR` | — | `0 / 1 / 2` | — | constants |
| `dogwatch.report.derive_status(findings: Sequence[Finding], diagnostics: Sequence[Diagnostic]) -> Status` | — | per DC-R7 | none | pure, total |
| `dogwatch.report.exit_code_for_status(status: Status) -> int` | — | `pass→0`, `fail→1`, `inconclusive→2` | none | pure, total |
| `dogwatch.report.build_report(cfg: DogwatchConfig, version: str, findings: Sequence[Finding] = (), diagnostics: Sequence[Diagnostic] = ()) -> dict[str, Any]` | — | The DC-R1 JSON object, with findings and diagnostics in canonical order (DC-R8) and `status = derive_status(...)` | None: performs no validation of adapter-supplied strings (see INV-S2) | pure, no I/O |
| `dogwatch.report.serialize_canonical(obj: Any) -> bytes` | — | unchanged: `json.dumps(sort_keys=True, indent=2, ensure_ascii=False, separators=(",", ": ")) + "\n"`, UTF-8 encoded | — | pure |
| `dogwatch.cli.scan(cfg: DogwatchConfig) -> tuple[tuple[Finding, ...], tuple[Diagnostic, ...]]` | a validated config | `((), ())` in CD-6 | **MUST NOT raise for scan conditions.** Invalid source and adapter failures are *returned* as error diagnostics (FR-013). Behaviour on unexpected exceptions is open (OQ-1). | The signature is frozen for the engine and adapter tickets. Tests replace it via `monkeypatch.setattr(dogwatch.cli, "scan", …)`, so `main` MUST look `scan` up as a module attribute at call time. |
| `dogwatch.output.write_report(data: bytes, output_arg: str) -> None` | — | unchanged | `OSError`, `BrokenPipeError` | unchanged (A-12) |

### IC-ERR — Error taxonomy and codes

**IC-ERR-1 — Exit codes (FR-016, A-6).**

| Code | Constant | Meaning |
|---|---|---|
| `0` | `EXIT_OK` | Report written, `status == "pass"` |
| `1` | `EXIT_GATE_FAILED` | Report written, `status == "fail"`. **Emitted for the first time in CD-6.** |
| `2` | `EXIT_ERROR` | Pre-scan config failure, `status == "inconclusive"`, usage error, same-file guard, or write failure. **Never a pass.** |

**IC-ERR-2 — Diagnostic id registry (FR-013, FR-017, ARCH §4.2).** Every id matches `^[a-z][a-z0-9]*(-[a-z0-9]+)*$`.

| Id | Source | Phase | Where it appears | Effect |
|---|---|---|---|---|
| `config-not-found` | `dogwatch` | pre-scan | stderr only, never in a report | exit 2, no report |
| `config-invalid` | `dogwatch` | pre-scan | stderr only | exit 2, no report |
| `exclude-unmatched` | `dogwatch` | pre-scan (stage 4) | stderr only | exit 2, no report |
| `source-syntax-invalid` | `dogwatch` | scan-time | report and stderr | `error` severity ⇒ `inconclusive`, exit 2 |
| *(adapter-chosen, e.g. `openapi-tool-failed`, `openapi-tool-timeout`)* | the adapter's name (≠ `dogwatch`, per the OQ-2 default) | scan-time | report and stderr | `error` severity ⇒ `inconclusive`, exit 2 |

**IC-ERR-3 — Stderr line grammar (FR-018, A-12).** Each line is one of:
- `dogwatch:<id>: <message>`, for diagnostics of either phase;
- `dogwatch: error: <message>`, for usage, guard and write errors;
- argparse's `usage: …` line.

**IC-ERR-4 — Config diagnostic catalogue (SC-001, FR-001, FR-002).**
- Every `config-invalid` and `exclude-unmatched` message for a document-stage or filesystem-stage failure MUST contain the offending key path from the table below.
- Messages marked **(preserved)** are existing CD-5 text, asserted by `test_config.py`, and MUST stay verbatim.
- The other templates are normative wording, so tests may assert the full text. `<p>` is the config path argument, `<v>` is the offending value.

| Edge case (frozen spec) | Id | Message template |
|---|---|---|
| Path missing | `config-not-found` | `<p> does not exist` **(preserved)** |
| Directory / unreadable | `config-invalid` | `<p> is not a readable file` **(preserved)** |
| Non-UTF-8 | `config-invalid` | `<p> is not valid UTF-8` **(preserved)** |
| TOML syntax error | `config-invalid` | `<p>:<line>: invalid TOML: <tomllib msg>` **(preserved)** |
| Empty file / no `python` / no or empty `packages` | `config-invalid` | `<p> requires at least one [[python.packages]] entry` **(preserved)** |
| Unknown key, any level | `config-invalid` | `<key path> is not supported in this version` **(preserved)** |
| `python` not a table | `config-invalid` | `python must be a table` **(preserved)** |
| `packages` not an array of tables | `config-invalid` | `python.packages must be a array of tables` **(preserved, including the existing article)** |
| Package `name`/`root` missing or non-string | `config-invalid` | `python.packages[i].<k> is required` / `… must be a string` **(preserved)** |
| Package name dotted, kebab or keyword | `config-invalid` | `python.packages[i].name '<v>' must be a single top-level identifier` **(preserved; now also fires for keywords, D-2)** |
| Package root missing, is a file, duplicate, split, nested (stage 3) | `config-invalid` | `python.packages[i]: <existing CD-5 message>`, where `i` is the index of the entry the existing message is about (for conflicts, the later entry `j`). See note N-1. |
| `exclude` not an array | `config-invalid` | `python.exclude must be an array of strings` |
| `exclude` entry not a string | `config-invalid` | `python.exclude[i] must be a string` |
| Pattern empty / absolute / `.`, `..` or empty segment / `?`, `[` or `\` | `config-invalid` | `python.exclude[i] '<v>' <constraint>`, where `<constraint>` ∈ {`must not be empty`, `must be relative`, `must not contain '.', '..' or empty segments`, `may use only '*' as a wildcard ('?', '[' and '\' are not allowed)`} |
| Pattern matches no file | `exclude-unmatched` | `python.exclude[i] '<v>' matches no file under a declared package directory` |
| `rules` not an array of tables | `config-invalid` | `python.rules must be an array of tables` |
| `kind` missing / non-string / unknown | `config-invalid` | `python.rules[i].kind is required` / `… must be a string` / `python.rules[i].kind '<v>' must be one of: forbid, layers` |
| Unknown key inside a rule, including the other kind's keys | `config-invalid` | `python.rules[i].<k> is not supported in this version` |
| `id`/`reason` missing or non-string | `config-invalid` | `python.rules[i].<k> is required` / `… must be a string` |
| `id` not kebab-case or > 64 chars | `config-invalid` | `python.rules[i].id '<v>' must be kebab-case ([a-z][a-z0-9]*(-[a-z0-9]+)*) and at most 64 characters` |
| Duplicate rule id | `config-invalid` | `python.rules[j].id '<v>' duplicates python.rules[i].id`, with `j` the later index |
| `reason` empty (`""`) | `config-invalid` | `python.rules[i].reason must not be empty` |
| A list field that is not an array of strings | `config-invalid` | `python.rules[i].<k> must be an array of strings` |
| `targets` missing (forbid) / `layers` missing (layers) | `config-invalid` | `python.rules[i].<k> is required` |
| Empty `targets`/`sources`/`except_*`/`layers` | `config-invalid` | `python.rules[i].<k> must not be empty` |
| Invalid selector (`a..b`, `foo-bar`, keyword segment) | `config-invalid` | `python.rules[i].<k>[j] '<v>' is not a valid selector` (for `container`: `python.rules[i].container '<v>' …`) |
| `except_sources`/`except_targets` not a strict descendant | `config-invalid` | `python.rules[i].except_sources[j] '<v>' must be a strict descendant of a sources entry` (respectively `… of a targets entry`) |
| Duplicate layer | `config-invalid` | `python.rules[i].layers[j] '<v>' is declared more than once` |
| One layer a dotted prefix of another | `config-invalid` | `python.rules[i].layers[j] '<v>' overlaps python.rules[i].layers[k] '<w>'`, with `j > k` |
| `exhaustive` non-bool | `config-invalid` | `python.rules[i].exhaustive must be a boolean` |
| `exhaustive = true` without `container` | `config-invalid` | `python.rules[i].container is required when exhaustive = true` |
| Layer not a strict descendant of `container` (including the container itself) | `config-invalid` | `python.rules[i].layers[j] '<v>' must be a strict descendant of container '<c>'` |
| `openapi` not a table / `contracts` not an array of tables | `config-invalid` | `openapi must be a table` / `openapi.contracts must be an array of tables` |
| Contract `id`/`path` missing or non-string, bad id, duplicate id | `config-invalid` | same templates as for rules, with prefix `openapi.contracts[i]` |
| Contract path: absolute / `.`, `..` or empty segment / backslash / bad extension | `config-invalid` | `openapi.contracts[i].path '<v>' <constraint>`, where `<constraint>` ∈ {`must be relative`, `must not contain '.', '..' or empty segments`, `must use '/' separators`, `must end in .yaml, .yml or .json`} |
| Duplicate contract path | `config-invalid` | `openapi.contracts[j].path '<v>' duplicates openapi.contracts[i].path` |

**N-1 (contract resolution of a conflict between upstream documents).** ARCH §5.1 says stage 3 keeps "the existing order and messages". FR-002 and SC-001 require *every* config-validation failure, including the package-structure edge cases, to name the TOML key path, and the existing stage-3 texts (for example `package 'x': directory 'r/x' does not exist`) do not. This contract follows the frozen requirement: stage 3 keeps its order and existing text but prefixes `python.packages[i]: `. The stage-3 assertions in `test_config.py` change accordingly. The operator can override this through CQ-1.

---

## 2. Event & Queue Contracts

**Not applicable.** There are no asynchronous surfaces: no queue, pub/sub, webhook, background job or retry loop (ARCH §5 "in-process, synchronous"; A-1). The only producer/consumer seam is the synchronous return value of `dogwatch.cli.scan` (IC-PY). Its delivery guarantee is "returned exactly once per run, or the process fails". There is no retry policy.

---

## 3. Data Contracts

### 3.1 Configuration entities (source of truth: `config.py` via `load_policy`; produced only on successful validation)

**DC-C1 — `DogwatchConfig`** (frozen; FR-003–FR-008, Key Entities)

| Field | Type | Nullable | Validation | Owner |
|---|---|---|---|---|
| `path_arg` | `str` | no | as given on the CLI | `config.py` |
| `raw` | `bytes` | no | the exact file bytes (digest input) | `config.py` |
| `packages` | `tuple[PackageDecl, ...]` | no | `len ≥ 1`, in declaration order | `config.py` |
| `exclusions` | `tuple[ExclusionDecl, ...]` | no | `len ≥ 0`, config order; `()` when absent | `exclude.py` |
| `rules` | `tuple[RuleDecl, ...]` | no | `len ≥ 0`, config order; ids unique | `rules.py` |
| `contracts` | `tuple[OpenApiContractDecl, ...]` | no | `len ≥ 0`, config order; ids and paths unique; `()` when `[openapi]` or `contracts` is absent | `contracts.py` |

**DC-C2 — `PackageDecl`** (frozen; FR-003, D-2)

| Field | Type | Nullable | Validation | Owner |
|---|---|---|---|---|
| `name` | `str` | no | `isidentifier() and not iskeyword()` | `config.py` |
| `root` | `str` | no | `<config_dir>/<root>/<name>` exists and is a directory; no duplicate, split or nested packages (stage 3) | `config.py` |

**DC-C3 — `ExclusionDecl`** (frozen; FR-004, D-1)

| Field | Type | Nullable | Validation | Owner |
|---|---|---|---|---|
| `pattern` | `str` | no | IC-CFG-2 syntax; matches ≥ 1 candidate file (stage 4). Duplicate patterns are **not** rejected, since no requirement asks for it; each is checked independently. | `exclude.py` |

**DC-C4 — `RuleDecl`** (frozen, kind-discriminated; FR-005–FR-007, ARCH §4.1)

| Field | Type | Nullable | forbid | layers | Validation |
|---|---|---|---|---|---|
| `id` | `str` | no | req | req | `^[a-z][a-z0-9]*(-[a-z0-9]+)*$`, `len ≤ 64`, unique across rules |
| `kind` | `Literal["forbid","layers"]` | no | req | req | closed set |
| `reason` | `str` | no | req | req | `len > 0` |
| `targets` | `tuple[str, ...]` | no | req, `len ≥ 1` | `()` | selectors (IC-CFG-3) |
| `sources` | `tuple[str, ...]` | no | opt, `len ≥ 1` when present; `()` means all scanned packages | `()` | selectors |
| `except_sources` | `tuple[str, ...]` | no | opt, `len ≥ 1` when present; each a strict descendant of some `sources` entry | `()` | selectors |
| `except_targets` | `tuple[str, ...]` | no | opt, `len ≥ 1` when present; each a strict descendant of some `targets` entry | `()` | selectors |
| `layers` | `tuple[str, ...]` | no | `()` | req, `len ≥ 1`, ordered, unique; `∀ a≠b: not b.startswith(a + ".")` | selectors |
| `container` | `str \| None` | yes | `None` | opt; required iff `exhaustive`; then every layer is a strict descendant of it | selector |
| `exhaustive` | `bool` | no | `False` | default `False` | TOML boolean only |

Owner: `rules.py`. Selectors are never resolved against modules (A-14).

**DC-C5 — `OpenApiContractDecl`** (frozen; FR-008, D-3)

| Field | Type | Nullable | Validation | Owner |
|---|---|---|---|---|
| `id` | `str` | no | kebab grammar ≤ 64 (shared `is_kebab_id`), unique across contracts | `contracts.py` |
| `path` | `str` | no | relative; `/`-separated; segments non-empty and not `.` or `..`; no `\`; ends `.yaml`, `.yml` or `.json` (case-sensitive); unique (textual); **existence not checked** | `contracts.py` |

### 3.2 Report entities (source of truth: `report.py` for the envelope and projection, `diagnostics.py` for `Diagnostic`, the scan seam for content)

**DC-R1 — Report envelope (JSON; all six keys always present; FR-010, A-4, A-8)**

| Field | JSON type | Nullable | Validation | Owner |
|---|---|---|---|---|
| `schema_version` | string | no | const `"0.2"` | `report.py` |
| `status` | string | no | `pass \| fail \| inconclusive`; equals DC-R7 applied to the arrays | `report.py` |
| `scanner.name` | string | no | const `"dogwatch"` | `report.py` |
| `scanner.version` | string | no | semver pattern (unchanged from 0.1); value is `dogwatch.__version__` | `report.py` |
| `policy.path` | string | no | `os.path.basename(path_arg)`; pattern `^[^/\\\u0000-\u001f]+$` (unchanged) | `report.py` |
| `policy.digest.sha256` | string | no | `^[0-9a-f]{64}$` = `sha256(raw).hexdigest()` | `report.py` |
| `findings` | array of DC-R3 | no | canonical order (DC-R8) | scan seam → `report.py` |
| `diagnostics` | array of DC-R5 | no | canonical order (DC-R8); never contains pre-scan ids | scan seam → `report.py` |

The CD-2 workflow fields remain **forbidden**: `commit_sha`, `object_format`, `dirty`, `base_sha`, `evaluation_date`, `scan_started_at` and the rest of the existing `FORBIDDEN_FIELDS` list. `additionalProperties: false` rejects them.

**DC-R2 — `Severity`**: `Literal["error","warning","info"]`. **`Status`**: `Literal["pass","fail","inconclusive"]`.

**DC-R3 — `Finding`** (frozen; FR-012, D-10)

| Field | Python type | JSON | Nullable | Validation | Owner |
|---|---|---|---|---|---|
| `source` | `str` | string | no | `minLength 1`; the producing adapter's name | adapter |
| `check_id` | `str` | string | no | `minLength 1`; the violated rule id (not schema-enforced against config) | adapter |
| `severity` | `Severity` | enum | no | DC-R2 | adapter |
| `message` | `str` | string | no | display only; not part of identity | adapter |
| `fingerprint` | `str` | string | no | `minLength 1`; derived only from rule, source and target, never from line, column, message or time; algorithm per adapter ticket (A-13, OQ-6) | adapter |
| `waiver` | `None` | `null` | **always null** | schema `{"type":"null"}`; key always emitted | `report.py` |
| `locator` | `Locator` | object | no | DC-R4 | adapter |

**DC-R4 — `Locator`** (frozen, flat; FR-012, D-11, A-9)

| Field | Python type | JSON | Nullable / presence | Validation |
|---|---|---|---|---|
| `path` | `str` | string | required | `minLength 1`; relative to the config directory |
| `line` | `int \| None` | integer | **omitted when `None`** (never `null`) | `≥ 1` |
| `column` | `int \| None` | integer | omitted when `None` | `≥ 1` |
| `source_module` | `str \| None` | string | omitted when `None` | `minLength 1` |
| `target_module` | `str \| None` | string | omitted when `None` | `minLength 1` |

**DC-R5 — `Diagnostic`** (frozen, one entity for both phases; FR-013, D-4)

| Field | Python type | JSON | Nullable | Validation | Owner |
|---|---|---|---|---|---|
| `source` | `str` | string | no | `minLength 1`; `"dogwatch"` is reserved for the scanner | scanner / adapter |
| `id` | `str` (widened from the CD-5 `Literal`) | string | no | `^[a-z][a-z0-9]*(-[a-z0-9]+)*$`; bare, with no `dogwatch:` prefix | scanner / adapter |
| `severity` | `Severity` | enum | no | DC-R2; pre-scan diagnostics are always `error` | scanner / adapter |
| `message` | `str` | string | no | any string | scanner / adapter |

Scanner ids are exported from `diagnostics.py` as named `Final[str]` constants: `CONFIG_NOT_FOUND`, `CONFIG_INVALID`, `EXCLUDE_UNMATCHED`, `SOURCE_SYNTAX_INVALID`.

**DC-R6 — JSON projection (ARCH §4.2).**
- `report.py` converts each entity with explicit functions. `dataclasses.asdict` is not used.
- Every `Finding` object has exactly the keys `{source, check_id, severity, message, fingerprint, waiver, locator}`.
- Every `Diagnostic` object has exactly `{source, id, severity, message}`.
- A `Locator` emits `path`, plus each optional key only when its value is non-`None`.

**DC-R7 — Status derivation (FR-011, ARCH §4.3).** Evaluated in order:
1. `inconclusive` if `any(d.severity == "error" for d in diagnostics)`;
2. else `fail` if `any(f.severity == "error" and f.waiver is None for f in findings)`;
3. else `pass`.

**DC-R8 — Canonical collection order (FR-014, ARCH §5.3).**
- Findings are sorted ascending by `(locator.path, locator.line or 0, locator.column or 0, check_id, fingerprint, source)`.
- Diagnostics are sorted ascending by `(source, id, message)`.
- Both use Python's default tuple and `str` (code point) ordering. Equal keys keep the input's relative order, since the sort is stable.
- This ordering applies **only** to report contents and their stderr mirror. Pre-scan `DogwatchError` diagnostics keep their stage order (IC-CFG-1).

**DC-R9 — Report JSON Schema 0.2** (`scanner/schemas/report-0.2.schema.json`; FR-015, plan §7.2). The validation semantics below are binding. Inlining the subschemas instead of using `$defs` is permitted.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:dogwatch:schema:report:0.2",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version", "status", "scanner", "policy", "findings", "diagnostics"],
  "properties": {
    "schema_version": {"const": "0.2"},
    "status": {"enum": ["pass", "fail", "inconclusive"]},
    "scanner": "<identical to report-0.1 'scanner' subschema>",
    "policy": "<identical to report-0.1 'policy' subschema>",
    "findings": {"type": "array", "items": {"$ref": "#/$defs/finding"}},
    "diagnostics": {"type": "array", "items": {"$ref": "#/$defs/diagnostic"}}
  },
  "$defs": {
    "severity": {"enum": ["error", "warning", "info"]},
    "finding": {
      "type": "object", "additionalProperties": false,
      "required": ["source", "check_id", "severity", "message", "fingerprint", "waiver", "locator"],
      "properties": {
        "source": {"type": "string", "minLength": 1},
        "check_id": {"type": "string", "minLength": 1},
        "severity": {"$ref": "#/$defs/severity"},
        "message": {"type": "string"},
        "fingerprint": {"type": "string", "minLength": 1},
        "waiver": {"type": "null"},
        "locator": {"$ref": "#/$defs/locator"}
      }
    },
    "locator": {
      "type": "object", "additionalProperties": false, "required": ["path"],
      "properties": {
        "path": {"type": "string", "minLength": 1},
        "line": {"type": "integer", "minimum": 1},
        "column": {"type": "integer", "minimum": 1},
        "source_module": {"type": "string", "minLength": 1},
        "target_module": {"type": "string", "minLength": 1}
      }
    },
    "diagnostic": {
      "type": "object", "additionalProperties": false,
      "required": ["source", "id", "severity", "message"],
      "properties": {
        "source": {"type": "string", "minLength": 1},
        "id": {"type": "string", "pattern": "^[a-z][a-z0-9]*(-[a-z0-9]+)*$"},
        "severity": {"$ref": "#/$defs/severity"},
        "message": {"type": "string"}
      }
    }
  }
}
```

(The two `"<identical to …>"` placeholders mean: copy those subschemas byte for byte from `report-0.1.schema.json`.)

### 3.3 Fixture data (FR-019, D-9)

**DC-F1 — `fixtures/full-surface/`.** Static data, never imported or executed. Contents:
- `dogwatch.toml` declaring ≥ 1 package, ≥ 1 `exclude` pattern that matches ≥ 1 real regular file under a package directory, ≥ 1 `forbid` rule, ≥ 1 `layers` rule, and exactly 1 `[[openapi.contracts]]` entry;
- the source tree;
- a checked-in static spec file at the contract's `path`;
- `expected-report.json`, produced only by `make regen-fixtures`, with `status: "pass"`, `findings: []`, `diagnostics: []`.

**DC-F2 — `fixtures/minimal/`.** The config and layout are unchanged. The golden is regenerated to 0.2 only through `make regen-fixtures`.

---

## 4. Boundary Invariants

Each invariant is a predicate that a test in `scanner/tests/` can assert. `run(C, O)` means invoking `dogwatch check --config C --output O` as a subprocess (or through `main`), returning `(exit, stdout, stderr, report_exists)`.

**Config → CLI boundary**
- **INV-V1 (validation precedes scan; AC-1):** with `cli.scan` replaced by a recorder, `run(C_invalid, O)` records **0** calls to `scan` for every invalid config `C_invalid` in the SC-001 catalogue.
- **INV-V2 (no report on pre-scan failure; A-7):** for every `C_invalid`: `exit == 2`, `not exists(O)` (or `O`'s bytes are unchanged if it existed before), and every stderr line matches `^dogwatch:(config-not-found|config-invalid|exclude-unmatched): .+$`.
- **INV-V3 (key-path precision; FR-002, SC-001):** for each IC-ERR-4 row except the four file-load rows, the raised `DogwatchError.diagnostics` contains a diagnostic whose `id` equals the row's id and whose `message` contains the row's key path. For the file-load rows, the message contains `<p>`, and for TOML errors it contains `:<line>:` with the correct 1-based line.
- **INV-V4 (pre-scan diagnostic shape):** `∀ d ∈ err.diagnostics: d.source == "dogwatch" and d.severity == "error" and d.id ∈ {config-not-found, config-invalid, exclude-unmatched}`.
- **INV-V5 (fail-fast staging; D-6):**
  - A config with an unknown key *and* a missing package directory yields exactly 1 diagnostic, the unknown-key one.
  - A config with a stage-3 defect *and* an unmatched exclusion yields only stage-3 diagnostics.
  - A document-stage failure always yields `len(diagnostics) == 1`.
- **INV-V6 (unknown-key determinism):** for a config with unknown keys `K` (at the 2a levels), the single message is `f"{sorted(K)[0]} is not supported in this version"`.
- **INV-V7 (accepted-surface completeness; AC-2, US-1, US-6):** `load_policy` succeeds on DC-F1's config. It also succeeds on each of these variants of that config: without `[[openapi.contracts]]`, without `rules`, without `exclude`, and packages-only.
- **INV-V8 (validated-entity soundness):** every `DogwatchConfig` returned by `load_policy` satisfies every DC-C1–DC-C5 validation predicate. For example: `len(packages) ≥ 1`, `len({r.id for r in rules}) == len(rules)`, and every forbid rule has `targets != ()`.
- **INV-V9 (selector non-resolution; A-14):** a config whose selectors name no existing module loads successfully.
- **INV-V10 (contract non-existence; FR-008):** a config whose contract `path` does not exist on disk loads successfully.

**Trust boundary (Edge Cases "Trust boundary"; ARCH §6)**
- **INV-T1 (read surface):** while `load_policy` runs, with `builtins.open`, `io.open` and `os.scandir` instrumented:
  - `open` is called only on `config_arg`;
  - `os.scandir` is called only on paths `p` with `realpath(p)` inside some `realpath(<config_dir>/<root>/<name>)`;
  - when `exclude` is absent or empty, `os.scandir` is called **0** times (D-13).
- **INV-T2 (no symlink traversal):** a symlink inside a package directory that points to a regular file or directory outside it neither satisfies a pattern nor is descended into. A pattern matching only that symlink yields `exclude-unmatched`.
- **INV-T3 (no import/execution):** for every fixture, `set(sys.modules)` after `run` (in-process) contains no module named after a fixture package, and a fixture source file that raises on import does not affect the outcome.

**Scan seam → report boundary**
- **INV-S1 (diagnostics are never violations; FR-013):** no Diagnostic JSON object has a `check_id` key, and no Finding object has an `id` key. Schema `additionalProperties: false` enforces both.
- **INV-S2 (schema validity; FR-015, SC-005):** every report written by the CLI validates against `report-0.2.schema.json`. This covers every golden and every constructed-mode report, including those with non-ASCII messages, warning/info entries and optional locator keys. An adapter that supplies a non-kebab diagnostic id or an empty `source` produces a schema-invalid report. `build_report` does not guard against this, so adapter tickets MUST cover it in their tests.
- **INV-S3 (pre-scan ids never reported; A-7):** `∀ d ∈ report.diagnostics: d.id ∉ {config-not-found, config-invalid, exclude-unmatched}`.
- **INV-S4 (scanner-reserved source; OQ-2 default):** a test-constructed adapter diagnostic has `source != "dogwatch"`. `source-syntax-invalid` has `source == "dogwatch"`.

**Report → exit boundary**
- **INV-E1 (status consistency; FR-011):** `report.status == derive_status(report.findings, report.diagnostics)` for every written report.
- **INV-E2 (exit purity; FR-016):** when a report is written, `exit == {"pass": 0, "fail": 1, "inconclusive": 2}[report.status]`.
- **INV-E3 (fail-closed):** `exit == 2 ⇒ (not report_exists) or report.status == "inconclusive"`, and `status == "pass" ⇒ exit == 0`.
- **INV-E4 (precedence):** `derive_status([error finding], [error diagnostic]) == "inconclusive"`. `derive_status([warning finding, info finding], [warning diagnostic]) == "pass"`.
- **INV-E5 (four-mode distinctness; FR-017, SC-002):** the four tuples `(report_exists, status, exit, any(d.source != "dogwatch" for d in diagnostics))` are pairwise distinct. They are produced by scan stubs returning an error finding, an error `source-syntax-invalid` diagnostic, and an error adapter diagnostic, plus one end-to-end invalid config. Expected values:
  - policy violation: `(T, fail, 1, F)`;
  - malformed config: `(F, —, 2, —)`;
  - invalid source syntax: `(T, inconclusive, 2, F)`;
  - adapter failure: `(T, inconclusive, 2, T)`.

**Serialization and determinism (FR-014, SC-003)**
- **INV-D1 (byte stability):** two runs on the same fixture give `bytes1 == bytes2`. This holds under each harness variant: differing `TZ`, `LC_ALL`, `HOME`, `PYTHONHASHSEED` and working directory.
- **INV-D2 (canonical form):** `bytes == serialize_canonical(json.loads(bytes))`, `bytes.endswith(b"\n")`, and non-ASCII characters appear literally (no `\u` escapes for printable non-ASCII).
- **INV-D3 (order independence):** for any permutation π of a scan result `(F, D)`, `build_report(cfg, v, π(F), π(D))` serializes to identical bytes.
- **INV-D4 (no ambient values):** report bytes contain none of: the current year as a timestamp field, `os.getcwd()`, `$HOME`, the hostname or the user name. The `FORBIDDEN_FIELDS` keys stay absent.
- **INV-D5 (provenance):** `report.policy.path == basename(C)`, `report.policy.digest.sha256 == sha256(read_bytes(C)).hexdigest()` and `report.scanner.version == dogwatch.__version__`.
- **INV-D6 (projection):** no `locator` value is JSON `null`. Every finding has the `waiver` key, and its value is `null`.

**Stderr boundary (FR-018, D-12)**
- **INV-O1 (mirror):** after a successful write, `stderr.splitlines() == [f"dogwatch:{d['id']}: {d['message']}" for d in report["diagnostics"]]`. This includes warning and info diagnostics, in report order. It is `[]` when `diagnostics == []`, which is the case for every CD-6 golden run.
- **INV-O2 (write failure):** when `write_report` raises `OSError`, no scan-time diagnostic line appears, the last stderr line starts with `dogwatch: error: cannot write report to `, `exit == 2`, and no `.<name>.*.tmp` file remains in the output directory.
- **INV-O3 (guard ordering):** when `--output` equals `--config`, `exit == 2`, the config bytes are unchanged and `scan` is called 0 times.

**Module-structure boundary (ARCH §3, constitution: isolation)**
- **INV-M1 (import DAG):** parse each module's `import` and `from` nodes with `ast`.
  - `diagnostics` imports no `dogwatch.*` module.
  - `_validate` imports only `dogwatch.diagnostics`.
  - `exclude`, `rules` and `contracts` import only `dogwatch._validate` and `dogwatch.diagnostics`, and never each other.
  - `config` does not import `report` or `cli`.
  - `report` does not import `cli`, `exclude`, `rules` or `contracts`.
  - The graph has no cycle.
- **INV-M2 (stdlib only):** every top-level import in `scanner/src/dogwatch/**` resolves to `sys.stdlib_module_names` or `dogwatch`. This is the existing `test_isolation.py`. `jsonschema` appears only under `tests/`.
- **INV-M3 (seam signature):** `inspect.signature(dogwatch.cli.scan)` has exactly one parameter, and `dogwatch.cli.scan(cfg) == ((), ())` for DC-F1's config.

---

## 5. Versioning & Compatibility

| Contract | Scheme | Compatibility rule | Deprecation policy | Trace |
|---|---|---|---|---|
| **VC-1 Report JSON** | `schema_version` string (`"0.2"`), with a matching schema file `report-<v>.schema.json` and `$id` `urn:dogwatch:schema:report:<v>` | **Strict, closed shape:** `additionalProperties: false` at every object level. *Any* added, removed or retyped field, or any relaxation (a non-null `waiver`, new locator keys, CD-2 provenance), MUST bump `schema_version`, ship a new schema file, and regenerate every golden in the same change. There is no compatibility promise between 0.x versions. A consumer MUST dispatch on `schema_version` and reject unknown values. No consumer exists yet: `api/` and `web/` are untouched. | No dual-publishing: when a version is superseded, its schema file is removed and lives on in git history (D-8). `report-0.1.schema.json` is deleted in CD-6, and the three test files that pinned it move to 0.2. | FR-010, FR-015, A-4, A-8, A-13, D-8, D-10, D-11 |
| **VC-2 `dogwatch.toml`** | No in-file version key. The accepted surface is defined by the scanner version. | **Closed surface:** unknown keys are rejected (FR-009), so a config written for a later ticket fails loudly instead of being silently ignored. Later tickets widen the surface additively (`type_checking`, `waivers`, baseline, `[openapi]` settings), so every config valid under CD-6 MUST stay valid. Narrowing or reinterpreting an accepted key is a breaking change and needs its own ticket. | None defined. No key is deprecated in CD-6. | FR-009, A-2, A-3 |
| **VC-3 CLI** | `dogwatch --version` semver (`scanner/pyproject.toml`, currently `0.1.0`) | The flags, defaults, stdout mode and exit-code meanings (0/1/2) are frozen. Exit `1` changes from "reserved" to "emitted". That is additive, because no CD-5 run could produce it. No requirement asks CD-6 to bump the package version. Bumping it would change every golden through `scanner.version`, so it is out of scope unless the operator asks. | Not applicable | FR-016, A-6, A-12 |
| **VC-4 Diagnostic ids** | Stable string identifiers (IC-ERR-2) | An id, once published, MUST NOT be renamed or repurposed. CI logs and later consumers match on it. Message text is **not** a compatibility surface beyond the IC-ERR-4 templates and the key-path inclusion required by INV-V3. New scanner ids are additive. Adapters add their own ids freely within the kebab grammar. | Not applicable | FR-013, FR-018 |
| **VC-5 Python seams** (IC-PY) | Internal, versioned with the package | `scan(cfg) -> (findings, diagnostics)`, `build_report(...)`, `derive_status`, `exit_code_for_status`, `Finding`, `Locator`, `Diagnostic` and `load_policy` are the **cross-ticket contract**. Engine and adapter tickets replace the body of `scan` without changing its signature. Adding Finding or Locator fields requires a VC-1 bump. `PolicyConfig` is renamed to `DogwatchConfig` with no alias, since no external importer exists. `render(err)` stays as a delegate. | Not applicable | ARCH §3, D-4, D-5 |
| **VC-6 Fingerprint** | Opaque non-empty string in 0.2 | The input domain is fixed (rule, source, target). The encoding is not. Pinning one (for example 64-hex) later tightens the schema and requires a VC-1 bump (OQ-6). | Not applicable | FR-012, A-13 |

---

## 6. Open Questions

Carried from ARCH §7, plus gaps found while writing these contracts. Each has a default that the contracts above already apply, so none of them blocks decomposition.

- **OQ-1 to OQ-6** (ARCH §7): an unexpected exception in `scan` falls through to Python's default exit 1; adapters use their own `source` name; the exclusion domain is `<root>/<name>/`; keywords are rejected in selector segments; `.` segments are rejected in contract paths; the fingerprint encoding is unpinned. The defaults are applied as written in ARCH §7.
- **CQ-1 (new): stage-3 package messages vs FR-002.** See N-1. *Default:* prefix `python.packages[i]: ` onto the existing text, which changes stage-3 assertions in `test_config.py`. *Alternative:* keep the CD-5 text verbatim and accept that SC-001 is not met for the five package-structure edge cases. Section that should answer: **FR-002 / SC-001**.
- **CQ-2 (new): `except_sources` when `sources` is absent.** FR-006 literally requires every `except_sources` entry to be a strict descendant of "some `sources` entry". When `sources` is absent (default scope: all scanned packages), there is no such entry, so any `except_sources` is invalid. *Default:* the literal reading; the rule is rejected with the IC-ERR-4 "must be a strict descendant of a sources entry" message. *Alternative:* treat the declared package names as the implicit `sources` for this check. Section that should answer: **FR-006**.
- **CQ-3 (new): whitespace-only `reason`.** FR-005 and A-10 say "non-empty". *Default:* `len(reason) > 0`, so `" "` is accepted. Section: **FR-005 / A-10**.
- **CQ-4 (new): multi-line diagnostic messages.** No requirement forbids newlines in `Diagnostic.message`. An embedded newline would break the one-line-per-diagnostic grammar in IC-ERR-3 and INV-O1. *Default:* not constrained in CD-6. Every scanner-produced message is single-line, and adapter tickets own their own messages. Section: **FR-018**.
