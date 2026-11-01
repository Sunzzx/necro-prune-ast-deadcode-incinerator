"""
necro_prune.cli
===============
CLI tool for necro-prune-ast-deadcode-incinerator.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .analyzer import DeadCodeAnalyzer
from .incinerator import ASTIncinerator


def main():
    parser = argparse.ArgumentParser(
        prog="necro-prune",
        description="AST-level dead code analysis and surgical incinerator.",
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="Subcommands")

    # audit
    audit_p = subparsers.add_parser("audit", help="Audit a python file or directory for dead symbols")
    audit_p.add_argument("path", type=Path, help="File or directory to audit")

    # incinerate
    incin_p = subparsers.add_parser("incinerate", help="Prune dead code from a file")
    incin_p.add_argument("path", type=Path, help="Target Python file")
    incin_p.add_argument("--inplace", "-i", action="store_true", help="Modify file in-place")

    args = parser.parse_args()

    if not args.subcommand or args.subcommand == "audit":
        target = getattr(args, "path", Path("."))
        analyzer = DeadCodeAnalyzer()
        files = [target] if target.is_file() else list(target.rglob("*.py"))

        total_dead = 0
        print(f"🔥 NECRO-PRUNE AST INCINERATOR: Auditing {len(files)} file(s) in {target}")
        for f in files:
            dead = analyzer.analyze_file(f)
            if dead:
                total_dead += len(dead)
                print(f"\n📄 {f.relative_to(target) if target.is_dir() else f.name}:")
                for s in dead:
                    print(f"  • Line {s.lineno}: Unused {s.kind} '{s.name}'")

        print(f"\n[Summary] Found {total_dead} dead symbol(s) across {len(files)} file(s).")
        sys.exit(0)

    elif args.subcommand == "incinerate":
        target = args.path
        if not target.is_file() or target.suffix != ".py":
            print(f"Error: {target} is not a valid Python file.", file=sys.stderr)
            sys.exit(1)

        incinerator = ASTIncinerator()
        result = incinerator.incinerate_file(target, inplace=args.inplace)
        if args.inplace:
            print(f"Successfully pruned dead code in-place: {target}")
        else:
            print(result)


if __name__ == "__main__":
    main()
