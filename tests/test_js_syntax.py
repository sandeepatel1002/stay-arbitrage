"""Frontend JS is syntax-checked with a real compiler — 0-console-error gate (spec §6).

Prefers node --check (a true JS engine parse); falls back to the esprima parser.
Skips silently ONLY if neither is installed.
"""
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

STATIC_INDEX = Path(__file__).resolve().parent.parent / "static" / "index.html"


def _script_src() -> str:
    html = STATIC_INDEX.read_text(encoding="utf-8")
    match = re.search(r"<script>(.*?)</script>", html, re.S)
    assert match, "inline <script> not found in index.html"
    return match.group(1)


def test_inline_js_parses_clean():
    js = _script_src()
    node = shutil.which("node")
    if node:
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
            fh.write(js)
            path = fh.name
        result = subprocess.run([node, "--check", path], capture_output=True, text=True)
        assert result.returncode == 0, "inline JS has syntax errors: " + result.stderr
        return

    import esprima  # pure-python fallback parser

    esprima.parseScript(js)
