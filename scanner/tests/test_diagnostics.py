import dataclasses
import re
import typing

import pytest

from dogwatch.diagnostics import (
    CONFIG_INVALID,
    CONFIG_NOT_FOUND,
    EXCLUDE_UNMATCHED,
    EXIT_ERROR,
    EXIT_GATE_FAILED,
    EXIT_OK,
    SOURCE_SYNTAX_INVALID,
    Diagnostic,
    DogwatchError,
    Severity,
    render,
    render_diagnostics,
)

LINE = re.compile(r"^dogwatch:(config-invalid|config-not-found): .+$")
KEBAB = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")


def _diagnostic(id: str, message: str, severity: Severity = "error") -> Diagnostic:
    return Diagnostic(source="dogwatch", id=id, severity=severity, message=message)


def test_render_two_diagnostics_one_line_each_with_trailing_newline() -> None:
    err = DogwatchError(
        (
            _diagnostic("config-not-found", "dogwatch.toml does not exist"),
            _diagnostic("config-invalid", "dogwatch.toml: package 'a' is nested"),
        )
    )

    out = render(err)

    assert out.endswith("\n")
    assert not out.endswith("\n\n")
    lines = out[:-1].split("\n")
    assert len(lines) == 2
    assert all(LINE.match(line) for line in lines)
    assert lines == [
        "dogwatch:config-not-found: dogwatch.toml does not exist",
        "dogwatch:config-invalid: dogwatch.toml: package 'a' is nested",
    ]


def test_render_diagnostics_of_empty_sequence_is_empty() -> None:
    assert render_diagnostics([]) == ""
    assert render_diagnostics(()) == ""


def test_render_diagnostics_renders_one_line_per_diagnostic() -> None:
    diagnostics = [
        _diagnostic(SOURCE_SYNTAX_INVALID, "src/acme/x.py:3: invalid syntax"),
        Diagnostic("openapi", "openapi-tool-failed", "warning", "oasdiff — exit 3"),
        _diagnostic(CONFIG_INVALID, "python must be a table", "info"),
    ]

    assert render_diagnostics(diagnostics) == "".join(
        f"dogwatch:{d.id}: {d.message}\n" for d in diagnostics
    )
    assert render_diagnostics(diagnostics).splitlines()[1] == (
        "dogwatch:openapi-tool-failed: oasdiff — exit 3"
    )


def test_render_delegates_to_render_diagnostics() -> None:
    err = DogwatchError(
        (
            _diagnostic(CONFIG_NOT_FOUND, "dogwatch.toml does not exist"),
            _diagnostic(EXCLUDE_UNMATCHED, "python.exclude[0] 'x' matches no file"),
        )
    )

    assert render(err) == render_diagnostics(err.diagnostics)


def test_diagnostic_has_exactly_the_four_fields() -> None:
    assert [f.name for f in dataclasses.fields(Diagnostic)] == [
        "source",
        "id",
        "severity",
        "message",
    ]
    hints = typing.get_type_hints(Diagnostic)
    assert hints["id"] is str
    assert typing.get_args(hints["severity"]) == ("error", "warning", "info")
    with pytest.raises(dataclasses.FrozenInstanceError):
        _diagnostic("config-invalid", "x").id = "other"  # type: ignore[misc]


def test_scanner_diagnostic_id_constants() -> None:
    ids = (CONFIG_NOT_FOUND, CONFIG_INVALID, EXCLUDE_UNMATCHED, SOURCE_SYNTAX_INVALID)

    assert ids == (
        "config-not-found",
        "config-invalid",
        "exclude-unmatched",
        "source-syntax-invalid",
    )
    assert all(KEBAB.match(i) for i in ids)


def test_dogwatch_error_requires_at_least_one_diagnostic() -> None:
    with pytest.raises(ValueError):
        DogwatchError(())


def test_exit_codes() -> None:
    assert (EXIT_OK, EXIT_GATE_FAILED, EXIT_ERROR) == (0, 1, 2)
