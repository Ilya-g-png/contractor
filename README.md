# Dogwatch

Monorepo with four separately runnable areas: the scanner CLI (`scanner/`), the FastAPI
report service (`api/`), the React web app (`web/`) and static fixture projects
(`fixtures/`). Run every command from the repo root. None of them needs credentials.

## Prerequisites

- macOS or Linux only. Windows is not supported.
- `make` (GNU or BSD), uv 0.12.x, Node 24.x (`web/.node-version`), pnpm 11.x
  (`packageManager` in `web/package.json`).
- Scanner CPython: `>=3.11`, supported on 3.11, 3.12, 3.13 and 3.14
  (`scanner/pyproject.toml`). The API needs CPython 3.14 (`api/pyproject.toml`).
  uv finds or downloads a matching interpreter. Set `UV_PYTHON` (for example
  `UV_PYTHON=3.11`) to pick the scanner's version, as CI does.

## Setup

```sh
make install   # install-scanner install-api install-web (uv sync --locked, pnpm install --frozen-lockfile)
```

`make install-scanner`, `make install-api` and `make install-web` set up one area each.

## Run and test each area

| Area | Run | Test | Lint / format |
|---|---|---|---|
| scanner | `make run-scanner` | `make test-scanner` | `make lint-scanner` / `make format-scanner` |
| api | `make run-api` | `make test-api` | `make lint-api` / `make format-api` |
| web | `make run-web` | `make test-web` | `make lint-web` / `make format-web` |
| fixtures | `make regen-fixtures` | `make test-fixtures` | - |

- All areas at once: `make test`, `make lint`, `make format`.
- `make run-scanner` prints the deterministic empty report for
  `fixtures/minimal/dogwatch.toml` to stdout. It is byte-identical to the golden:
  `make -s run-scanner | diff - fixtures/minimal/expected-report.json`.
- `make regen-fixtures` is the only command that rewrites `fixtures/*/expected-report.json`.
- `make build-web` type-checks, builds `web/dist/` and enforces the bundle budget;
  `cd web && pnpm run preview` then serves it.
- `make bench-api` load-tests `/api/v1/health` (needs `make run-api` in another terminal;
  CSVs go to `api/.bench/`). It is not part of `make test` or CI.

## Defaults

- API: `http://127.0.0.1:8000`. Override with `DOGWATCH_API_HOST` and `DOGWATCH_API_PORT`
  (`api/.env.example`).
- Web: dev server `http://127.0.0.1:5173`, preview `http://127.0.0.1:4173`. Both proxy
  `/api` to the API. `VITE_DOGWATCH_API_BASE_URL` defaults to `/api/v1` (`web/.env.example`).
- No secrets are used anywhere. `.env` and `.env.*` are git-ignored.

## CI

`.github/workflows/ci.yml` runs on pull requests and pushes to `main` and calls only the
Makefile targets above. Recommended branch protection on `main` (applied by an admin):
require `scanner (3.11)`, `scanner (3.12)`, `scanner (3.13)`, `scanner (3.14)`, `api`,
`web`, `fixtures (ubuntu-24.04, 3.11)`, `fixtures (ubuntu-24.04, 3.14)`,
`fixtures (macos-15, 3.11)` and `fixtures (macos-15, 3.14)`.

## Recovery runbook

1. `git clone https://github.com/Ilya-g-png/contractor && cd contractor`
2. Install the pinned tools: make, uv 0.12.x, Node 24.x, pnpm 11.x.
3. `make install`
4. `make test`. Green means recovered.

## Direction for later tickets (provisional)

- Auth (provisional): GitHub Actions OIDC JWT (RS256, JWKS-verified) or a hashed project API key.
- Sessions (provisional): HttpOnly SameSite=Lax session cookie plus a CSRF token.
- Database (provisional): zero-downtime expand-contract DB migrations.
- Observability (provisional): OpenTelemetry -> Collector -> Prometheus (metrics), Grafana Loki (logs), Grafana Tempo (traces).
- Infrastructure (provisional): Terraform IaC; API as an OCI image plus web static assets; hosting undecided.
- Secrets (provisional): GitHub Actions OIDC federation plus a cloud-provider secret manager (AWS Secrets Manager / GCP Secret Manager).
- Rollout (provisional): blue-green with a feature-flag kill-switch; CD-5 rollback = git revert of the merge commit.
