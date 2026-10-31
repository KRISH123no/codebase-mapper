"""A local page for people who would rather not use a terminal.

`http.server` from the standard library, bound to localhost and nothing else.
A tool that reads arbitrary directories must not be reachable from the
network, and the easiest way to guarantee that is to never offer the choice.

Nothing here executes the project it is given. The analysis is the same `ast`
parse the command line does, so pointing this at a stranger's repository is
as safe as reading it.
"""

from __future__ import annotations

import html
import threading
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .coverage import load
from .findings import collect
from .graph import Graph
from .history import commits, couplings, undeclared
from .html import render
from .parse import parse

#: Localhost only. Not configurable, deliberately.
HOST = "127.0.0.1"


def analyse(path: str, *, use_git: bool = True) -> str:
    """Run the whole thing and return the report, or an explanation."""
    root = Path(path).expanduser()
    if not root.is_dir():
        return _message("Not a folder", f"{root} is not a directory on this machine.")

    project = parse(root)
    modules = project.source
    if not modules:
        return _message(
            "No Python here",
            f"Nothing under {root} parsed as a Python module. "
            "This reads Python only.",
        )

    covered, _ = load(modules, root)
    graph = Graph(modules)

    log = commits(root) if use_git else []
    coupling = undeclared(couplings(log), modules, root) if log else []

    return render(
        graph, collect(graph), root=str(root.resolve()),
        covered=covered, commits=len(log),
    )


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        url = urlparse(self.path)
        if url.path == "/":
            self._send(FORM.format(error="", path=""))
            return
        if url.path == "/map":
            query = parse_qs(url.query)
            path = (query.get("path") or [""])[0].strip()
            if not path:
                self._send(FORM.format(error="", path=""))
                return
            try:
                body = analyse(path, use_git="nogit" not in query)
            except Exception:
                traceback.print_exc()
                body = _message(
                    "That did not work",
                    "Something went wrong reading that folder. The terminal "
                    "running this has the details.",
                )
            self._send(body)
            return
        self.send_error(404)

    def log_message(self, *_args) -> None:
        """Quiet. The page is the output, not the access log."""

    def _send(self, body: str) -> None:
        payload = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def _message(title: str, detail: str) -> str:
    return FORM.format(
        error=f'<div class="error"><strong>{html.escape(title)}</strong>'
              f"<p>{html.escape(detail)}</p></div>",
        path="",
    )


def serve(port: int = 8000, *, open_browser: bool = True) -> int:
    server = ThreadingHTTPServer((HOST, port), Handler)
    where = f"http://{HOST}:{port}"
    print(f"codebase-mapper on {where}")
    print("  reading only — it never runs the code you point it at")
    print("  ctrl-c to stop")
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(where)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        server.server_close()
    return 0


FORM = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>codebase-mapper</title>
<style>
  * {{ box-sizing: border-box }}
  body {{ margin:0; background:#000; color:#e6edf3; min-height:100vh;
    display:flex; align-items:center; justify-content:center; padding:24px;
    font:15px/1.6 ui-monospace, SFMono-Regular, Menlo, monospace }}
  main {{ width:100%; max-width:620px }}
  h1 {{ font-size:22px; margin:0 0 6px; font-weight:600 }}
  p.sub {{ color:#8b949e; margin:0 0 32px }}
  label {{ display:block; color:#8b949e; font-size:12px; text-transform:uppercase;
    letter-spacing:.08em; margin-bottom:8px }}
  input[type=text] {{ width:100%; padding:13px 15px; background:#0d1117; color:#e6edf3;
    border:1px solid #30363d; border-radius:8px; font:inherit }}
  input[type=text]:focus {{ outline:none; border-color:#58a6ff }}
  .row {{ display:flex; gap:10px; margin-top:14px; align-items:center }}
  button {{ padding:13px 24px; background:#e6edf3; color:#000; border:0;
    border-radius:8px; font:inherit; font-weight:600; cursor:pointer }}
  button:hover {{ background:#fff }}
  .check {{ color:#8b949e; font-size:13px; display:flex; align-items:center; gap:6px }}
  .hint {{ color:#6b7684; font-size:13px; margin-top:28px; line-height:1.8 }}
  .hint code {{ color:#8b949e }}
  .error {{ background:#1a0f0f; border:1px solid #5c2626; border-radius:8px;
    padding:14px 16px; margin-bottom:24px }}
  .error strong {{ color:#f85149 }}
  .error p {{ margin:4px 0 0; color:#8b949e; font-size:13px }}
</style></head><body><main>
  <h1>codebase-mapper</h1>
  <p class="sub">What is load-bearing in a codebase, and what is untested.</p>
  {error}
  <form action="/map" method="get">
    <label for="path">Path to a Python project on this machine</label>
    <input type="text" id="path" name="path" value="{path}" autofocus
           placeholder="/Users/you/code/your-project">
    <div class="row">
      <button type="submit">Map it</button>
      <label class="check"><input type="checkbox" name="nogit" value="1"> skip git history</label>
    </div>
  </form>
  <p class="hint">
    Reads the source with Python's own parser and never runs it.<br>
    For the strongest finding, generate coverage first:
    <code>coverage run -m pytest &amp;&amp; coverage xml</code><br>
    Runs on this machine only — nothing is uploaded anywhere.
  </p>
</main></body></html>
"""
