from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

import functionals.cron as cron
from functionals.cron.runtime import cron_matches, sync_project_jobs
from functionals.cron.state import clear_state_caches, cron_job_registry


@pytest.fixture(autouse=True)
def _reset_cron_state() -> None:
    cron.reset_registry()
    clear_state_caches()
    yield
    cron.reset_registry()
    clear_state_caches()


def test_register_interval_job_and_sync_to_state(tmp_path: Path) -> None:
    src = tmp_path / "src" / "app"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("", encoding="utf-8")
    (src / "jobs.py").write_text(
        "\n".join(
            [
                "from __future__ import annotations",
                "import functionals.cron as cron",
                "@cron.job(name='nightly-build', trigger=cron.interval(minutes=5), target='local_async')",
                "def nightly_build() -> str:",
                "    return 'ok'",
            ]
        ),
        encoding="utf-8",
    )

    package, loaded, jobs = sync_project_jobs(tmp_path)
    assert package == "app"
    assert loaded >= 2
    assert jobs == 1

    rows = cron_job_registry(tmp_path).filter(project_root=str(tmp_path), order_by="name")
    assert len(rows) == 1
    assert rows[0].name == "nightly-build"
    assert rows[0].trigger_kind == "interval"


def test_duplicate_job_name_raises() -> None:
    @cron.job(name="sync", trigger=cron.interval(seconds=10))
    def one() -> None:
        return None

    with pytest.raises(ValueError, match="already registered"):
        @cron.job(name="sync", trigger=cron.interval(seconds=20))
        def two() -> None:
            return None


def test_event_validation_and_cron_matching() -> None:
    with pytest.raises(ValueError):
        cron.event("file_change", paths=[])

    with pytest.raises(ValueError):
        cron.event("webhook", path="deploy")

    trigger = cron.event("webhook", path="/deploy", token="abc")
    assert trigger.kind == "webhook"

    now = datetime(2026, 1, 1, 2, 0)
    assert cron_matches("0 2 * * *", now) is True
    assert cron_matches("5 2 * * *", now) is False
