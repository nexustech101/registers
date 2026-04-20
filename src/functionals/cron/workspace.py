"""
Workspace helpers for organizing and running registered DevOps workflow files.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Any

from functionals.cron.state import (
    CronWorkflowRecord,
    create_event,
    cron_workflow_registry,
    parse_json,
    record_run,
    resolve_root,
    utc_now,
)


@dataclass(frozen=True)
class WorkspaceResult:
    root: Path
    created: tuple[Path, ...]
    existing: tuple[Path, ...]


@dataclass(frozen=True)
class WorkflowExecutionResult:
    kind: str
    status: str
    message: str
    event_id: int | None = None
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""


def ensure_workspace(root: str | Path = ".") -> WorkspaceResult:
    root_path = resolve_root(root)
    layout = [
        root_path / "ops",
        root_path / "ops" / "workflows",
        root_path / "ops" / "workflows" / "cron",
        root_path / "ops" / "workflows" / "windows",
        root_path / "ops" / "workflows" / "ci",
        root_path / "ops" / "scripts",
        root_path / "src" / "app" / "ops",
        root_path / "src" / "app" / "ops" / "jobs",
    ]
    created: list[Path] = []
    existing: list[Path] = []
    for path in layout:
        if path.exists():
            existing.append(path)
            continue
        path.mkdir(parents=True, exist_ok=True)
        created.append(path)

    init_targets = [
        root_path / "src" / "app" / "ops" / "__init__.py",
        root_path / "src" / "app" / "ops" / "jobs" / "__init__.py",
    ]
    for path in init_targets:
        if path.exists():
            existing.append(path)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
        created.append(path)

    return WorkspaceResult(
        root=root_path,
        created=tuple(created),
        existing=tuple(existing),
    )


def register_workflow(
    *,
    root: str | Path = ".",
    name: str,
    file_path: str,
    target: str = "local_async",
    job_name: str = "",
    command: str = "",
    enabled: bool = True,
    metadata: dict[str, Any] | None = None,
) -> CronWorkflowRecord:
    root_path = resolve_root(root)
    workflow_name = name.strip()
    if not workflow_name:
        raise ValueError("workflow name is required.")

    raw_file = file_path.strip()
    if not raw_file:
        raise ValueError("workflow file path is required.")
    path = Path(raw_file)
    if not path.is_absolute():
        path = (root_path / path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Workflow file does not exist: {path}")

    linked_job = job_name.strip()
    run_command = command.strip()
    if not linked_job and not run_command:
        raise ValueError("register_workflow requires either job_name or command.")
    if linked_job and run_command:
        raise ValueError("register_workflow accepts only one execution mode: job_name or command.")

    reg = cron_workflow_registry(root_path)
    workflow_key = f"{root_path}:{workflow_name}"
    existing = reg.get(workflow_key=workflow_key)
    created_at = existing.created_at if existing is not None else utc_now()
    
    return reg.upsert(
        id=getattr(existing, "id", None),
        workflow_key=workflow_key,
        project_root=str(root_path),
        name=workflow_name,
        file_path=str(path),
        target=target.strip() or "local_async",
        job_name=linked_job,
        command=run_command,
        enabled=bool(enabled),
        metadata=json.dumps(metadata or {}, sort_keys=True),
        created_at=created_at,
        updated_at=utc_now(),
    )


def list_workflows(root: str | Path = ".") -> list[CronWorkflowRecord]:
    root_path = resolve_root(root)
    return cron_workflow_registry(root_path).filter(project_root=str(root_path), order_by="name")


def _run_shell_command(command: str, *, cwd: Path) -> tuple[int, str, str]:
    launchers: list[list[str]]
    if os.name == "nt":
        launchers = [
            ["powershell", "-NoLogo", "-NoProfile", "-Command", command],
            ["cmd", "/c", command],
        ]
    else:
        launchers = [["bash", "-lc", command]]

    last_exc: Exception | None = None
    for argv in launchers:
        try:
            completed = subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True)
            return int(completed.returncode), completed.stdout or "", completed.stderr or ""
        except FileNotFoundError as exc:
            last_exc = exc
            continue
    if last_exc is not None:
        raise RuntimeError(f"No shell launcher available for command execution: {last_exc}") from last_exc
    raise RuntimeError("No shell launcher available for command execution.")


def run_registered_workflow(
    *,
    root: str | Path = ".",
    name: str,
    payload: dict[str, Any] | None = None,
) -> WorkflowExecutionResult:
    root_path = resolve_root(root)
    workflow_name = name.strip()
    if not workflow_name:
        raise ValueError("workflow name is required.")

    row = cron_workflow_registry(root_path).get(
        workflow_key=f"{root_path}:{workflow_name}"
    )
    if row is None:
        raise ValueError(f"No registered workflow named '{workflow_name}' for {root_path}.")
    if not row.enabled:
        return WorkflowExecutionResult(kind="workflow", status="skipped", message="Workflow is disabled.")

    if row.job_name.strip():
        event = create_event(
            root=root_path,
            job_name=row.job_name.strip(),
            source="workflow",
            payload=payload or {},
            status="pending",
        )
        return WorkflowExecutionResult(
            kind="job",
            status="success",
            message=f"Queued workflow-linked job '{row.job_name}'.",
            event_id=event.id,
        )

    if row.command.strip():
        started = utc_now()
        begin = time.perf_counter()
        code, stdout, stderr = _run_shell_command(row.command, cwd=root_path)
        status = "success" if code == 0 else "failure"
        message = "Workflow command completed." if code == 0 else "Workflow command failed."
        record_run(
            root=root_path,
            job_name=f"workflow:{workflow_name}",
            event_id=None,
            status=status,
            message=message,
            started_at=started,
            finished_at=utc_now(),
            duration_ms=int((time.perf_counter() - begin) * 1000),
        )
        return WorkflowExecutionResult(
            kind="command",
            status=status,
            message=message,
            exit_code=code,
            stdout=stdout.strip(),
            stderr=stderr.strip(),
        )

    metadata = parse_json(row.metadata, {})
    return WorkflowExecutionResult(
        kind="workflow",
        status="success",
        message=f"No execution mode set; metadata={metadata}",
    )
