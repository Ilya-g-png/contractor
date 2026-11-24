# OpenAPI fixture matrix

Git-history fixtures for the OpenAPI adapter, run by
`tests/openapi/test_fixture_matrix.py` (marker `golden`).

## Layout

Each case is one directory `<case-name>/` containing:

- `base/` - the tree committed as the baseline in a temporary local Git
  repository and tagged `baseline`.
- `candidate/` - the tree that replaces `base/` in the working copy.
- `dogwatch.toml` - the policy; it declares the `pets-api` contract at
  `api/openapi.yaml` and any severity or waiver entries.
- `case.json` - the matrix `category`, an optional `baseline_ref` (default
  `baseline`), the `tool` behavior of the controlled oasdiff substitute
  (`null` when oasdiff must not run), and the expected exit code, finding
  check IDs and diagnostic IDs.
- `expected-report.json` - the pinned canonical report.
- `expected-invocation.json` - present only when oasdiff runs; the pinned
  argv, environment, limits and observed input permissions, with the private
  temporary directory shown as `{private}` and the substitute as
  `{substitute}`.

The harness commits with a fixed identity and date, so baseline commit IDs
and therefore the expected bytes are reproducible. Every case runs the public
`dogwatch check` command twice against a freshly materialized repository.

## Controlled substitute

oasdiff is replaced by `tests/openapi/oasdiff_substitute.py`, run through the
real runner. It records what it observes and then emits the changelog records
(or failure behavior) declared in `case.json`. Those records are reviewed
stand-ins for oasdiff v1.39.0 changelog JSON; no network, external reference
or mutable release is used. The timeout case declares `deadline_seconds`,
which shortens only the harness's wall-clock wait; the pinned invocation still
records the 60-second deadline the runner requested.

## Updating expected outputs

Tests never write expected artifacts. After a deliberate change to a case,
the oasdiff pin or normalization, regenerate and review the diff:

    cd scanner && uv run --locked python -m tests.openapi.regenerate_fixture_matrix
