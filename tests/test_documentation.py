# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src"


class DocumentationTests(unittest.TestCase):
    def test_source_modules_have_module_docstrings(self) -> None:
        missing = []
        for path in sorted(SOURCE.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            if path.name != "__init__.py" and ast.get_docstring(tree) is None:
                missing.append(path.relative_to(ROOT).as_posix())
        self.assertEqual(missing, [])

    def test_public_definitions_have_docstrings(self) -> None:
        missing = []
        for path in sorted(SOURCE.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    if not node.name.startswith("_") and ast.get_docstring(node) is None:
                        missing.append(f"{path.relative_to(ROOT)}:{node.lineno} {node.name}")
                if isinstance(node, ast.ClassDef):
                    for member in node.body:
                        if (
                            isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef))
                            and not member.name.startswith("_")
                            and ast.get_docstring(member) is None
                        ):
                            missing.append(
                                f"{path.relative_to(ROOT)}:{member.lineno} "
                                f"{node.name}.{member.name}"
                            )
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
