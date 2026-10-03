# Implementation Plan — CD-5: Monorepo bootstrap (scanner CLI, API, web app, deterministic fixture)

Source of truth: `artifacts/planning/frozen_spec.md`. Prior decisions this plan relies on:
- CD-2 report lifecycle and trust boundary: `/Users/iliaglushkov/Documents/sandbox/contractor/.am/reports/9c37b285-b35d-4dc2-be1c-2347272422e0-research-paper.md` (§2.3 provenance, §2.4 trust boundary)
- CD-3 policy file and diagnostics: `/Users/iliaglushkov/Documents/sandbox/contractor/.am/reports/7ee72c98-20e3-41ff-9321-386775b7a72e-research-paper.md` (§2.1, §2.2, §2.12)
- CD-4 fixture conventions: `/Users/iliaglushkov/Documents/sandbox/contractor/.am/reports/5b28548a-4c88-4600-b7cc-a6df1df95c7b-research-paper.md` (§2.6)

Workspace state I checked: the repository has only `.am/` (platform-managed, never touched) and `.playwright-mcp/` (to be git-ignored). It has one commit, `4ab1bdc`, and no source, manifests or constitution file. This is a greenfield plan.

---

## 1. Summary

CD-5 builds the foundation that later tickets land on. It creates four separate areas in one repository:

- `scanner/`: the `dogwatch` command-line tool, standard library only at runtime.
- `api/`: `dogwatch-api`, a stateless FastAPI service exposing only `/api/v1/health` and `/api/v1/openapi.json`.
- `web/`: a static React single-page app rendered in the browser (CSR), built with Vite, showing a shell and an API status indicator.
- `fixtures/`: static fixture projects with golden reports.

There is no product logic. Each Python area is its own `uv` project with its own `uv.lock`, so this is not a uv workspace (FR-002). The web area is a `pnpm` project with `pnpm-lock.yaml`. A root `Makefile` gives one command per action (FR-005). CI calls the same Makefile targets (FR-089).

The GitHub Actions workflow runs four jobs in parallel:
- scanner, as a CPython 3.11–3.14 matrix
- api
- web, including the bundle-budget build
- fixtures, on Linux and macOS × CPython 3.11 and 3.14

The workflow has read-only permissions, uses no secrets and pins actions to SHAs (FR-085–FR-089).

The scanner's one real behaviour is to:
1. validate the minimal `dogwatch.toml` shape (FR-013) and its package structure (FR-013a), and
2. write a canonical, byte-deterministic `schema_version: "0.1"` report with empty `findings` (FR-020–FR-026), using an atomic write.

A golden-file test checks it against `fixtures/minimal/expected-report.json` (FR-032). All deploy, observability, secrets and rollout topics are recorded as **provisional** direction in the README only (FR-090, A-11).

---

## 2. Technical Context

| Aspect | Decision | Trace |
|---|---|---|
| Languages | Python (scanner, API); TypeScript, strict mode (web) | A-2 |
| Scanner Python range | CPython **3.11–3.14** (`requires-python = ">=3.11"`). 3.15 is added if it is final at implementation; see Research R-1. | FR-009 |
| Pinned dev/API CPython | **3.14.x**, full patch in root `.python-version`. It is inside the scanner range. | FR-006 |
| Python tooling | `uv` pinned through `[tool.uv] required-version` in each `pyproject.toml`, `ruff` (format and lint), `mypy --strict`, `pytest`, `jsonschema` (scanner dev only, for the schema test) | A-2, FR-025 |
| Scanner build backend | `uv_build` (reuses the uv toolchain, no extra tool) | A-2 |
| Scanner runtime dependencies | **None**. Uses `argparse`, `tomllib`, `hashlib`, `json`, `tempfile` and `os` from the standard library. | FR-009, FR-014, FR-063 |
| API | FastAPI plus `uvicorn` (plain, no `[standard]` extra). Settings read with the standard library (`os.environ`), so no pydantic-settings dependency. | A-2, FR-091 |
| API tests | `pytest` + `httpx` (FastAPI `TestClient`) | A-2 |
| Web | React 19, Vite 8 (Rolldown), static SPA, CSR | A-2, FR-071 |
| Web tooling | Vitest + Testing Library + jsdom + `axe-core`; ESLint (flat config, `typescript-eslint`, `react-hooks`, `jsx-a11y`); Prettier; **stylelint** + `stylelint-declaration-strict-value` (token enforcement); `browserslist-to-esbuild` (build target) | A-2, FR-070, FR-078, FR-079 |
| Node / package manager | Node **24.x LTS** (`web/.node-version`, `engines.node`); **pnpm 11.x** (`packageManager` field) | FR-006 |
| Root task runner | GNU/BSD `make` | A-2 |
| Storage | None (stateless API, no database) | FR-055 |
| Platforms | macOS and Linux for local work; GitHub-hosted `ubuntu-24.04` and `macos-15` runners in CI. Windows is unsupported. | FR-090, A-3 |
| Performance goals | Health endpoint p95 ≤ 50 ms and p99 ≤ 100 ms at 20 concurrent clients for 60 s (SC-006). Home route initial JS ≤ 100 KB gzip, CSS ≤ 20 KB gzip (FR-074). LCP ≤ 2.5 s, CLS ≤ 0.1, TBT ≤ 200 ms as a proxy for INP ≤ 200 ms (SC-008). Scanner peak RSS ≤ 200 MB (FR-094). CI ≤ 10 min wall-clock and ≤ 25 runner-minutes (FR-095). | SCs |
| Scale | Single local API process. One fixture. No production traffic. | FR-094 |

**NEEDS CLARIFICATION:** none blocking. Eight non-blocking items are resolved with defaults in §5 (R-1…R-8). Items that need an operator decision later are listed under Open Questions.

---

## 3. Constitution Check

I found no project constitution file in the workspace (the repo root and `.am/` hold only the runtime pointer). The gates below use the binding principles of the frozen spec and the prior ADRs.

| Principle | Gate | Evidence |
|---|---|---|
| No execution of analysed code (CD-2 §2.4; CD-3 parse-only) | **PASS** | The scanner only checks filesystem existence (FR-013a). It never opens `.py` files in `fixtures/` (FR-014, FR-031). A test asserts this by monkeypatching `open`/`importlib` (§8 V-S7). |
| Trust boundary and untrusted rendering (CD-2 §2.4) | **PASS** | The web app reads only `status === "ok"` from the health body and never renders response text (FR-073a). The CSP-compatible build has no inline script (FR-075), enforced by `check-build.mjs`. |
| No credentials (FR-091, SC-011) | **PASS** | The workflow has no `secrets.` references and no `pull_request_target`, and declares `permissions: contents: read`. All settings have defaults. |
| Determinism (FR-024) | **PASS** | Canonical JSON. No time, environment, cwd, hostname or absolute paths in the output. A golden test across environment variants and two CPython versions on two operating systems. |
| Area isolation (FR-002, FR-003) | **PASS** | Separate `uv` projects and lockfiles (not a uv workspace). The web area has no Python. CI jobs install one area each. |
| Right-size and no product logic (A-7, FR-043, FR-055, FR-058, FR-059) | **PASS** | No database, router library, global store, workers, rate limiting, IaC or containers. |
| Stable names (A-1, A-13) | **PASS** | `dogwatch`, `dogwatch.toml`, `dogwatch:` prefix, `dogwatch-api`, `DOGWATCH_API_`, `schema_version`, `dogwatch:config-not-found` are used verbatim. |
| Reuse of prior decisions | **PASS** | CD-3 §2.2 package semantics, CD-3 §2.12 `config-invalid`, CD-2 §2.3 field names and §2.4 error codes, CD-4 §2.6 one-directory-per-fixture convention. |
| New dependencies need justification | **EXCEPTION (justified)** | Three web dev dependencies are not named in A-2: `stylelint` + `stylelint-declaration-strict-value` (FR-078 needs a lint error for hard-coded values, and ESLint cannot lint CSS values); `browserslist-to-esbuild` (FR-070 requires the build to target exactly the browserslist set, but Vite's `build.target` does not read browserslist); `eslint-plugin-jsx-a11y` (supports FR-079, cheap). All are dev-only and add 0 bytes to the bundle. |

No ERROR gates.

---

## 4. Project Structure

```
/
├── .gitignore                 # .venv/ node_modules/ dist/ build/ __pycache__/ *.egg-info/ .mypy_cache/ .ruff_cache/ .pytest_cache/ coverage/ .env .env.* !.env.example .playwright-mcp/   (NOT .am/)  FR-007
├── .gitattributes             # "* text=auto eol=lf" and "fixtures/** text eol=lf"   FR-008
├── .python-version            # 3.14.Z (full patch)   FR-006
├── Makefile                   # contract C7   FR-005, FR-089
├── README.md                  # quickstart ≤ 80 lines (§7 C11)   FR-004, SC-010
├── .github/workflows/ci.yml   # contract C10   FR-085–FR-089
├── scanner/
│   ├── pyproject.toml         # name=dogwatch, version=0.1.0, requires-python>=3.11, [project.scripts] dogwatch="dogwatch.cli:main", [tool.uv] required-version, ruff target py311, mypy python_version=3.11 strict
│   ├── uv.lock
│   ├── schemas/report-0.1.schema.json          # C3   FR-025
│   ├── src/dogwatch/
│   │   ├── __init__.py        # __version__ = importlib.metadata.version("dogwatch")
│   │   ├── __main__.py        # python -m dogwatch → cli.main()
│   │   ├── cli.py             # argparse, dispatch, exit-code mapping
│   │   ├── diagnostics.py     # DiagnosticId constants, DogwatchError, stderr formatting
│   │   ├── config.py          # read bytes → tomllib → shape check → structure check → PolicyConfig
│   │   ├── report.py          # build_report(), serialize_canonical()
│   │   ├── output.py          # atomic file write / stdout write
│   │   └── py.typed
│   └── tests/
│       ├── conftest.py        # repo_root fixture, make_config(tmp_path, toml, dirs)
│       ├── test_cli.py  test_config_shape.py  test_config_structure.py
│       ├── test_report.py  test_output.py  test_resources.py
│       └── golden/            # owned by WP-F (seam, see §8)
│           ├── __init__.py
│           ├── harness.py     # discover fixtures, run CLI subprocess, diff
│           ├── test_fixture_goldens.py   # pytest marker "golden"
│           └── regenerate.py  # explicit golden rewrite (FR-034)
├── api/
│   ├── pyproject.toml         # name=dogwatch-api, version=0.1.0, requires-python ==3.14.*, deps fastapi, uvicorn; dev: pytest, httpx, mypy, ruff; scripts dogwatch-api="dogwatch_api.__main__:main"
│   ├── uv.lock
│   ├── .env.example           # DOGWATCH_API_HOST, DOGWATCH_API_PORT   FR-091
│   ├── scripts/bench_health.py # SC-006 acceptance load generator (httpx async)
│   ├── src/dogwatch_api/
│   │   ├── __init__.py  __main__.py  settings.py  app.py
│   │   ├── health.py  problems.py  middleware.py  log.py  py.typed
│   └── tests/ test_health.py test_problems.py test_request_id.py test_logging.py test_openapi.py test_settings.py test_main.py
├── web/
│   ├── package.json           # name dogwatch-web, private, type module, packageManager pnpm@11.x.y, engines.node 24.x, browserslist (C9), scripts (C7)
│   ├── pnpm-lock.yaml  .node-version  .env.example (VITE_DOGWATCH_API_BASE_URL)
│   ├── index.html             # lang="en", <title>Dogwatch</title>, viewport meta, single module script src
│   ├── vite.config.ts         # build.manifest, target from browserslist, dev/preview proxy, vitest config
│   ├── tsconfig.json  tsconfig.node.json  eslint.config.js  .prettierrc.json  .prettierignore  stylelint.config.js
│   ├── public/favicon.svg
│   ├── scripts/check-build.mjs   # budget (FR-074) + no-inline-script (FR-075)
│   └── src/
│       ├── main.tsx  App.tsx  router.ts  strings.ts
│       ├── api/health.ts
│       ├── components/ErrorBoundary.tsx  components/ApiStatus.tsx
│       ├── views/HomeView.tsx  views/NotFoundView.tsx
│       ├── styles/tokens.css  styles/global.css
│       ├── test/setup.ts  test/axe.ts
│       └── **/*.test.tsx
└── fixtures/
    ├── README.md              # layout convention   FR-033
    └── minimal/
        ├── dogwatch.toml
        ├── src/acme_shop/__init__.py  orders.py  payments.py
        └── expected-report.json
```

---

## 5. Research Notes

**R-1: Newest final CPython minor (FR-009).** As of the plan date, 2026-10-03, 3.15.0rc3 shipped on 2026-10-02 and the 3.15.0 final release moved to **2026-10-09** (per web search: [python.org blog, 3.15.0rc3](https://blog.python.org/2026/10/python-3150-rc3/), [linuxcompatible.org](https://www.linuxcompatible.org/story/python-3150rc3-release-candidate-announced-stable-release-set-for-october-9-2026), [PEP 790](https://peps.python.org/pep-0790/)).
- *Decision:* the range is **3.11–3.14**.
- *Rule for the implementer:* if 3.15.0 final has been published when the scanner work package starts, add `"3.15"` to the scanner matrix, use 3.15 as the "newest" fixtures entry, and add the trove classifier. The dev/API pin stays 3.14 either way, which is still inside the range.
- *Risk:* dev tools such as mypy may not publish 3.15 wheels on day one. If `uv lock` or the tests fail on 3.15, use the 3.14 ceiling and record that in the PR.
- *Rejected:* adding 3.15 to the matrix as a pre-release, because FR-009 requires a final release.

**R-2: Diagnostic form for usage and output-write errors.** FR-016 allows exactly one new ID (`config-not-found`), but FR-052 also maps usage errors, unwritable output, and output equal to config, to exit 2.
- *Decision:* usage errors use argparse's standard output (`usage: …` and `dogwatch: error: …`, exit 2). Output-write failures and output-equals-config print `dogwatch: error: <message>`. This uses the `dogwatch:` prefix but **no diagnostic ID**, because these are runtime errors, not policy diagnostics.
- *Rejected:* inventing `dogwatch:output-unwritable`, because it would add an unsanctioned catalogue ID. This is raised as an open question.

**R-3: "Dotted name split across roots" when `name` is a single identifier (CD-3 §2.2).**
- *Decision:* `name` must satisfy `str.isidentifier()` and contain no dots; a dotted name gets `config-invalid`, "must be a single top-level identifier".
- Two entries with the same `name` and the same resolved root get **"duplicate package"**.
- Two entries with the same `name` and different roots get **"package `<name>` split across roots `<r1>`, `<r2>`"**.
- That gives four distinct seeded cases for SC-013: missing directory, duplicate, nested, split.

**R-4: Config path exists but is not a readable regular file** (for example a directory, or permission denied).
- *Decision:* `config-not-found` only when the path does not exist (`os.path.lexists` is false). Otherwise `config-invalid` with "is not a readable file". Invalid UTF-8 (`UnicodeDecodeError`) also gives `config-invalid`.
- Rationale: FR-016 defines not-found strictly as "does not exist".

**R-5: TOML error line number across 3.11–3.14.** Python 3.14 added `TOMLDecodeError.lineno`/`colno`; 3.11–3.13 only include `(at line N, column M)` in the message (per web search: [docs.python.org tomllib 3.14](https://docs.python.org/tr/3.14/library/tomllib.html)).
- *Decision:* use `getattr(exc, "lineno", None)` and fall back to the regex `r"at line (\d+), column (\d+)"`.
- Output format: `dogwatch:config-invalid: <config-arg>:<line>: invalid TOML: <msg>`.
- Tests assert the prefix, the path and the line only, not the message text, which varies by version.

**R-6: Vite build target from browserslist (FR-070).** Vite 8 uses Rolldown/Oxc, and its `build.target` takes esbuild-style targets with a default of `baseline-widely-available`, not browserslist (per web search: [vite.dev Vite 8 migration](https://vite.dev/guide/migration), [announcing Vite 8](https://vite.dev/blog/announcing-vite8)).
- *Decision:* keep the single source in the `browserslist` field of `package.json`, and set `build.target = browserslistToEsbuild()` and `build.cssTarget` to the same value.
- *Rejected:* hand-maintaining a target list, which would duplicate the source of truth.

**R-7: axe in jsdom cannot evaluate colour contrast.**
- *Decision:* the Vitest axe run uses tags `wcag2a, wcag2aa, wcag21a, wcag21aa, wcag22aa` and asserts `violations.length === 0` (SC-009). The `color-contrast` rule returns *incomplete* in jsdom, so contrast (SC 1.4.3) is checked by Lighthouse accessibility at acceptance and by choosing token colours with a ≥ 4.5:1 ratio, documented in comments in `tokens.css`.
- *Rejected:* adding Playwright to CI, which costs time in the CI budget and is not required by any FR.

**R-8: Problem-detail `type` URI.**
- *Decision:* use a URN, `urn:dogwatch:problem:<code>`. RFC 9457 allows URIs that cannot be dereferenced, and this avoids inventing a domain the project doesn't own.
- *Rejected:* `about:blank`, which would lose the per-code type, and a made-up `https://` domain.

**Toolchain pins** (per web search; exact patches are fixed by the implementer at the time of work, and the lockfiles record the rest):
- uv 0.12.x, with 0.12.10 published on 2026-09-04 ([astral-sh/uv releases](https://github.com/astral-sh/uv/releases), [newreleases.io uv 0.12.2](https://newreleases.io/project/pypi/uv/release/0.12.2))
- Node 24 Active LTS until Node 26 enters LTS in late October 2026 ([dev.to Node 26 vs 24](https://dev.to/aarav_chandel_bf81a1120b1/nodejs-26-vs-nodejs-24-lts-should-you-upgrade-now-3l83))
- pnpm 11.x, which requires Node ≥ 22 and defaults to `minimumReleaseAge` = 1 day ([InfoQ pnpm 11](https://infoq.com/news/2026/04/pnpm-11-rc-release/), [releases.sh pnpm 11.14](https://releases.sh/release/rel_wc5MI044rLDNKoulEML7q-pnpm-11-11-11-14))

**Smaller decisions (all traced to an FR):**
- **No router library.** `router.ts` maps `location.pathname` to a view (FR-072, right-size), which keeps React (~60 KB gzip) well under the 100 KB budget. The Not Found "Home" link is `<a href="/">`, a normal document navigation.
- **Budget unit.** KB means **1000 bytes**. This is the stricter reading and satisfies both interpretations of FR-074.
- **Fixture test placement.** It lives under `scanner/tests/golden/` because the fixtures area has no manifest (Key Entities). It is selected with the pytest marker `golden`, so `test-scanner` and `test-fixtures` stay separate statuses (AS-3.1).
- **API port in use.** `__main__` binds the socket itself and passes it to `uvicorn.Server.run(sockets=[sock])`. On `EADDRINUSE` it prints `dogwatch-api: error: 127.0.0.1:8000 is already in use; set DOGWATCH_API_PORT to choose another port` and exits 1. There is no race and no fallback port (edge case).
- **API exception handling.** It is done in a **pure ASGI middleware**, not in Starlette's `ServerErrorMiddleware`. Starlette's handler sits outside user middleware, so the 500 response would otherwise lose `X-Request-ID` and the single log line (FR-061, AS-4.4).

---

## 6. Data Model

No persistence (FR-055). Entities are in-memory or file contracts. Names follow frozen spec §4.

**Policy file** (`dogwatch.toml`, CD-5 subset; validated by `config.py`; validation stops at the first failing stage):

| Stage | Check | Failure |
|---|---|---|
| V0 exists | `os.path.lexists(config)` | `config-not-found` "`<path>` does not exist" |
| V1 read | regular file, readable, UTF-8 | `config-invalid` "`<path>` is not a readable file" or "is not valid UTF-8" |
| V2 parse | `tomllib.loads` | `config-invalid` "`<path>:<line>`: invalid TOML: …" |
| V3 shape | top-level keys == {`python`}; `python` keys == {`packages`}; `packages` is a non-empty array of tables; each table's keys == {`name`,`root`}; both strings; `name.isidentifier()` | `config-invalid` "`<dotted.key>` is not supported in this version" for unknown or extra keys (including `python.rules`, `openapi`, waivers); "requires at least one [[python.packages]] entry"; type errors |
| V4 structure | For each entry, in declaration order: `P = config_dir / root / name` must exist as a directory. Then pairwise: duplicate (same name, same `realpath(root)`), split (same name, different root), nested (`realpath(P_j)` is inside `realpath(P_i)`, i ≠ j). | `config-invalid`, one stderr line per failure, naming the package and `root/name` as declared |

Output type: `PolicyConfig(path_arg: str, raw: bytes, packages: tuple[PackageDecl, ...])`, where `PackageDecl(name: str, root: str)`. Only filesystem metadata calls are made (`os.path.isdir`, `realpath`). No file under `P` is opened (FR-013a).

**Report** (bootstrap envelope, `schema_version` `"0.1"`). Contract C3.

| Field | Type | Source |
|---|---|---|
| `schema_version` | const `"0.1"` | FR-021 |
| `scanner.name` | const `"dogwatch"` | FR-012 |
| `scanner.version` | SemVer, no leading `v`; from `importlib.metadata.version("dogwatch")`, `0.1.0` | FR-012 |
| `policy.path` | basename of the `--config` argument as given (not resolved) → `"dogwatch.toml"` | FR-022 |
| `policy.digest.sha256` | lowercase hex SHA-256 of the raw bytes | FR-023 |
| `findings` | `[]` (schema: `"items": false`) | FR-020, FR-026 |

Serialization: `json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False) + "\n"`, encoded as UTF-8 with no BOM and written as bytes, so there is no newline translation. Key order is `findings`, `policy`, `scanner`, `schema_version`.

**Diagnostic**: `id ∈ {config-invalid, config-not-found}`, `message`, `exit_code = 2`. Implemented as `DogwatchError(diagnostics: list[Diagnostic])`.

**Scanner run outcome**: `start → validate_config → (error → exit 2, no file) | build_report → write → (write error → exit 2, temp removed) | success → exit 0`. `gate-failed` (exit 1) is unreachable.

**Health status**: `{status: "ok", service: "dogwatch-api", version: str}`, a pydantic `HealthStatus` model.

**Problem detail**: `{type: "urn:dogwatch:problem:<code>", title, status: int, detail: str, code}`.

**API status indicator** (web): `checking → available` (2xx, JSON parses, `status === "ok"`) `| unavailable` (anything else, including the 5 s timeout). Terminal. A late resolve after the terminal state is ignored.

**CI check**: `queued → running → passed | failed | cancelled` (cancelled only through `concurrency.cancel-in-progress`).

**Settings (API)**: `host: str = "127.0.0.1"` from `DOGWATCH_API_HOST`; `port: int = 8000` from `DOGWATCH_API_PORT` (1–65535). An invalid value gives exit 1 with a message naming the variable.

---

## 7. Interface Contracts

### C1 — Scanner CLI
```
dogwatch --version                 → stdout "dogwatch 0.1.0\n", exit 0
dogwatch check [--config PATH] [--output PATH|-]
   defaults: --config ./dogwatch.toml   --output ./dogwatch-report.json
```
| Outcome | Exit | stdout | stderr | Filesystem |
|---|---|---|---|---|
| Valid config | 0 | report bytes if `--output -`, else empty | empty | target replaced atomically (temp file in the target's directory, `fsync`, `os.replace`) |
| Missing config | 2 | empty | `dogwatch:config-not-found: <path> does not exist` | nothing created |
| Invalid TOML / shape / structure | 2 | empty | one or more `dogwatch:config-invalid: <message>` lines | nothing created |
| Output unwritable, or output resolves to the same file as config | 2 | empty | `dogwatch: error: <message>` (R-2) | no file at target, temp removed |
| Usage error, or no subcommand | 2 | empty | argparse usage | nothing created |

Exit 1 is reserved. The scanner makes no network calls and emits no telemetry (FR-063). `python -m dogwatch` behaves the same.

### C2 — Policy file (0.1 subset)
```toml
[python]

[[python.packages]]
name = "acme_shop"   # single identifier
root = "src"         # relative to this file's directory
```

### C3 — Report JSON Schema (`scanner/schemas/report-0.1.schema.json`, Draft 2020-12)
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:dogwatch:schema:report:0.1",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version", "scanner", "policy", "findings"],
  "properties": {
    "schema_version": {"const": "0.1"},
    "scanner": {"type": "object", "additionalProperties": false, "required": ["name", "version"],
      "properties": {"name": {"const": "dogwatch"},
        "version": {"type": "string", "pattern": "^(0|[1-9]\\d*)\\.(0|[1-9]\\d*)\\.(0|[1-9]\\d*)(?:-[0-9A-Za-z.-]+)?(?:\\+[0-9A-Za-z.-]+)?$"}}},
    "policy": {"type": "object", "additionalProperties": false, "required": ["path", "digest"],
      "properties": {"path": {"type": "string", "minLength": 1, "pattern": "^[^/\\\\\\u0000-\\u001f]+$"},
        "digest": {"type": "object", "additionalProperties": false, "required": ["sha256"],
          "properties": {"sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"}}}}},
    "findings": {"type": "array", "items": false}
  }
}
```
Evolution is expand-contract (FR-056). A new file is added per `schema_version`, and `0.1` is never edited after merge.

### C4 — HTTP API (`dogwatch-api`, default `[redacted-secret]`)
| Method | Path | Request | 200 response | Errors |
|---|---|---|---|---|
| GET | `/api/v1/health` | none, unauthenticated | `application/json` `{"status":"ok","service":"dogwatch-api","version":"0.1.0"}` | 405 for other methods |
| GET | `/api/v1/openapi.json` | none, unauthenticated | OpenAPI **3.1** document (`openapi_url` set; `docs_url=None`, `redoc_url=None` because the docs UIs load CDN scripts) | 405 |
| any | any other path | — | — | 404 `not-found` |

Error taxonomy (FR-050/051). All errors are `Content-Type: application/problem+json`.

| Code | HTTP | Trigger in CD-5 | Body detail |
|---|---|---|---|
| `not-found` | 404 | unknown route | "No route matches `<path>`" (path only, no query string) |
| `method-not-allowed` | 405 | known path, wrong method; `Allow` header set | lists the allowed methods |
| `validation-failed` | 422 | `RequestValidationError`. Tested through a test-only route added to `create_app()` in tests; no product endpoint is added. | "Request validation failed (N errors)"; no input is echoed |
| `internal-error` | 500 | any unhandled exception | "Internal server error." No stack trace or exception text. |
| *reserved* `schema-invalid` 400, `payload-too-large` 413, `in-flight` 409, `idempotency-conflict` 422, `rate-limited` 429 | — | not emitted | constants only, in `problems.py` |

Headers on **every** response, including 404, 405 and 500: `X-Request-ID`. The incoming value is echoed if it matches `^[\x20-\x7E]{1,128}$`; otherwise the service generates `uuid4()`.

### C5 — API request log line (stdout, one JSON object per request, `\n`-terminated)
```json
{"ts":"2026-10-03T12:00:00.123Z","level":"info","event":"request","request_id":"…","method":"GET","route":"/api/v1/health","status":200,"duration_ms":1.42}
```
- `route` is the matched route template, or `null` when there is no match.
- On 5xx: `level: "error"`, plus `error_type` and `error_traceback` in the same line, so there is still one line per request.
- Never logged: bodies, query strings, header values other than the validated request ID.
- Uvicorn's access log is disabled (`access_log=False`).

### C6 — Configuration variables
| Variable | Area | Default | Notes |
|---|---|---|---|
| `DOGWATCH_API_HOST` | api | `127.0.0.1` | FR-044 |
| `DOGWATCH_API_PORT` | api | `8000` | integer 1–65535 |
| `VITE_DOGWATCH_API_BASE_URL` | web, build-time | `/api/v1` | FR-073a; documented in `web/.env.example` |
| `UV_PYTHON` | scanner, CI | unset → `.python-version` | selects the matrix interpreter (uv's built-in variable) |

### C7 — Root Makefile targets (the binding contract between WP-0, area work packages and CI)
| Target | Command (run inside the area directory) |
|---|---|
| `install` | `install-scanner install-api install-web` |
| `install-scanner` / `install-api` | `uv sync --locked` |
| `install-web` | `pnpm install --frozen-lockfile` |
| `test` | `test-scanner test-fixtures test-api test-web` |
| `test-scanner` | `uv run --locked pytest -m "not golden"` |
| `test-fixtures` | `uv run --locked pytest -m golden` (in `scanner/`) |
| `test-api` | `uv run --locked pytest` |
| `test-web` | `pnpm run test` (→ `vitest run`), after `install-web` |
| `lint` | `lint-scanner lint-api lint-web` |
| `lint-scanner` / `lint-api` | `uv run --locked ruff format --check . && uv run --locked ruff check . && uv run --locked mypy` |
| `lint-web` | `pnpm run lint` (→ `prettier --check . && eslint . && stylelint "src/**/*.css" && tsc --noEmit -p tsconfig.json`) |
| `format` | `format-scanner format-api format-web` (`ruff format .`, `ruff check --fix .`, `prettier --write .`) |
| `build-web` | `pnpm run build` (→ `tsc --noEmit && vite build && node scripts/check-build.mjs`) |
| `run-scanner` | `uv run --locked dogwatch check --config ../fixtures/minimal/dogwatch.toml --output -` |
| `run-api` | `uv run --locked dogwatch-api` |
| `run-web` | `pnpm run dev` (127.0.0.1:5173, `strictPort`, proxies `/api` → `[redacted-secret]`) |
| `regen-fixtures` | `uv run --locked python -m tests.golden.regenerate` (in `scanner/`) |
| `bench-api` | `uv run --locked python scripts/bench_health.py --concurrency 20 --duration 60` (acceptance only) |

`uv run --locked` also creates the environment, so `make test-scanner` works straight after cloning. `UV_PYTHON` passes through from the environment.

### C8 — Web ↔ API consumption
- `fetchHealth(baseUrl, signal): Promise<"available"|"unavailable">`
- It sends `GET ${baseUrl}/health` with `AbortSignal.any([signal, AbortSignal.timeout(5000)])` and is called exactly once per mount of `ApiStatus`. The effect cleanup aborts.
- Result is `available` only if `res.ok`, `await res.json()` succeeds, and `body.status === "ok"`. Every other outcome, including throws, is `unavailable`.
- No response text is rendered.
- Status text comes from `strings.ts`: "Checking API…", "API available", "API unavailable". It sits in `<p role="status" aria-live="polite">`.

### C9 — Web build contract
- `browserslist`: `["last 2 Chrome versions","last 2 Edge versions","last 2 Firefox versions","last 2 Safari versions","last 2 iOS versions"]` (FR-070).
- `vite build` with `build.manifest: true` and content-hashed `assets/[name]-[hash].js`.
- `check-build.mjs` fails (exit 1) when either:
  - gzip(level 9) of the `index.html` entry chunk plus its transitive static `imports` from `.vite/manifest.json` is > 100 000 bytes, or total gzip of `dist/**/*.css` is > 20 000 bytes; or
  - `dist/index.html` contains a `<script>` without `src`, or any `on[a-z]+=` attribute.
- `vite preview` serves `index.html` for unknown paths (SPA fallback) and uses the same proxy.

### C10 — CI workflow (`.github/workflows/ci.yml`)
- **Triggers:** `pull_request` (branches: `main`) and `push` (branches: `main`). Never `pull_request_target`.
- **Settings:** top-level `permissions: contents: read`. `concurrency: {group: ci-${{ github.event.pull_request.number || github.ref }}, cancel-in-progress: true}`.
- **Actions:** `actions/checkout`, `astral-sh/setup-uv` (`version-file: scanner/pyproject.toml`, `enable-cache: true`), `actions/setup-node` (`node-version-file: web/.node-version`, `cache: pnpm`), `pnpm/action-setup` (`package_json_file: web/package.json`). Each is pinned to a full 40-character SHA with a trailing `# vX.Y.Z` comment.

| Job (status name) | Runner | Matrix | Steps |
|---|---|---|---|
| `scanner (3.11)`, `(3.12)`, `(3.13)`, `(3.14)` | ubuntu-24.04 | `python: [3.11, 3.12, 3.13, 3.14]`, `UV_PYTHON` env | `make lint-scanner` (3.11 entry only, so mypy runs on the floor) → `make test-scanner` |
| `api` | ubuntu-24.04 | — | `make lint-api test-api` |
| `web` | ubuntu-24.04 | — | `make install-web lint-web test-web build-web` |
| `fixtures (ubuntu-24.04, 3.11)` …`(macos-15, 3.14)` | ubuntu-24.04, macos-15 | os × `[3.11, 3.14]` | `make test-fixtures` |

`timeout-minutes: 10` on every job. Estimated cost: about 15 runner-minutes and about 4 minutes of wall-clock time (FR-095).

### C11 — README.md line budget (≤ 80 lines, SC-010)
| Section | Lines |
|---|---|
| Title and one-paragraph intro | ~4 |
| Prerequisites (make, uv 0.12.x, Node 24.x, pnpm 11.x; scanner CPython 3.11–3.14; macOS/Linux only, Windows unsupported) | ~8 |
| Install / test all / lint all / format all | ~8 |
| Per-area table: run / test / lint / format for all four areas, with fixtures marked "static data; `make regen-fixtures`" | ~12 |
| Defaults (API 127.0.0.1:8000, web 5173, env vars) | ~5 |
| "Direction for later tickets (provisional)" | ~25 |
| Branch protection and recovery runbook | ~6 |

The "Direction" section covers, one or two lines each: auth (FR-046), expand-contract DB migrations (FR-057), OTel → Collector → Prometheus/Loki/Tempo (FR-062), session cookies and CSRF (FR-082), Terraform, OCI images and static assets with the hosting target undecided (FR-090), GitHub OIDC plus the cloud-provider secret manager (FR-092), blue-green plus feature-flag kill-switch (FR-093). Each choice is labelled provisional.

### C12 — Fixture convention (`fixtures/README.md`, FR-033)
`fixtures/<kebab-name>/` holds `dogwatch.toml`, its source tree, and `expected-report.json`. The golden harness discovers every `fixtures/*/dogwatch.toml`. Fixtures are static data and are never installed, imported or executed (FR-031).

---

## 8. Parallelization Strategy

`team_work=True`, `max_concurrency=3`.

### Ownership and write scopes
| WP | Owner scope (exclusive write) | Must not touch |
|---|---|---|
| **WP-0 Foundation** | `/.gitignore`, `/.gitattributes`, `/.python-version`, `/Makefile` (complete per C7) | `.am/**` (ever) |
| **WP-S Scanner** | `scanner/**` except `scanner/tests/golden/**` | Makefile, fixtures |
| **WP-A API** | `api/**` | everything else |
| **WP-W Web** | `web/**` | everything else |
| **WP-F Fixtures + golden** | `fixtures/**`, `scanner/tests/golden/**`, and **one seam line** in `scanner/pyproject.toml` that registers the `golden` pytest marker (coordinate with WP-S: WP-S pre-registers it, so WP-F does not edit) | scanner `src/` |
| **WP-I Integration** | `.github/workflows/ci.yml`, `README.md`; the only WP allowed to amend `Makefile` after WP-0 | area code (escalate defects to the area WP) |

### Dependency graph
```
WP-0 ──┬──► WP-S ──► WP-F ──┐
       ├──► WP-A ───────────┼──► WP-I
       └──► WP-W ───────────┘
```
- **Wave 1:** WP-0.
- **Wave 2:** WP-S, WP-A, WP-W in parallel (3 slots).
- **Wave 3:** WP-F, which needs C1/C3 implemented to generate the golden file. Fixture *source data* has no dependency and may be written early if a slot is free.
- **Wave 4:** WP-I.

### Integration seams
1. **C7 Makefile ↔ area scripts.** WP-W must expose `lint`, `test`, `build`, `dev`, `format` scripts in `package.json` with these exact names. WP-S and WP-A must make `ruff`, `mypy` and `pytest` runnable with no arguments (config lives in `pyproject.toml`).
2. **C1/C3 ↔ golden harness.** WP-F invokes `[sys.executable, "-m", "dogwatch", "check", "--config", <abs>, "--output", <tmp>]`, plus one test that checks the `dogwatch` console script exists.
3. **Pytest marker `golden`.** Declared in `scanner/pyproject.toml` `[tool.pytest.ini_options] markers` by WP-S, with `--strict-markers`.
4. **C8 health contract ↔ C4.** WP-W stubs `fetch` in tests (A-8). There is no runtime coupling in tests.
5. **Version strings.** `scanner` 0.1.0 is embedded in the golden file. Any version bump requires `make regen-fixtures` in the same PR.

### Key implementation notes per WP (for task generation)
- **WP-S:** atomic write in `output.py`. Check output equals config with `Path.resolve()` equality, and `os.path.samefile` when both exist, before parsing finishes writing anything. Write stdout through `sys.stdout.buffer`. Set `mypy python_version = "3.11"` and ruff `target-version = "py311"`.
- **WP-A:** `create_app()` factory with exception handlers for `StarletteHTTPException` (404/405) and `RequestValidationError` (422). A pure ASGI `RequestContextMiddleware` handles request IDs, timing, the log line, the header in `http.response.start`, and the catch-all 500 problem response when the response hasn't started.
- **WP-W:** `<html lang="en">`; `App` contains `ErrorBoundary` › `header` (brand) and `main` (view). There is one `h1` per view, focus-visible outlines from tokens, breakpoints `@media (min-width: 640px)` and `(min-width: 1024px)` (literals; the stylelint rule exempts media params), and min width 320 px with no horizontal scroll. Only a light theme, with tokens on `:root` so a dark theme can override them later. No cookies or storage, and no third-party origins.
- **WP-F:** the golden test parametrizes **5 environment variants**, each with a distinct temporary cwd and HOME:
  - `TZ` ∈ {UTC, America/Los_Angeles, Asia/Kolkata, Pacific/Chatham, Etc/GMT+12}
  - `LC_ALL`/`LANG` ∈ {C, C.UTF-8, en_US.UTF-8, tr_TR.UTF-8, POSIX}
  - a random `PYTHONHASHSEED`

  Five variants × two CPython versions gives 10 runs per OS, which is SC-002. On mismatch it prints a `difflib.unified_diff`. `regenerate.py` is the only code that writes golden files.
- **WP-I:** resolve action SHAs with `gh api repos/<owner>/<action>/git/ref/tags/<tag>`. Verify no `secrets.` strings appear (`grep`).

### Integration checkpoints
| CP | After | Gate |
|---|---|---|
| CP-1 | WP-0 | `git check-attr eol fixtures/x` → `lf`; `make -n test` prints the C7 commands; `.am/` is neither ignored nor modified |
| CP-2 | each of WP-S/A/W | `make lint-<area> test-<area>` green in a clean clone with only that area's toolchain installed (SC-003) |
| CP-3 | WP-F | `UV_PYTHON=3.11 make test-fixtures` and `UV_PYTHON=3.14 make test-fixtures` green locally on macOS |
| CP-4 | WP-I | PR CI shows all 10 statuses green; total runner-minutes ≤ 25 |
| CP-5 | acceptance | SC-001/002/004/005/006/008/011/012 manual or once-off measurements |

### Verification matrix
| ID | Requirement(s) | Test / check | Location | CI job |
|---|---|---|---|---|
| V-S1 | FR-010–012, FR-015 | CLI parsing, `--version`, defaults, exit codes | `scanner/tests/test_cli.py` | scanner |
| V-S2 | FR-013, FR-016, AS-2.4/2.5, edge cases | missing, unreadable, malformed (line number), unsupported keys, empty, no packages, dotted name | `test_config_shape.py` | scanner |
| V-S3 | FR-013a, SC-013, AS-2.6/2.7 | missing dir, file-not-dir, duplicate, split, nested → exit 2 and no file; zero `.py` files → exit 0; no `__init__.py` OK | `test_config_structure.py` | scanner |
| V-S4 | FR-020–026 | canonical bytes (sorted keys, LF, one trailing newline, no BOM, non-ASCII literal); schema validation; no provenance keys | `test_report.py` | scanner |
| V-S5 | FR-015, edge cases | unwritable dir, permission denied, output == config, `--output -`; target untouched and no temp left | `test_output.py` | scanner |
| V-S6 | FR-094 | child `ru_maxrss` ≤ 200 MB (bytes on macOS, KiB on Linux) | `test_resources.py` | scanner |
| V-S7 | FR-014, FR-031 | monkeypatch `builtins.open`/`io.open_code`/`importlib.import_module` to fail on paths under the package dir; run passes | `test_config_structure.py` | scanner |
| V-S8 | FR-009, SC-012, AS-3.6 | matrix 3.11–3.14; mypy on 3.11; `pip install` on 3.10 refused (acceptance) | ci.yml | scanner |
| V-F1 | FR-032, SC-002, AS-2.2/2.3, AS-3.3 | golden byte equality × 5 env variants | `scanner/tests/golden/` | fixtures (×4) |
| V-F2 | FR-034 | test never writes: assert golden mtime/bytes unchanged after the run | same | fixtures |
| V-A1 | FR-040, FR-042, FR-045 | health body; OpenAPI `openapi` starts with `3.1`; no auth | `api/tests/test_health.py`, `test_openapi.py` | api |
| V-A2 | FR-050/051 | 404, 405 (with `Allow`), 422, 500 problem bodies; no traceback in 500 body | `test_problems.py` | api |
| V-A3 | FR-060/061, AS-4.4 | echo valid ID; replace oversized or control-char IDs; exactly one JSON line per request, including 500; no query string in the log | `test_request_id.py`, `test_logging.py` | api |
| V-A4 | FR-044, FR-091, port edge case | defaults 127.0.0.1:8000; invalid port variable; port-in-use message | `test_settings.py`, `test_main.py` | api |
| V-A5 | SC-006 | `make bench-api`: p95 ≤ 50 ms, p99 ≤ 100 ms, 0 errors | acceptance | — |
| V-W1 | FR-073, AS-5.1/5.2, edge cases | fake timers and fetch stubs for checking, available, unavailable, timeout, late success ignored, non-JSON, `status≠ok`, one call | `ApiStatus.test.tsx` | web |
| V-W2 | FR-072, AS-5.3 | `/` → Home; `/nope` → "Page not found" plus link to `/` | `App.test.tsx` | web |
| V-W3 | FR-076 | throwing child → "Something went wrong" plus reload button | `ErrorBoundary.test.tsx` | web |
| V-W4 | FR-079, SC-009 | axe on Home and Not Found: 0 violations; one `h1`, landmarks, live region | `a11y.test.tsx` | web |
| V-W5 | FR-074/075, SC-007, AS-5.4 | `check-build.mjs` | `make build-web` | web |
| V-W6 | FR-078, FR-081 | stylelint strict-value; no `document.cookie`/`localStorage`/`sessionStorage` (ESLint `no-restricted-globals`/`no-restricted-properties`) | `make lint-web` | web |
| V-W7 | SC-008 | Lighthouse mobile preset, median of 3, on `pnpm preview`: LCP ≤ 2.5 s, CLS ≤ 0.1, TBT ≤ 200 ms; accessibility contrast pass | acceptance | — |
| V-I1 | FR-085–089, SC-011 | workflow review: triggers, permissions, SHAs, concurrency, no `secrets.`; fork PR run | acceptance | — |
| V-I2 | SC-004 | 3 seeded format violations plus 1 golden change → matching red status | throwaway PRs | — |
| V-I3 | SC-001, SC-010 | timed clean clone on ubuntu and macOS ≤ 10 min; README checklist and `wc -l` ≤ 80 | acceptance | — |
| V-I4 | SC-005 (DORA lead time) | Actions API over 30 days: median ≤ 10 min, p95 ≤ 15 min | post-merge | — |

---

## Bundle Coverage (required sections → where addressed)

| Required section | Coverage |
|---|---|
| api_surface_and_versioning / api_consumption_contract | C4 (`/api/v1/` prefix, a breaking change needs `/api/v2/`, FR-041); C8 |
| auth_and_identity_model / auth_session_and_csrf_model | CD-5 endpoints are unauthenticated (FR-045). README records **GitHub Actions OIDC (JWT, RS256, JWKS, audience-bound)** plus a hashed project **API key**, and `HttpOnly`/`Secure`/`SameSite=Lax` sessions with CSRF token or same-origin header (FR-046, FR-082). |
| data_model_and_storage / migration_and_schema_evolution | §6; no DB. Report schema follows **expand-contract** with one schema file per version (FR-056). Future DB migrations are **zero-downtime expand-contract** (add → backfill → switch reads → remove) (FR-057). |
| background_jobs / event_and_messaging / rate_limiting | None in CD-5 (FR-058, FR-059). `rate-limited` 429 is reserved. |
| error_taxonomy_and_codes | C1 exit codes and diagnostics; C4 problem codes (404/405/422/500 plus reserved 400/409/413/422/429). |
| observability_and_slo / observability_stack | C5 JSON logs now. Provisional stack: **OpenTelemetry** SDK (logs, metrics, traces) → OTLP → Collector → **Prometheus** (metrics), **Grafana Loki** (logs), **Grafana Tempo** (traces) (FR-062). SLO: SC-006 p95/p99. |
| deployment_topology / target_environments / container_and_orchestration | Local and CI only (FR-090). Provisional: OCI images for the API, static assets for the web app; orchestration undecided. |
| infrastructure_as_code_strategy | None built. Provisional **Terraform**, provider undecided (FR-090). |
| ci_cd_pipeline_topology | C10. |
| secrets_and_config / secrets_and_credentials | No secrets (FR-091), C6. Provisional **GitHub Actions OIDC** federation plus a **cloud-provider secret manager** (FR-092). |
| rollout_and_rollback | CD-5: revert the merge commit, which passes the same CI. Later: **blue-green** with traffic switched back, plus a **feature-flag kill-switch** (FR-093). |
| scaling / cost | Single process, ≤ 200 MB scanner RSS, USD 0/month, ≤ 25 runner-minutes and ≤ 10 min per CI run (FR-094/095). |
| retention / backup_and_DR / disaster_recovery_runbook / compliance_and_audit | No stored data. Runbook: re-clone → `make install` → `make test`. Audit trail is git history plus Actions logs. Branch protection is recommended (FR-096–098). |
| target_browsers / rendering / routing / state / responsive / tokens / a11y / i18n / perf / analytics / error_boundary / assets | C9 browserslist; **CSR** static SPA; history-routed two views; view-local state; 320 px reflow with breakpoints at 640 and 1024; `tokens.css`; **WCAG 2.2 AA**; English `strings.ts`; JS ≤ 100 KB and CSS ≤ 20 KB gzip, LCP ≤ 2.5 s, CLS ≤ 0.1, INP ≤ 200 ms (TBT proxy); no analytics, cookies or storage; top-level error boundary, no service worker; content-hashed assets with no splitting yet and later views lazy-loaded. |

---

## Open Questions (non-gating; defaults applied)

1. **R-2:** Should runtime errors (unwritable output, output == config) get catalogued diagnostic IDs, for example `dogwatch:output-unwritable`, in the CD-3 catalogue? The default is `dogwatch: error:` with no ID.
2. **R-1:** Confirm that the scanner range ceiling is decided by 3.15.0's final release on 2026-10-09 relative to when implementation starts, and that falling back to 3.14 is acceptable if dev tools lack 3.15 wheels.
3. **R-3:** Confirm that "dotted name split across roots" means *the same `name` declared under different roots*, given CD-3's single-identifier `name`.
4. **A-13 follow-ups** (outside CD-5's write scope): update CD-4 §2.5 `schema` → `schema_version`, and add `config-not-found` to CD-3 §2.12.

Sources:
- [Python 3.15.0 candidate 3 is here! (python.org blog)](https://blog.python.org/2026/10/python-3150-rc3/)
- [Python 3.15.0rc3: stable release set for October 9, 2026](https://www.linuxcompatible.org/story/python-3150rc3-release-candidate-announced-stable-release-set-for-october-9-2026)
- [PEP 790](https://peps.python.org/pep-0790/)
- [tomllib docs (3.14)](https://docs.python.org/tr/3.14/library/tomllib.html)
- [Vite: Migration from v7](https://vite.dev/guide/migration)
- [Announcing Vite 8](https://vite.dev/blog/announcing-vite8)
- [astral-sh/uv releases](https://github.com/astral-sh/uv/releases)
- [pypi uv 0.12.2](https://newreleases.io/project/pypi/uv/release/0.12.2)
- [Node.js 26 vs Node.js 24 LTS](https://dev.to/aarav_chandel_bf81a1120b1/nodejs-26-vs-nodejs-24-lts-should-you-upgrade-now-3l83)
- [InfoQ: pnpm 11 RC](https://infoq.com/news/2026/04/pnpm-11-rc-release/)
- [pnpm 11.14 release notes](https://releases.sh/release/rel_wc5MI044rLDNKoulEML7q-pnpm-11-11-11-14)
