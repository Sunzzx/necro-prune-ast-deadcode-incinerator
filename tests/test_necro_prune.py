"""
Tests for necro-prune-ast-deadcode-incinerator
"""

from necro_prune.analyzer import DeadCodeAnalyzer
from necro_prune.incinerator import ASTIncinerator


def test_analyzer_detects_unused_function():
    code = """
def used_function():
    return 42

def dead_function():
    return -1

def main():
    print(used_function())
"""
    analyzer = DeadCodeAnalyzer()
    dead = analyzer.analyze_source(code)
    dead_names = [d.name for d in dead]
    assert "dead_function" in dead_names
    assert "used_function" not in dead_names


def test_incinerator_pruning():
    code = """
def dead_fn():
    pass

def active_fn():
    return 100

print(active_fn())
"""
    incinerator = ASTIncinerator()
    pruned = incinerator.incinerate_source(code)
    assert "dead_fn" not in pruned
    assert "active_fn" in pruned
    assert "return 100" in pruned
