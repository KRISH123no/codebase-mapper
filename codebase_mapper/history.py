"""What changes together, which is the coupling nobody declared.

An import graph shows the dependencies someone wrote down. Git shows the ones
that are real. If two files are edited in the same commit four times out of
five and neither imports the other, they are coupled — through a shared
database column, a protocol both ends implement, a constant copied into both.

That is where the surprises in an unfamiliar codebase live, and no
import-based tool can see it, because there is nothing in the source to see.

Pure `git log` and arithmetic. The repository is never modified.
"""

from __future__ import annotations

import subprocess
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class Coupling:
    left: str
    right: str
    together: int
    #: Commits touching either one.
    either: int

    @property
    def strength(self) -> float:
        """How often "one changed" meant "both changed"."""
        return self.together / self.either if self.either else 0.0


def commits(root: str | Path, *, limit: int = 2000) -> list[list[str]]:
    """Each commit as the list of files it touched.

    Merges are excluded: a merge commit touches everything both branches did
    and would couple every file to every other file.
    """
    try:
        done = subprocess.run(
            ["git", "-C", str(root), "log", "--no-merges", "--name-only",
             "--pretty=format:%x00", f"-n{limit}"],
            capture_output=True, text=True, timeout=60, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if done.returncode != 0:
        return []

    out = []
    for block in done.stdout.split("\x00"):
        files = [line.strip() for line in block.splitlines() if line.strip()]
        if files:
            out.append(files)
    return out


def couplings(
    changes: list[list[str]],
    *,
    min_together: int = 3,
    min_strength: float = 0.6,
    max_files: int = 25,
) -> list[Coupling]:
    """Pairs of files that keep changing together.

    Commits touching more than ``max_files`` are dropped: a reformat or a
    rename sweep touches everything at once and would couple the whole
    project. They say nothing about design.
    """
    seen: dict[str, int] = defaultdict(int)
    pairs: dict[tuple[str, str], int] = defaultdict(int)

    for files in changes:
        unique = sorted(set(files))
        if len(unique) > max_files or len(unique) < 2:
            for name in unique:
                seen[name] += 1
            continue
        for name in unique:
            seen[name] += 1
        for i, left in enumerate(unique):
            for right in unique[i + 1:]:
                pairs[(left, right)] += 1

    found = []
    for (left, right), together in pairs.items():
        if together < min_together:
            continue
        either = seen[left] + seen[right] - together
        coupling = Coupling(left, right, together, either)
        if coupling.strength >= min_strength:
            found.append(coupling)

    return sorted(found, key=lambda c: (-c.strength, -c.together))


def undeclared(found: list[Coupling], modules: dict, root: str | Path) -> list[Coupling]:
    """Only the couplings the imports do not already explain.

    Two files that change together *and* import each other is not news — that
    is the dependency working as intended.
    """
    root = Path(root)
    by_path: dict[str, str] = {}
    for name, module in modules.items():
        try:
            by_path[str(Path(module.path).relative_to(root))] = name
        except ValueError:
            by_path[module.path] = name

    out = []
    for coupling in found:
        left = by_path.get(coupling.left)
        right = by_path.get(coupling.right)
        if left is None or right is None:
            continue  # not a module we parsed: a config file, a template
        if right in modules[left].imports or left in modules[right].imports:
            continue
        out.append(coupling)
    return out
