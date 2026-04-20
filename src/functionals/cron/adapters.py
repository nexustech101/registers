"""
Deployment artifact generation and apply adapters for cron jobs.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
import sys

from functionals.cron.state import CronJobRecord, cron_job_registry, parse_json, resolve_root


SUPPORTED_APPLY_TARGETS = {"linux_cron", "windows_task_scheduler"}


@dataclass(frozen=True)
class AdapterReport:
    created: tuple[str, ...] = ()
    updated: tuple[str, ...] = ()
    skipped: tuple[str, ...] = ()
    applied: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()


def _default_extension(target: str) -> str:
    """Return the default file extension for a given target type."""
    if target == "linux_cron":
        return ".cron"
    if target == "windows_task_scheduler":
        return ".xml"
    if target == "github_actions":
        return ".yml"
    return ".toml"


def _resolve_deployment_path(root: Path, job: CronJobRecord) -> Path:
    """Determine the file path for a cron job's deployment artifact based on its configuration."""
    if job.deployment_file.strip():
        path = Path(job.deployment_file)
        if not path.is_absolute():
            path = (root / path).resolve()
        return path
    default_dir = root / ".fx" / "cron" / "deployments"
    default_dir.mkdir(parents=True, exist_ok=True)
    return default_dir / f"{job.name}{_default_extension(job.target)}"


def _render_linux(job: CronJobRecord, root: Path) -> str:
    """Render a cron job as a Linux cron entry."""
    trigger = parse_json(job.trigger_config, {})
    expression = trigger.get("expression", "")
    if not expression and job.trigger_kind == "interval":
        seconds = int(trigger.get("seconds", 0))
        minutes = max(1, seconds // 60) if seconds > 0 else 1
        expression = f"*/{minutes} * * * *"
    if not expression:
        expression = "*/5 * * * *"
    command = f"cd {root} && fx cron trigger {job.name} {root}"
    return f"{expression} {command}\n"


def _render_windows(job: CronJobRecord, root: Path) -> str:
    """Render a cron job as a Windows Task Scheduler entry."""
    trigger = parse_json(job.trigger_config, {})
    expression = trigger.get("expression", "*/5 * * * *")
    return "\n".join(
        [
            "<Task>",
            f"  <Name>functionals-{job.name}</Name>",
            f"  <Trigger>{expression}</Trigger>",
            "  <Action>",
            f"    <Command>{sys.executable}</Command>",
            f"    <Arguments>-m functionals.fx.commands cron trigger {job.name} {root}</Arguments>",
            "  </Action>",
            "</Task>",
        ]
    ) + "\n"


def _render_github_actions(job: CronJobRecord, root: Path) -> str:
    """Render a cron job as a GitHub Actions workflow file."""
    trigger = parse_json(job.trigger_config, {})
    expression = trigger.get("expression", "*/15 * * * *")
    return "\n".join(
        [
            f"name: {job.name}",
            "on:",
            "  workflow_dispatch: {}",
            "  schedule:",
            f"    - cron: '{expression}'",
            "jobs:",
            "  run-job:",
            "    runs-on: ubuntu-latest",
            "    steps:",
            "      - uses: actions/checkout@v4",
            "      - name: Trigger Functionals cron job",
            f"        run: fx cron trigger {job.name} {root}",
        ]
    ) + "\n"


def _render_local(job: CronJobRecord) -> str:
    """Render a cron job as a local configuration file."""
    return "\n".join(
        [
            "[job]",
            f"name = \"{job.name}\"",
            f"target = \"{job.target}\"",
            f"trigger_kind = \"{job.trigger_kind}\"",
            f"enabled = {str(job.enabled).lower()}",
            f"max_runtime = {job.max_runtime}",
        ]
    ) + "\n"


def _render_content(job: CronJobRecord, root: Path) -> str:
    """Render the content of a deployment artifact for a given cron job based on its target type."""
    if job.target == "linux_cron":
        return _render_linux(job, root)
    if job.target == "windows_task_scheduler":
        return _render_windows(job, root)
    if job.target == "github_actions":
        return _render_github_actions(job, root)
    return _render_local(job)


def generate_artifacts(*, root: str | Path = ".", target: str = "") -> AdapterReport:
    """Generate deployment artifacts for cron jobs."""
    root_path = resolve_root(root)
    rows = cron_job_registry(root_path).filter(project_root=str(root_path), order_by="name")

    # Track which artifacts were accessed or modified for reporting purposes
    created: list[str] = []
    updated: list[str] = []
    skipped: list[str] = []

    for job in rows:
        if target.strip() and job.target != target.strip():
            skipped.append(f"{job.name} (target mismatch)")
            continue
        path = _resolve_deployment_path(root_path, job)
        path.parent.mkdir(parents=True, exist_ok=True)
        content = _render_content(job, root_path)
        if path.exists():
            old = path.read_text(encoding="utf-8")
            if old == content:
                skipped.append(str(path))
            else:
                path.write_text(content, encoding="utf-8")
                updated.append(str(path))
        else:
            path.write_text(content, encoding="utf-8")
            created.append(str(path))

    return AdapterReport(
        created=tuple(created),
        updated=tuple(updated),
        skipped=tuple(skipped),
    )


def _run(argv: list[str], *, cwd: Path) -> None:
    """Run a job and raise an error if it fails, including stderr output for debugging."""
    completed = subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True)
    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        raise RuntimeError(f"Command failed ({completed.returncode}): {' '.join(argv)} {stderr}")


def apply_artifacts(*, root: str | Path = ".", target: str = "") -> AdapterReport:
    """Apply deployment artifacts for cron jobs."""
    root_path = resolve_root(root)
    rows = cron_job_registry(root_path).filter(project_root=str(root_path), order_by="name")
    applied: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []

    generated = generate_artifacts(root=root_path, target=target)
    skipped.extend(generated.skipped)

    for job in rows:
        if target.strip() and job.target != target.strip():
            continue
        if job.target not in SUPPORTED_APPLY_TARGETS:
            skipped.append(f"{job.name} ({job.target}: generate-only)")
            continue

        path = _resolve_deployment_path(root_path, job)
        try:
            if job.target == "linux_cron":
                if os.name == "nt":
                    raise RuntimeError("linux_cron apply is not supported on Windows hosts.")
                _run(["crontab", str(path)], cwd=root_path)
            elif job.target == "windows_task_scheduler":
                if os.name != "nt":
                    raise RuntimeError("windows_task_scheduler apply is only supported on Windows hosts.")
                _run(
                    [
                        "schtasks",
                        "/Create",
                        "/TN",
                        f"functionals-{job.name}",
                        "/XML",
                        str(path),
                        "/F",
                    ],
                    cwd=root_path,
                )
            applied.append(job.name)
        except Exception as exc:
            errors.append(f"{job.name}: {exc}")

    return AdapterReport(
        created=generated.created,
        updated=generated.updated,
        skipped=tuple(skipped),
        applied=tuple(applied),
        errors=tuple(errors),
    )
