"""The local page. The binding address matters more than the markup."""

import threading
import urllib.request
from http.server import ThreadingHTTPServer

import pytest
from conftest import project

from codebase_mapper.server import HOST, Handler, analyse


def test_it_binds_to_localhost_and_nothing_else():
    """A tool that reads arbitrary directories must not be on the network.
    The easiest way to guarantee that is to never offer the choice."""
    assert HOST == "127.0.0.1"


def test_a_real_project_produces_a_report(tiny):
    out = analyse(str(tiny), use_git=False)
    assert "<h2>Findings</h2>" in out and "<h2>Structure</h2>" in out


def test_a_path_that_is_not_a_folder_explains_itself(tmp_path):
    out = analyse(str(tmp_path / "nope"), use_git=False)
    assert "Not a folder" in out


def test_a_folder_with_no_python_explains_itself(tmp_path):
    (tmp_path / "notes.txt").write_text("hello")
    out = analyse(str(tmp_path), use_git=False)
    assert "No Python here" in out


def test_a_path_cannot_inject_markup(tmp_path):
    """The path comes from a query string, which anyone can write."""
    out = analyse("<script>alert(1)</script>", use_git=False)
    assert "<script>alert(1)</script>" not in out
    assert "&lt;script&gt;" in out


def test_the_home_page_offers_the_form(tiny):
    out = analyse(str(tiny / "nope"), use_git=False)
    assert 'name="path"' in out, "an error still shows the form to try again"


# ------------------------------------------------------------- over HTTP


@pytest.fixture
def running():
    server = ThreadingHTTPServer((HOST, 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://{HOST}:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def get(url: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        return error.code, ""


def test_the_form_is_served(running):
    status, body = get(running + "/")
    assert status == 200 and "codebase-mapper" in body


def test_an_empty_path_returns_the_form_rather_than_an_error(running):
    status, body = get(running + "/map?path=")
    assert status == 200 and 'name="path"' in body


def test_mapping_a_project_over_http(running, tiny):
    from urllib.parse import quote

    status, body = get(f"{running}/map?path={quote(str(tiny))}&nogit=1")
    assert status == 200
    assert "<h2>Findings</h2>" in body and "4 modules" in body


def test_an_unknown_route_is_a_404(running):
    status, _ = get(running + "/whatever")
    assert status == 404


def test_the_page_reports_hidden_coupling_too(tmp_path, monkeypatch):
    """The git analysis was being computed and then thrown away, so the page
    silently dropped one of the three headline findings."""
    import codebase_mapper.server as server
    from codebase_mapper.history import Coupling

    project(tmp_path, {
        "pkg/__init__.py": "", "pkg/a.py": "x = 1\n", "pkg/b.py": "y = 1\n",
    })
    monkeypatch.setattr(server, "commits", lambda *a, **k: [["pkg/a.py", "pkg/b.py"]] * 9)
    monkeypatch.setattr(
        server, "undeclared",
        lambda *a, **k: [Coupling("pkg/a.py", "pkg/b.py", together=9, either=10)],
    )
    out = server.analyse(str(tmp_path), use_git=True)
    assert "pkg/a.py + pkg/b.py" in out
