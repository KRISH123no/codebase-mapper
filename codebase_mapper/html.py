"""A single file you can open, send, or attach to something.

Deliberately not a force-directed graph. Four hundred nodes in a spring
layout is a hairball: it looks like architecture, communicates nothing, and
is the reason this genre of tool gets opened once.

What a person actually wants on arriving at an unfamiliar codebase is reading
order. So the map here is **layered**: modules that depend on nothing sit at
the bottom, and each layer above depends only on the ones below it. Read it
upwards and you are reading the project in the order it was built.

No CDN, no JavaScript, no network. One file that works offline forever, which
is the only kind of artifact worth sending someone.
"""

from __future__ import annotations

import html
from datetime import datetime

from .graph import Graph
from .model import Finding

#: Matches the terminal: the mark tells you how much to care.
BANDS = ((20.0, "high"), (6.0, "medium"), (0.0, "low"))


def band(severity: float) -> str:
    for threshold, name in BANDS:
        if severity >= threshold:
            return name
    return "low"


def layers(graph: Graph) -> list[list[str]]:
    """Modules grouped so that each layer depends only on the ones below it.

    A module's layer is one above the deepest thing it depends on. Anything
    caught in a cycle has no such answer, so the whole cycle is placed one
    above its deepest external dependency and marked — the alternative is
    looping forever.
    """
    depth: dict[str, int] = {}
    resolving: set[str] = set()

    def level(name: str) -> int:
        if name in depth:
            return depth[name]
        if name in resolving:
            return 0  # inside a cycle; broken here and flagged separately
        resolving.add(name)
        children = graph.edges.get(name, set())
        depth[name] = 1 + max((level(c) for c in children), default=-1)
        resolving.discard(name)
        return depth[name]

    for name in graph.edges:
        level(name)

    grouped: dict[int, list[str]] = {}
    for name, value in depth.items():
        grouped.setdefault(value, []).append(name)
    return [sorted(grouped[k]) for k in sorted(grouped)]


def render(
    graph: Graph,
    findings: list[Finding],
    *,
    root: str,
    covered: int = 0,
    commits: int = 0,
) -> str:
    cycles = graph.cycles()
    in_cycle = {name for group in cycles for name in group}
    stack = layers(graph)

    facts = [
        f"{len(graph)} modules",
        f"{len(stack)} layers",
        f"{len(cycles)} cycle{'s' if len(cycles) != 1 else ''}",
        f"{covered} with coverage" if covered else "no coverage report",
    ]
    if commits:
        facts.append(f"{commits} commits read")

    return _PAGE.format(
        root=html.escape(root),
        when=datetime.now().strftime("%-d %B %Y"),
        facts=" · ".join(html.escape(f) for f in facts),
        findings=_findings(findings),
        map=_map(graph, stack, in_cycle),
        table=_table(graph),
    )


def _findings(findings: list[Finding]) -> str:
    if not findings:
        return '<p class="empty">Nothing worth reporting — this is a tidy project.</p>'
    out = []
    for finding in findings:
        advice = (
            f'<p class="advice">{html.escape(finding.advice)}</p>'
            if finding.advice else ""
        )
        detail = (
            f'<p class="detail">{html.escape(finding.detail)}</p>'
            if finding.detail else ""
        )
        out.append(
            f'<article class="finding {band(finding.severity)}">'
            f'<h3>{html.escape(finding.subject)}</h3>'
            f'<p class="headline">{html.escape(finding.headline)}</p>'
            f"{detail}{advice}</article>"
        )
    return "\n".join(out)


def _map(graph: Graph, stack: list[list[str]], in_cycle: set[str]) -> str:
    """Bottom layer first in the data, top layer first on the page — because
    you read downward and dependencies should arrive before their users."""
    out = []
    for index, names in reversed(list(enumerate(stack))):
        chips = []
        for name in names:
            node = graph.nodes[name]
            classes = ["chip"]
            if name in in_cycle:
                classes.append("cycle")
            coverage = node.module.coverage
            if coverage is not None and coverage < 0.5 and node.fan_in >= 2:
                classes.append("risk")
            title = f"{node.fan_in} depend on it · depends on {node.fan_out}"
            if coverage is not None:
                title += f" · {coverage:.0%} covered"
            chips.append(
                f'<span class="{" ".join(classes)}" title="{html.escape(title)}">'
                f'{html.escape(name)}<em>{node.fan_in}</em></span>'
            )
        label = "depends on nothing" if index == 0 else f"layer {index}"
        out.append(
            f'<div class="layer"><div class="tier">{html.escape(label)}</div>'
            f'<div class="chips">{"".join(chips)}</div></div>'
        )
    return "\n".join(out)


def _table(graph: Graph) -> str:
    rows = []
    for node in graph.ranked():
        coverage = node.module.coverage
        shown = f"{coverage:.0%}" if coverage is not None else "—"
        risky = ' class="risk"' if coverage is not None and coverage < 0.5 and node.fan_in >= 2 else ""
        rows.append(
            f"<tr{risky}><td>{html.escape(node.name)}</td><td>{node.fan_in}</td>"
            f"<td>{node.fan_out}</td><td>{node.instability:.2f}</td>"
            f"<td>{node.abstractness:.2f}</td><td>{node.distance:.2f}</td>"
            f"<td>{shown}</td></tr>"
        )
    return "\n".join(rows)


_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>codebase-mapper — {root}</title>
<style>
  :root {{
    color-scheme: light dark;
    --bg:#0d1117; --card:#161b22; --line:#30363d; --text:#e6edf3; --dim:#8b949e;
    --high:#f85149; --med:#d29922; --low:#8b949e; --ok:#3fb950;
  }}
  @media (prefers-color-scheme: light) {{
    :root {{ --bg:#fff; --card:#f6f8fa; --line:#d0d7de; --text:#1f2328; --dim:#656d76; }}
  }}
  * {{ box-sizing:border-box }}
  body {{ margin:0; background:var(--bg); color:var(--text); padding:32px 24px 64px;
    font:14px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace; max-width:1100px;
    margin-inline:auto }}
  h1 {{ font-size:19px; margin:0 }}
  .sub {{ color:var(--dim); margin:4px 0 32px }}
  h2 {{ font-size:12px; color:var(--dim); text-transform:uppercase; letter-spacing:.08em;
    margin:36px 0 12px; font-weight:500 }}
  .finding {{ background:var(--card); border:1px solid var(--line); border-left-width:3px;
    border-radius:7px; padding:12px 16px; margin-bottom:10px }}
  .finding.high {{ border-left-color:var(--high) }}
  .finding.medium {{ border-left-color:var(--med) }}
  .finding.low {{ border-left-color:var(--low) }}
  .finding h3 {{ font-size:14px; margin:0 0 3px; font-weight:600 }}
  .headline {{ margin:0; color:var(--text) }}
  .detail, .advice {{ margin:6px 0 0; color:var(--dim); font-size:13px }}
  .advice {{ color:var(--text) }}
  .advice::before {{ content:"→ "; color:var(--dim) }}
  .empty {{ color:var(--ok) }}
  .layer {{ display:flex; gap:14px; align-items:baseline; padding:8px 0;
    border-bottom:1px solid var(--line) }}
  .layer:last-child {{ border-bottom:none }}
  .tier {{ color:var(--dim); font-size:11px; min-width:130px; text-align:right;
    text-transform:uppercase; letter-spacing:.06em }}
  .chips {{ display:flex; flex-wrap:wrap; gap:6px }}
  .chip {{ background:var(--card); border:1px solid var(--line); border-radius:5px;
    padding:3px 8px; font-size:12px; white-space:nowrap }}
  .chip em {{ font-style:normal; color:var(--dim); margin-left:6px }}
  .chip.cycle {{ border-color:var(--med) }}
  .chip.risk {{ border-color:var(--high) }}
  table {{ width:100%; border-collapse:collapse; font-size:12px }}
  th,td {{ text-align:right; padding:5px 10px; border-bottom:1px solid var(--line) }}
  th:first-child, td:first-child {{ text-align:left }}
  th {{ color:var(--dim); font-weight:500 }}
  tr.risk td {{ color:var(--high) }}
  .note {{ color:var(--dim); font-size:12px; margin-top:28px; line-height:1.7 }}
</style></head><body>
<h1>{root}</h1>
<p class="sub">{facts} · {when}</p>

<h2>Findings</h2>
{findings}

<h2>Structure</h2>
<p class="sub">Each layer depends only on the ones below it. The number on a module is how many
others depend on it. Amber means it is in a cycle, red means load-bearing and thinly tested.</p>
{map}

<h2>Metrics</h2>
<table>
<tr><th>module</th><th>Ca</th><th>Ce</th><th>I</th><th>A</th><th>D</th><th>cov</th></tr>
{table}
</table>

<p class="note">
Ca: how many modules depend on this one. Ce: how many it depends on.
I = Ce/(Ca+Ce), instability — 0 means nothing can force it to change.
A: the share of its classes that are abstract. D = |A+I-1|, distance from the balance between them.
<br><br>
These are measurements, not judgements. This report does not know whether the architecture suits
the problem, and anything described as a proxy is a hint to look, not a verdict.
</p>
</body></html>
"""
