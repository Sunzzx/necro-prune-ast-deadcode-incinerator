"""Tests for necro-prune-ast-deadcode-incinerator."""

from __future__ import annotations

import textwrap

from necro_prune.analyzer import DeadCodeAnalyzer
from necro_prune.incinerator import ASTIncinerator


def test_analyzer_detects_unused_function():
    code = textwrap.dedent(
        """
        def used_function():
            return 42

        def dead_function():
            return -1

        def main():
            print(used_function())
        """
    )
    analyzer = DeadCodeAnalyzer()
    dead = analyzer.analyze_source(code)
    dead_names = [d.name for d in dead]
    assert "dead_function" in dead_names
    assert "used_function" not in dead_names
    assert "main" not in dead_names


def test_incinerator_pruning():
    code = textwrap.dedent(
        """
        def dead_fn():
            pass

        def active_fn():
            return 100

        print(active_fn())
        """
    )
    incinerator = ASTIncinerator()
    pruned = incinerator.incinerate_source(code)
    assert "dead_fn" not in pruned
    assert "active_fn" in pruned
    assert "return 100" in pruned


def test_dunder_all_keeps_exports():
    code = textwrap.dedent(
        """
        __all__ = ["public_api"]

        def public_api():
            return 1

        def hidden_helper():
            return 2
        """
    )
    dead = DeadCodeAnalyzer().analyze_source(code)
    names = {d.name for d in dead}
    assert "public_api" not in names
    assert "hidden_helper" in names


def test_transitive_reachability_through_call_graph():
    code = textwrap.dedent(
        """
        def leaf():
            return 1

        def mid():
            return leaf()

        def main():
            return mid()

        def orphan():
            return 99
        """
    )
    dead = DeadCodeAnalyzer().analyze_source(code)
    names = {d.name for d in dead}
    assert names == {"orphan"}


def test_async_function_detection_and_prune():
    code = textwrap.dedent(
        """
        async def live_async():
            return 1

        async def dead_async():
            return 2

        def main():
            return live_async
        """
    )
    dead = DeadCodeAnalyzer().analyze_source(code)
    names = {d.name for d in dead}
    assert "dead_async" in names
    assert "live_async" not in names
    pruned = ASTIncinerator().incinerate_source(code)
    assert "dead_async" not in pruned
    assert "live_async" in pruned


def test_unused_import_and_assign_pruned():
    code = textwrap.dedent(
        """
        import os
        import sys

        DEAD_CONST = 3
        LIVE = 1

        def main():
            return LIVE + sys.version_info[0]
        """
    )
    dead = DeadCodeAnalyzer().analyze_source(code)
    names = {d.name for d in dead}
    assert "os" in names
    assert "DEAD_CONST" in names
    assert "sys" not in names
    assert "LIVE" not in names
    pruned = ASTIncinerator().incinerate_source(code)
    assert "import os" not in pruned
    assert "DEAD_CONST" not in pruned
    assert "sys" in pruned


def test_class_kept_when_instantiated():
    code = textwrap.dedent(
        """
        class Live:
            def method(self):
                return 1

        class Dead:
            def method(self):
                return 2

        def main():
            return Live()
        """
    )
    dead = DeadCodeAnalyzer().analyze_source(code)
    names = {d.name for d in dead}
    assert "Dead" in names
    assert "Live" not in names


def test_module_level_call_seeds_without_main():
    code = textwrap.dedent(
        """
        def helper():
            return 5

        def unused():
            return 0

        print(helper())
        """
    )
    dead = DeadCodeAnalyzer().analyze_source(code)
    names = {d.name for d in dead}
    assert "unused" in names
    assert "helper" not in names


def test_syntax_error_returns_empty():
    assert DeadCodeAnalyzer().analyze_source("def broken(:\n") == []


def test_extra_keep_preserves_symbol():
    code = textwrap.dedent(
        """
        def plugin_hook():
            return "hook"

        def noise():
            return 0
        """
    )
    pruned = ASTIncinerator().incinerate_source(code, extra_keep=["plugin_hook"])
    assert "plugin_hook" in pruned
    assert "noise" not in pruned
