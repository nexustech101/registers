from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import functionals.cli as cli
import pytest

import functionals.cron.daemon as daemon_module


@pytest.fixture()
def daemon() -> Any:
    cli.reset_registry()
    reloaded = importlib.reload(daemon_module)
    yield reloaded
    cli.reset_registry()


def test_daemon_main_supports_option_only_invocation(tmp_path: Path, daemon: Any) -> None:
    captured: dict[str, Any] = {}

    async def _fake_run_daemon(**kwargs):
        captured.update(kwargs)
        return None

    daemon.run_daemon = _fake_run_daemon

    code = daemon.main(
        [
            "--root",
            str(tmp_path),
            "--workers",
            "2",
            "--poll-interval",
            "0.5",
            "--webhook-host",
            "0.0.0.0",
            "--webhook-port",
            "9911",
        ]
    )

    assert code == 0
    assert captured["root"] == str(tmp_path)
    assert captured["workers"] == 2
    assert captured["poll_interval"] == 0.5
    assert captured["webhook_host"] == "0.0.0.0"
    assert captured["webhook_port"] == 9911


def test_daemon_main_supports_explicit_command(tmp_path: Path, daemon: Any) -> None:
    captured: dict[str, Any] = {}

    async def _fake_run_daemon(**kwargs):
        captured.update(kwargs)
        return None

    daemon.run_daemon = _fake_run_daemon

    code = daemon.main(["daemon", "--root", str(tmp_path), "--workers", "3"])
    assert code == 0
    assert captured["root"] == str(tmp_path)
    assert captured["workers"] == 3


def test_daemon_main_defaults_to_daemon_command(daemon: Any) -> None:
    calls = {"count": 0}

    async def _fake_run_daemon(**_kwargs):
        calls["count"] += 1
        return None

    daemon.run_daemon = _fake_run_daemon
    code = daemon.main([])
    assert code == 0
    assert calls["count"] == 1
