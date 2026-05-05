from __future__ import annotations

import pytest

import registers
import registers.cli as cli_module
from registers import get_registry, register, reset_registry, run


@pytest.fixture()
def registers_module():
    return registers


def test_cli_convenience_imports_match_cli_module(registers_module) -> None:
    assert registers_module.cli is cli_module
    assert register is cli_module.register
    assert run is cli_module.run
    assert get_registry is cli_module.get_registry
    assert reset_registry is cli_module.reset_registry
