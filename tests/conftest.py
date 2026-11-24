import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

FIXTURES = os.path.join(ROOT, "tests", "fixtures", "projects")


@pytest.fixture
def fixtures_dir() -> str:
    return FIXTURES


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.delenv("NO_COLOR", raising=False)
