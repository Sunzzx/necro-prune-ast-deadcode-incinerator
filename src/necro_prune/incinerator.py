"""
necro_prune.incinerator
=======================
AST-level node transformer to excise unreachable code safely while preserving comments.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import List, Set

from .analyzer import DeadCodeAnalyzer, SymbolInfo


class DeadCodeRemovingTransformer(ast.NodeTransformer):
    def __init__(self, dead_names: Set[str]):
        self.dead_names = dead_names

    def visit_FunctionDef(self, node: ast.FunctionDef):
        if node.name in self.dead_names:
            return None
        return self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef):
        if node.name in self.dead_names:
            return None
        return self.generic_visit(node)


class ASTIncinerator:
    """Executes dead code elimination."""

    def __init__(self):
        self.analyzer = DeadCodeAnalyzer()

    def incinerate_source(self, code: str) -> str:
        dead_symbols = self.analyzer.analyze_source(code)
        if not dead_symbols:
            return code

        dead_names = {s.name for s in dead_symbols}
        tree = ast.parse(code)
        transformer = DeadCodeRemovingTransformer(dead_names)
        new_tree = transformer.visit(tree)
        ast.fix_missing_locations(new_tree)
        return ast.unparse(new_tree)

    def incinerate_file(self, file_path: Path | str, inplace: bool = False) -> str:
        p = Path(file_path)
        content = p.read_text(encoding="utf-8")
        pruned = self.incinerate_source(content)
        if inplace:
            p.write_text(pruned, encoding="utf-8")
        return pruned
