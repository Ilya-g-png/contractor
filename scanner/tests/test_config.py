import ast
import builtins
import dataclasses
import io
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from dogwatch.config import PackageDecl, PolicyConfig, load_policy
from dogwatch.diagnostics import Diagnostic, DogwatchError
from tests.conftest import MakeConfig

CONFIG_SOURCE = Path(__file__).resolve().parents[1] / "src" / "dogwatch" / "config.py"
ACME = '[[python.packages]]\nname = "acme"\nroot = "src"\n'


@pytest.fixture(autouse=True)
def _chdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def _entries(*pairs: tuple[str, str]) -> str:
    return "".join(
        f'[[python.packages]]\nname = "{name}"\nroot = "{root}"\n'
        for name, root in pairs
    )


def _diagnostics(config_arg: str = "dogwatch.toml") -> tuple[Diagnostic, ...]:
    with pytest.raises(DogwatchError) as excinfo:
        load_policy(config_arg)
    return excinfo.value.diagnostics


def _invalid_message(config_arg: str = "dogwatch.toml") -> str:
    diagnostics = _diagnostics(config_arg)
    assert len(diagnostics) == 1
    assert diagnostics[0].id == "config-invalid"
    return diagnostics[0].message


def test_valid_config_returns_frozen_policy_config(make_config: MakeConfig) -> None:
    text = ACME + _entries(("beta", "lib"))
    make_config(text, dirs=["src/acme", "lib/beta"])

    policy = load_policy("dogwatch.toml")

    assert policy == PolicyConfig(
        path_arg="dogwatch.toml",
        raw=text.encode("utf-8"),
        packages=(PackageDecl("acme", "src"), PackageDecl("beta", "lib")),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        policy.packages[0].name = "other"  # type: ignore[misc]


def test_package_roots_resolve_against_config_directory(tmp_path: Path) -> None:
    (tmp_path / "sub" / "src" / "acme").mkdir(parents=True)
    (tmp_path / "sub" / "dogwatch.toml").write_text(ACME, encoding="utf-8")

    policy = load_policy("sub/dogwatch.toml")

    assert policy.path_arg == "sub/dogwatch.toml"
    assert policy.packages == (PackageDecl("acme", "src"),)


@pytest.mark.parametrize("contents", [{}, {"mod.py": "x = 1\n"}, {"README": "x\n"}])
def test_package_without_py_files_or_init_is_valid(
    make_config: MakeConfig, tmp_path: Path, contents: dict[str, str]
) -> None:
    make_config(ACME, dirs=["src/acme"])
    for name, body in contents.items():
        (tmp_path / "src" / "acme" / name).write_text(body, encoding="utf-8")

    assert load_policy("dogwatch.toml").packages == (PackageDecl("acme", "src"),)


def test_v0_missing_config() -> None:
    assert _diagnostics("missing.toml") == (
        Diagnostic("config-not-found", "missing.toml does not exist"),
    )


def test_v1_directory_as_config(tmp_path: Path) -> None:
    (tmp_path / "conf.toml").mkdir()

    assert _invalid_message("conf.toml") == "conf.toml is not a readable file"


def test_v1_invalid_utf8(tmp_path: Path) -> None:
    (tmp_path / "dogwatch.toml").write_bytes(b"name = '\xff'\n")

    assert _invalid_message() == "dogwatch.toml is not valid UTF-8"


@pytest.mark.parametrize(
    ("text", "line"),
    [
        ("x = = 1\n", 1),
        ("x = 1\ny = 2\nz = = 3\n", 3),
        ("a = 1\na = 2\n", 2),
        ('[[python.packages]]\nname =\nroot = "src"\n', 2),
    ],
)
def test_v2_malformed_toml_reports_line(
    make_config: MakeConfig, text: str, line: int
) -> None:
    make_config(text)

    message = _invalid_message()

    prefix = f"dogwatch.toml:{line}: invalid TOML: "
    assert message.startswith(prefix)
    assert len(message) > len(prefix)
    assert "\n" not in message


def test_v2_utf8_bom_is_invalid_toml(tmp_path: Path) -> None:
    (tmp_path / "dogwatch.toml").write_bytes(b"\xef\xbb\xbf" + ACME.encode("utf-8"))

    assert _invalid_message().startswith("dogwatch.toml:1: invalid TOML: ")


@pytest.mark.parametrize(
    ("text", "key"),
    [
        ('[[python.rules]]\nid = "x"\n' + ACME, "python.rules"),
        ('[openapi]\nspec = "x"\n' + ACME, "openapi"),
        (ACME + 'include = ["*"]\n', "python.packages[0].include"),
        ('zebra = 1\n[openapi]\nspec = "x"\n[[python.rules]]\nid = "x"\n', "openapi"),
    ],
)
def test_v3_unsupported_key(make_config: MakeConfig, text: str, key: str) -> None:
    make_config(text, dirs=["src/acme"])

    assert _invalid_message() == f"{key} is not supported in this version"


@pytest.mark.parametrize(
    "text", ["", "[python]\n", "[python]\npackages = []\n"], ids=["empty", "py", "list"]
)
def test_v3_requires_a_package(make_config: MakeConfig, text: str) -> None:
    make_config(text)

    assert _invalid_message() == (
        "dogwatch.toml requires at least one [[python.packages]] entry"
    )


@pytest.mark.parametrize(
    ("text", "key", "expected"),
    [
        ("python = 1\n", "python", "a table"),
        ("[python]\npackages = 1\n", "python.packages", "a array of tables"),
        ("[python]\npackages = [1]\n", "python.packages", "a array of tables"),
        (
            '[[python.packages]]\nname = 1\nroot = "src"\n',
            "python.packages[0].name",
            "a string",
        ),
        (
            ACME + '[[python.packages]]\nname = "b"\nroot = ["src"]\n',
            "python.packages[1].root",
            "a string",
        ),
    ],
)
def test_v3_wrong_type(
    make_config: MakeConfig, text: str, key: str, expected: str
) -> None:
    make_config(text)

    assert _invalid_message() == f"{key} must be {expected}"


@pytest.mark.parametrize(
    ("text", "key"),
    [
        ('[[python.packages]]\nroot = "src"\n', "python.packages[0].name"),
        (ACME + '[[python.packages]]\nname = "b"\n', "python.packages[1].root"),
    ],
)
def test_v3_missing_field(make_config: MakeConfig, text: str, key: str) -> None:
    make_config(text)

    assert _invalid_message() == f"{key} is required"


@pytest.mark.parametrize("name", ["a.b", "1abc", ""])
def test_v3_name_must_be_identifier(make_config: MakeConfig, name: str) -> None:
    make_config(_entries((name, "src")))

    assert _invalid_message() == (
        f"python.packages[0].name '{name}' must be a single top-level identifier"
    )


def test_v4_missing_directory(make_config: MakeConfig) -> None:
    make_config(ACME)

    assert _invalid_message() == "package 'acme': directory 'src/acme' does not exist"


def test_v4_file_instead_of_directory(make_config: MakeConfig, tmp_path: Path) -> None:
    make_config(ACME, dirs=["src"])
    (tmp_path / "src" / "acme").write_text("", encoding="utf-8")

    assert _invalid_message() == "package 'acme': 'src/acme' is not a directory"


def test_v4_duplicate(make_config: MakeConfig) -> None:
    make_config(_entries(("acme", "src"), ("acme", "./src")), dirs=["src/acme"])

    assert _invalid_message() == (
        "package 'acme' is declared more than once (root './src')"
    )


def test_v4_split(make_config: MakeConfig) -> None:
    make_config(
        _entries(("acme", "src"), ("acme", "lib")), dirs=["src/acme", "lib/acme"]
    )

    assert _invalid_message() == "package 'acme' split across roots 'src', 'lib'"


@pytest.mark.parametrize(
    "pairs",
    [
        (("acme", "src"), ("inner", "src/acme")),
        (("inner", "src/acme"), ("acme", "src")),
    ],
    ids=["outer-first", "inner-first"],
)
def test_v4_nested(
    make_config: MakeConfig, pairs: tuple[tuple[str, str], tuple[str, str]]
) -> None:
    make_config(_entries(*pairs), dirs=["src/acme/inner"])
    (name_i, root_i), (name_j, root_j) = pairs

    assert _invalid_message() == (
        f"packages '{name_i}' ('{root_i}/{name_i}') "
        f"and '{name_j}' ('{root_j}/{name_j}') are nested"
    )


def test_v4_reports_every_failure_in_contract_order(
    make_config: MakeConfig, tmp_path: Path
) -> None:
    make_config(
        _entries(
            ("acme", "r1"),
            ("gone", "src"),
            ("acme", "r1"),
            ("flat", "src"),
            ("acme", "r2"),
            ("inner", "r1/acme"),
        ),
        dirs=["r1/acme/inner", "r2/acme", "src"],
    )
    (tmp_path / "src" / "flat").write_text("", encoding="utf-8")

    diagnostics = _diagnostics()

    assert {d.id for d in diagnostics} == {"config-invalid"}
    assert [d.message for d in diagnostics] == [
        "package 'gone': directory 'src/gone' does not exist",
        "package 'flat': 'src/flat' is not a directory",
        "package 'acme' is declared more than once (root 'r1')",
        "package 'acme' split across roots 'r1', 'r2'",
        "packages 'acme' ('r1/acme') and 'inner' ('r1/acme/inner') are nested",
        "package 'acme' split across roots 'r1', 'r2'",
        "packages 'acme' ('r1/acme') and 'inner' ('r1/acme/inner') are nested",
    ]


def test_stages_stop_at_first_failure(make_config: MakeConfig) -> None:
    make_config(ACME + 'extra = "x"\n')

    assert _invalid_message() == (
        "python.packages[0].extra is not supported in this version"
    )


def test_load_policy_never_opens_or_lists_package_directories(
    make_config: MakeConfig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_config(
        _entries(("acme", "src"), ("beta", "lib")), dirs=["src/acme/sub", "lib/beta"]
    )
    (tmp_path / "src" / "acme" / "__init__.py").write_text("raise SystemExit\n")
    package_dirs = [
        os.path.realpath(tmp_path / "src" / "acme"),
        os.path.realpath(tmp_path / "lib" / "beta"),
    ]
    calls: list[str] = []

    def recording(fn: Callable[..., Any]) -> Callable[..., Any]:
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            target = args[0] if args else kwargs.get("path", kwargs.get("file", "."))
            if isinstance(target, (str, bytes, os.PathLike)):
                calls.append(os.path.realpath(os.fsdecode(target)))
            return fn(*args, **kwargs)

        return wrapper

    for module, attr in [
        (builtins, "open"),
        (io, "open"),
        (os, "open"),
        (os, "scandir"),
        (os, "listdir"),
    ]:
        monkeypatch.setattr(module, attr, recording(getattr(module, attr)))

    load_policy("dogwatch.toml")

    assert os.path.realpath(tmp_path / "dogwatch.toml") in calls
    touched = [
        call
        for call in calls
        for package_dir in package_dirs
        if call == package_dir or call.startswith(package_dir + os.sep)
    ]
    assert touched == []


def test_config_module_restricts_imports_and_os_calls() -> None:
    tree = ast.parse(CONFIG_SOURCE.read_bytes())
    imported = {
        alias.name.partition(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module.partition(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    os_calls = {
        ast.unparse(node.func)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and ast.unparse(node.func).startswith("os.")
    }

    assert not imported & {"importlib", "ast"}
    assert "os" in imported
    assert os_calls <= {
        "os.path.lexists",
        "os.path.isdir",
        "os.path.realpath",
        "os.path.isfile",
        "os.path.join",
        "os.path.dirname",
    }
