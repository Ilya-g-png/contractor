
# Architecture Contracts: CD-5 (monorepo bootstrap: scanner CLI, API, web app, deterministic fixture)

**Sources of truth**
- Architecture: `artifacts/design/architecture.md` (cited as **ARCH §x**).
- Frozen spec: `artifacts/planning/frozen_spec.md` (cited as **FS FR-/AS-/SC-**).
- Implementation plan contracts C1–C12: `artifacts/planning/implementation_plan.md` §7 (cited as **PLAN Cx**). The plan only adds precision. Where it conflicts with ARCH, ARCH wins, and the conflict is listed in §6.
- Prior ADRs, referenced only through ARCH and FS:
  - CD-2: `/Users/iliaglushkov/Documents/sandbox/contractor/.am/reports/9c37b285-b35d-4dc2-be1c-2347272422e0-research-paper.md`
  - CD-3: `/Users/iliaglushkov/Documents/sandbox/contractor/.am/reports/7ee72c98-20e3-41ff-9321-386775b7a72e-research-paper.md`
  - CD-4: `/Users/iliaglushkov/Documents/sandbox/contractor/.am/reports/5b28548a-4c88-4600-b7cc-a6df1df95c7b-research-paper.md`

**Conventions**
- **ID prefixes:**
  - `IC-n`: interface contract
  - `EC-n`: event/queue contract
  - `DC-n`: data contract
  - `INV-n`: boundary invariant
  - `VC-n`: versioning rule
  - `G-n`: open gap
- **Normative words.** "MUST", "MUST NOT" and "MAY" are normative. Text in *italics* is explanation only.
- **Message templates.** `<angle>` placeholders mark substituted values. Other text in a template is normative. Tests MUST assert the diagnostic prefix, the ID and every named placeholder value. Tests MUST NOT assert free text that comes from the interpreter, such as `tomllib` messages.
- **Size units.** KB = 1000 bytes and MB = 10⁶ bytes, except where marked otherwise (ARCH §6.30).

---

## 1. Interface Contracts

### IC-1: Scanner CLI `dogwatch` (ARCH §3.2, §4.4, §6.10; FS FR-010–FR-016, FR-052; PLAN C1)

**Entry points.** The two entry points below MUST behave identically for the same argv, environment and cwd. The golden harness uses the second one (ARCH §5 E5).
- The console script `dogwatch`, from `[project.scripts] dogwatch = "dogwatch.cli:main"`.
- `python -m dogwatch`.

**Grammar**
```
dogwatch --version
dogwatch check [--config PATH] [--output PATH | --output -]
```

| Argument | Type | Default | Rule |
|---|---|---|---|
| `--version` | flag (top level) | — | Prints `dogwatch <version>\n` to stdout and exits `0`. `<version>` is `importlib.metadata.version("dogwatch")`: SemVer 2.0.0 with no leading `v`, `0.1.0` in CD-5 (FR-012). |
| `--config PATH` | string | `./dogwatch.toml`, resolved against the process cwd | Taken literally. `-` is **not** stdin; it means a file named `-`. |
| `--output PATH` | string | `./dogwatch-report.json`, resolved against the process cwd | `-` means write the report bytes to `sys.stdout.buffer` (FR-011). |
| no subcommand / unknown flag | — | — | Usage error: argparse `usage:` plus `dogwatch: error: …` on stderr, exit `2`. |

**Processing order.** This order is normative. The first failure ends the run.
1. Parse argv.
2. Validate the config through stages V0–V4 (DC-1).
3. **Output-target check:** reject when the output is not `-` and either `os.path.realpath(output) == os.path.realpath(config)` or, when both exist, `os.path.samefile(output, config)`.
4. Build the report (DC-3).
5. Write it (IC-1.W).
6. Exit `0`.

**Response matrix**

| Outcome | Exit | stdout | stderr | Filesystem effect |
|---|---|---|---|---|
| Valid config, file output | `0` | empty | empty | The target exists and holds exactly the DC-3 bytes. It is created or replaced atomically. |
| Valid config, `--output -` | `0` | exactly the DC-3 bytes | empty | none |
| V0 failure | `2` | empty | `dogwatch:config-not-found: <config_arg> does not exist` | nothing created or modified |
| V1–V3 failure | `2` | empty | exactly one `dogwatch:config-invalid: …` line (DC-1 templates) | nothing created or modified |
| V4 failure(s) | `2` | empty | one `dogwatch:config-invalid: …` line **per** failure, in the order DC-1 defines | nothing created or modified |
| Output path is the same file as the config | `2` | empty | `dogwatch: error: output path <output_arg> is the same file as config <config_arg>` | nothing created or modified |
| Output not writable (missing directory, permission denied, `ENOSPC`, broken stdout pipe) | `2` | possibly partial bytes, **stdout mode only** | `dogwatch: error: cannot write report to <output_arg>: <strerror>` | target path unchanged; temp file removed |
| Usage error | `2` | empty | argparse usage text | nothing created or modified |
| Gate failed | `1` | — | — | **reserved, never emitted in CD-5** (FR-015) |

The `dogwatch: error:` form deliberately carries no catalogue ID. This is the ARCH OQ-1 default; see G-6.

**Atomic write (IC-1.W)** (ARCH §3.2 `output`, §5 E4)
- Create a temp file in the target's own directory, named `.<target-basename>.<random>.tmp`.
- Write all bytes, `flush`, then `os.fsync`.
- `chmod` the temp file to `0o666 & ~umask`. *This stops the 0600 mode of `tempfile` from leaking into the report.*
- `os.replace(temp, target)`.
- On any `OSError` at any step, unlink the temp file (ignoring errors from the unlink), then exit `2`.
- Exactly one report file is produced per successful run.

**Side-effect rules**
- No network I/O. No telemetry (FR-063).
- No reads of any path under a declared package directory (FR-013a, FR-014).
- No writes anywhere except the temp file and the target.

**Idempotency.** `dogwatch check` is idempotent. Given the same config bytes, the same config basename and the same scanner version, repeated runs produce byte-identical outputs (INV-D1). If the target already holds those bytes, re-running leaves its content unchanged.

### IC-2: Root task contract, the `Makefile` (ARCH §3.1, §6.17; FS FR-005, FR-089; PLAN C7)

Each target runs inside exactly one area directory and calls only that area's tool. These targets are what CI and the README call (INV-C3).

| Target | Runs in | Command | Prerequisite targets |
|---|---|---|---|
| `install` | — | — | `install-scanner install-api install-web` |
| `install-scanner` | `scanner/` | `uv sync --locked` | — |
| `install-api` | `api/` | `uv sync --locked` | — |
| `install-web` | `web/` | `pnpm install --frozen-lockfile` | — |
| `test` | — | — | `test-scanner test-fixtures test-api test-web` |
| `test-scanner` | `scanner/` | `uv run --locked pytest -m "not golden"` | — |
| `test-fixtures` | `scanner/` | `uv run --locked pytest -m golden` | — |
| `test-api` | `api/` | `uv run --locked pytest` | — |
| `test-web` | `web/` | `pnpm run test` (→ `vitest run`) | `install-web` |
| `lint` | — | — | `lint-scanner lint-api lint-web` |
| `lint-scanner`, `lint-api` | area | `uv run --locked ruff format --check . && uv run --locked ruff check . && uv run --locked mypy` | — |
| `lint-web` | `web/` | `pnpm run lint` (→ `prettier --check . && eslint . && stylelint "src/**/*.css" && tsc --noEmit -p tsconfig.json`) | `install-web` |
| `format` | — | — | `format-scanner format-api format-web` |
| `format-scanner`, `format-api` | area | `uv run --locked ruff format . && uv run --locked ruff check --fix .` | — |
| `format-web` | `web/` | `pnpm run format` (→ `prettier --write .`) | `install-web` |
| `build-web` | `web/` | `pnpm run build` (→ `tsc --noEmit && vite build && node scripts/check-build.mjs`) | `install-web` |
| `run-scanner` | `scanner/` | `uv run --locked dogwatch check --config ../fixtures/minimal/dogwatch.toml --output -` | — |
| `run-api` | `api/` | `uv run --locked dogwatch-api` | — |
| `run-web` | `web/` | `pnpm run dev` | `install-web` |
| `regen-fixtures` | `scanner/` | `uv run --locked python -m tests.golden.regenerate` | — |
| `bench-api` | `api/` | `uv run --locked --group bench locust -f scripts/locustfile.py --headless -u 20 -r 20 -t 60s --host http://127.0.0.1:8000 --csv <outdir>/health` (ARCH §2.3, §6.9). Acceptance only, and it requires a running `run-api`. | — |

**Exit semantics**
- Every target returns the exit status of its first failing command; success is `0`.
- A target MUST NOT install or invoke another area's toolchain (FR-002, AS-1.2–1.4).
- `UV_PYTHON` passes through from the caller's environment unchanged.

**`package.json` scripts the Makefile depends on.** WP-W MUST expose exactly these names: `dev`, `build`, `preview`, `test`, `lint`, `format`.

**Python tool configuration.** The scanner and API MUST keep `pytest`, `ruff` and `mypy` configuration in `pyproject.toml`, so the commands above need no arguments.

**Idempotency.**
- `install-*`, `lint-*`, `test-*`, `build-web` and `run-scanner` are idempotent.
- `format-*` converges: a second run makes no changes.
- `regen-fixtures` is the **only** target that writes golden files (FR-034).

### IC-3: HTTP API `dogwatch-api` (ARCH §3.3, §4.5, §6.1, §6.10; FS FR-040–FR-045, FR-050–FR-051, FR-060–FR-061; PLAN C4)

**Base.** `http://<DOGWATCH_API_HOST>:<DOGWATCH_API_PORT>`, default `http://127.0.0.1:8000` (FR-044).

**Transport.** HTTP/1.1 through plain uvicorn. TLS is not used in CD-5.

**Auth.** None on any endpoint (FR-045). There is no session or cookie, and the API sets no `Set-Cookie` headers.

**Router settings**
- `redirect_slashes=False`. Any path not listed below, *including the trailing-slash variants* `/api/v1/health/` and `/api/v1/openapi.json/`, returns `404 not-found` and is not redirected. This follows the "anything else → 404" row in ARCH §6.1.
- `docs_url=None`, `redoc_url=None`, `openapi_url="/api/v1/openapi.json"`.

#### IC-3.1 `GET /api/v1/health`
| Aspect | Contract |
|---|---|
| Request | No body. Query parameters are ignored. Optional header `X-Request-ID` (IC-3.4). |
| 200 response | `Content-Type: application/json`. Body is DC-5: `{"status":"ok","service":"dogwatch-api","version":"0.1.0"}`, where `version` = `importlib.metadata.version("dogwatch-api")`. |
| Errors | Any method other than the route's permitted ones: `405 method-not-allowed`, with an `Allow` header listing the permitted methods (it includes `GET`). Unhandled exception: `500 internal-error`. |
| Idempotency | Safe and idempotent (RFC 9110). No state is read or written. |
| Caching | No `Cache-Control` is required in CD-5. *The client never caches; see IC-5.1.* |

#### IC-3.2 `GET /api/v1/openapi.json`
| Aspect | Contract |
|---|---|
| Request | No body |
| 200 response | `Content-Type: application/json`. The body is an OpenAPI document where `openapi` matches `^3\.1\.\d+$`, `info.title == "dogwatch-api"`, `info.version == "0.1.0"`, and `set(paths) == {"/api/v1/health"}` (FR-042, FR-043). `components.schemas` contains `HealthStatus`, whose `status` is constrained to `"ok"`. |
| Errors | 405 and 500, as in IC-3.1 |
| Idempotency | Safe and idempotent. The document is deterministic for a given build. |

#### IC-3.3 Fallback (any other method/path)
`404 not-found` (DC-6).

#### IC-3.4 Headers on every response (FR-061, AS-4.4)

`X-Request-ID` MUST be present on **every** response: 200, 404, 405, 422 and 500.

- **Accepted value.** The first `X-Request-ID` request header is echoed byte-for-byte iff it matches `^[\x20-\x7E]{1,128}$`.
- **Generated value.** Otherwise, including when the header is absent, empty, over 128 characters, or contains non-printable or non-ASCII bytes, the service generates `str(uuid.uuid4())`: 36 characters, lowercase, hyphenated.
- **Never echoed.** A rejected incoming value is never logged or echoed.

#### IC-3.5 Error responses (RFC 9457; FR-050, FR-051)

- Every non-2xx response MUST have `Content-Type: application/problem+json` and a DC-6 body.
- Stack traces, exception messages, request bodies and query strings MUST NOT appear in any response body.

| `code` | HTTP | `title` | `detail` template | CD-5 trigger | Extra headers |
|---|---|---|---|---|---|
| `not-found` | 404 | `Not Found` | `No route matches <path>`. `<path>` is `scope["path"]` without the query string. | unknown path | — |
| `method-not-allowed` | 405 | `Method Not Allowed` | `Method <METHOD> is not allowed; allowed: <comma-separated methods>` | known path, wrong method | `Allow` |
| `validation-failed` | 422 | `Validation Failed` | `Request validation failed (<n> errors)`. No input values are echoed. | `RequestValidationError`. Exercised **only** through a test-only route registered by the test suite (ARCH §6.10). | — |
| `internal-error` | 500 | `Internal Server Error` | `Internal server error.` (fixed text) | any unhandled exception, caught by the outermost pure-ASGI `RequestContext` middleware, provided the response has not started (ARCH §3.3) | — |
| `schema-invalid` | 400 | — | — | **reserved, never emitted** | — |
| `payload-too-large` | 413 | — | — | **reserved** | — |
| `in-flight` | 409 | — | — | **reserved** | — |
| `idempotency-conflict` | 422 | — | — | **reserved** | — |
| `rate-limited` | 429 | — | — | **reserved** | — |

- Reserved codes exist only as constants in `dogwatch_api.problems`.
- If an exception is raised after `http.response.start` has been sent, the connection is closed without a problem body. The log line (DC-7) is still emitted, with `level:"error"`.

### IC-4: API process startup (ARCH §3.3 `settings`/`__main__`, §4.8; FS FR-044, FR-091, edge "port in use")

**Entry points.** These are equivalent:
- the console script `dogwatch-api`, from `dogwatch_api.__main__:main`
- `python -m dogwatch_api`

**Inputs.** Environment variables only (DC-8). There are no CLI flags.

| Condition | Exit | stderr |
|---|---|---|
| Normal shutdown (SIGINT/SIGTERM) | `0` | uvicorn lifecycle lines (not part of this contract) |
| `DOGWATCH_API_PORT` is not a base-10 integer in 1–65535 | `1` | `dogwatch-api: error: DOGWATCH_API_PORT must be an integer between 1 and 65535` |
| `DOGWATCH_API_HOST` is empty, or the bind fails with `EADDRNOTAVAIL`/`gaierror` | `1` | `dogwatch-api: error: cannot bind DOGWATCH_API_HOST=<host>` |
| Port already in use (`EADDRINUSE`) | `1` | `dogwatch-api: error: <host>:<port> is already in use; set DOGWATCH_API_PORT to choose another port` |

- The process binds the socket itself, then runs `uvicorn.Server` with `sockets=[sock]`, `access_log=False` and one worker.
- It never retries on another port.

### IC-5: Web client interfaces (ARCH §3.4, §4.6, §5 E6, §6.22–§6.25; FS FR-072, FR-073, FR-073a; PLAN C8)

#### IC-5.1 `fetchHealth`, the module `web/src/api/health.ts`
```ts
export type HealthResult = "available" | "unavailable";
export function fetchHealth(baseUrl: string, signal: AbortSignal): Promise<HealthResult>;
```
| Aspect | Contract |
|---|---|
| Request | `fetch(`${trimTrailingSlashes(baseUrl)}/health`, { method: "GET", headers: { Accept: "application/json" }, signal: AbortSignal.any([signal, AbortSignal.timeout(5000)]) })`. No body, no custom credentials option, no other headers. |
| Result | `"available"` iff all of: `res.ok`; `await res.json()` resolves; the parsed value is a non-null object; its `status === "ok"`. Otherwise `"unavailable"`. |
| Errors | **Never rejects.** Network errors, `AbortError`, `TimeoutError`, JSON parse errors and non-2xx responses all resolve to `"unavailable"`. |
| Rendering | No response field other than the boolean check is ever read, stored or rendered (FR-073a, CD-2 §2.4). |
| Call cardinality | Exactly one call per mount of `ApiStatus`. The effect cleanup aborts `signal`. |
| Idempotency | GET only. Repeat calls are safe. |

`baseUrl` = `import.meta.env.VITE_DOGWATCH_API_BASE_URL ?? "/api/v1"` (DC-8).

#### IC-5.2 `resolveView`, the module `web/src/router.ts`
```ts
export type ViewId = "home" | "not-found";
export function resolveView(pathname: string): ViewId; // "/" → "home"; every other string → "not-found"
```
- Paths are history-based. A `#fragment` is never consulted.
- Matching is exact: `/index.html` and `/x/` resolve to `not-found`.
- Not Found shows `<a href="/">` to Home, which is a full document navigation (FR-072, AS-5.3).

#### IC-5.3 DOM contract (FR-079, ARCH §6.28)

**Document**
- `<html lang="en">`.
- Shell: `<header>` contains the brand text from `strings.productName`, as text and not a heading. `<main>` contains the current view.

**Views**
- Each view renders exactly one `<h1>`.

**API status indicator**
- Rendered as `<p role="status" aria-live="polite">`.
- Its text is exactly one of `strings.apiStatus.checking | available | unavailable`.

**Error boundary fallback**
- Text `strings.error.title`.
- A `<button type="button">` labelled `strings.error.reload` that calls `location.reload()`.

#### IC-5.4 Dev and preview servers (ARCH §5 E7, §6.11; FS FR-073a)

| Server | Bind | Behaviour |
|---|---|---|
| `pnpm run dev` | `127.0.0.1:5173`, `strictPort: true` | Proxies `/api` → `http://127.0.0.1:8000`. SPA fallback (`appType: "spa"`). |
| `pnpm run preview` | `127.0.0.1:4173`, `strictPort: true` (Vite default port; see G-5) | Same proxy and fallback. Serves `dist/`. |

When the API is unreachable, the proxy returns 5xx, and IC-5.1 maps that to `"unavailable"` (AS-5.2).

### IC-6: Web build gate `web/scripts/check-build.mjs` (ARCH §3.4, §6.30, §6.33; FS FR-074, FR-075; PLAN C9)

| Aspect | Contract |
|---|---|
| Inputs | `dist/.vite/manifest.json`, `dist/index.html`, `dist/**/*.css` |
| JS measure | Sum of `gzip(level=9)` byte lengths of the manifest entry for `index.html` (`isEntry: true`) **plus** every chunk reachable through its `imports` (transitive, static only; `dynamicImports` are excluded) |
| CSS measure | Sum of `gzip(level=9)` byte lengths of every `dist/**/*.css` file |
| Fail conditions (exit `1`) | JS > **100 000** bytes. CSS > **20 000** bytes. `dist/index.html` contains a `<script` element without a `src` attribute. `dist/index.html` matches `/\son[a-z]+\s*=/i`. The manifest is missing. |
| Success | exit `0`. Prints one line per measure: `js-initial <bytes>/100000`, `css-total <bytes>/20000` |
| Idempotency | Pure read. The same `dist/` always gives the same result. |

### IC-7: Golden harness and regenerate (ARCH §3.2 `tests/golden`, §5 E5, §6.34; FS FR-032, FR-034; PLAN C12)

**Discovery**
- Sorted glob of `<repo>/fixtures/*/dogwatch.toml`.
- Each match is one fixture whose golden file is the sibling `expected-report.json`.

**Invocation per fixture and variant**
- argv: `[sys.executable, "-m", "dogwatch", "check", "--config", <absolute config path>, "--output", <tmp>/out.json]`
- cwd: a fresh temporary directory.

**Environment per variant**
- The parent environment is used **minus** `TZ`, `LC_*`, `LANG`, `PYTHONHASHSEED` and `HOME`, plus the variant values.
- `HOME` is set to a fresh temporary directory.
- Variant *k* (k = 0…4):

| k | `TZ` | `LC_ALL` = `LANG` |
|---|---|---|
| 0 | `UTC` | `C` |
| 1 | `America/Los_Angeles` | `C.UTF-8` |
| 2 | `Asia/Kolkata` | `en_US.UTF-8` |
| 3 | `Pacific/Chatham` | `tr_TR.UTF-8` |
| 4 | `Etc/GMT+12` | `POSIX` |

- `PYTHONHASHSEED` is a random integer in [1, 4294967295].
- *An unavailable locale falls back silently at the libc level, which is acceptable because output must not depend on locale anyway.*

**Assertions**
- Exit is `0`.
- stderr is empty.
- `out.json` bytes equal the golden bytes.
- On mismatch, the failure message is `difflib.unified_diff(golden_lines, actual_lines, "expected-report.json", "actual")`.
- On non-zero exit, the failure message includes the captured stderr.

**Additional check.** One test asserts that `shutil.which("dogwatch")` resolves inside the active environment.

**Regenerate** (`python -m tests.golden.regenerate`)
- Runs variant 0 for every discovered fixture.
- Writes `expected-report.json` through IC-1.W semantics.
- Prints `regenerated <relative path>` per fixture and exits `0`. Exits `1` if any fixture fails.

**Write rule.** The pytest run never opens a golden file for writing (INV-F2).

### IC-8: CI workflow interface `.github/workflows/ci.yml` (ARCH §2.6, §6.17; FS FR-085–FR-089; PLAN C10)

**Triggers and settings**
- Triggers: `pull_request` with `branches: [main]`, and `push` with `branches: [main]`. `pull_request_target`, `workflow_run` and `schedule` are not used.
- Top-level `permissions: contents: read`. No job-level permission escalation.
- `concurrency: { group: ci-${{ github.event.pull_request.number || github.ref }}, cancel-in-progress: true }`.
- Every `uses:` is pinned as `<owner>/<repo>@<40-hex SHA> # vX.Y.Z`. Allowed actions: `actions/checkout`, `astral-sh/setup-uv`, `actions/setup-node`, `pnpm/action-setup`.
- Toolchain sources:
  - `setup-uv` uses `version-file: scanner/pyproject.toml` for scanner and fixtures jobs and `api/pyproject.toml` for the api job.
  - `setup-node` uses `node-version-file: web/.node-version`.
  - `pnpm/action-setup` reads `web/package.json` `packageManager`.
- `timeout-minutes: 10` on every job.

**Published status names.** These names are the consumer contract for branch protection (FR-098):

| Status name | Runner | Steps (Makefile targets only) |
|---|---|---|
| `scanner (3.11)` | ubuntu-24.04 | `make lint-scanner test-scanner` with `UV_PYTHON=3.11` |
| `scanner (3.12)`, `scanner (3.13)`, `scanner (3.14)` | ubuntu-24.04 | `make test-scanner` with `UV_PYTHON=<v>` |
| `api` | ubuntu-24.04 | `make lint-api test-api` |
| `web` | ubuntu-24.04 | `make install-web lint-web test-web build-web` |
| `fixtures (ubuntu-24.04, 3.11)`, `fixtures (ubuntu-24.04, 3.14)`, `fixtures (macos-15, 3.11)`, `fixtures (macos-15, 3.14)` | per name | `make test-fixtures` with `UV_PYTHON=<v>` |

- That is 10 statuses. If 3.15 qualifies under ARCH OQ-2, `scanner (3.15)` is added and the fixtures entries use 3.15 as the newest version (12 statuses).
- No step references `secrets.`, and no artifacts are uploaded.

---

## 2. Event & Queue Contracts

CD-5 has **no asynchronous messaging surface**: no queues, pub/sub, schedulers, background workers, webhooks it receives, or event publishing (FS FR-058; ARCH §2.5, §5, §6.6, §6.7). Every interaction in ARCH §5 (E1–E8) is synchronous. The table below lists every asynchronous or stream-like edge that exists, so nothing is left implicit.

| ID | Surface | Producer | Consumer | Payload schema | Delivery guarantee | Retry policy |
|---|---|---|---|---|---|---|
| EC-1 | GitHub `pull_request` (types: GitHub default `opened`, `synchronize`, `reopened`) and `push` to `main` (ARCH §5 E9) | GitHub | `ci.yml` | GitHub webhook event payload (GitHub-owned; CD-5 reads only `github.ref` and `github.event.pull_request.number`, for the concurrency group) | GitHub-managed, at-least-once trigger. A superseded run for the same group is **cancelled**, so only the newest run per group reaches a terminal state other than `cancelled` (FR-088). | No automatic retry. Re-run is manual in the GitHub UI and produces the same commands (IC-8). |
| EC-2 | API request log stream, stdout (ARCH §6.9, E8) | `RequestContext` middleware | Developer terminal and CI logs today; an OpenTelemetry Collector later (provisional) | DC-7, one JSON object per line, `\n`-terminated | Best-effort, at-most-once. A logging failure MUST NOT change the HTTP response (ARCH §5 E8). | None |

**Explicitly not present (MUST NOT be introduced by CD-5)**
- CD-2's isolated validation worker.
- The `pending`/`complete`/`failed` status resource.
- Any report-ingestion event.

These are reserved for the ingestion ticket (FR-058). A reviewer predicate is INV-R1.

---

## 3. Data Contracts

"Nullable" means the field may hold JSON `null`, or Python `None` for in-memory types. TOML has no null, so policy fields are never nullable.

### DC-1: Policy file `dogwatch.toml`, CD-5 subset (ARCH §4.1; FS FR-013, FR-013a; CD-3 §2.1–§2.2)

**Source of truth:** the user-authored file. **Validator:** `dogwatch.config`.

| Field (dotted) | Type | Nullable | Required | Validation |
|---|---|---|---|---|
| (document) | TOML 1.0 table | no | yes | Valid UTF-8, with or without a BOM (see G-7). Top-level keys are exactly `{python}`. |
| `python` | table | no | yes | Keys are exactly `{packages}` |
| `python.packages` | array of tables | no | yes | Length ≥ 1 |
| `python.packages[i].name` | string | no | yes | `name.isidentifier()` is true. Because of that, the name contains no `.` (ARCH OQ-3 default). |
| `python.packages[i].root` | string | no | yes | Resolved as `config_dir / root`. V4 requires `config_dir / root / name` to be an existing directory. |

**Validation stages.** Validation stops at the first failing stage. Within V4, every failure is reported. Stages V0–V3 emit exactly one line.

| Stage | Predicate | stderr template on failure |
|---|---|---|
| V0 | `os.path.lexists(config_arg)` | `dogwatch:config-not-found: <config_arg> does not exist` |
| V1 | `os.path.isfile(config_arg)` and readable | `dogwatch:config-invalid: <config_arg> is not a readable file` |
| V1 | bytes decode as UTF-8 | `dogwatch:config-invalid: <config_arg> is not valid UTF-8` |
| V2 | `tomllib.loads(text)` succeeds. `<line>` = `exc.lineno` if present (3.14+), else group 1 of `at line (\d+)` in `str(exc)`, else `?`. | `dogwatch:config-invalid: <config_arg>:<line>: invalid TOML: <msg>` |
| V3 | Unknown key anywhere. `<dotted.key>` uses table names joined by `.` and array elements as `[i]` (0-based), e.g. `python.rules`, `openapi`, `python.packages[0].include`. | `dogwatch:config-invalid: <dotted.key> is not supported in this version` |
| V3 | `python` or `python.packages` is missing or empty, or the file is empty | `dogwatch:config-invalid: <config_arg> requires at least one [[python.packages]] entry` |
| V3 | Wrong type: `python` is not a table, `packages` is not an array of tables, `name` or `root` is not a string, or `name`/`root` is missing | `dogwatch:config-invalid: <dotted.key> must be a <table\|array of tables\|string>` (or `<dotted.key> is required`) |
| V3 | `name` is not an identifier | `dogwatch:config-invalid: python.packages[<i>].name '<name>' must be a single top-level identifier` |
| V4a (per entry, declaration order) | `config_dir/root/name` does not exist | `dogwatch:config-invalid: package '<name>': directory '<root>/<name>' does not exist` |
| V4a | The path exists but is not a directory | `dogwatch:config-invalid: package '<name>': '<root>/<name>' is not a directory` |
| V4b (pairs i<j in declaration order, among V4a-passing entries) | same `name`, same `realpath(config_dir/root)` | `dogwatch:config-invalid: package '<name>' is declared more than once (root '<root_j>')` |
| V4b | same `name`, different `realpath(root)` | `dogwatch:config-invalid: package '<name>' split across roots '<root_i>', '<root_j>'` |
| V4b | different names, and `realpath(P_j)` is inside `realpath(P_i)` or the other way round | `dogwatch:config-invalid: packages '<name_i>' ('<root_i>/<name_i>') and '<name_j>' ('<root_j>/<name_j>') are nested` |

Notes on V3 unknown keys:
- When several keys are unknown, only the first in sorted dotted-key order is reported. The single-line rule applies.
- A `[[python.rules]]`, waiver or `[openapi]` table falls under this case (FR-013).

**Not errors:**
- a package directory with zero `.py` files (AS-2.7)
- a package directory without `__init__.py` (PEP 420)

**Permitted filesystem calls in V4:** only `os.path.lexists`, `os.path.isdir` and `os.path.realpath`. No `open`, `os.listdir`, `os.scandir`, `importlib` or `ast` call is allowed on any path under `config_dir/root` (FR-013a, FR-014; INV-S1).

### DC-2: In-memory config types (ARCH §4.1)

| Type | Field | Type | Nullable | Validation / source |
|---|---|---|---|---|
| `PackageDecl` (frozen dataclass) | `name` | `str` | no | DC-1 V3 |
| | `root` | `str` | no | Kept as declared, not resolved |
| `PolicyConfig` (frozen dataclass) | `path_arg` | `str` | no | `--config` argument exactly as given |
| | `raw` | `bytes` | no | Exact file bytes. These are the input to `policy.digest.sha256`. |
| | `packages` | `tuple[PackageDecl, ...]` | no | Declaration order, length ≥ 1 |

### DC-3: Report, `schema_version` `"0.1"` (ARCH §4.2, §4.3; FS FR-020–FR-026; PLAN C3)

**Producer:** `dogwatch.report` plus `dogwatch.output`.

**Schema file:** `scanner/schemas/report-0.1.schema.json`. It is immutable after merge.

| Field | Type | Nullable | Validation | Value in CD-5 | Source of truth |
|---|---|---|---|---|---|
| `schema_version` | string | no | `const "0.1"` | `"0.1"` | `dogwatch.report` constant |
| `scanner` | object | no | `additionalProperties: false`; requires `name`, `version` | — | — |
| `scanner.name` | string | no | `const "dogwatch"` | `"dogwatch"` | constant |
| `scanner.version` | string | no | SemVer 2.0.0 regex, no leading `v` | `"0.1.0"` | `importlib.metadata.version("dogwatch")` from `scanner/pyproject.toml` |
| `policy` | object | no | `additionalProperties: false`; requires `path`, `digest` | — | — |
| `policy.path` | string | no | `minLength 1`; no `/`, `\` or U+0000–U+001F | `"dogwatch.toml"` | `os.path.basename(PolicyConfig.path_arg)` |
| `policy.digest` | object | no | `additionalProperties: false`; requires `sha256` | — | — |
| `policy.digest.sha256` | string | no | `^[0-9a-f]{64}$` | SHA-256 of `PolicyConfig.raw` | `hashlib.sha256(raw).hexdigest()` |
| `findings` | array | no | `items: false`, which forces the array to be empty | `[]` | constant |

**Fields that MUST be absent:** `commit_sha`, `object_format`, `dirty`, `base_sha`, `evaluation_date`, `scan_started_at`, `scan_finished_at`, `report_id`, and any field carrying source code, file content or snippets (FR-020, FR-026). The schema rejects them through `additionalProperties: false`.

**Normative JSON Schema**
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:dogwatch:schema:report:0.1",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version", "scanner", "policy", "findings"],
  "properties": {
    "schema_version": {"const": "0.1"},
    "scanner": {
      "type": "object", "additionalProperties": false, "required": ["name", "version"],
      "properties": {
        "name": {"const": "dogwatch"},
        "version": {"type": "string", "pattern": "^(0|[1-9]\\d*)\\.(0|[1-9]\\d*)\\.(0|[1-9]\\d*)(?:-[0-9A-Za-z.-]+)?(?:\\+[0-9A-Za-z.-]+)?$"}
      }
    },
    "policy": {
      "type": "object", "additionalProperties": false, "required": ["path", "digest"],
      "properties": {
        "path": {"type": "string", "minLength": 1, "pattern": "^[^/\\\\\\u0000-\\u001f]+$"},
        "digest": {
          "type": "object", "additionalProperties": false, "required": ["sha256"],
          "properties": {"sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"}}
        }
      }
    },
    "findings": {"type": "array", "items": false}
  }
}
```

**Canonical byte encoding** (FR-024)
- Bytes are `(json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False, separators=(",", ": ")) + "\n").encode("utf-8")`.
- No BOM. Written as bytes, so there is no newline translation.

The resulting shape is normative. Only the digest varies, by config bytes:
```json
{
  "findings": [],
  "policy": {
    "digest": {
      "sha256": "<64 lowercase hex>"
    },
    "path": "dogwatch.toml"
  },
  "scanner": {
    "name": "dogwatch",
    "version": "0.1.0"
  },
  "schema_version": "0.1"
}
```

### DC-4: Diagnostic (ARCH §4.4; FS FR-016, FR-052)

| Field | Type | Nullable | Validation |
|---|---|---|---|
| `id` | `Literal["config-invalid", "config-not-found"]` | no | Catalogue entries. Rendered as `dogwatch:<id>`. |
| `message` | `str` | no | Single line with no `\n`. Uses the DC-1 templates. |
| exit code (derived) | `int` | no | Always `2` |

- `DogwatchError(diagnostics: tuple[Diagnostic, ...])` holds at least one diagnostic.
- Rendering: `"\n".join(f"dogwatch:{d.id}: {d.message}" for d in diagnostics) + "\n"` to stderr.

### DC-5: `HealthStatus` (ARCH §4.5; FS FR-040)

**Producer:** `dogwatch_api.health`, as a pydantic model. **Consumer:** web IC-5.1, which reads only `status`.

| Field | Type | Nullable | Validation | Value |
|---|---|---|---|---|
| `status` | string | no | `Literal["ok"]` | `"ok"` |
| `service` | string | no | `Literal["dogwatch-api"]` | `"dogwatch-api"` |
| `version` | string | no | SemVer 2.0.0 | `importlib.metadata.version("dogwatch-api")`, which is `0.1.0` |

No other fields are present.

### DC-6: `ProblemDetail` (ARCH §4.5, §6.10; FS FR-050, FR-051)

**Producer:** `dogwatch_api.problems` and the middleware 500 path. **Media type:** `application/problem+json`.

| Field | Type | Nullable | Validation |
|---|---|---|---|
| `type` | string | no | `urn:dogwatch:problem:<code>` |
| `title` | string | no | Fixed per code (IC-3.5) |
| `status` | integer | no | Equals the HTTP status code |
| `detail` | string | no | Per-code template (IC-3.5). Never contains a stack trace, exception text, query string or request body. |
| `code` | string | no | One of the active codes `not-found`, `method-not-allowed`, `validation-failed`, `internal-error` |

No other fields are present.

### DC-7: API request log line (ARCH §6.9; FS FR-060, FR-061; PLAN C5)

- **Producer:** `RequestContext` middleware through stdlib `logging` with the JSON formatter in `dogwatch_api.log`.
- **Sink:** stdout. Exactly one line per HTTP request.
- The line is a compact JSON object (`separators=(",", ":")`), terminated by `\n`.

| Field | Type | Nullable | Validation / rule |
|---|---|---|---|
| `ts` | string | no | RFC 3339 UTC at completion, millisecond precision, `Z` suffix: `YYYY-MM-DDTHH:MM:SS.mmmZ` |
| `level` | string | no | `"error"` when status ≥ 500 or an unhandled exception occurred. `"info"` otherwise. |
| `event` | string | no | `const "request"` |
| `request_id` | string | no | The value sent in `X-Request-ID` (IC-3.4) |
| `method` | string | no | The request method as received |
| `route` | string | **yes** | `path` of the first route in `app.router.routes` whose `matches(scope)` is `Match.FULL`. Otherwise the first with `Match.PARTIAL` (the 405 case). Otherwise `null` (404). |
| `status` | integer | no | The response status sent. If an exception occurs after the response started, it is the status already sent. |
| `duration_ms` | number | no | ≥ 0. `time.perf_counter()` delta, rounded to 2 decimals. |
| `error_type` | string | absent unless an unhandled exception occurred | Fully qualified exception class name |
| `error_traceback` | string | absent unless an unhandled exception occurred | `traceback.format_exception` text joined into one JSON string (newlines escaped) |

**MUST NOT appear:** request or response bodies, the query string, the raw path of an unmatched request, any header other than the validated request ID, or a rejected incoming request ID.

**Outside this contract:** uvicorn lifecycle and startup lines. They MUST NOT be written as `event:"request"` lines.

### DC-8: Configuration variables (ARCH §4.8; FS FR-044, FR-073a, FR-091)

| Variable | Area | Type | Default | Validation | Secret | Documented in |
|---|---|---|---|---|---|---|
| `DOGWATCH_API_HOST` | api, runtime | string | `127.0.0.1` | non-empty | no | `api/.env.example` |
| `DOGWATCH_API_PORT` | api, runtime | integer | `8000` | 1–65535, base 10 | no | `api/.env.example` |
| `VITE_DOGWATCH_API_BASE_URL` | web, **build time** | string (path or absolute URL) | `/api/v1` | Trailing `/` is trimmed by IC-5.1 | no | `web/.env.example` |
| `UV_PYTHON` | scanner/fixtures, local and CI | CPython version | unset, so `.python-version` (3.14.x) applies | must be inside the scanner range | no | README |

- No other `DOGWATCH_API_*` variable is read.
- `.env` and `.env.*` are git-ignored, and `!.env.example` is kept (ARCH §3.1).

### DC-9: Web view state `ApiStatusState` (ARCH §4.6; FS Key Entities)

| State | Entry condition | Rendered text (`strings.apiStatus.*`) | Terminal |
|---|---|---|---|
| `checking` | mount | `Checking API…` (U+2026) | no |
| `available` | IC-5.1 resolves `"available"` while in `checking` | `API available` | yes |
| `unavailable` | IC-5.1 resolves `"unavailable"` while in `checking` | `API unavailable` | yes |

- Allowed transitions: `checking → available`, `checking → unavailable`. No other transitions.
- A resolution after unmount or after a terminal state is discarded.

### DC-10: Strings module `web/src/strings.ts` (ARCH §3.4, §6.29; FS FR-080)

The module exports one `const strings` object. Every user-visible string in `web/src` MUST come from it.

| Key | Value | Fixed by |
|---|---|---|
| `productName` | `Dogwatch` | FS A-1 |
| `home.title` | `Dashboard` | this contract |
| `notFound.title` | `Page not found` | FS AS-5.3 |
| `notFound.homeLink` | `Back to home` | this contract |
| `apiStatus.checking` / `available` / `unavailable` | `Checking API…` / `API available` / `API unavailable` | FS FR-073 |
| `error.title` | `Something went wrong` | FS FR-076 |
| `error.reload` | `Reload` | this contract |

### DC-11: Design tokens `web/src/styles/tokens.css` (ARCH §6.27; FS FR-078)

- **Scope.** Tokens are declared only on `:root` in this file. The light theme is the only one.
- **Name families:** `--color-*`, `--space-*`, `--font-*` (family, size, weight, line height) and `--radius-*`.
- **Contrast annotation.** Each foreground/background color pair used for text carries a comment `/* contrast <fg> on <bg>: <ratio>:1 */` with ratio ≥ 4.5.
- **Focus token.** A focus-outline color token MUST exist and be used for `:focus-visible`.
- **Lint rule.** Outside `tokens.css`, color, spacing, font-size and border-radius declarations MUST use `var(--…)`; stylelint errors otherwise. `@media` parameters are exempt.
- **Theming seam.** A future theme overrides the same names under a selector such as `[data-theme="dark"]`.

### DC-12: Fixture layout and golden file (ARCH §3.5; FS FR-030–FR-034; PLAN C12)

| Path | Type | Rule |
|---|---|---|
| `fixtures/README.md` | doc | States the convention below |
| `fixtures/<kebab-name>/` | directory | One per fixture. `<kebab-name>` matches `^[a-z0-9]+(-[a-z0-9]+)*$`. |
| `fixtures/<name>/dogwatch.toml` | DC-1 | Must pass V0–V4 |
| `fixtures/<name>/<root>/<package>/…` | static source | Never imported, executed or installed (FR-031) |
| `fixtures/<name>/expected-report.json` | DC-3 bytes | Written only by IC-7 regenerate |
| `fixtures/minimal/` | instance | Package `acme_shop`, root `src`, modules `__init__.py`, `orders.py`, `payments.py` |

`.gitattributes` MUST contain `fixtures/** text eol=lf` (FR-008).

### DC-13: CI check state (ARCH §4.7)

`queued → running → passed | failed | cancelled`. `cancelled` is reachable only through `concurrency.cancel-in-progress` or the job `timeout-minutes`. GitHub reports a timeout as failure.

---

## 4. Boundary Invariants

Each invariant is a predicate with the place it is checked. **CI** means it runs on every CI run. **Acc** means it is checked once at acceptance.

### Area isolation (FS FR-002, FR-003; ARCH §3.6)

| ID | Predicate | Checked by |
|---|---|---|
| INV-A1 | `grep -rE "^\s*(from\|import)\s+dogwatch_api" scanner/src` and `grep -rE "^\s*(from\|import)\s+dogwatch\b" api/src` both return no matches. Neither `pyproject.toml` lists the other area as a dependency. | CI lint step (scanner and api tests) |
| INV-A2 | For each area X in {scanner, api, web}, running `make test-X` in a clean clone with only X's toolchain installed exits `0` (SC-003). The web suite passes with no `python3`/`uv` on `PATH`. | CI (separate jobs) and Acc |
| INV-A3 | `scanner/uv.lock`, `api/uv.lock` and `web/pnpm-lock.yaml` exist. There is no root lockfile and no `[tool.uv.workspace]`. | CI (`uv sync --locked`, `pnpm install --frozen-lockfile` fail on drift; FR-087) |
| INV-A4 | `git diff --name-only <base>...HEAD -- .am/` is empty, and `.gitignore` contains no line matching `^/?\.am` (FR-007). | Review checklist and Acc |

### Scanner trust boundary (FS FR-013a, FR-014, FR-063; ARCH §3.2)

| ID | Predicate | Checked by |
|---|---|---|
| INV-S1 | During `dogwatch check` on `fixtures/minimal`, a monkeypatched `builtins.open`/`io.open`/`os.open`/`os.scandir`/`os.listdir` records zero calls on paths under `realpath(config_dir/root/name)`. After the run, `"acme_shop" not in sys.modules`. | scanner tests, CI |
| INV-S2 | With `socket.socket.connect` monkeypatched to raise, `dogwatch check` still exits `0` on `fixtures/minimal`. The scanner runtime imports no module outside the stdlib: `[project] dependencies == []`. | scanner tests, CI |
| INV-S3 | For every exit-`2` case in IC-1 (the four SC-013 seeds, V0, V2, V3, unwritable output, output == config), the output path does not exist after the run when it did not exist before. When it existed before, its bytes and mtime are unchanged. No `.*.tmp` file remains in its directory. | scanner tests, CI |
| INV-S4 | When the exit code is `0`, stderr is empty. When it is `2`, every stderr line matches `^dogwatch:(config-invalid\|config-not-found): .+$` or `^dogwatch: error: .+$`, or the output is argparse usage. | scanner tests, CI |
| INV-S5 | Exit code `1` is never produced by any CD-5 test case. | scanner tests, CI |
| INV-S6 | SC-013: 4 of 4 seeded invalid structures (missing dir, duplicate, nested, split) exit `2` with `dogwatch:config-invalid` and produce no file. A package with zero `.py` files exits `0` with `findings == []`. | scanner tests, CI |
| INV-S7 | Peak RSS from `resource.getrusage(RUSAGE_CHILDREN).ru_maxrss` after a subprocess run on `fixtures/minimal` is ≤ 200 × 10⁶ bytes. The value is normalised as bytes on darwin and KiB × 1024 on linux (FR-094, ARCH §6.14). | scanner tests, CI |

### Determinism and report integrity (FS FR-020–FR-026, FR-032, FR-034; ARCH §4.2, §6.34)

| ID | Predicate | Checked by |
|---|---|---|
| INV-D1 | For every IC-7 variant k ∈ 0..4, interpreter ∈ {3.11, newest} and OS ∈ {ubuntu-24.04, macos-15}: `sha256(output) == sha256(fixtures/minimal/expected-report.json)` (20/20 runs, SC-002). | CI fixtures jobs and Acc scripted loop |
| INV-D2 | `Draft202012Validator(schema).validate(json.loads(output))` passes, and `Draft202012Validator.check_schema(schema)` passes. | scanner tests, CI |
| INV-D3 | `output.startswith(b"\xef\xbb\xbf") is False`, `b"\r" not in output`, `output.endswith(b"}\n") and not output.endswith(b"\n\n")`, and `output == canonical(json.loads(output))` (DC-3 encoding). | scanner tests and fixtures, CI |
| INV-D4 | `policy.path == "dogwatch.toml"`, and the output contains none of the substrings `os.getcwd()`, `os.path.expanduser("~")`, `socket.gethostname()` or `getpass.getuser()`. | fixtures tests, CI |
| INV-D5 | Seeded: a config containing non-ASCII comments produces a digest equal to `hashlib.sha256(raw).hexdigest()`, and output that is byte-stable across the variants. | scanner tests, CI |
| INV-F1 | `git check-attr eol -- fixtures/minimal/dogwatch.toml fixtures/minimal/expected-report.json` reports `lf` for both. | Acc (CP-1) |
| INV-F2 | After `make test-fixtures`, `git status --porcelain fixtures/` is empty. The golden-file mtime is unchanged. | CI (fixtures job, final step check) |
| INV-F3 | A seeded change to any field of `expected-report.json` turns every `fixtures (…)` status red (SC-004, AS-3.3). | Acc, throwaway PR |

### API boundary (FS FR-040–FR-051, FR-060–FR-061; ARCH §3.3, §6.1, §6.9, §6.10)

| ID | Predicate | Checked by |
|---|---|---|
| INV-P1 | For each request in {GET health, GET openapi, GET `/api/v1/nope`, GET `/api/v1/health/`, POST health, GET test-only 422 route, GET test-only raising route}: the response has an `X-Request-ID` header, and exactly one stdout line parses as DC-7 with `request_id` equal to that header. | api tests, CI |
| INV-P2 | Every non-2xx response has `content-type == "application/problem+json"`, a body whose keys are exactly `{type,title,status,detail,code}`, `body.status == response.status_code`, and `body.type == "urn:dogwatch:problem:" + body.code`. | api tests, CI |
| INV-P3 | In the 500 response body, neither the raised exception's message nor the substring `Traceback` appears. The matching log line has `level == "error"` and a non-empty `error_traceback`. | api tests, CI |
| INV-P4 | Request ID `"a"*128` is echoed. `"a"*129`, `"x\ny"` and `"é"` are replaced by a value matching `^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$`, and the rejected raw value appears in no log line. | api tests, CI |
| INV-P5 | A request to `/api/v1/health?token=secret` with an `Authorization: Bearer x` header produces a log line containing neither `secret` nor `Bearer`. | api tests, CI |
| INV-P6 | `set(openapi["paths"]) == {"/api/v1/health"}` and `openapi["openapi"].startswith("3.1")`. `/docs` and `/redoc` return 404. | api tests, CI |
| INV-P7 | With no `DOGWATCH_API_*` variables set, the settings resolve to host `127.0.0.1` and port `8000`. `DOGWATCH_API_PORT=0` and `=abc` exit `1` with stderr containing `DOGWATCH_API_PORT`. A port held by another socket exits `1` with stderr containing `DOGWATCH_API_PORT` and the port number. | api tests, CI |
| INV-P8 | **SC-006 latency SLO.** `GET /api/v1/health` **p95 ≤ 50 ms and p99 ≤ 100 ms with 0 failures**, read from Locust `health_stats.csv` (the row `Aggregated`, columns `95%` and `99%`).<br>• **Tool:** **Locust** headless.<br>• **Load:** **20 concurrent users** (`-u 20 -r 20`), **sustained 60 s** (`-t 60s`).<br>• **Dataset:** none; the endpoint is stateless and 0 rows are stored.<br>• **Environment:** **1× GitHub-hosted `ubuntu-24.04` standard runner**, **1 uvicorn process with 1 worker**, generator co-located over loopback, **no DB tier**. | Acc (`make bench-api`) |

### Web boundary (FS FR-070–FR-081; ARCH §3.4, §6.21–§6.33)

| ID | Predicate | Checked by |
|---|---|---|
| INV-W1 | With `fetch` stubbed to return each of {200 `{"status":"ok"}`, 200 `{"status":"degraded"}`, 200 `"not json"`, 503, a rejected promise, never-resolving + 5 s fake timers}, the status text is `API available` for the first and `API unavailable` for every other case. After the terminal state, a late `{"status":"ok"}` does not change the text. | web tests, CI |
| INV-W2 | `fetch` is called exactly once per mount, with URL `"/api/v1/health"` by default. Unmount aborts the signal. | web tests, CI |
| INV-W3 | A stubbed response body containing `<img src=x onerror=alert(1)>` is never present in the DOM (`container.innerHTML` does not include it). | web tests, CI |
| INV-W4 | **SC-009, WCAG 2.2 Level AA.** `axe.run(container, { runOnly: { type: "tag", values: ["wcag2a","wcag2aa","wcag21a","wcag21aa","wcag22aa"] } })` gives `violations.length === 0` for Home and Not Found.<br>• **Tool:** axe-core in Vitest with jsdom.<br>• **Throttling:** not applicable (static DOM).<br>• WCAG SCs covered: 1.3.1 Info and Relationships (landmarks), 2.4.7 Focus Visible (token outline), 3.1.1 Language of Page, 4.1.3 Status Messages (polite live region).<br>• SC 1.4.3 Contrast (Minimum) is verified by the Lighthouse accessibility audit at Acc (ARCH OQ-5). | web tests, CI and Acc |
| INV-W5 | **SC-007 bundle budget.** IC-6 reports **Home initial JS ≤ 100 000 bytes gzip** and **total CSS ≤ 20 000 bytes gzip**.<br>• **Tool:** `check-build.mjs` (gzip level 9) in the CI `web` job, on every run.<br>• **Throttling:** not applicable (build-time size). | CI |
| INV-W6 | `dist/index.html` has no inline `<script>` and no `on*=` attributes (FR-075). `grep -rE "https?://" dist/` matches no external origin in a `src`/`href`/`@import`/`url(` context. | CI (IC-6, plus a web test over `dist/`) |
| INV-W7 | ESLint fails on any use of `document.cookie`, `localStorage` or `sessionStorage` (`no-restricted-globals` / `no-restricted-properties`). No `serviceWorker.register` appears in `src/` (FR-076, FR-081). | CI lint-web |
| INV-W8 | A component that throws during render, inside `<ErrorBoundary>`, renders `Something went wrong` and a `Reload` button, not an empty `main`. | web tests, CI |
| INV-W9 | `resolveView("/") === "home"`. `resolveView(p) === "not-found"` for p in {"/x", "/index.html", "/a/b", ""}. | web tests, CI |
| INV-W10 | **SC-008 Core Web Vitals (lab).** On the Home view, **LCP ≤ 2.5 s, CLS ≤ 0.1, TBT ≤ 200 ms** (TBT is the lab proxy for **INP ≤ 200 ms**).<br>• **Tool:** **Lighthouse** mobile preset against `pnpm run preview` (`127.0.0.1:4173`), median of 3 runs.<br>• **Throttling:** simulated **Slow 4G** and **4× CPU slowdown**. | Acc |
| INV-W11 | **FR-077 Reflow.** At viewport width **320 CSS px**, `document.documentElement.scrollWidth <= 320` on Home and Not Found (WCAG 2.2 SC 1.4.10).<br>• **Tool:** Chrome DevTools device toolbar or a Playwright trace at acceptance.<br>• **Throttling:** desktop cable, no CPU throttle. | Acc |
| INV-W12 | `package.json` `browserslist` equals the ARCH §6.21 list, and `vite.config.ts` derives `build.target`/`build.cssTarget` only from `browserslistToEsbuild()`. No literal target array appears. | CI lint-web (a vitest config test) |

### CI and repository (FS FR-085–FR-089, FR-095; ARCH §6.15, §6.17)

| ID | Predicate | Checked by |
|---|---|---|
| INV-C1 | `ci.yml` contains no `secrets.` string and no `pull_request_target`. It sets `permissions: contents: read` at the top level, and every `uses:` matches `@[0-9a-f]{40}\s+# v\d+\.\d+\.\d+`. | Acc (`grep`) and review |
| INV-C2 | A fork PR run reports the same 10 statuses as an in-repo PR, all `passed` (SC-011, AS-3.4). | Acc (requires a public repo; ARCH OQ-6) |
| INV-C3 | Every `run:` line in `ci.yml` starts with `make ` and names only IC-2 targets (FR-089). | Acc (`grep`) |
| INV-C4 | A seeded unformatted file in each of `scanner/`, `api/` and `web/` turns the matching status (`scanner (3.11)`, `api`, `web`) red (SC-004, AS-3.2). A seeded `match` statement typed with 3.12+ syntax (e.g. `type X = int`) turns `scanner (3.11)` red (AS-3.6). | Acc |
| INV-C5 | **FR-095 pipeline cost.** Per CI run, the sum of job durations is ≤ 25 runner-minutes and the workflow wall-clock is ≤ 10 min.<br>• **Measurement source:** GitHub Actions REST `GET /repos/{owner}/{repo}/actions/runs/{id}/timing` and the job `started_at`/`completed_at` fields.<br>• **Scope:** every PR run and every push run to `main`. | Acc and spot checks |
| INV-C6 | **SC-005 DORA lead time for changes (pre-deployment proxy).** From push to `main` until every required status is `success`: **median ≤ 10 min, p95 ≤ 15 min**.<br>• **Window:** rolling **30 days** after merge.<br>• **Scope:** all pushes to `main`.<br>• **Measurement source:** GitHub Actions analytics through the Actions REST API run timestamps (`run_started_at` → last check-run `completed_at`). | Post-merge report |
| INV-C7 | **SC-001 recovery / time-to-green.** `git clone` → `make install` → `make test` exits `0` in **≤ 10 min wall-clock** with 0 credential prompts.<br>• **Scope:** one clean GitHub-hosted `ubuntu-24.04` runner and one clean macOS machine.<br>• **Measurement source:** GitHub Actions job timing for Linux, `time` for macOS. | Acc |
| INV-C8 | **SC-012.** `uv pip install ./scanner --python 3.10` fails with a `requires-python` error. `scanner/pyproject.toml` contains `requires-python = ">=3.11"`. | Acc and CI matrix |
| INV-C9 | `README.md` has ≤ 80 lines (`wc -l`). It contains every IC-2 user-facing target (`install`, `test`, `test-scanner`, `test-api`, `test-web`, `test-fixtures`, `lint`, `format`, `run-*`, `regen-fixtures`). Every deploy-related line in it contains the word `provisional` (SC-010, FR-090). | Acc checklist |

### Reserved-scope guard (FS A-7, FR-043, FR-055, FR-058, FR-059)

| ID | Predicate | Checked by |
|---|---|---|
| INV-R1 | The repository adds no database driver, ORM, queue/broker client, scheduler, rate-limit library, Dockerfile, Terraform file, or container/orchestrator manifest: `find . -name Dockerfile -o -name '*.tf'` is empty. The api `pyproject.toml` runtime dependencies are exactly `{fastapi, uvicorn}`. | Review and Acc |

---

## 5. Versioning & Compatibility

| ID | Contract | Versioning scheme | Compatibility expectation | Deprecation policy |
|---|---|---|---|---|
| VC-1 | **Report** (DC-3) | `schema_version` string `"<major>.<minor>"`. One frozen schema file per published version: `scanner/schemas/report-<ver>.schema.json`, `$id urn:dogwatch:schema:report:<ver>` (FR-056, ARCH §4.3). | **`0.x` has no compatibility promise** (FR-021). Future ingestion rejects major `0` (CD-2 §2.3). From `1.0`, **expand-contract**: within a major, only additive optional fields, and consumers MUST ignore unknown optional fields. Removal or rename requires a new major after consumers have migrated. `report-0.1.schema.json` is byte-immutable after merge. | A field is removed only in the next major. The old schema file stays checked in so old reports remain valid. The expected `0.1` → `0.2` step adds CD-2 provenance (and may change `policy.path` semantics; ARCH OQ-4). |
| VC-2 | **Scanner CLI** (IC-1): command names, flags, defaults, exit codes, `--output -` | SemVer of the `dogwatch` package (`scanner.version`). Pre-1.0 in CD-5. | The names `dogwatch`, `check`, `--config`, `--output`, the default file names, exit `0/1/2` meanings and the `dogwatch:` prefix are **public contracts** (FS A-1). Renaming any of them is breaking. Additive flags are minor. | A breaking CLI change needs a major bump once ≥ 1.0. Pre-1.0 it needs a minor bump with a README note. Any version bump requires `make regen-fixtures` in the same PR (INV-D1). |
| VC-3 | **Diagnostic catalogue** (DC-4) | Stable string IDs under `dogwatch:` | IDs are never renamed, reused or merged. `config-not-found` MUST stay separate from `config-invalid` (FR-016). New IDs are additive and registered in CD-3 §2.12 (A-13). Message text is not a contract beyond the DC-1 placeholders. | No ID removal. A superseded ID stays emitted until a scanner major bump. |
| VC-4 | **HTTP API** (IC-3) | URL path prefix `/api/v<major>/` (FR-041). `info.version` follows the `dogwatch-api` package SemVer. | Within `v1`: only new endpoints and new optional response fields. Clients (IC-5.1) MUST ignore unknown fields. A breaking change creates `/api/v2/`. | The FS defines no overlap window for `v1` after `v2` ships, so see G-4. CD-5 has a single consumer (the web shell). |
| VC-5 | **Problem codes** (DC-6, IC-3.5) | Stable `code` strings and `type` URNs `urn:dogwatch:problem:<code>` | Active and reserved codes keep their HTTP status forever. Reserved codes (`schema-invalid` 400, `payload-too-large` 413, `in-flight` 409, `idempotency-conflict` 422, `rate-limited` 429) MUST NOT be repurposed. New codes are additive. | No removal within `v1` |
| VC-6 | **Health body** (DC-5) | Covered by VC-4 | `status` keeps the value set `{"ok"}` within `v1`. Adding values such as `"degraded"` is breaking for IC-5.1's boolean check, so it needs either a client update in the same release or `v2`. | — |
| VC-7 | **Log line** (DC-7) | Unversioned in CD-5 (`event:"request"`) | Field additions are allowed. Renaming or removing fields is a breaking change for later Collector pipelines (provisional), and must be coordinated with the observability ticket. | — |
| VC-8 | **Configuration variables** (DC-8) | Prefix `DOGWATCH_API_` (A-1). `VITE_DOGWATCH_API_BASE_URL`. | Names and defaults are stable. New variables are additive and MUST have safe defaults (FR-091). | A renamed variable is read under both names for one minor release. |
| VC-9 | **Policy file subset** (DC-1) | Governed by the CD-3 policy versioning; CD-5 accepts a strict subset | Later tickets *widen* acceptance (rules, waivers, `openapi`). CD-5 rejects them with `config-invalid` "not supported in this version". A file valid under CD-5 MUST stay valid and produce `findings: []` semantics in later versions unless rules are added. | — |
| VC-10 | **Makefile targets** (IC-2) and `package.json` script names | Unversioned. Names are the contract between README, CI and the areas. | Renaming a target requires updating `README.md` and `ci.yml` in the same change (FR-089). | — |
| VC-11 | **CI status names** (IC-8) | Derived from job IDs and matrix values | Renaming a job or matrix value breaks branch protection (FR-098). It must be paired with an admin update of the required checks. Adding a CPython minor adds statuses and is additive. | Raising the CPython ceiling is a separate change (FR-009). Dropping 3.11 is out of scope. |
| VC-12 | **Toolchain pins** | `.python-version` (3.14.x), `requires-python`, `[tool.uv] required-version` (uv 0.12.x), `web/.node-version` and `engines.node` (Node 24.x), `packageManager` (pnpm 11.x) | CI reads the same files (FR-006). Bumps are dedicated changes. The Node 26 bump is a separate change (ARCH §2.1). | — |
| VC-13 | **Fixture convention** (DC-12) | Unversioned layout | Additive. New fixtures add directories. An optional git-history sub-layout (`base/`, `candidate/`) must be recorded before CD-4 (ARCH OQ-8). | — |
| VC-14 | **Design tokens** (DC-11) and **strings keys** (DC-10) | Unversioned internal contracts | Token names are stable so themes can override them. Values may change if the contrast annotations stay ≥ 4.5:1. | — |

---

## Appendix A: Bundle section coverage (web-development)

Every required section is listed below. "Built" means CD-5 implements a contract for it. "Recorded" means it is a provisional direction written to the README and not built (FS FR-090, A-11).

| Bundle section | Status | Contract / location |
|---|---|---|
| api_surface_and_versioning | Built | IC-3, VC-4 |
| auth_and_identity_model | Built (none) and Recorded | CD-5: unauthenticated (FR-045). Recorded (FR-046, ARCH §6.2): uploads use **GitHub Actions OIDC**, a **JWT** (RS256) verified by **JWKS** with `kid`, exact issuer and audience, `exp/nbf/iat` with ≤ 60 s skew, single-use `jti`, and `repository_id`/`repository_owner_id` binding; *or* a project-scoped **API key** stored hashed and revocable. Operator auth is undecided. |
| auth_session_and_csrf_model | Recorded | No session, cookie or state-changing endpoint in CD-5 (FR-082). Target: **session** cookies `HttpOnly; Secure; SameSite=Lax` (or stricter), plus a CSRF token or same-origin custom-header check on every state-changing request. |
| data_model_and_storage | Built (files only) | DC-1…DC-13. No database (FR-055). |
| migration_and_schema_evolution | Built and Recorded | Report: **expand-contract** (VC-1). Future DB: **zero-downtime expand-contract** migrations (add → backfill → switch reads → remove later) (FR-057). |
| background_jobs_and_scheduling | None | §2. CD-2 validation worker deferred (FR-058). |
| event_and_messaging_contract | None | §2 EC-1/EC-2 only |
| rate_limiting_and_quotas | None, codes reserved | `rate-limited` 429 reserved (VC-5). Per-token/per-project limits and caps (10 MiB compressed, about 50 MiB decompressed, 25,000 findings) deferred (FR-059, FR-094). |
| observability_and_slo, observability_stack | Built (logs) and Recorded | Built: DC-7, IC-3.4, INV-P8 SLO. Recorded triad (FR-062, provisional): **OpenTelemetry** SDK for **logs, metrics and traces** → OTLP → **OpenTelemetry Collector** → **Prometheus** (metrics), **Grafana Loki** (logs), **Grafana Tempo** (traces). The scanner emits no telemetry. |
| error_taxonomy_and_codes | Built | IC-3.5 (HTTP 404/405/422/500 plus reserved 400/409/413/422/429), IC-1 and DC-1 (exit 0/1/2, `dogwatch:config-invalid`, `dogwatch:config-not-found`), IC-4 (exit 1) |
| deployment_topology_and_envs, target_environments | Built (local + CI) and Recorded | Local: API `127.0.0.1:8000`, web `127.0.0.1:5173` (dev) / `:4173` (preview) with same-origin `/api` proxy. CI: `ubuntu-24.04`, `macos-15`. Recorded: API as an OCI image, web as static assets same-origin with `/api/v1`. Hosting target undecided (provisional). |
| container_and_orchestration_model | Recorded | No images in CD-5 (INV-R1). API becomes an OCI image. Orchestrator undecided (provisional). |
| infrastructure_as_code_strategy | Recorded | **Terraform** (provisional). Provider is chosen with the hosting target. No IaC in CD-5. |
| ci_cd_pipeline_topology | Built | IC-8, INV-C1–C6 |
| scaling_and_resource_limits | Built | Single API process with 1 worker. Scanner peak RSS ≤ 200 MB (INV-S7). |
| secrets_and_config_management, secrets_and_credentials_management | Built (no secrets) and Recorded | DC-8. Zero `secrets.` references in CI (INV-C1). Recorded (FR-092, provisional): CI → cloud through **GitHub Actions OIDC** federation; runtime secrets in the **cloud-provider secret manager** (e.g. AWS Secrets Manager / GCP Secret Manager); upload API keys stored hashed only. |
| rollout_and_rollback_strategy | Built (revert) and Recorded | CD-5 rollback is a **git revert** of the merge commit on `main`, passing the same CI. Recorded: **blue-green** releases (rollback = switch traffic back to the previous color) plus a **feature-flag kill-switch** for new ingestion behaviour (FR-093). |
| cost_and_resource_budget | Built | USD 0/month infrastructure. ≤ 25 runner-minutes and ≤ 10 min per run (INV-C5). |
| data_retention_and_compliance, compliance_and_audit_trails | Built (none stored) | No user or report data and no personal data. No CI artifacts. Audit trail = git history plus Actions logs. Branch protection requiring the IC-8 statuses is recommended (A-10). Report retention is deferred (CD-2). |
| backup_and_disaster_recovery, disaster_recovery_runbook | Built | GitHub remote is the system of record. Runbook: clone → install pinned prerequisites → `make install` → `make test` green (INV-C7, RTO ≤ 10 min). |
| target_browsers_and_versions | Built | INV-W12, ARCH §6.21 list |
| routing_and_navigation_model | Built | IC-5.2 |
| rendering_strategy | Built | **CSR**: static SPA built by Vite. SSR/SSG/ISR/RSC rejected (FR-071). |
| state_management_and_data_fetching | Built | DC-9, IC-5.1. View-local state only, no global store or query cache. |
| api_consumption_contract | Built | IC-5.1, DC-5, VC-4/VC-6 |
| responsive_breakpoints_and_layout | Built | Compact < 640 px, medium 640–1023 px, wide ≥ 1024 px, mobile-first `min-width` queries. INV-W11. |
| design_tokens_and_theming | Built | DC-11 |
| accessibility_wcag_level | Built | **WCAG 2.2 Level AA**. IC-5.3, INV-W4. |
| i18n_and_locale_strategy | Built | `lang="en"`, DC-10. Scanner output is locale-independent (INV-D1, variant `tr_TR.UTF-8`). |
| performance_budget | Built | INV-W5 (JS ≤ 100 KB, CSS ≤ 20 KB gzip, initial Home route), INV-W10 (LCP/CLS/TBT→INP) |
| analytics_and_consent_model | Built (none) | INV-W7. No cookies, no storage, no third-party scripts, so no consent banner. |
| error_boundary_and_offline_strategy | Built | INV-W8, DC-9. No service worker. |
| asset_pipeline_and_code_splitting | Built | IC-6. Content-hashed assets. Later views use `React.lazy`. |

**DORA metrics.** Lead time for changes is quantified in INV-C6. **Deploy frequency, MTTR and change failure rate** have no CD-5 subject because nothing is deployed (FR-090). They become required SCs in the deployment ticket, measured from the deployment platform's events and the incident tool chosen with the hosting target.

---

## Appendix B: Open gaps (NEEDS CLARIFICATION, non-blocking; defaults applied)

| ID | Gap | Default applied in these contracts | Trace |
|---|---|---|---|
| G-1 | PLAN C7 defines `bench-api` as an httpx script (`scripts/bench_health.py`). ARCH §2.3 selects **Locust** in an opt-in `bench` uv dependency group. | ARCH wins: Locust (IC-2, INV-P8). The plan's script is not built. | ARCH §2.3, §6.9 |
| G-2 | Trailing-slash behaviour is not stated. FastAPI's default 307 redirect contradicts "anything else → 404". | `redirect_slashes=False` (IC-3) | ARCH §6.1 |
| G-3 | `root` values that are absolute or contain `..` are not addressed by FS or ARCH. | No extra rule in CD-5. The V4 existence and nesting checks apply. `root` never reaches the report, so determinism is unaffected. CD-3 implementation should decide. | FS FR-013a, CD-3 §2.2 |
| G-4 | No HTTP deprecation window or overlap period for `/api/v1` after `/api/v2` ships | None defined. To be decided with the first breaking API change (CD-2 ingestion ticket). | FS FR-041 |
| G-5 | ARCH does not name the `vite preview` port | `127.0.0.1:4173` (Vite default), `strictPort` | ARCH §6.11 |
| G-6 | Diagnostic ID for output-write and output == config errors | `dogwatch: error: <message>`, with no catalogue ID | ARCH OQ-1 |
| G-7 | A UTF-8 BOM in `dogwatch.toml`: `tomllib` rejects a leading U+FEFF | Decode with `utf-8` (not `utf-8-sig`). A BOM therefore fails V2 as `config-invalid` invalid TOML. The digest is always over raw bytes. | FS FR-023, edge "non-ASCII content" |
| G-8 | CPython 3.15 ceiling, `policy.path` repo-relative semantics in later versions, real-browser contrast in CI, repository visibility, CD-4 F8e exit code, git-history fixture layout | As ARCH OQ-2, OQ-4, OQ-5, OQ-6, OQ-7, OQ-8 | ARCH §7 |
