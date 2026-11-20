"""
necro_prune.analyzer
====================
Parses Python ASTs, builds symbol definitions + reference graphs, and computes
module-level reachability from configurable entry points.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set


DEFAULT_ENTRY_POINTS: frozenset[str] = frozenset(
    {
        "main",
        "cli",
        "run",
        "app",
        "handler",
        "lambda_handler",
        "application",
    }
)


@dataclass
class SymbolInfo:
    name: str
    kind: str  # function, async_function, class, assign, import
    lineno: int
    referenced_count: int = 0
    references: Set[str] = field(default_factory=set)
    is_export: bool = False
    scope: str = "module"  # module | class:<Name>


class _ModuleCollector(ast.NodeVisitor):
    """Collect module-level defs and a coarse name-use graph."""

    def __init__(self) -> None:
        self.definitions: Dict[str, SymbolInfo] = {}
        self.usages: Set[str] = set()
        self.edges: Dict[str, Set[str]] = {}  # def -> names it references
        self.exports: Set[str] = set()
        self._def_stack: List[str] = []
        self._class_stack: List[str] = []

    # ----- helpers -----
    def _current_def(self) -> Optional[str]:
        return self._def_stack[-1] if self._def_stack else None

    def _record_use(self, name: str) -> None:
        self.usages.add(name)
        cur = self._current_def()
        if cur is not None:
            self.edges.setdefault(cur, set()).add(name)

    def _add_def(self, name: str, kind: str, lineno: int, scope: str = "module") -> None:
        # First definition wins for top-level reporting; class methods use scoped keys.
        key = name if scope == "module" else f"{scope}.{name}"
        if key in self.definitions:
            return
        self.definitions[key] = SymbolInfo(
            name=name if scope == "module" else key,
            kind=kind,
            lineno=lineno,
            scope=scope,
        )
        self.edges.setdefault(key, set())

    # ----- visitors -----
    def visit_Assign(self, node: ast.Assign) -> None:
        # Capture __all__ exports
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "__all__":
                self.exports |= _extract_string_list(node.value)
        if not self._class_stack and not self._def_stack:
            for target in node.targets:
                for name in _target_names(target):
                    if name != "__all__":
                        self._add_def(name, "assign", node.lineno)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if not self._class_stack and not self._def_stack and isinstance(node.target, ast.Name):
            if node.target.id != "__all__":
                self._add_def(node.target.id, "assign", node.lineno)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function_like(node, "function")

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function_like(node, "async_function")

    def _visit_function_like(self, node: ast.AST, kind: str) -> None:
        name = node.name  # type: ignore[attr-defined]
        lineno = node.lineno  # type: ignore[attr-defined]
        is_dunder = name.startswith("__") and name.endswith("__")
        if self._class_stack:
            scope = f"class:{self._class_stack[-1]}"
            if not is_dunder:
                self._add_def(name, kind, lineno, scope=scope)
            # Still walk body for uses that bubble to module via free names
            self._def_stack.append(f"{scope}.{name}" if not is_dunder else f"{scope}.__dunder__")
            self.generic_visit(node)
            self._def_stack.pop()
            return

        if not is_dunder:
            self._add_def(name, kind, lineno, scope="module")
            self._def_stack.append(name)
            self.generic_visit(node)
            self._def_stack.pop()
        else:
            self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if not self._class_stack and not self._def_stack:
            self._add_def(node.name, "class", node.lineno, scope="module")
        self._class_stack.append(node.name)
        # Class body references attribute bases etc.
        self._def_stack.append(node.name)
        self.generic_visit(node)
        self._def_stack.pop()
        self._class_stack.pop()

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load):
            self._record_use(node.id)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        # `mod.foo` / `self.foo` — record attr name as soft use for method liveness
        if isinstance(node.ctx, ast.Load):
            self._record_use(node.attr)
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        if not self._def_stack and not self._class_stack:
            for alias in node.names:
                bound = alias.asname or alias.name.split(".")[0]
                self._add_def(bound, "import", node.lineno)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if not self._def_stack and not self._class_stack:
            for alias in node.names:
                if alias.name == "*":
                    continue
                bound = alias.asname or alias.name
                self._add_def(bound, "import", node.lineno)
        self.generic_visit(node)


def _target_names(target: ast.AST) -> List[str]:
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, (ast.Tuple, ast.List)):
        names: List[str] = []
        for elt in target.elts:
            names.extend(_target_names(elt))
        return names
    return []


def _extract_string_list(node: ast.AST) -> Set[str]:
    out: Set[str] = set()
    if isinstance(node, (ast.List, ast.Tuple)):
        for elt in node.elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                out.add(elt.value)
    return out


class DeadCodeAnalyzer:
    """Analyzes Python modules for unreferenced top-level definitions."""

    def __init__(
        self,
        entry_points: Optional[Iterable[str]] = None,
        keep_dunder_all: bool = True,
        keep_private: bool = False,
    ) -> None:
        self.entry_points: Set[str] = set(entry_points) if entry_points else set(DEFAULT_ENTRY_POINTS)
        self.keep_dunder_all = keep_dunder_all
        self.keep_private = keep_private  # if True, names starting with _ are never dead

    def analyze_source(self, code: str) -> List[SymbolInfo]:
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return []

        collector = _ModuleCollector()
        collector.visit(tree)

        # Seed reachability from entry points + exports + anything referenced at module scope
        reachable: Set[str] = set()
        seeds: Set[str] = set(collector.usages)  # module-level loads already recorded outside defs too
        # usages includes everything; better seed from edges of synthetic module root:
        # Re-walk: names used outside any def are already in usages while def_stack empty —
        # collector records ALL loads into usages, so we need a cleaner approach:
        reachable |= self._module_level_seeds(tree, collector)

        for ep in self.entry_points:
            if ep in collector.definitions:
                reachable.add(ep)
        if self.keep_dunder_all:
            reachable |= collector.exports
            for exp in collector.exports:
                if exp in collector.definitions:
                    reachable.add(exp)

        # Fixed-point over call/reference graph (module-level symbols only)
        queue = list(reachable)
        while queue:
            name = queue.pop()
            for dep in collector.edges.get(name, ()):
                # dep may be a bare name matching a module def
                if dep in collector.definitions and dep not in reachable:
                    reachable.add(dep)
                    queue.append(dep)
                # class methods referenced by attr name: mark class live methods
                for key, sym in collector.definitions.items():
                    if sym.scope.startswith("class:") and sym.name.endswith(f".{dep}") or (
                        sym.scope.startswith("class:") and key.endswith(f".{dep}")
                    ):
                        if key not in reachable:
                            reachable.add(key)
                            queue.append(key)
                    if sym.kind == "class" and dep == sym.name and sym.name not in reachable:
                        reachable.add(sym.name)
                        queue.append(sym.name)

        dead: List[SymbolInfo] = []
        for key, sym in collector.definitions.items():
            if sym.scope != "module":
                # Class methods: dead only if owning class is dead (handled below via class)
                continue
            if key in reachable:
                sym.referenced_count = 1
                continue
            if key in self.entry_points:
                continue
            if self.keep_private and key.startswith("_") and not key.startswith("__"):
                continue
            if key in collector.exports:
                continue
            dead.append(sym)

        # If a class is dead, its methods are implicitly dead (not reported separately).
        # If a class is live, methods are kept (conservative).
        return sorted(dead, key=lambda s: s.lineno)

    def _module_level_seeds(self, tree: ast.AST, collector: _ModuleCollector) -> Set[str]:
        """Names loaded at module scope (not inside function/class bodies)."""
        seeds: Set[str] = set()

        class ModuleUseVisitor(ast.NodeVisitor):
            def __init__(self) -> None:
                self.depth = 0

            def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
                self.depth += 1
                # do not recurse into body for module seeds
                self.depth -= 1

            def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
                pass

            def visit_ClassDef(self, node: ast.ClassDef) -> None:
                # class body base names are module-level-ish; visit bases only
                for base in node.bases:
                    self.visit(base)
                for kw in node.keywords:
                    self.visit(kw.value)

            def visit_Name(self, node: ast.Name) -> None:
                if isinstance(node.ctx, ast.Load):
                    seeds.add(node.id)

            def visit_Attribute(self, node: ast.Attribute) -> None:
                if isinstance(node.ctx, ast.Load):
                    seeds.add(node.attr)
                self.generic_visit(node)

        ModuleUseVisitor().visit(tree)
        # Also: if __name__ == "__main__" block calls something — already covered by Name loads
        return seeds

    def analyze_file(self, file_path: Path | str) -> List[SymbolInfo]:
        p = Path(file_path)
        if not p.exists() or p.suffix != ".py":
            return []
        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
            return self.analyze_source(content)
        except OSError:
            return []

    def analyze_directory(self, root: Path | str) -> Dict[str, List[SymbolInfo]]:
        root_p = Path(root)
        report: Dict[str, List[SymbolInfo]] = {}
        for path in sorted(root_p.rglob("*.py")):
            if any(part.startswith(".") or part in {"venv", ".venv", "node_modules"} for part in path.parts):
                continue
            dead = self.analyze_file(path)
            if dead:
                report[str(path)] = dead
        return report
