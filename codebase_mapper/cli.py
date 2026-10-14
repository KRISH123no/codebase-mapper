"""`codebase-mapper <path>` — what is load-bearing, and what is untested."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .coverage import ensure_report, load
from .findings import collect
from .graph import Graph
from .history import commits, couplings, undeclared
from .parse import parse
from .report import BOLD, DIM, findings_lines, legend, paint, summary, table


def cmd_map(args) -> int:
    root = Path(args.path).expanduser().resolve()
    if not root.is_dir():
        print(f"not a directory: {root}")
        return 1

    project = parse(root)
    modules = project.modules if args.include_tests else project.source
    if not modules:
        print(f"no Python modules found under {root}")
        return 1

    covered, _report = load(modules, root, args.coverage)
    graph = Graph(modules)

    coupling = []
    log = []
    if not args.no_git:
        log = commits(root, limit=args.commits)
        coupling = undeclared(couplings(log), modules, root)

    found = collect(graph, coupling)

    print(paint(str(root), BOLD))
    print("\n".join(summary(graph, covered=covered, commits=len(log))))
    print()
    print("\n".join(findings_lines(found, limit=999 if args.all else args.limit,
                                   verbose=args.verbose)))

    if args.numbers:
        print("\n".join(table(graph)))
        print()
        print("\n".join(legend()))

    if not covered:
        print(paint(f"  no coverage report found — run `{ensure_report(root)}` "
                    "and the strongest finding becomes available", DIM))
    if project.unreadable:
        print(paint(f"  {len(project.unreadable)} file(s) could not be parsed", DIM))
    return 0


def cmd_numbers(args) -> int:
    args.numbers = True
    args.limit = 0
    return cmd_map(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codebase-mapper",
        description="what is load-bearing in this codebase, and what is untested",
    )
    parser.add_argument("--version", action="version", version=f"codebase-mapper {__version__}")
    sub = parser.add_subparsers(dest="command")

    def shared(p):
        p.add_argument("path", nargs="?", default=".", help="the project to read")
        p.add_argument("--coverage", help="path to a Cobertura XML report")
        p.add_argument("--include-tests", action="store_true",
                       help="count test modules as part of the graph")
        p.add_argument("--no-git", action="store_true", help="skip the history analysis")
        p.add_argument("--commits", type=int, default=2000)
        p.add_argument("-v", "--verbose", action="store_true")

    mapped = sub.add_parser("map", help="the findings, worst first")
    shared(mapped)
    mapped.add_argument("--limit", type=int, default=8)
    mapped.add_argument("--all", action="store_true")
    mapped.add_argument("--numbers", action="store_true", help="also print the metrics table")
    mapped.set_defaults(func=cmd_map)

    numbers = sub.add_parser("numbers", help="the metrics table, to argue with the ranking")
    shared(numbers)
    numbers.set_defaults(func=cmd_numbers, all=False)

    return parser


COMMANDS = ("map", "numbers")


def normalise(argv: list[str]) -> list[str]:
    """`codebase-mapper .` is what people type, so make it mean `map .`.

    Done before parsing, not after: argparse rejects an unknown subcommand by
    exiting, so there is no "after" to recover in.
    """
    if not argv:
        return ["map"]
    if argv[0] in COMMANDS or argv[0].startswith("-"):
        return argv
    return ["map", *argv]


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(normalise(list(sys.argv[1:] if argv is None else argv)))
    if not getattr(args, "func", None):
        parser.print_help()
        return 1
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130
