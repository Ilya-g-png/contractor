I'm drafting the spec now. Its contracts follow the CD-2, CD-3, and CD-4 research papers, and the GitHub remote supports using GitHub Actions for CI.

# Draft Specification — CD-5: Bootstrap the monorepo, scanner CLI, API, web app, and deterministic fixture project

## 1. Overview

Dogwatch (the product name used in the CD-2, CD-3 and CD-4 research ADRs) has three parts: a Python scanner/CLI that runs on the customer's side and writes a JSON report, a FastAPI report service that will later ingest those reports, and a TypeScript web dashboard where operators view them. The repository is currently empty. It holds only the platform-managed `.am/` directory, and its remote is `github.com/Ilya-g-png/contractor`. This feature sets up the foundation that later product tickets build on: four separately runnable areas (scanner, API service, web app, checked-in fixture project), one documented command per test suite that needs no credentials, a scanner that writes a byte-for-byte deterministic *empty* report from a minimal fixture configuration, and CI that enforces formatting, linting and focused tests on every change. No product logic is included: no rule evaluation, report ingestion, persistence, authentication or deployment. It matters because every later ticket (CD-3 import-boundary rules, CD-4 OpenAPI adapter, CD-2 ingestion and dashboard) needs a reproducible place to land, with quality gates that already work.

Prior work this draft binds to:
- CD-2, workflow / trust boundary / report lifecycle: `/Users/iliaglushkov/Documents/sandbox/contractor/.am/reports/9c37b285-b35d-4dc2-be1c-2347272422e0-research-paper.md`
- CD-3, import-boundary policy and `dogwatch.toml`: `/Users/iliaglushkov/Documents/sandbox/contractor/.am/reports/7ee72c98-20e3-41ff-9321-386775b7a72e-research-paper.md`
- CD-4, OpenAPI adapter, finding schema and fixture conventions: `/Users/iliaglushkov/Documents/sandbox/contractor/.am/reports/5b28548a-4c88-4600-b7cc-a6df1df95c7b-research-paper.md`

---

## 2. User Scenarios

### US-1 — Contributor bootstraps and tests the repo from a fresh clone (P1)
A new contributor clones the repository, follows the root quickstart, and runs every component's tests locally without credentials.

- **AS-1.1** Given a fresh clone on macOS or Linux with only the documented prerequisites installed, When the contributor runs the documented install command and then the documented "test everything" command, Then all four areas' test suites run and pass, and no prompt for credentials, tokens or secrets appears.
- **AS-1.2** Given a fresh clone, When the contributor runs the documented test command for the scanner area only, Then only the scanner's suite runs and it passes without the API, web or other area's dependencies installed.
- **AS-1.3** Given a fresh clone, When the contributor runs the documented test command for the API area only, Then only the API suite runs and passes without the scanner or web dependencies installed.
- **AS-1.4** Given a fresh clone, When the contributor runs the documented test command for the web area only, Then only the web suite runs and passes without any Python toolchain installed.
- **AS-1.5** Given the root quickstart, When a reader looks for how to run, test, lint and format each area, Then every one of those commands for all four areas is listed in that one document.

### US-2 — Developer produces a deterministic empty report from the fixture project (P1)
A developer runs the scanner against the checked-in minimal fixture configuration and gets a byte-identical empty JSON report every time, on any supported machine.

- **AS-2.1** Given the minimal fixture project, When the developer runs `dogwatch check` with the fixture's `dogwatch.toml`, Then the scanner exits `0` and writes a JSON report whose `findings` array is empty.
- **AS-2.2** Given the same fixture and scanner version, When the scanner runs twice in a row, on different days, in different working directories, or on macOS and on Linux, Then the two output files are byte-identical.
- **AS-2.3** Given the checked-in golden report for the minimal fixture, When the fixture test runs, Then the produced report is byte-identical to the golden report.
- **AS-2.4** Given a fixture configuration path that does not exist, When the scanner runs, Then it exits `2`, writes no report file, and prints a `dogwatch:`-prefixed diagnostic naming the missing path to stderr.
- **AS-2.5** Given a configuration file with invalid TOML syntax, When the scanner runs, Then it exits `2`, writes no report, and prints `dogwatch:config-invalid` with the file and line of the error.

### US-3 — CI enforces quality gates on every change (P2)
A maintainer opens a pull request and CI checks formatting, linting and focused tests for every initialized area.

- **AS-3.1** Given a pull request against `main`, When CI runs, Then it runs format checks, lint checks and tests for the scanner, API and web areas, plus the fixture determinism test, and reports one status per area.
- **AS-3.2** Given a pull request that adds an unformatted file to any one area, When CI runs, Then that area's check fails and the PR shows a failing status.
- **AS-3.3** Given a pull request that breaks the fixture golden report (for example by changing a report field), When CI runs, Then the determinism check fails.
- **AS-3.4** Given a pull request from a fork, When CI runs, Then it completes without access to any repository secrets and still runs every check above.
- **AS-3.5** Given a push to `main`, When CI runs, Then the same checks run as on pull requests.

### US-4 — Developer runs the API service locally (P2)
A developer starts the report service locally and checks that it is alive.

- **AS-4.1** Given the API area's dependencies are installed, When the developer runs the documented start command with no environment variables set, Then the service starts on the documented default local address.
- **AS-4.2** Given the service is running, When a client sends `GET /api/v1/health`, Then the response is `200` with a JSON body containing `status: "ok"`, the service name, and the service version.
- **AS-4.3** Given the service is running, When a client requests an unknown path under `/api/v1/`, Then the response is `404` with an `application/problem+json` body whose `code` is `not-found`.
- **AS-4.4** Given any request, When the service responds, Then the response carries an `X-Request-ID` header (echoed if the client sent one, generated otherwise), and one structured log line with that ID goes to stdout.

### US-5 — Developer runs the web app shell locally (P3)
A developer starts the web app and sees the dashboard shell with the API's status.

- **AS-5.1** Given the web area's dependencies are installed and the API is running, When the developer runs the documented web start command and opens the documented local URL, Then the page shows the product name and an API status indicator reading "API available".
- **AS-5.2** Given the API is *not* running, When the page loads, Then the indicator reads "API unavailable" and the page does not crash or show a blank screen.
- **AS-5.3** Given an unknown client-side route, When the developer navigates to it, Then a "Page not found" view is shown with a link back to the home view.
- **AS-5.4** Given the documented production build command, When it runs, Then it produces static assets, and the build fails if the initial JavaScript budget (FR-074) is exceeded.

---

## 3. Functional Requirements

### 3.1 Repository layout and scaffold

- **FR-001** The repository MUST contain four top-level areas, each in its own directory: the scanner (`scanner/`), the API service (`api/`), the web application (`web/`), and the fixture projects (`fixtures/`).
- **FR-002** Each of the scanner, API and web areas MUST have its own dependency manifest and committed lockfile, and MUST install, run and test without installing any other area's dependencies.
- **FR-003** The scanner and API areas MUST NOT depend on each other's code at install time or at import time.
- **FR-004** The repository root MUST contain a quickstart document (`README.md`) that lists: prerequisites with pinned versions; the install command; for each area, the run, test, lint and format commands; and the "run all tests" command.
- **FR-005** The repository root MUST provide one entry point per action, so that each of these is a single documented command: test scanner, test API, test web, test fixtures, test all, lint all, format all.
- **FR-006** Toolchain versions (Python interpreter, Node.js runtime, package managers) MUST be pinned in files checked into the repository, and CI MUST use the same pins.
- **FR-007** Ignore rules MUST exclude local build output, dependency directories, virtual environments, local env files (`.env`), and the local tool directory `.playwright-mcp/`. CD-5 MUST NOT modify or ignore the platform-managed `.am/` directory.
- **FR-008** Line endings for fixture inputs and golden files MUST be fixed to LF through repository attributes, so their bytes do not change with checkout settings.

### 3.2 Scanner CLI (scaffold only)

- **FR-010** The scanner MUST install a command named `dogwatch` with a `check` subcommand, following the CD-3 command naming (`dogwatch check`).
- **FR-011** `dogwatch check` MUST accept `--config PATH`, defaulting to `./dogwatch.toml`, and `--output PATH`, defaulting to `./dogwatch-report.json`. `--output -` writes to stdout.
- **FR-012** `dogwatch --version` MUST print the scanner name and SemVer version without a leading `v`, following CD-2's `scanner.version` format.
- **FR-013** In CD-5 the scanner MUST accept only the minimal configuration shape: a `[python]` table with one or more `[[python.packages]]` entries, each having `name` and `root` (CD-3 §2.2). Any other table or key MUST be rejected with `dogwatch:config-invalid` and a message saying it is not supported in this version. This prevents a config with rules from silently producing an "empty = clean" report.
- **FR-014** For a valid minimal configuration the scanner MUST write a report (§3.3) with an empty `findings` array and exit `0`. It MUST NOT parse, import or run any code in the fixture project, which keeps the CD-3 parse-only and CD-2 no-execution posture.
- **FR-015** Scanner exit codes MUST be: `0` = report written; `1` = reserved for "gate failed" (never emitted in CD-5); `2` = error (usage error, config not found, config invalid, output not writable). On exit `2` no report file may be created, and a partial file must not be left behind.
- **FR-016** Scanner diagnostics MUST go to stderr in the form `dogwatch:<diagnostic-id>: <message>`, using CD-3's reserved `dogwatch:` namespace. CD-5 uses `dogwatch:config-invalid` (from CD-3 §2.12) and adds one new diagnostic, `dogwatch:config-not-found`. The new one is flagged as new ground and must be added to the CD-3 diagnostic catalogue.

### 3.3 Report contract (bootstrap envelope) — *data model*

- **FR-020** The report MUST be a single UTF-8 JSON object with these top-level fields: `schema_version`, `scanner` (`name`, `version`), `policy` (`path`, `digest.sha256`), and `findings` (an array, empty in CD-5). Field names follow CD-2 §2.3. [NEEDS CLARIFICATION: CD-2 §2.3 marks `commit_sha`, `object_format`, `dirty`, `base_sha`, `evaluation_date`, `scan_started_at`, `scan_finished_at` and `report_id` as *required*, but timestamps, report IDs and the monorepo commit SHA change on every run or commit, which conflicts with this ticket's "deterministic" criterion. Should the CD-5 report (a) be a pre-1.0 envelope that leaves out all volatile provenance fields, which arrive with the provenance/upload ticket (the proposed default), or (b) already carry the full CD-2 provenance block, with determinism coming from explicit override flags (fixed timestamps, `--today`, a fixed `report_id`) and the git fields set to `null`? Related: CD-4 §2.5 names its envelope field `schema` while CD-2 uses `schema_version`. Which name is canonical? Default: `schema_version`, because CD-2 owns the report lifecycle.]
- **FR-021** `schema_version` MUST be `"0.1"` for CD-5. A major version of `0` means pre-release and is never accepted by a future ingestion endpoint's major-version allow-list (CD-2 §2.3).
- **FR-022** `policy.path` MUST be the config file's path relative to the directory that contains it (so `"dogwatch.toml"`). It MUST NOT contain absolute paths, user names, hostnames or any other machine-dependent value.
- **FR-023** `policy.digest.sha256` MUST be the lowercase hex SHA-256 of the config file's raw bytes (CD-2 §2.3).
- **FR-024** Serialization MUST be canonical: object keys sorted lexicographically, two-space indentation, `\n` line endings, exactly one trailing newline, no byte-order mark, and non-ASCII characters emitted literally as UTF-8. Identical inputs (config bytes and scanner version) MUST give byte-identical output regardless of wall-clock time, timezone, locale, working directory, environment variables or operating system.
- **FR-025** A JSON Schema for report `schema_version` `0.1` MUST be checked in under the scanner area, with `additionalProperties: false` at every object level (CD-2 §2.4). Scanner tests MUST validate the produced report against it.
- **FR-026** The report MUST NOT be able to carry source code, file contents or snippets (CD-2 §2.2). The schema has no field for them.

### 3.4 Fixture project

- **FR-030** `fixtures/` MUST contain a minimal fixture project, `fixtures/minimal/`, made of a `dogwatch.toml` that declares one package (FR-013), a tiny Python package under the declared `root` with at least two modules, and the golden report `expected-report.json`.
- **FR-031** The fixture project MUST be static data. It is never installed, imported or run by any test or tool.
- **FR-032** A fixture test MUST run `dogwatch check` against `fixtures/minimal/dogwatch.toml`, compare the output byte-for-byte with `expected-report.json`, and on mismatch print a readable diff.
- **FR-033** The fixtures area MUST have a documented layout convention (one directory per fixture, holding its config and golden output), so later CD-3 and CD-4 fixture matrices (for example CD-4 F1–F8e) can be added without restructuring.
- **FR-034** Updating golden files MUST be an explicit, documented action (for example a dedicated regenerate command). The test MUST NOT rewrite golden files during a normal run.

### 3.5 API surface and versioning

- **FR-040** The API service MUST expose `GET /api/v1/health`, returning `200` with `{"status": "ok", "service": "dogwatch-api", "version": "<semver>"}`.
- **FR-041** All product endpoints MUST live under the URL path prefix `/api/v1/`. A breaking change to any endpoint requires a new major prefix (`/api/v2/`), and additive changes (new optional response fields, new endpoints) stay within `v1`.
- **FR-042** The service MUST serve its machine-readable OpenAPI 3.1 description at `/api/v1/openapi.json`.
- **FR-043** CD-5 MUST NOT add any ingestion, upload, storage or report-reading endpoint. Those belong to the CD-2 implementation ticket.
- **FR-044** With no environment variables set, the service MUST bind only to the loopback interface (`127.0.0.1`) on a documented default port.

### 3.6 Auth and identity model

- **FR-045** In CD-5, `GET /api/v1/health` and `GET /api/v1/openapi.json` are the only endpoints, and both are unauthenticated. CD-5 MUST NOT add any login, session, token or credential handling.
- **FR-046** The quickstart MUST record the auth model that later tickets will implement, as decided in CD-2 §2.2: report uploads are authenticated with **GitHub Actions OIDC (JWT, RS256, verified via JWKS, audience-bound)**, or with a **project-scoped upload API key** stored hashed and revocable, for local and non-GitHub CI uploads. Operator (dashboard) authentication is not yet decided and is out of scope for CD-5.

### 3.7 Error taxonomy and codes

- **FR-050** API error responses MUST use `application/problem+json` (RFC 9457) with `type`, `title`, `status`, `detail`, and a stable machine-readable `code`.
- **FR-051** CD-5 MUST define and test these API codes: `not-found` (404), `method-not-allowed` (405), `validation-failed` (422), and `internal-error` (500, with no stack trace or internal detail in the body). Reserved for later tickets, from CD-2 §2.4: `payload-too-large` (413), `schema-invalid` (400), `idempotency-conflict` (422), `in-flight` (409), `rate-limited` (429).
- **FR-052** Scanner error categories MUST map to exit codes as in FR-015 and use the diagnostic IDs in FR-016.

### 3.8 Data model, storage, migration and schema evolution

- **FR-055** CD-5 MUST NOT add a database or any persistent server-side storage. The API is stateless.
- **FR-056** Report schema evolution MUST follow **expand-contract**. Within one major `schema_version`, changes are additive only: new optional fields, which consumers ignore if unknown, are added first, and removal or renaming happens only in a new major after consumers have moved. Each published `schema_version` keeps its own checked-in JSON Schema file, so old reports can still be validated.
- **FR-057** The quickstart MUST record that future database schema changes, once persistence arrives with CD-2 ingestion, follow zero-downtime expand-contract migrations: add, backfill, switch reads, then remove in a later release.

### 3.9 Background jobs, events and messaging

- **FR-058** CD-5 MUST NOT add background workers, schedulers, queues or event publishing. CD-2's isolated validation worker and its `pending`/`complete`/`failed` status resource are deferred to the ingestion ticket.

### 3.10 Rate limiting and quotas

- **FR-059** CD-5 MUST NOT add rate limiting. Per-token and per-project rate limits and per-project report caps (CD-2 §2.4) are deferred to the ingestion ticket. The `rate-limited` (429) code is reserved in FR-051.

### 3.11 Observability (service and stack)

- **FR-060** The API MUST write one structured JSON log line to stdout per request, containing timestamp (RFC 3339 UTC), level, request ID, method, route template, status and duration in ms. It MUST NOT log request bodies, headers carrying credentials, or query strings.
- **FR-061** The API MUST accept an incoming `X-Request-ID` (at most 128 printable ASCII characters; otherwise replaced) or generate one, echo it in the response, and include it in every log line for that request.
- **FR-062** CD-5 MUST NOT add metrics or tracing exporters. The quickstart MUST record the target observability stack for later tickets: **OpenTelemetry** SDK instrumentation for **logs, metrics and traces**, exported over OTLP to an **OpenTelemetry Collector**, which forwards metrics to **Prometheus**, logs to **Grafana Loki** and traces to **Grafana Tempo**. These are provisional defaults until the hosting target is decided (see FR-090).
- **FR-063** The scanner MUST NOT emit telemetry of any kind. It runs on customer machines and makes no network calls (CD-2 §2.4).

### 3.12 Web application

**Target browsers and versions**
- **FR-070** The web app MUST declare its supported browsers in one checked-in configuration: the latest two stable major versions of Chrome, Edge, Firefox and Safari (macOS and iOS). The production build MUST target exactly that set.

**Rendering strategy**
- **FR-071** The web app MUST use **client-side rendering (CSR)** as a statically built single-page application. Reasons: the dashboard is an authenticated operator tool with no SEO requirement, and static assets need no server-side runtime, so the API remains the only server-side process.

**Routing and navigation**
- **FR-072** The web app MUST have exactly two views in CD-5: Home (`/`) and a Not Found view for any other path, with a link back to Home. Routes use URL paths (history-based), not hash fragments.

**State management, data fetching and API consumption**
- **FR-073** The Home view MUST request `GET /api/v1/health` once on load and show one of three states: "Checking API…", "API available" or "API unavailable". The request times out after 5 seconds, and timeouts, network errors and non-2xx responses all show "API unavailable". CD-5 MUST NOT add a global state store. Server data is held in view-local state.
- **FR-073a** The API base URL MUST be same-origin `/api/v1` by default. In local development the web dev server proxies `/api` to the API's documented default address. The base URL can be overridden at build time through one documented variable. The web app MUST treat API responses as untrusted text and render them only as plain text (CD-2 §2.4).

**Asset pipeline, code splitting and performance budget**
- **FR-074** The production build MUST emit content-hashed static assets. The **initial JavaScript for the Home route MUST be ≤ 100 KB gzip**, and the **total CSS ≤ 20 KB gzip**. The build check fails when either is exceeded. CD-5 needs no route-level code splitting (two tiny views). Later views MUST be lazy-loaded so the Home budget holds.
- **FR-075** The built `index.html` MUST contain no inline `<script>` and no inline event handlers, so the app runs under a strict Content Security Policy of `default-src 'self'` (CD-2 §2.4). The app MUST NOT load third-party scripts, fonts or styles from external origins.

**Error boundary and offline strategy**
- **FR-076** The web app MUST wrap the view tree in a top-level error boundary. An uncaught render error shows a static "Something went wrong" message with a reload action, not a blank page. CD-5 MUST NOT add offline support or a service worker. Losing the network only affects the API status indicator.

**Responsive breakpoints and layout**
- **FR-077** The layout MUST work from 320 CSS px wide upward without horizontal scrolling (WCAG 2.2 SC 1.4.10 Reflow), with two breakpoints: compact (< 640 px), medium (640–1023 px) and wide (≥ 1024 px).

**Design tokens and theming**
- **FR-078** Color, spacing, typography and radius values MUST be defined once as named design tokens (CSS custom properties) and referenced everywhere else. Hard-coded values outside the token file are lint errors where the tooling supports that check. CD-5 ships a light theme only. The tokens are structured so a dark theme can override them later.

**Accessibility**
- **FR-079** The web app MUST meet **WCAG 2.2 Level AA**. It needs a document `lang`, a single `h1`, landmark regions (`header`, `main`), visible focus indicators, text contrast ≥ 4.5:1 (SC 1.4.3), and an API status indicator announced to assistive technology through a polite live region (SC 4.1.3 Status Messages). Web tests MUST run automated axe-core checks on the Home and Not Found views.

**i18n and locale**
- **FR-080** The CD-5 UI is English only (`lang="en"`), with no locale switching. User-visible strings MUST be kept in one module per area rather than spread through the view code, so a later i18n layer can extract them.

**Analytics and consent**
- **FR-081** The web app MUST NOT include analytics, tracking, or any other third-party script, and MUST NOT set cookies or write to local or session storage. No consent banner is needed because nothing is collected.

**Auth session and CSRF**
- **FR-082** CD-5 has no session, cookies or state-changing endpoints, so no CSRF protection is needed yet. The quickstart MUST record that once operator login exists, sessions use `HttpOnly`, `Secure`, `SameSite=Lax` (or stricter) cookies, and every state-changing request requires a CSRF token or a same-origin custom-header check. The exact mechanism belongs to the auth ticket.

### 3.13 CI/CD pipeline topology

- **FR-085** CI MUST run on **GitHub Actions** (the repository's remote is GitHub) for every pull request targeting `main` and every push to `main`.
- **FR-086** CI MUST have one job per area: **scanner** (format check, lint, type check, tests including the report-schema test), **api** (format check, lint, type check, tests), **web** (format check, lint, type check, tests including the axe checks, production build with the budget check from FR-074), and **fixtures** (the determinism test from FR-032 on Linux *and* macOS runners). The jobs run in parallel and each reports its own status.
- **FR-087** CI MUST install dependencies strictly from the committed lockfiles and fail if a lockfile is out of date with its manifest.
- **FR-088** The CI workflow MUST declare `permissions: contents: read` at the top level, use no repository secrets, never use the `pull_request_target` trigger (CD-2 §2.5), pin every third-party action to a full commit SHA, and cancel superseded runs for the same branch or PR.
- **FR-089** CI MUST run the same commands documented in the quickstart (FR-005), so passing locally and passing in CI mean the same thing.

### 3.14 Target environments, deployment topology, containers and IaC

- **FR-090** CD-5 has two target environments only: **local development** (macOS and Linux) and **CI** (GitHub-hosted runners). CD-5 MUST NOT provision staging or production, build or publish container images, or add infrastructure-as-code. The quickstart MUST record the intended direction: infrastructure defined in **Terraform**, and API and web delivered as OCI container images and static assets respectively. [NEEDS CLARIFICATION: Which hosting target (cloud provider or platform) will Dogwatch run on? It decides the Terraform provider, the secret manager (FR-092), the observability backends (FR-062) and the container orchestration model. CD-5 does not depend on the answer, but every deploy-related default here is provisional until it is chosen.]

### 3.15 Secrets, credentials and configuration

- **FR-091** CD-5 MUST need no secrets, either locally or in CI. All configuration has safe defaults. The API reads optional settings only from environment variables with the prefix `DOGWATCH_API_`. A committed `.env.example` documents each one with non-secret example values, and real `.env` files are git-ignored.
- **FR-092** The quickstart MUST record the secrets model for later tickets: CI authenticates to cloud resources through **GitHub Actions OIDC** federation (no long-lived cloud keys in repository secrets), and runtime secrets live in the hosting platform's **cloud-provider secret manager** (for example AWS Secrets Manager / GCP Secret Manager, chosen by the FR-090 clarification). Upload API keys are stored only as hashes (CD-2 §2.2).

### 3.16 Rollout and rollback

- **FR-093** Because CD-5 deploys nothing, rollback means reverting the merge commit on `main`. That revert MUST pass the same CI checks. The quickstart MUST record that later deployments use **blue-green** releases with traffic switched back to the previous color as the rollback mechanism, plus a **feature-flag kill-switch** for new ingestion behaviour.

### 3.17 Scaling, cost, retention, backup/DR, compliance and audit

- **FR-094** *Scaling and resource limits:* the API runs as a single local process in CD-5. The scanner MUST run on the minimal fixture using ≤ 200 MB peak resident memory. CD-2's ingestion size and structure limits (10 MiB compressed, about 50 MiB decompressed, 25,000 findings) are deferred to the ingestion ticket.
- **FR-095** *Cost and resource budget:* CD-5 incurs no infrastructure cost (USD 0/month). A CI run MUST finish in ≤ 10 minutes wall-clock and use ≤ 25 runner-minutes across all jobs. The macOS fixture job is limited to the fixture determinism test because of its higher per-minute cost.
- **FR-096** *Data retention:* CD-5 stores no user or report data. CI keeps no build artifacts beyond GitHub's default log retention. The report retention period is an open CD-2 question, deferred to the ingestion ticket.
- **FR-097** *Backup and disaster recovery:* the GitHub remote is the system of record. The documented recovery runbook is: re-clone, install from the lockfiles, run "test all". All required state is in the repository, and nothing outside it needs backing up.
- **FR-098** *Compliance and audit trail:* CD-5 processes no personal data. The audit trail is git history plus GitHub Actions run logs. The quickstart MUST recommend branch protection on `main` that requires all FR-086 checks to pass. Applying it is a repository-admin action outside the code change.

---

## 4. Key Entities

| Entity | Attributes | Relationships / notes |
|---|---|---|
| **Area** | name (`scanner`, `api`, `web`, `fixtures`), directory, dependency manifest + lockfile (not for `fixtures`), run/test/lint/format commands | Each area is independently installable (FR-002). CI has one job per area (FR-086). |
| **Policy file** (`dogwatch.toml`) | raw bytes, SHA-256 digest, `[python]` table, `[[python.packages]]` entries (`name`, `root`) | CD-3 §2.1–2.2 shape, restricted to the minimal subset in CD-5 (FR-013). Referenced by Report `policy`. |
| **Report** (bootstrap envelope) | `schema_version` (`"0.1"`), `scanner.name`, `scanner.version`, `policy.path`, `policy.digest.sha256`, `findings[]` (empty) | Produced by `dogwatch check` from one Policy file. Validated by the Report JSON Schema. Volatile CD-2 provenance fields are pending the FR-020 clarification. |
| **Report JSON Schema** | `schema_version` it governs, strict `additionalProperties: false` | One file per published `schema_version` (FR-056). |
| **Fixture project** | directory name, Policy file, static Python package, golden report | `fixtures/minimal/` in CD-5. Later CD-3 and CD-4 fixtures follow the same convention (FR-033). |
| **Golden report** | expected bytes | Compared byte-for-byte with the Report produced from its Fixture (FR-032). Changed only by the explicit regenerate action (FR-034). |
| **Diagnostic** | id (`dogwatch:<kebab-id>`), message, exit code | `config-invalid` (CD-3), `config-not-found` (new). |
| **Health status** | `status`, `service`, `version` | Returned by `GET /api/v1/health`. Consumed by the web Home view. |
| **Problem detail** | `type`, `title`, `status`, `detail`, `code` | Every API error (FR-050/051). |
| **API status indicator** (web view state) | states: `checking` → `available` \| `unavailable` | Starts as `checking` on load. Moves to `available` on 2xx with `status: "ok"`, otherwise (including timeout) to `unavailable`. Terminal until the page reloads. |
| **Scanner run outcome** | `success` (exit 0, report written) \| `error` (exit 2, no report) | `gate-failed` (exit 1) is reserved and unreachable in CD-5. |
| **CI check** | area, state `queued` → `running` → `passed` \| `failed` \| `cancelled` | `cancelled` only when a newer run supersedes it (FR-088). |

---

## 5. Success Criteria

- **SC-001 — Fresh-clone time to green.** From a fresh clone with only the documented prerequisites, install plus "test all" finishes successfully in ≤ 10 minutes, with 0 credential prompts. *Measured* by timing the quickstart steps on a clean GitHub-hosted Ubuntu runner and on one clean macOS machine at acceptance.
- **SC-002 — Report determinism.** 20 out of 20 runs of `dogwatch check` on `fixtures/minimal` (10 on Linux, 10 on macOS, spread across different working directories, `TZ` values and locales) produce output whose SHA-256 equals the golden report's. *Measured* by the CI fixture job on both OSes plus a scripted 10-run loop per OS at acceptance.
- **SC-003 — Area isolation.** 3 out of 3 test suites (scanner, API, web) pass when only that area's dependencies are installed. *Measured* by running each area's test command in a separate clean environment at acceptance, which is the same as the parallel CI jobs.
- **SC-004 — Gates catch violations.** 3 out of 3 deliberately seeded formatting violations (one per code area) and 1 out of 1 seeded golden-report change each turn the matching CI check red. *Measured* once at acceptance with a throwaway PR per seeded defect.
- **SC-005 — CI lead time (DORA "lead time for changes", pre-deployment proxy).** Median time from a push to `main` until all CI checks are green is ≤ 10 minutes, and p95 is ≤ 15 minutes, over the first 30 days after merge. *Measured* from GitHub Actions run start/finish timestamps through the Actions API.
- **SC-006 — API latency.** `GET /api/v1/health` has **p95 ≤ 50 ms and p99 ≤ 100 ms at 20 concurrent clients sustained for 60 seconds**, with 0 errors, on a GitHub-hosted Ubuntu runner against a local single-process instance. *Measured* with an HTTP load generator run once at acceptance, recording the percentile report.
- **SC-007 — Web JS budget.** Initial JavaScript for the Home route is ≤ 100 KB gzip, and CSS is ≤ 20 KB gzip. *Measured* automatically by the web CI job's build size check on every run.
- **SC-008 — Core Web Vitals (lab).** On the production build served locally, the Home view reaches **LCP ≤ 2.5 s**, **CLS ≤ 0.1** and Total Blocking Time ≤ 200 ms. TBT stands in for **INP ≤ 200 ms**, because CD-5 has no user interactions to measure in the field. *Measured* with Lighthouse (mobile preset, simulated throttling), median of 3 runs at acceptance.
- **SC-009 — Accessibility.** 0 axe-core violations for WCAG 2.0/2.1/2.2 A and AA rule tags on the Home and Not Found views. *Measured* by the automated axe checks in the web test suite on every CI run.
- **SC-010 — Quickstart completeness and brevity.** The root quickstart lists 100% of the commands in FR-005, plus per-area run commands, and is ≤ 80 lines long. *Measured* by a checklist review at acceptance (command list against FR-005, `wc -l`).
- **SC-011 — No credentials anywhere.** The CI workflow uses 0 repository secrets, and every CI run on a fork PR passes the same checks as an in-repo PR. *Measured* by inspecting the workflow for `secrets.` references, plus one fork-PR run at acceptance.

---

## 6. Edge Cases

- **Missing config:** `--config` points to a path that does not exist. Exit `2`, `dogwatch:config-not-found`, no report written.
- **Malformed TOML:** exit `2`, `dogwatch:config-invalid` with file and line, no report.
- **Unsupported config content:** valid TOML that contains rule tables (`[[python.rules]]`), waivers, `[openapi]`, or unknown keys. Exit `2`, `dogwatch:config-invalid` ("not supported in this version"). An empty report must never be written for a config the scanner can't evaluate (FR-013).
- **Empty config file or no `[[python.packages]]`:** exit `2`, `dogwatch:config-invalid`.
- **Output path not writable** (directory missing, permission denied): exit `2`, and no partial file is left at the target path.
- **Output path equals the config path:** rejected with exit `2` before anything is written.
- **Non-ASCII content in the config** (for example comments): the digest is computed over raw bytes, and the output stays deterministic.
- **CRLF checkout of fixture files:** blocked by repository attributes (FR-008). If CRLF bytes appear anyway, the digest changes and the golden test fails visibly rather than silently.
- **Scanner version bump:** the golden report changes (`scanner.version`). Regenerating it with the explicit command (FR-034) is part of the release change.
- **Determinism hazards:** different `TZ`, `LANG`/`LC_ALL`, working directory, home directory, hostname, Python hash seed, or filesystem iteration order must not change the output (FR-024).
- **API port already in use:** startup fails with a clear message naming the port and the override variable. No silent fallback to another port.
- **Malformed or oversized `X-Request-ID`:** replaced with a generated ID, never echoed raw into logs (log injection).
- **Unexpected server exception:** `500 internal-error` problem detail without a stack trace. The full error is logged with the request ID.
- **Web: API slow (> 5 s):** shows "API unavailable" once the timeout fires. A late success does not flip the state.
- **Web: API returns non-JSON or `status` ≠ `"ok"`:** shows "API unavailable".
- **Web: deep link to an unknown route under static hosting:** the Not Found view is shown, and the dev/preview server serves `index.html` for unknown paths.
- **Web: JavaScript render error:** the top-level error boundary fallback is shown (FR-076).
- **Fork PRs:** CI runs with a read-only token and no secrets, and must still pass (SC-011).
- **Lockfile drift:** a manifest edited without updating the lockfile fails CI install (FR-087).
- **Windows contributors:** not supported in CD-5 (Assumption A-3). Commands may fail, and the quickstart says so.

---

## 7. Assumptions

- **A-1 — Product and command names.** The product is "Dogwatch", the CLI command is `dogwatch`, and the policy file is `dogwatch.toml`, as used consistently in the CD-2, CD-3 and CD-4 papers, even though the repository is named `contractor`. [NEEDS CLARIFICATION: Confirm that "Dogwatch" / `dogwatch` / `dogwatch.toml` are the final public names. They become the CLI, config-file and package contracts every later ticket binds to, and renaming them after release is a breaking change.]
- **A-2 — Stack baseline (greenfield decisions; provisional until the architect stage confirms).**
  - Python areas: one pinned CPython version; `uv` for environments and lockfiles; `ruff` for formatting and linting; `mypy` (strict) for type checking; `pytest` for tests.
  - API: FastAPI on an ASGI server.
  - Web: TypeScript in strict mode; React built with Vite as a static SPA; Vitest with Testing Library and axe-core for tests; ESLint for linting and Prettier for formatting; `pnpm` with a committed lockfile.
  - Root task runner: `make`, which is preinstalled on macOS and Linux.
- **A-3 — Supported developer platforms.** macOS and Linux. Windows is out of scope for CD-5.
- **A-4 — "Without external credentials"** means no account, token or secret. Downloading packages from public registries (PyPI, npm) during install is allowed. Fully offline installs are not required.
- **A-5 — "Focused tests"** means each CI job runs only its own area's tests, all jobs run on every change, and no path filtering is applied, because the suites are small enough that path-filtering complexity isn't justified yet.
- **A-6 — Fixture location.** Fixture projects live inside the monorepo (`fixtures/`), so their git provenance is the monorepo's. That is one reason the CD-5 report leaves out git-derived fields (FR-020 default).
- **A-7 — No product logic.** Rule evaluation (CD-3), the OpenAPI adapter (CD-4), ingestion, persistence, `dogwatch upload`, the published GitHub Action, and authentication (CD-2) are all out of scope. CD-5 only reserves names, codes and conventions for them.
- **A-8 — Web ↔ API coupling.** The web shell calls only the health endpoint, to prove the same-origin consumption contract. Each still runs and tests independently: web tests stub the API.
- **A-9 — Budgets and thresholds** (100 KB JS, 20 KB CSS, 50 ms p95, 10-minute CI, 80-line quickstart) are proposed defaults sized for an empty shell. They are not sourced limits, and the owner may tighten them.
- **A-10 — Branch protection** is recommended but applied by a repository admin outside this change (FR-098).
- **A-11 — Deferred-only bundle topics.** Background jobs, messaging, rate limiting, persistence, deployment, IaC, secrets managers, observability backends, rollout, backup and retention are recorded as direction (FRs 057–098), not built, because the ticket covers foundations only. The deploy-related choices (Terraform, OpenTelemetry → Prometheus/Loki/Tempo, cloud-provider secret manager, blue-green) are provisional until the hosting question in FR-090 is answered.
- **A-12 — Open prior-research questions not resolved here:** the report retention period, the GHES/self-managed GitLab targets (CD-2 §5), and the inconsistent stale-waiver severity between CD-3 and CD-4. None affects CD-5.
