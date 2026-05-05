from __future__ import annotations

import pytest

import registers
import registers.db as db_module
from registers import DatabaseRegistry, database_registry


@pytest.fixture()
def registers_module():
    return registers


def test_db_convenience_imports_match_db_module(registers_module) -> None:
    assert registers_module.db is db_module
    assert DatabaseRegistry is db_module.DatabaseRegistry
    assert database_registry is db_module.database_registry
