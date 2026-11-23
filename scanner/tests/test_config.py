import ast
import builtins
import dataclasses
import io
import keyword
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from dogwatch.cli import main
from dogwatch.config import DogwatchConfig, PackageDecl, load_policy
from dogwatch.contracts import OpenApiContractDecl
from dogwatch.diagnostics import Diagnostic, DogwatchError
from dogwatch.exclude import ExclusionDecl
from dogwatch.rules import RuleDecl
from tests.conftest import MakeConfig

CONFIG_SOURCE = Path(__file__).resolve().parents[1] / "src" / "dogwatch" / "config.py"
ACME = '[[python.packages]]\nname = "acme"\nroot = "src"\n'
EXCLUDE = '[python]\nexclude = ["src/acme/legacy/**"]\n'
FORBID = (
    '[[python.rules]]\nid = "no-legacy"\nkind = "forbid"\nreason = "Legacy is frozen"\n'
    'targets = ["acme.legacy"]\nsources = ["acme"]\nexcept_sources = ["acme.legacy"]\n'
)
LAYERS = (
    '[[python.rules]]\nid = "layering"\nkind = "layers"\n'
    'reason = "UI sits above domain"\nlayers = ["acme.ui", "acme.domain"]\n'
    'container = "acme"\nexhaustive = true\n'
)
CONTRACT = '[[openapi.contracts]]\nid = "public-api"\npath = "api/openapi.yaml"\n'
FORBID_DECL = RuleDecl(
    id="no-legacy",
    kind="forbid",
    reason="Legacy is frozen",
    targets=("acme.legacy",),
    sources=("acme",),
    except_sources=("acme.legacy",),
)
LAYERS_DECL = RuleDecl(
    id="layering",
    kind="layers",
    reason="UI sits above domain",
    layers=("acme.ui", "acme.domain"),
    container="acme",
    exhaustive=True,
)
PRE_SCAN_IDS = {"config-not-found", "config-invalid", "exclude-unmatched"}


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
    diagnostics = excinfo.value.diagnostics
    assert all(
        d.source == "dogwatch" and d.severity == "error" and d.id in PRE_SCAN_IDS
        for d in diagnostics
    )
    return diagnostics


def _invalid_message(config_arg: str = "dogwatch.toml") -> str:
    diagnostics = _diagnostics(config_arg)
    assert len(diagnostics) == 1
    assert diagnostics[0].id == "config-invalid"
    return diagnostics[0].message


def _sound(config: DogwatchConfig) -> DogwatchConfig:
    config_dir = os.path.dirname(config.path_arg)
    assert len(config.packages) >= 1
    for package in config.packages:
        assert package.name.isidentifier() and not keyword.iskeyword(package.name)
        assert os.path.isdir(os.path.join(config_dir, package.root, package.name))
    assert all(exclusion.pattern for exclusion in config.exclusions)
    assert len({rule.id for rule in config.rules}) == len(config.rules)
    for rule in config.rules:
        assert rule.reason
        if rule.kind == "forbid":
            assert rule.targets != () and rule.layers == ()
        else:
            assert rule.layers != () and rule.targets == ()
            assert len(set(rule.layers)) == len(rule.layers)
            assert not rule.exhaustive or rule.container is not None
    assert len({c.id for c in config.contracts}) == len(config.contracts)
    assert len({c.path for c in config.contracts}) == len(config.contracts)
    assert all(c.path.endswith((".yaml", ".yml", ".json")) for c in config.contracts)
    return config


def _load(config_arg: str = "dogwatch.toml") -> DogwatchConfig:
    return _sound(load_policy(config_arg))


def test_valid_config_returns_frozen_policy_config(make_config: MakeConfig) -> None:
    text = ACME + _entries(("beta", "lib"))
    make_config(text, dirs=["src/acme", "lib/beta"])

    policy = _load()

    assert policy == DogwatchConfig(
        path_arg="dogwatch.toml",
        raw=text.encode("utf-8"),
        packages=(PackageDecl("acme", "src"), PackageDecl("beta", "lib")),
        exclusions=(),
        rules=(),
        contracts=(),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        policy.packages[0].name = "other"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("exclude", "rules", "contracts"),
    [
        (True, True, True),
        (True, True, False),
        (True, False, True),
        (False, True, True),
        (False, False, False),
    ],
    ids=["full-surface", "no-contracts", "no-rules", "no-exclude", "packages-only"],
)
def test_accepted_surface_loads(
    make_config: MakeConfig,
    tmp_path: Path,
    exclude: bool,
    rules: bool,
    contracts: bool,
) -> None:
    text = (
        (EXCLUDE if exclude else "")
        + ACME
        + (FORBID + LAYERS if rules else "")
        + (CONTRACT if contracts else "")
    )
    make_config(text, dirs=["src/acme/legacy"])
    (tmp_path / "src" / "acme" / "legacy" / "old.py").write_text("x = 1\n")

    assert _load() == DogwatchConfig(
        path_arg="dogwatch.toml",
        raw=text.encode("utf-8"),
        packages=(PackageDecl("acme", "src"),),
        exclusions=(ExclusionDecl("src/acme/legacy/**"),) if exclude else (),
        rules=(FORBID_DECL, LAYERS_DECL) if rules else (),
        contracts=(OpenApiContractDecl("public-api", "api/openapi.yaml"),)
        if contracts
        else (),
    )


@pytest.mark.parametrize(
    "text",
    [
        "[python]\nexclude = []\n" + ACME,
        ACME + "[openapi]\n",
        ACME + "[openapi]\ncontracts = []\n",
    ],
    ids=["empty-exclude", "empty-openapi", "openapi-no-contracts"],
)
def test_empty_optional_declarations_load(make_config: MakeConfig, text: str) -> None:
    make_config(text, dirs=["src/acme"])

    policy = _load()

    assert (policy.exclusions, policy.rules, policy.contracts) == ((), (), ())


def test_package_roots_resolve_against_config_directory(tmp_path: Path) -> None:
    (tmp_path / "sub" / "src" / "acme" / "legacy").mkdir(parents=True)
    (tmp_path / "sub" / "src" / "acme" / "legacy" / "old.py").write_text("")
    (tmp_path / "sub" / "dogwatch.toml").write_text(EXCLUDE + ACME, encoding="utf-8")

    policy = _load("sub/dogwatch.toml")

    assert policy.path_arg == "sub/dogwatch.toml"
    assert policy.packages == (PackageDecl("acme", "src"),)


@pytest.mark.parametrize("contents", [{}, {"mod.py": "x = 1\n"}, {"README": "x\n"}])
def test_package_without_py_files_or_init_is_valid(
    make_config: MakeConfig, tmp_path: Path, contents: dict[str, str]
) -> None:
    make_config(ACME, dirs=["src/acme"])
    for name, body in contents.items():
        (tmp_path / "src" / "acme" / name).write_text(body, encoding="utf-8")

    assert _load().packages == (PackageDecl("acme", "src"),)


def test_v0_missing_config() -> None:
    assert _diagnostics("missing.toml") == (
        Diagnostic(
            "dogwatch", "config-not-found", "error", "missing.toml does not exist"
        ),
    )


def test_v1_directory_as_config(tmp_path: Path) -> None:
    (tmp_path / "conf.toml").mkdir()

    assert _invalid_message("conf.toml") == "conf.toml is not a readable file"


@pytest.mark.skipif(os.geteuid() == 0, reason="root can read any file")
def test_v1_unreadable_config(make_config: MakeConfig) -> None:
    config = make_config(ACME, dirs=["src/acme"])
    config.chmod(0)
    try:
        assert _invalid_message() == "dogwatch.toml is not a readable file"
    finally:
        config.chmod(0o644)


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
        ('[python]\ntype_checking = "strict"\n' + ACME, "python.type_checking"),
        ('[python]\nclock = "2026-01-01"\n' + ACME, "python.clock"),
        ("[python]\nmax_waiver_days = 30\n" + ACME, "python.max_waiver_days"),
        (ACME + '[[python.waivers]]\nrule = "x"\n', "python.waivers"),
        ('baseline = "dogwatch-baseline.json"\n' + ACME, "baseline"),
        ('[python]\nbaseline = "dogwatch-baseline.json"\n' + ACME, "python.baseline"),
        (ACME + '[openapi]\nseverity = "error"\n', "openapi.severity"),
        ("zebra = 1\n" + ACME, "zebra"),
        (ACME + 'include = ["*"]\n', "python.packages[0].include"),
        (ACME + CONTRACT + 'title = "x"\n', "openapi.contracts[0].title"),
    ],
)
def test_v3_unsupported_key(make_config: MakeConfig, text: str, key: str) -> None:
    make_config(text, dirs=["src/acme"])

    assert _invalid_message() == f"{key} is not supported in this version"


def test_v3_reports_first_of_sorted_unsupported_keys(make_config: MakeConfig) -> None:
    make_config(
        'zebra = 1\n[python]\nclock = "x"\n'
        + ACME
        + 'extra = 1\n[openapi]\nseverity = "x"\n'
        + CONTRACT
        + "extra = 1\n"
    )
    unknown = [
        "zebra",
        "python.clock",
        "python.packages[0].extra",
        "openapi.severity",
        "openapi.contracts[0].extra",
    ]

    assert (
        _invalid_message() == f"{sorted(unknown)[0]} is not supported in this version"
    )


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
        ("openapi = 1\n" + ACME, "openapi", "a table"),
        (
            ACME + "[openapi]\ncontracts = 1\n",
            "openapi.contracts",
            "an array of tables",
        ),
        ("[python]\nexclude = 1\n" + ACME, "python.exclude", "an array of strings"),
        ("[python]\nrules = 1\n" + ACME, "python.rules", "an array of tables"),
    ],
)
def test_v3_wrong_type(
    make_config: MakeConfig, text: str, key: str, expected: str
) -> None:
    make_config(text, dirs=["src/acme"])

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


@pytest.mark.parametrize("name", ["a.b", "foo-bar", "class", "None", "1abc", ""])
def test_v3_name_must_be_identifier(make_config: MakeConfig, name: str) -> None:
    make_config(_entries((name, "src")))

    assert _invalid_message() == (
        f"python.packages[0].name '{name}' must be a single top-level identifier"
    )


@pytest.mark.parametrize(
    ("text", "message"),
    [
        (
            '[python]\nexclude = ["/abs"]\n'
            + _entries(("acme", "x"))
            + "[[python.rules]]\n",
            "python.exclude[0] '/abs' must be relative",
        ),
        (
            "[python]\nexclude = [1]\n" + _entries(("1x", "src")),
            "python.packages[0].name '1x' must be a single top-level identifier",
        ),
        (
            "openapi = 1\n" + _entries(("acme", "x")) + "[[python.rules]]\n",
            "python.rules[0].kind is required",
        ),
        (
            _entries(("acme", "x")) + CONTRACT + '[[openapi.contracts]]\nid = "A"\n',
            "openapi.contracts[1].id 'A' must be kebab-case "
            "([a-z][a-z0-9]*(-[a-z0-9]+)*) and at most 64 characters",
        ),
    ],
    ids=["exclude-before-rules", "packages-first", "rules-before-openapi", "contracts"],
)
def test_document_stage_runs_in_order_before_filesystem_stage(
    make_config: MakeConfig, text: str, message: str
) -> None:
    make_config(text)

    assert _invalid_message() == message


def test_v4_missing_directory(make_config: MakeConfig) -> None:
    make_config(ACME)

    assert _invalid_message() == (
        "python.packages[0]: package 'acme': directory 'src/acme' does not exist"
    )


def test_v4_file_instead_of_directory(make_config: MakeConfig, tmp_path: Path) -> None:
    make_config(ACME, dirs=["src"])
    (tmp_path / "src" / "acme").write_text("", encoding="utf-8")

    assert _invalid_message() == (
        "python.packages[0]: package 'acme': 'src/acme' is not a directory"
    )


def test_v4_duplicate(make_config: MakeConfig) -> None:
    make_config(_entries(("acme", "src"), ("acme", "./src")), dirs=["src/acme"])

    assert _invalid_message() == (
        "python.packages[1]: package 'acme' is declared more than once (root './src')"
    )


def test_v4_split(make_config: MakeConfig) -> None:
    make_config(
        _entries(("acme", "src"), ("acme", "lib")), dirs=["src/acme", "lib/acme"]
    )

    assert _invalid_message() == (
        "python.packages[1]: package 'acme' split across roots 'src', 'lib'"
    )


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
        f"python.packages[1]: packages '{name_i}' ('{root_i}/{name_i}') "
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
        "python.packages[1]: package 'gone': directory 'src/gone' does not exist",
        "python.packages[3]: package 'flat': 'src/flat' is not a directory",
        "python.packages[2]: package 'acme' is declared more than once (root 'r1')",
        "python.packages[4]: package 'acme' split across roots 'r1', 'r2'",
        "python.packages[5]: packages 'acme' ('r1/acme') "
        "and 'inner' ('r1/acme/inner') are nested",
        "python.packages[4]: package 'acme' split across roots 'r1', 'r2'",
        "python.packages[5]: packages 'acme' ('r1/acme') "
        "and 'inner' ('r1/acme/inner') are nested",
    ]


def test_exclude_unmatched_reports_each_pattern_in_config_order(
    make_config: MakeConfig, tmp_path: Path
) -> None:
    make_config(
        '[python]\nexclude = ["src/acme/gen/**", "src/acme/*.py", "lib/**"]\n' + ACME,
        dirs=["src/acme"],
    )
    (tmp_path / "src" / "acme" / "mod.py").write_text("")

    assert _diagnostics() == (
        Diagnostic(
            "dogwatch",
            "exclude-unmatched",
            "error",
            "python.exclude[0] 'src/acme/gen/**' "
            "matches no file under a declared package directory",
        ),
        Diagnostic(
            "dogwatch",
            "exclude-unmatched",
            "error",
            "python.exclude[2] 'lib/**' "
            "matches no file under a declared package directory",
        ),
    )


def test_unknown_key_masks_missing_package_directory(make_config: MakeConfig) -> None:
    make_config(ACME + 'extra = "x"\n')

    assert _invalid_message() == (
        "python.packages[0].extra is not supported in this version"
    )


def test_filesystem_stage_masks_unmatched_exclusion(make_config: MakeConfig) -> None:
    make_config(
        '[python]\nexclude = ["src/acme/gen/**"]\n' + ACME + _entries(("gone", "src")),
        dirs=["src/acme"],
    )

    assert _diagnostics() == (
        Diagnostic(
            "dogwatch",
            "config-invalid",
            "error",
            "python.packages[1]: package 'gone': directory 'src/gone' does not exist",
        ),
    )


def test_selectors_and_contract_paths_are_not_resolved(
    make_config: MakeConfig,
) -> None:
    make_config(
        ACME
        + FORBID.replace('targets = ["acme.legacy"]', 'targets = ["ghost.module"]')
        + CONTRACT.replace("api/openapi.yaml", "missing/spec.json"),
        dirs=["src/acme"],
    )

    policy = _load()

    assert policy.rules[0].targets == ("ghost.module",)
    assert policy.contracts == (OpenApiContractDecl("public-api", "missing/spec.json"),)


def _record_io(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    calls: list[tuple[str, str]] = []

    def recording(name: str, fn: Callable[..., Any]) -> Callable[..., Any]:
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            target = args[0] if args else kwargs.get("path", kwargs.get("file", "."))
            if isinstance(target, (str, bytes, os.PathLike)):
                calls.append((name, os.path.realpath(os.fsdecode(target))))
            return fn(*args, **kwargs)

        return wrapper

    for module, attr, name in [
        (builtins, "open", "open"),
        (io, "open", "open"),
        (os, "open", "open"),
        (os, "scandir", "scandir"),
        (os, "listdir", "listdir"),
    ]:
        monkeypatch.setattr(module, attr, recording(name, getattr(module, attr)))
    return calls


def _two_packages(make_config: MakeConfig, tmp_path: Path, prefix: str) -> list[str]:
    make_config(
        prefix + _entries(("acme", "src"), ("beta", "lib")),
        dirs=["src/acme/sub", "lib/beta"],
    )
    (tmp_path / "src" / "acme" / "__init__.py").write_text("raise SystemExit\n")
    (tmp_path / "src" / "acme" / "sub" / "mod.py").write_text("raise SystemExit\n")
    return [
        os.path.realpath(tmp_path / "src" / "acme"),
        os.path.realpath(tmp_path / "lib" / "beta"),
    ]


@pytest.mark.parametrize(
    "prefix", ["", "[python]\nexclude = []\n"], ids=["absent", "empty"]
)
def test_load_policy_without_exclusions_never_lists_directories(
    make_config: MakeConfig,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    prefix: str,
) -> None:
    _two_packages(make_config, tmp_path, prefix)
    calls = _record_io(monkeypatch)

    load_policy("dogwatch.toml")

    assert calls == [("open", os.path.realpath(tmp_path / "dogwatch.toml"))]


def test_load_policy_with_exclusions_lists_only_package_directories(
    make_config: MakeConfig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package_dirs = _two_packages(
        make_config, tmp_path, '[python]\nexclude = ["src/acme/sub/*.py"]\n'
    )
    calls = _record_io(monkeypatch)

    load_policy("dogwatch.toml")

    opened = [path for name, path in calls if name == "open"]
    listed = [path for name, path in calls if name == "scandir"]
    assert opened == [os.path.realpath(tmp_path / "dogwatch.toml")]
    assert listed
    assert all(
        any(path == d or path.startswith(d + os.sep) for d in package_dirs)
        for path in listed
    )
    assert [name for name, _ in calls if name == "listdir"] == []


def test_cli_exclude_unmatched_exits_2_without_report(
    make_config: MakeConfig,
    tmp_path: Path,
    capsysbinary: pytest.CaptureFixture[bytes],
) -> None:
    make_config('[python]\nexclude = ["src/acme/gen/**"]\n' + ACME, dirs=["src/acme"])

    code = main(["check", "--config", "dogwatch.toml", "--output", "report.json"])

    captured = capsysbinary.readouterr()
    assert code == 2
    assert captured.out == b""
    assert captured.err == (
        b"dogwatch:exclude-unmatched: python.exclude[0] 'src/acme/gen/**' "
        b"matches no file under a declared package directory\n"
    )
    assert not (tmp_path / "report.json").exists()


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
    dogwatch_imports = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module
        and node.module.startswith("dogwatch.")
    }
    os_calls = {
        ast.unparse(node.func)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and ast.unparse(node.func).startswith("os.")
    }

    assert not imported & {"importlib", "ast"}
    assert "os" in imported
    assert dogwatch_imports == {
        "dogwatch.diagnostics",
        "dogwatch._validate",
        "dogwatch.exclude",
        "dogwatch.rules",
        "dogwatch.contracts",
    }
    assert os_calls <= {
        "os.path.lexists",
        "os.path.isdir",
        "os.path.realpath",
        "os.path.isfile",
        "os.path.join",
        "os.path.dirname",
    }
