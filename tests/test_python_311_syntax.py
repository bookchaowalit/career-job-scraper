"""Every tracked Python file must parse on Python 3.11, the CI and hosted-capture runtime.

generate_insights.py once used PEP 701 f-strings (quote reuse, Python 3.12+) and could not
even be imported on 3.11; ruff only caught it once pyproject.toml declared requires-python.
"""
import ast
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _tracked_python_files():
    out = subprocess.run(
        ["git", "ls-files", "*.py"], cwd=ROOT, capture_output=True, text=True, check=False
    ).stdout.split()
    return out or [str(p.relative_to(ROOT)) for p in ROOT.rglob("*.py") if ".venv" not in p.parts]


@pytest.mark.parametrize("rel", _tracked_python_files())
def test_parses_with_python_311_grammar(rel):
    source = (ROOT / rel).read_text(encoding="utf-8")
    ast.parse(source, filename=rel, feature_version=(3, 11))
