# Root task contract (IC-2). Each recipe runs in exactly one area directory
# and calls only that area's toolchain. Portable across GNU make and BSD make.

BENCH_OUTDIR ?= .bench

.PHONY: install install-scanner install-api install-web \
    test test-scanner test-fixtures test-api test-web \
    lint lint-scanner lint-api lint-web \
    format format-scanner format-api format-web \
    build-web run-scanner run-api run-web regen-fixtures bench-api

install: install-scanner install-api install-web

install-scanner:
	cd scanner && uv sync --locked

install-api:
	cd api && uv sync --locked

install-web:
	cd web && pnpm install --frozen-lockfile

test: test-scanner test-fixtures test-api test-web

test-scanner:
	cd scanner && uv run --locked pytest -m "not golden"

test-fixtures:
	cd scanner && uv run --locked pytest -m golden

test-api:
	cd api && uv run --locked pytest

test-web: install-web
	cd web && pnpm run test

lint: lint-scanner lint-api lint-web

lint-scanner:
	cd scanner && uv run --locked ruff format --check . && uv run --locked ruff check . && uv run --locked mypy

lint-api:
	cd api && uv run --locked ruff format --check . && uv run --locked ruff check . && uv run --locked mypy

lint-web: install-web
	cd web && pnpm run lint

format: format-scanner format-api format-web

format-scanner:
	cd scanner && uv run --locked ruff format . && uv run --locked ruff check --fix .

format-api:
	cd api && uv run --locked ruff format . && uv run --locked ruff check --fix .

format-web: install-web
	cd web && pnpm run format

build-web: install-web
	cd web && pnpm run build

run-scanner:
	cd scanner && uv run --locked dogwatch check --config ../fixtures/minimal/dogwatch.toml --output -

run-api:
	cd api && uv run --locked dogwatch-api

run-web: install-web
	cd web && pnpm run dev

regen-fixtures:
	cd scanner && uv run --locked python -m tests.golden.regenerate

bench-api:
	cd api && mkdir -p $(BENCH_OUTDIR) && uv run --locked --group bench locust -f scripts/locustfile.py --headless -u 20 -r 20 -t 60s --host http://127.0.0.1:8000 --csv $(BENCH_OUTDIR)/health
