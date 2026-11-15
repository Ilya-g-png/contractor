import ast
import graphlib
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "dogwatch"
MODULES = {path.stem for path in PACKAGE.glob("*.py")}
VALIDATORS = ["exclude", "rules", "contracts"]


def _resolve(name: str) -> str:
    return name if name in MODULES else "__init__"


def _dogwatch_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_bytes(), filename=str(path))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top, _, rest = alias.name.partition(".")
                if top == "dogwatch":
                    imported.add(_resolve(rest.partition(".")[0]))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level == 0:
                top, _, rest = module.partition(".")
                if top != "dogwatch":
                    continue
            else:
                rest = module
            if rest:
                imported.add(_resolve(rest.partition(".")[0]))
            else:
                imported.update(_resolve(alias.name) for alias in node.names)
    imported.discard(path.stem)
    return imported


GRAPH = {path.stem: _dogwatch_imports(path) for path in sorted(PACKAGE.glob("*.py"))}


def test_graph_covers_every_module_and_known_edges() -> None:
    assert {"diagnostics", "_validate", "config", "report", "cli"} <= set(GRAPH)
    assert set(VALIDATORS) <= set(GRAPH)
    assert {"_validate", "diagnostics", *VALIDATORS} <= GRAPH["config"]
    assert {"config", "report", "__init__"} <= GRAPH["cli"]


def test_diagnostics_imports_no_dogwatch_module() -> None:
    assert GRAPH["diagnostics"] == set()


def test_validate_imports_only_diagnostics() -> None:
    assert GRAPH["_validate"] == {"diagnostics"}


@pytest.mark.parametrize("module", VALIDATORS)
def test_validators_import_only_shared_helpers(module: str) -> None:
    assert GRAPH[module] <= {"_validate", "diagnostics"}
    assert GRAPH[module].isdisjoint(VALIDATORS)


def test_config_does_not_import_report_or_cli() -> None:
    assert GRAPH["config"].isdisjoint({"report", "cli"})


def test_report_does_not_import_cli_or_validators() -> None:
    assert GRAPH["report"].isdisjoint({"cli", *VALIDATORS})


def test_import_graph_is_acyclic() -> None:
    order = list(graphlib.TopologicalSorter(GRAPH).static_order())

    assert set(order) == set(GRAPH)
