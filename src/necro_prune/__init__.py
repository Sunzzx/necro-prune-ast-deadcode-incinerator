"""
necro-prune-ast-deadcode-incinerator
===================================
AST-level dead code analysis and unreferenced symbol reachability engine.
"""

from .analyzer import DeadCodeAnalyzer, SymbolInfo
from .incinerator import ASTIncinerator

__version__ = "0.1.0"
__all__ = ["DeadCodeAnalyzer", "SymbolInfo", "ASTIncinerator"]
