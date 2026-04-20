from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from functionals.cron.state import clear_state_caches, cron_event_registry, cron_run_registry
from functionals.cron.workspace import (
    ensure_workspace,
    list_workflows,
    register_workflow,
    run_registered_workflow,
)


@pytest.fixture(autouse=True)
def _clear_workspace_state() -> None:
    clear_state_caches()
    yield
    clear_state_caches()


def test_ensure_workspace_creates_expected_structure(tmp_path: Path) -> None:
    result = ensure_workspace(tmp_path)
    assert result.root == tmp_path
    assert (tmp_path / "ops" / "workflows" / "cron").exists()
    assert (tmp_path / "ops" / "workflows" / "windows").exists()
    assert (tmp_path / "ops" / "workflows" / "ci").exists()
    assert (tmp_path / "src" / "app" / "ops" / "jobs" / "__init__.py").exists()
    assert len(result.created) >= 1


def test_register_and_list_workflow(tmp_path: Path) -> None:
    ensure_workspace(tmp_path)
    workflow_file = tmp_path / "ops" / "workflows" / "ci" / "deploy.yml"
    workflow_file.write_text("name: deploy\n", encoding="utf-8")

    row = register_workflow(
        root=tmp_path,
        name="deploy",
        file_path=str(workflow_file),
        target="github_actions",
        job_name="nightly-build",
        metadata={"team": "platform"},
    )
    assert row.name == "deploy"
    assert row.job_name == "nightly-build"
    assert row.target == "github_actions"

    rows = list_workflows(tmp_path)
    assert len(rows) == 1
    assert rows[0].name == "deploy"


def test_run_registered_workflow_job_mode_queues_event(tmp_path: Path) -> None:
    ensure_workspace(tmp_path)
    workflow_file = tmp_path / "ops" / "workflows" / "cron" / "build.cron"
    workflow_file.write_text("* * * * *\n", encoding="utf-8")

    register_workflow(
        root=tmp_path,
        name="build-workflow",
        file_path=str(workflow_file),
        target="linux_cron",
        job_name="build-job",
    )
    result = run_registered_workflow(root=tmp_path, name="build-workflow", payload={"sha": "abc"})
    assert result.status == "success"
    assert result.kind == "job"
    assert result.event_id is not None

    events = cron_event_registry(tmp_path).filter(project_root=str(tmp_path), order_by="-id", limit=1)
    assert events
    assert events[0].job_name == "build-job"
    assert events[0].source == "workflow"


def test_run_registered_workflow_command_mode_records_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ensure_workspace(tmp_path)
    workflow_file = tmp_path / "ops" / "workflows" / "ci" / "command.yml"
    workflow_file.write_text("name: cmd\n", encoding="utf-8")

    register_workflow(
        root=tmp_path,
        name="cmd-workflow",
        file_path=str(workflow_file),
        command="echo deploy",
    )

    def _fake_run(argv, cwd, capture_output, text):
        assert capture_output is True
        assert text is True
        return SimpleNamespace(returncode=0, stdout="ok\n", stderr="")

    monkeypatch.setattr("functionals.cron.workspace.subprocess.run", _fake_run)

    result = run_registered_workflow(root=tmp_path, name="cmd-workflow")
    assert result.status == "success"
    assert result.kind == "command"
    assert result.exit_code == 0
    assert result.stdout == "ok"

    runs = cron_run_registry(tmp_path).filter(project_root=str(tmp_path), order_by="-id", limit=1)
    assert runs
    assert runs[0].job_name == "workflow:cmd-workflow"
    assert runs[0].status == "success"
