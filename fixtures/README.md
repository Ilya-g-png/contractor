# Fixtures

Static fixture projects used by the golden-file harness (`make test-fixtures`).

## Layout

Each fixture is one directory `fixtures/<kebab-name>/`, where `<kebab-name>`
matches `^[a-z0-9]+(-[a-z0-9]+)*$`. It contains:

- `dogwatch.toml` - the policy file; it must pass config validation (V0-V4).
- the source tree it declares, at `<root>/<package>/...`.
- `expected-report.json` - the golden report for that config.

`fixtures/minimal/` declares the package `acme_shop` with root `src` and
holds `src/acme_shop/{__init__,orders,payments}.py`.

## Rules

- Fixtures are static data. They are never installed, imported or executed,
  and no fixture has a `pyproject.toml`, `setup.py` or `requirements*.txt`.
- Golden files change only via `make regen-fixtures`. Never edit
  `expected-report.json` by hand.
- All fixture files use LF line endings (`fixtures/** text eol=lf` in
  `.gitattributes`).
- New fixtures add new directories; existing fixtures keep their layout.

## Pending: git-history fixtures (OQ-8)

Fixtures that need their own git history (for example a baseline at a tag
`base`) are not covered yet. An optional sub-layout such as `base/` and
`candidate/` subdirectories, turned into a temporary repository at test time,
is pending OQ-8 and must be recorded here before such fixtures are added.
