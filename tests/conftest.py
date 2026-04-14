from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from registers.db import dispose_all


@pytest.fixture(autouse=True)
def _dispose_engines():
    """Ensure engine connections are cleaned up between every test."""
    yield
    dispose_all()


def db_url(tmp_path: Path, name: str = "test") -> str:
    return f"sqlite:///{tmp_path / f'{name}.db'}"
