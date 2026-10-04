"""
muse/ is the UI-framework-agnostic playback/DJ core: no module in it may import
ui_qt or PySide6 at runtime. Imports under `if TYPE_CHECKING:` are allowed,
since they exist only for type hints.

Checked by parsing the source, so the modules are not imported.
"""

import ast
from pathlib import Path

import pytest

MUSE_DIR = Path(__file__).resolve().parents[3] / "muse"
FORBIDDEN_ROOTS = {"ui_qt", "PySide6"}


def _is_type_checking_block(node: ast.AST) -> bool:
    if not isinstance(node, ast.If):
        return False
    test = node.test
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or \
        (isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING")


def _runtime_imports(tree: ast.AST):
    """Imported module names, skipping `if TYPE_CHECKING:` bodies."""
    stack = [tree]
    while stack:
        node = stack.pop()
        if _is_type_checking_block(node):
            stack.extend(node.orelse)
            continue
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            yield node.lineno, node.module
        stack.extend(ast.iter_child_nodes(node))


def _violations():
    found = []
    for path in sorted(MUSE_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for lineno, module in _runtime_imports(tree):
            if module.split(".")[0] in FORBIDDEN_ROOTS:
                found.append(f"muse/{path.name}:{lineno} imports {module}")
    return found


@pytest.mark.unit
def test_muse_sources_found():
    assert any(MUSE_DIR.glob("*.py"))


@pytest.mark.unit
def test_muse_does_not_import_ui_at_runtime():
    assert _violations() == []
