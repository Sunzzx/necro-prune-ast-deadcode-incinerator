"""
necro_prune.analyzer
====================
Parses Python ASTs, builds symbol definitions and references, and computes the reachability DAG.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Set, Tuple


@dataclass
class SymbolInfo:
    name: str
    kind: str  # function, class, import
    lineno: int
    referenced_count: int = 0
    references: Set[str] = field(default_factory=set)


class ASTSymbolVisitor(ast.NodeVisitor):
    def __init__(self):
        self.definitions: Dict[str, SymbolInfo] = {}
        self.usages: Set[str] = set()

    def visit_FunctionDef(self, node: ast.FunctionDef):
        # Don't flag dunder or standard magic methods
        if not (node.name.startswith("__") and node.name.endswith("__")):
            self.definitions[node.name] = SymbolInfo(
                name=node.name,
                kind="function",
                lineno=node.lineno,
            )
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        if not (node.name.startswith("__") and node.name.endswith("__")):
            self.definitions[node.name] = SymbolInfo(
                name=node.name,
                kind="async_function",
                lineno=node.lineno,
            )
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef):
        self.definitions[node.name] = SymbolInfo(
            name=node.name,
            kind="class",
            lineno=node.lineno,
        )
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name):
        if isinstance(node.ctx, ast.Load):
            self.usages.add(node.id)
        self.generic_visit(node)


class DeadCodeAnalyzer:
    """Analyzes Python code for unreferenced definitions."""

    def analyze_source(self, code: str) -> List[SymbolInfo]:
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return []

        visitor = ASTSymbolVisitor()
        visitor.visit(tree)

        dead_symbols: List[SymbolInfo] = []
        for name, sym in visitor.definitions.items():
            if name not in visitor.usages and name != "main":
                dead_symbols.append(sym)

        return dead_symbols

    def analyze_file(self, file_path: Path | str) -> List[SymbolInfo]:
        p = Path(file_path)
        if not p.exists() or not p.suffix == ".py":
            return []
        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
            return self.analyze_source(content)
        except Exception:
            return []
