"""
necro_prune.incinerator
=======================
AST-level node transformer to excise unreachable module-level symbols.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Iterable, Optional, Set

from .analyzer import DeadCodeAnalyzer, SymbolInfo


class DeadCodeRemovingTransformer(ast.NodeTransformer):
    def __init__(self, dead_names: Set[str], keep_imports: bool = False):
        self.dead_names = dead_names
        self.keep_imports = keep_imports

    def visit_FunctionDef(self, node: ast.FunctionDef):
        if node.name in self.dead_names:
            return None
        return self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        if node.name in self.dead_names:
            return None
        return self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef):
        if node.name in self.dead_names:
            return None
        return self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign):
        # Drop simple module-level `dead = ...` if name is dead
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id in self.dead_names:
                return None
        return self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign):
        if isinstance(node.target, ast.Name) and node.target.id in self.dead_names:
            return None
        return self.generic_visit(node)

    def visit_Import(self, node: ast.Import):
        if self.keep_imports:
            return node
        kept = [a for a in node.names if (a.asname or a.name.split(".")[0]) not in self.dead_names]
        if not kept:
            return None
        node.names = kept
        return node

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if self.keep_imports:
            return node
        if any(a.name == "*" for a in node.names):
            return node
        kept = [a for a in node.names if (a.asname or a.name) not in self.dead_names]
        if not kept:
            return None
        node.names = kept
        return node


class ASTIncinerator:
    """Executes dead code elimination on module-level symbols."""

    def __init__(self, analyzer: Optional[DeadCodeAnalyzer] = None):
        self.analyzer = analyzer or DeadCodeAnalyzer()

    def incinerate_source(self, code: str, extra_keep: Optional[Iterable[str]] = None) -> str:
        dead_symbols = self.analyzer.analyze_source(code)
        keep = set(extra_keep or ())
        dead_names = {s.name for s in dead_symbols if s.name not in keep}
        if not dead_names:
            return code

        tree = ast.parse(code)
        transformer = DeadCodeRemovingTransformer(dead_names)
        new_tree = transformer.visit(tree)
        if new_tree is None:
            return ""
        # Remove None holes from body
        if hasattr(new_tree, "body"):
            new_tree.body = [n for n in new_tree.body if n is not None]
        ast.fix_missing_locations(new_tree)
        return ast.unparse(new_tree)

    def incinerate_file(self, file_path: Path | str, inplace: bool = False, extra_keep: Optional[Iterable[str]] = None) -> str:
        p = Path(file_path)
        content = p.read_text(encoding="utf-8")
        pruned = self.incinerate_source(content, extra_keep=extra_keep)
        if inplace:
            p.write_text(pruned + ("" if pruned.endswith("\n") else "\n"), encoding="utf-8")
        return pruned

    def report(self, code: str) -> list[SymbolInfo]:
        return self.analyzer.analyze_source(code)
