from __future__ import annotations

import asyncio
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from typing import Any

from functionals.cron.adapters import apply_artifacts, generate_artifacts
from functionals.cron.runtime import build_event_payload, run_daemon, sync_project_jobs
from functionals.cron.state import (
    create_event as create_cron_event,
    cron_event_registry,
    cron_job_registry,
    cron_run_registry,
    cron_runtime_registry,
    mark_runtime_stopped,
    upsert_runtime,
)
from functionals.cron.workspace import (
    ensure_workspace as ensure_cron_workspace,
    list_workflows as list_cron_workflows,
    register_workflow as register_cron_workflow,
    run_registered_workflow,
)
from functionals.fx.commands import argument, option, register
from functionals.fx.state import record_operation, resolve_root
from functionals.fx.support import render_runtime_summary


def _pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _wait_for_pid_exit(pid: int, *, timeout_seconds: float = 6.0) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if not _pid_is_alive(pid):
            return True
        time.sleep(0.15)
    return not _pid_is_alive(pid)


def _spawn_cron_daemon(*, root_path: Path, workers: int) -> int:
    argv = [
        sys.executable,
        "-m",
        "functionals.cron.daemon",
        "--root",
        str(root_path),
        "--workers",
        str(max(1, workers)),
    ]
    popen_kwargs: dict[str, Any] = {
        "cwd": str(root_path),
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "start_new_session": True,
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]
    proc = subprocess.Popen(argv, **popen_kwargs)
    return int(proc.pid)


def _sync_cron_jobs(root_path: Path) -> tuple[str | None, int, int]:
    return sync_project_jobs(root_path)


@register(name="cron", description="Manage cron runtime, jobs, and deployment artifacts")
@option("--cron")
@argument("action", type=str, help="Action: start|stop|status|jobs|trigger|generate|apply|workspace|register|workflows|run-workflow")
@argument("subject", type=str, default="", help="Root path or job name (trigger action)")
@argument("root", type=str, default=".", help="Project root path")
@argument("workers", type=int, default=4, help="Worker count for start action")
@argument("foreground", type=bool, default=False, help="Run start in foreground mode")
@argument("target", type=str, default="", help="Target filter for generate/apply")
@argument("payload", type=str, default="", help="Optional JSON payload for trigger")
@argument("workflow_file", type=str, default="", help="Workflow file path for register action")
@argument("job", type=str, default="", help="Linked cron job name for register action")
@argument("command", type=str, default="", help="Shell command for register/run-workflow actions")
@argument("metadata", type=str, default="", help="Optional JSON metadata for workflow registration")
def cron_manage(
    action: str,
    subject: str = "",
    root: str = ".",
    workers: int = 4,
    foreground: bool = False,
    target: str = "",
    payload: str = "",
    workflow_file: str = "",
    job: str = "",
    command: str = "",
    metadata: str = "",
) -> str:
    normalized = action.strip().lower()
    if not normalized:
        raise ValueError("cron action is required.")

    arguments = {
        "action": normalized,
        "subject": subject,
        "root": root,
        "workers": workers,
        "foreground": foreground,
        "target": target,
        "workflow_file": workflow_file,
        "job": job,
        "command": command,
        "metadata": metadata,
    }

    if normalized in {"start", "stop", "status", "jobs", "generate", "apply", "workspace", "workflows"}:
        root_token = subject.strip() or root
        root_path = resolve_root(root_token)
    else:
        root_path = resolve_root(root)

    try:
        if normalized == "start":
            package, loaded_modules, synced = _sync_cron_jobs(root_path)
            if foreground:
                summary = asyncio.run(run_daemon(root=root_path, workers=max(1, workers)))
                record_operation(
                    root=root_path,
                    command="cron",
                    arguments=arguments,
                    status="success",
                    message=f"cron start foreground completed (jobs={summary.jobs}).",
                )
                return render_runtime_summary(
                    "FX Cron Start Result",
                    fields=[
                        ("Status", "success"),
                        ("Mode", "foreground"),
                        ("Project", str(root_path)),
                        ("Jobs", summary.jobs),
                        ("Workers", summary.workers),
                        ("Package", package or "missing"),
                        ("Loaded modules", loaded_modules),
                        ("Synced jobs", synced),
                    ],
                )

            runtime = cron_runtime_registry(root_path).get(project_root=str(root_path))
            if runtime is not None and runtime.status == "running" and _pid_is_alive(runtime.pid):
                return render_runtime_summary(
                    "FX Cron Start Result",
                    fields=[
                        ("Status", "success"),
                        ("Mode", "background"),
                        ("Project", str(root_path)),
                        ("PID", runtime.pid),
                        ("Message", "Cron daemon is already running."),
                    ],
                )

            pid = _spawn_cron_daemon(root_path=root_path, workers=max(1, workers))
            time.sleep(0.4)
            started = _pid_is_alive(pid)
            status_value = "success" if started else "failure"
            message = f"Started cron daemon (pid={pid})." if started else "Cron daemon failed to start."
            record_operation(
                root=root_path,
                command="cron",
                arguments=arguments,
                status=status_value,
                message=message,
            )
            if not started:
                raise RuntimeError(message)
            upsert_runtime(
                root=root_path,
                pid=pid,
                status="running",
                workers=max(1, workers),
            )

            return render_runtime_summary(
                "FX Cron Start Result",
                fields=[
                    ("Status", "success"),
                    ("Mode", "background"),
                    ("Project", str(root_path)),
                    ("PID", pid),
                    ("Workers", max(1, workers)),
                    ("Package", package or "missing"),
                    ("Loaded modules", loaded_modules),
                    ("Synced jobs", synced),
                ],
            )

        if normalized == "stop":
            runtime = cron_runtime_registry(root_path).get(project_root=str(root_path))
            if runtime is None:
                record_operation(
                    root=root_path,
                    command="cron",
                    arguments=arguments,
                    status="success",
                    message="Cron daemon not running.",
                )
                return render_runtime_summary(
                    "FX Cron Stop Result",
                    fields=[
                        ("Status", "success"),
                        ("Project", str(root_path)),
                        ("Message", "Cron daemon is not running."),
                    ],
                )

            pid = int(runtime.pid)
            if _pid_is_alive(pid):
                try:
                    os.kill(pid, signal.SIGTERM)
                except OSError as exc:
                    raise RuntimeError(f"Failed to stop cron daemon pid={pid}: {exc}") from exc
                exited = _wait_for_pid_exit(pid)
            else:
                exited = True

            mark_runtime_stopped(root_path)
            status_value = "success" if exited else "failure"
            message = "Stopped cron daemon." if exited else "Cron daemon did not exit in time."
            record_operation(
                root=root_path,
                command="cron",
                arguments=arguments,
                status=status_value,
                message=message,
            )
            if not exited:
                raise RuntimeError(message)

            return render_runtime_summary(
                "FX Cron Stop Result",
                fields=[
                    ("Status", "success"),
                    ("Project", str(root_path)),
                    ("PID", pid),
                    ("Message", message),
                ],
            )

        if normalized == "workspace":
            workspace = ensure_cron_workspace(root_path)
            record_operation(
                root=root_path,
                command="cron",
                arguments=arguments,
                status="success",
                message=(
                    f"Prepared cron workspace (created={len(workspace.created)}, "
                    f"existing={len(workspace.existing)})."
                ),
            )
            return render_runtime_summary(
                "FX Cron Workspace Result",
                fields=[
                    ("Status", "success"),
                    ("Project", str(root_path)),
                ],
                sections=[
                    ("Created", tuple(str(path) for path in workspace.created)),
                    ("Existing", tuple(str(path) for path in workspace.existing)),
                ],
            )

        if normalized == "register":
            workflow_name = subject.strip()
            if not workflow_name:
                raise ValueError("register action requires a workflow name: fx cron register <name> [root].")
            file_value = workflow_file.strip()
            if not file_value:
                raise ValueError("register action requires --workflow-file.")
            workflow_metadata = build_event_payload(metadata)
            row = register_cron_workflow(
                root=root_path,
                name=workflow_name,
                file_path=file_value,
                target=target or "local_async",
                job_name=job.strip(),
                command=command.strip(),
                metadata=workflow_metadata,
            )
            record_operation(
                root=root_path,
                command="cron",
                arguments=arguments,
                status="success",
                message=f"Registered workflow '{row.name}'.",
            )
            return render_runtime_summary(
                "FX Cron Register Result",
                fields=[
                    ("Status", "success"),
                    ("Project", str(root_path)),
                    ("Workflow", row.name),
                    ("File", row.file_path),
                    ("Target", row.target),
                    ("Job", row.job_name or "-"),
                    ("Command", row.command or "-"),
                ],
            )

        if normalized == "workflows":
            rows = list_cron_workflows(root_path)
            if not rows:
                return render_runtime_summary(
                    "FX Cron Workflows Result",
                    fields=[
                        ("Status", "success"),
                        ("Project", str(root_path)),
                        ("Message", "No workflows registered."),
                    ],
                )
            lines = [
                "FX Cron Workflows Result",
                "Status: success",
                f"Project: {root_path}",
                "Workflows:",
            ]
            for row in rows:
                mode = "job" if row.job_name else ("command" if row.command else "metadata")
                lines.append(
                    f"  {row.name} ({mode}, target={row.target}, enabled={row.enabled}, file={row.file_path})"
                )
            return "\n".join(lines)

        if normalized == "run-workflow":
            workflow_name = subject.strip()
            if not workflow_name:
                raise ValueError("run-workflow action requires workflow name: fx cron run-workflow <name> [root].")
            payload_dict = build_event_payload(payload)
            result = run_registered_workflow(
                root=root_path,
                name=workflow_name,
                payload=payload_dict,
            )
            status_value = "success" if result.status in {"success", "skipped"} else "failure"
            record_operation(
                root=root_path,
                command="cron",
                arguments=arguments,
                status=status_value,
                message=result.message,
            )
            return render_runtime_summary(
                "FX Cron Run Workflow Result",
                fields=[
                    ("Status", result.status),
                    ("Project", str(root_path)),
                    ("Workflow", workflow_name),
                    ("Mode", result.kind),
                    ("Message", result.message),
                    ("Event ID", result.event_id if result.event_id is not None else "-"),
                    ("Exit code", result.exit_code if result.exit_code is not None else "-"),
                ],
            )

        if normalized == "status":
            runtime = cron_runtime_registry(root_path).get(project_root=str(root_path))
            jobs_total = cron_job_registry(root_path).count(project_root=str(root_path))
            workflows_total = list_cron_workflows(root_path)
            pending_events = cron_event_registry(root_path).count(project_root=str(root_path), status="pending")
            queued_events = cron_event_registry(root_path).count(project_root=str(root_path), status="queued")
            total_runs = cron_run_registry(root_path).count(project_root=str(root_path))

            running = False
            pid = 0
            workers_value = 0
            runtime_status = "stopped"
            if runtime is not None:
                pid = int(runtime.pid)
                workers_value = int(runtime.workers)
                running = runtime.status == "running" and _pid_is_alive(pid)
                runtime_status = "running" if running else runtime.status

            return render_runtime_summary(
                "FX Cron Status Result",
                fields=[
                    ("Status", "success"),
                    ("Project", str(root_path)),
                    ("Runtime", runtime_status),
                    ("PID", pid),
                    ("Workers", workers_value),
                    ("Jobs", jobs_total),
                    ("Workflows", len(workflows_total)),
                    ("Pending events", pending_events),
                    ("Queued events", queued_events),
                    ("Runs", total_runs),
                ],
            )

        if normalized == "jobs":
            package, loaded_modules, synced = _sync_cron_jobs(root_path)
            rows = cron_job_registry(root_path).filter(project_root=str(root_path), order_by="name")
            if not rows:
                return render_runtime_summary(
                    "FX Cron Jobs Result",
                    fields=[
                        ("Status", "success"),
                        ("Project", str(root_path)),
                        ("Message", "No cron jobs registered."),
                        ("Package", package or "missing"),
                        ("Loaded modules", loaded_modules),
                        ("Synced jobs", synced),
                    ],
                )

            lines = [
                "FX Cron Jobs Result",
                "Status: success",
                f"Project: {root_path}",
                f"Package: {package or 'missing'}",
                f"Loaded modules: {loaded_modules}",
                f"Synced jobs: {synced}",
                "Jobs:",
            ]
            for row in rows:
                lines.append(
                    f"  {row.name} ({row.trigger_kind}, target={row.target}, enabled={row.enabled})"
                )
            return "\n".join(lines)

        if normalized == "trigger":
            job_name = subject.strip()
            if not job_name:
                raise ValueError("trigger action requires a job name: fx cron trigger <job_name> [root].")

            _sync_cron_jobs(root_path)
            job_row = cron_job_registry(root_path).get(
                job_key=f"{root_path}:{job_name}"
            )
            if job_row is None:
                raise ValueError(f"No cron job named '{job_name}' is registered for {root_path}.")

            payload_dict = build_event_payload(payload)
            event = create_cron_event(
                root=root_path,
                job_name=job_name,
                source="manual",
                payload=payload_dict,
                status="pending",
            )
            record_operation(
                root=root_path,
                command="cron",
                arguments=arguments,
                status="success",
                message=f"Queued manual trigger for '{job_name}' (event_id={event.id}).",
            )
            return render_runtime_summary(
                "FX Cron Trigger Result",
                fields=[
                    ("Status", "success"),
                    ("Project", str(root_path)),
                    ("Job", job_name),
                    ("Event ID", event.id),
                    ("Queue status", event.status),
                ],
            )

        if normalized == "generate":
            _sync_cron_jobs(root_path)
            report = generate_artifacts(root=root_path, target=target)
            record_operation(
                root=root_path,
                command="cron",
                arguments=arguments,
                status="success",
                message=(
                    f"Generated cron artifacts (created={len(report.created)}, "
                    f"updated={len(report.updated)}, skipped={len(report.skipped)})."
                ),
            )
            return render_runtime_summary(
                "FX Cron Generate Result",
                fields=[
                    ("Status", "success"),
                    ("Project", str(root_path)),
                    ("Target", target or "all"),
                ],
                sections=[
                    ("Created", report.created),
                    ("Updated", report.updated),
                    ("Skipped", report.skipped),
                ],
            )

        if normalized == "apply":
            _sync_cron_jobs(root_path)
            report = apply_artifacts(root=root_path, target=target)
            success = len(report.errors) == 0
            record_operation(
                root=root_path,
                command="cron",
                arguments=arguments,
                status="success" if success else "failure",
                message=(
                    f"Applied cron artifacts (applied={len(report.applied)}, errors={len(report.errors)})."
                ),
            )
            if not success:
                return render_runtime_summary(
                    "FX Cron Apply Result",
                    fields=[
                        ("Status", "failure"),
                        ("Project", str(root_path)),
                        ("Target", target or "all"),
                    ],
                    sections=[
                        ("Applied", report.applied),
                        ("Skipped", report.skipped),
                        ("Errors", report.errors),
                    ],
                )
            return render_runtime_summary(
                "FX Cron Apply Result",
                fields=[
                    ("Status", "success"),
                    ("Project", str(root_path)),
                    ("Target", target or "all"),
                ],
                sections=[
                    ("Applied", report.applied),
                    ("Skipped", report.skipped),
                ],
            )

        raise ValueError(
            "Unknown cron action. Use start, stop, status, jobs, trigger, generate, apply, workspace, register, workflows, or run-workflow."
        )
    except Exception as exc:
        record_operation(
            root=root_path,
            command="cron",
            arguments=arguments,
            status="failure",
            message=str(exc),
        )
        raise

