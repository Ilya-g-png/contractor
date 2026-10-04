import re

import pytest

from dogwatch.diagnostics import (
    EXIT_ERROR,
    EXIT_GATE_FAILED,
    EXIT_OK,
    Diagnostic,
    DogwatchError,
    render,
)

LINE = re.compile(r"^dogwatch:(config-invalid|config-not-found): .+$")


def test_render_two_diagnostics_one_line_each_with_trailing_newline() -> None:
    err = DogwatchError(
        (
            Diagnostic("config-not-found", "dogwatch.toml does not exist"),
            Diagnostic("config-invalid", "dogwatch.toml: package 'a' is nested"),
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


def test_dogwatch_error_requires_at_least_one_diagnostic() -> None:
    with pytest.raises(ValueError):
        DogwatchError(())


def test_exit_codes() -> None:
    assert (EXIT_OK, EXIT_GATE_FAILED, EXIT_ERROR) == (0, 1, 2)
