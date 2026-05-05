from __future__ import annotations

import importlib
import inspect

import pytest

import registers
import registers.cron as cron_module
from registers import (
    cron_get_registry,
    cron_register,
    cron_reset_registry,
    cron_run,
    cron_schedule,
)


@pytest.fixture()
def registers_module():
    return registers


def test_cron_submodule_import_path_is_preserved(registers_module) -> None:
    daemon_module = importlib.import_module("registers.cron.daemon")

    assert inspect.ismodule(registers_module.cron)
    assert registers_module.cron is cron_module
    assert daemon_module.__name__ == "registers.cron.daemon"


def test_cron_convenience_imports_match_cron_module(registers_module) -> None:
    assert cron_schedule is cron_module.cron
    assert cron_register is cron_module.register
    assert cron_run is cron_module.run
    assert cron_get_registry is cron_module.get_registry
    assert cron_reset_registry is cron_module.reset_registry
