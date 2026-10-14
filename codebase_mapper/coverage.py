"""Which lines the test suite actually runs.

Coverage on its own is close to meaningless — "68% covered" tells you nothing
about whether the covered 68% is the part that matters. Laid over the
dependency graph it becomes the sharpest thing this tool says: *the module
nine others depend on is the one nobody tests.*

Cobertura XML is read because every runner emits it: `coverage xml` for
Python, and the same shape from Java, .NET and Go tooling. No dependency —
`xml.etree` ships with Python.
"""

from __future__ import annotations

import os
from pathlib import Path
from xml.etree import ElementTree

#: Where runners drop the report, in the order people actually have them.
CANDIDATES = ("coverage.xml", "cobertura.xml", "reports/coverage.xml", "htmlcov/coverage.xml")


def find_report(root: str | Path) -> Path | None:
    root = Path(root)
    for name in CANDIDATES:
        candidate = root / name
        if candidate.is_file():
            return candidate
    return None


def read(path: str | Path) -> dict[str, float]:
    """Map a source path to the fraction of its lines that were executed.

    Keys are whatever the report called the file; matching them to modules is
    `attach`'s problem, because reports disagree about whether paths are
    absolute, relative, or relative to a source root that is not the repo.
    """
    try:
        tree = ElementTree.parse(path)
    except (OSError, ElementTree.ParseError):
        return {}

    rates: dict[str, float] = {}
    for element in tree.iter("class"):
        filename = element.get("filename")
        if not filename:
            continue
        try:
            rates[filename] = float(element.get("line-rate", 0.0))
        except ValueError:
            continue
    return rates


def attach(modules: dict, rates: dict[str, float], root: str | Path) -> int:
    """Put a coverage figure on every module we can match. Returns how many.

    Matching is done from the right. A report may say `src/pkg/thing.py` while
    the module is at `/abs/repo/src/pkg/thing.py`, or the other way round, so
    the longest shared suffix of path segments wins — which is exact when it
    matches and silent when it does not, rather than guessing.
    """
    if not rates:
        return 0

    by_suffix: dict[tuple[str, ...], float] = {}
    for filename, rate in rates.items():
        parts = tuple(Path(filename).parts)
        by_suffix[parts] = rate

    matched = 0
    root = Path(root)
    for module in modules.values():
        parts = tuple(Path(module.path).parts)
        best: float | None = None
        best_length = 0
        for candidate, rate in by_suffix.items():
            length = _shared_suffix(parts, candidate)
            # One segment is just a filename; two means a directory agreed too.
            if length >= 2 and length > best_length:
                best, best_length = rate, length
        if best is not None:
            module.coverage = best
            matched += 1
    return matched


def _shared_suffix(left: tuple[str, ...], right: tuple[str, ...]) -> int:
    count = 0
    for a, b in zip(reversed(left), reversed(right), strict=False):
        if a != b:
            break
        count += 1
    return count


def load(modules: dict, root: str | Path, path: str | Path | None = None) -> tuple[int, Path | None]:
    """Find a report, read it, attach it. Returns (modules matched, report used)."""
    report = Path(path) if path else find_report(root)
    if report is None or not report.is_file():
        return 0, None
    return attach(modules, read(report), root), report


def ensure_report(root: str | Path) -> str:
    """What to run to produce one, for when there is nothing to read."""
    return "coverage run -m pytest && coverage xml" if os.name != "nt" else "coverage xml"
