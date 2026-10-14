"""Printing it so the answer arrives before the explanation."""

from __future__ import annotations

import os
import sys
from collections.abc import Sequence

from .graph import Graph
from .model import Finding

BOLD, DIM, RESET = "\033[1m", "\033[2m", "\033[0m"
RED, AMBER, GREEN, BLUE = (
    "\033[38;5;203m", "\033[38;5;214m", "\033[38;5;35m", "\033[38;5;39m",
)

#: Worst first, and the mark says how much to care without reading the number.
MARKS = ((20.0, "!!", RED), (6.0, "! ", AMBER), (0.0, "· ", DIM))


def colour() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("MAPPER_COLOR") == "always":
        return True
    return sys.stdout.isatty()


def paint(text: str, style: str) -> str:
    return f"{style}{text}{RESET}" if colour() else text


def mark(severity: float) -> tuple[str, str]:
    for threshold, symbol, style in MARKS:
        if severity >= threshold:
            return symbol, style
    return "· ", DIM


def summary(graph: Graph, *, covered: int, commits: int) -> list[str]:
    cycles = graph.cycles()
    bits = [
        f"{len(graph)} modules",
        f"depth {graph.depth()}",
        f"{len(cycles)} cycle{'s' if len(cycles) != 1 else ''}",
    ]
    bits.append(f"{covered} with coverage" if covered else "no coverage report")
    if commits:
        bits.append(f"{commits} commits read")
    return ["  " + paint(" · ".join(bits), DIM)]


def findings_lines(found: Sequence[Finding], *, limit: int = 10, verbose: bool = False) -> list[str]:
    if not found:
        return ["  " + paint("nothing worth reporting — this is a tidy project", GREEN)]

    out: list[str] = []
    for finding in found[:limit]:
        symbol, style = mark(finding.severity)
        out.append(f"  {paint(symbol, style)} {paint(finding.subject, BOLD)}")
        out.append(f"     {finding.headline}")
        if verbose and finding.detail:
            out.append(f"     {paint(finding.detail, DIM)}")
        if finding.advice:
            out.append(f"     {paint('→ ' + finding.advice, style)}")
        out.append("")
    if len(found) > limit:
        out.append("  " + paint(f"{len(found) - limit} more — pass --all", DIM))
    return out


def table(graph: Graph, *, limit: int = 15) -> list[str]:
    """The numbers, for when someone wants to argue with the ranking."""
    head = (
        f"  {'module':<30} {'Ca':>3} {'Ce':>3} {'I':>5} {'A':>5} {'D':>5} {'cov':>5}"
    )
    out = [paint(head, DIM)]
    for node in graph.ranked()[:limit]:
        coverage = node.module.coverage
        shown = f"{coverage:.0%}" if coverage is not None else "—"
        tint = ""
        if coverage is not None and node.fan_in >= 2 and coverage < 0.5:
            tint = RED
        out.append(
            f"  {paint(node.name[:30].ljust(30), tint)} {node.fan_in:3} {node.fan_out:3} "
            f"{node.instability:5.2f} {node.abstractness:5.2f} {node.distance:5.2f} {shown:>5}"
        )
    return out


def legend() -> list[str]:
    return [
        paint("  Ca  how many modules depend on this one", DIM),
        paint("  Ce  how many it depends on", DIM),
        paint("  I   instability, Ce/(Ca+Ce) — 0 means nothing can force it to change", DIM),
        paint("  A   abstractness — share of its classes that are abstract", DIM),
        paint("  D   |A+I-1| — distance from the balance between the two", DIM),
    ]
