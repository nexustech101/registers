from __future__ import annotations

import importlib
from pathlib import Path
import shutil
import sys
from typing import Literal

from functionals.fx.commands import argument, option, register
from functionals.fx.plugin_sync import sync_plugins_from_checkout
from functionals.fx.runtime_ops import (
    clone_repo,
    editable_install_target,
    ensure_venv_python,
    progress_steps,
    run_checked,
)
from functionals.fx.state import (
    plugin_registry,
    project_registry,
    record_operation,
    resolve_root,
    utc_now,
)
from functionals.fx.structure import (
    discover_project_package,
    resolve_plugin_import_base,
    resolve_plugin_layout,
)
from functionals.fx.support import render_runtime_summary


@register(name="run", description="Run the structured project application")
@option("--run")
@argument("root", type=str, default=".", help="Project root path")
@argument("host", type=str, default="127.0.0.1", help="Host binding for DB/FastAPI projects")
@argument("port", type=int, default=8000, help="Port for DB/FastAPI projects")
@argument("reload", type=bool, default=False, help="Enable auto-reload for DB/FastAPI projects")
def run_project(
    root: str = ".",
    host: str = "127.0.0.1",
    port: int = 8000,
    reload: bool = False,
) -> str:
    root_path = resolve_root(root)
    project_type = "cli"
    argv: list[str] = []
    cwd = root_path

    try:
        package_name = discover_project_package(root_path)
        project = project_registry(root_path).get(root_path=str(root_path))
        project_type = getattr(project, "project_type", "")
        src_root = root_path / "src"
        has_src_package = bool(
            package_name
            and (src_root / package_name / "__init__.py").exists()
        )
        if has_src_package:
            cwd = src_root

        has_cli_layout = bool(package_name and (root_path / "src" / package_name / "todo.py").exists()) or (root_path / "app.py").exists()
        has_db_layout = bool(package_name and (root_path / "src" / package_name / "api.py").exists()) or (root_path / "models.py").exists()
        if not project_type:
            project_type = "db" if has_db_layout and not has_cli_layout else "cli"

        if project_type == "db":
            if package_name:
                argv = [
                    str(Path(sys.executable)),
                    "-m",
                    "uvicorn",
                    f"{package_name}.api:app",
                    "--host",
                    host,
                    "--port",
                    str(port),
                ]
                if reload:
                    argv.append("--reload")
            else:
                raise ValueError("Could not determine package name for DB project run.")
        else:
            if package_name:
                argv = [str(Path(sys.executable)), "-m", package_name]
            elif (root_path / "app.py").exists():
                argv = [str(Path(sys.executable)), str(root_path / "app.py")]
            else:
                raise ValueError("Could not determine CLI entrypoint for project run.")

        run_checked(argv, cwd=cwd)
    except Exception as exc:
        record_operation(
            root=root_path,
            command="run",
            arguments={
                "root": str(root_path),
                "project_type": project_type,
                "host": host,
                "port": port,
                "reload": reload,
            },
            status="failure",
            message=str(exc),
        )
        raise

    record_operation(
        root=root_path,
        command="run",
        arguments={
            "root": str(root_path),
            "project_type": project_type,
            "host": host,
            "port": port,
            "reload": reload,
        },
        status="success",
        message="Application command executed successfully.",
    )
    return render_runtime_summary(
        "FX Run Result",
        fields=[
            ("Status", "success"),
            ("Project", str(root_path)),
            ("Project type", project_type),
            ("Command", " ".join(argv)),
        ],
    )


@register(name="install", description="Install the project package in editable mode")
@option("--install")
@argument("root", type=str, default=".", help="Project root path")
@argument("venv_path", type=str, default="", help="Optional virtualenv path to create/use, for example '.venv'")
@argument("extras", type=str, default="", help="Optional extras list, for example 'dev' or 'dev,docs'")
def install_project(
    root: str = ".",
    venv_path: str = "",
    extras: str = "",
) -> str:
    root_path = resolve_root(root)
    editable_target = ""
    argv: list[str] = []

    try:
        with progress_steps(total=3, desc="fx install") as progress:
            progress.set_postfix_str("resolving python environment")
            python_exe = ensure_venv_python(root_path, venv_path)
            progress.update(1)

            progress.set_postfix_str("building editable target")
            editable_target = editable_install_target(root_path, extras)
            argv = [str(python_exe), "-m", "pip", "install", "-e", editable_target]
            progress.update(1)

            progress.set_postfix_str("running pip install -e")
            run_checked(argv, cwd=root_path)
            progress.update(1)
    except Exception as exc:
        record_operation(
            root=root_path,
            command="install",
            arguments={
                "root": str(root_path),
                "venv_path": venv_path,
                "extras": extras,
            },
            status="failure",
            message=str(exc),
        )
        raise

    record_operation(
        root=root_path,
        command="install",
        arguments={
            "root": str(root_path),
            "venv_path": venv_path,
            "extras": extras,
        },
        status="success",
        message="Editable install completed successfully.",
    )
    return render_runtime_summary(
        "FX Install Result",
        fields=[
            ("Status", "success"),
            ("Project", str(root_path)),
            ("Target", editable_target),
            ("Command", " ".join(argv)),
        ],
    )


@register(name="update", description="Update the decorates package from selected source")
@option("--update")
@argument("root", type=str, default=".", help="Project root path")
@argument("source", type=Literal["pypi", "git", "path"], default="pypi", help="Update source: pypi, git, or path")
@argument("repo", type=str, default="", help="Git repository URL when source=git")
@argument("ref", type=str, default="main", help="Git ref/branch/tag when source=git")
@argument("path", type=str, default="", help="Local source path when source=path")
@argument("venv_path", type=str, default="", help="Optional virtualenv path to create/use")
@argument("package", type=str, default="decorates", help="Package name/egg name to upgrade")
def update_project(
    root: str = ".",
    source: Literal["pypi", "git", "path"] = "pypi",
    repo: str = "",
    ref: str = "main",
    path: str = "",
    venv_path: str = "",
    package: str = "decorates",
) -> str:
    root_path = resolve_root(root)
    pkg = package.strip() or "decorates"
    argv: list[str] = []

    try:
        with progress_steps(total=3, desc="fx update") as progress:
            progress.set_postfix_str("resolving python environment")
            python_exe = ensure_venv_python(root_path, venv_path)
            progress.update(1)

            progress.set_postfix_str("resolving update source")
            if source == "pypi":
                if repo.strip() or path.strip():
                    raise ValueError("source='pypi' does not accept --repo or --path.")
                argv = [str(python_exe), "-m", "pip", "install", "--upgrade", pkg]
            elif source == "git":
                if not repo.strip():
                    raise ValueError("source='git' requires --repo.")
                if path.strip():
                    raise ValueError("source='git' does not accept --path.")
                git_spec = f"git+{repo}@{ref}#egg={pkg}"
                argv = [str(python_exe), "-m", "pip", "install", "--upgrade", git_spec]
            else:
                if not path.strip():
                    raise ValueError("source='path' requires --path.")
                if repo.strip():
                    raise ValueError("source='path' does not accept --repo.")
                source_path = Path(path)
                if not source_path.is_absolute():
                    source_path = (root_path / source_path).resolve()
                if not source_path.exists():
                    raise FileNotFoundError(f"Update source path does not exist: {source_path}")
                argv = [str(python_exe), "-m", "pip", "install", "--upgrade", str(source_path)]
            progress.update(1)

            progress.set_postfix_str("running pip install --upgrade")
            run_checked(argv, cwd=root_path)
            progress.update(1)
    except Exception as exc:
        record_operation(
            root=root_path,
            command="update",
            arguments={
                "root": str(root_path),
                "source": source,
                "repo": repo,
                "ref": ref,
                "path": path,
                "venv_path": venv_path,
                "package": pkg,
            },
            status="failure",
            message=str(exc),
        )
        raise

    record_operation(
        root=root_path,
        command="update",
        arguments={
            "root": str(root_path),
            "source": source,
            "repo": repo,
            "ref": ref,
            "path": path,
            "venv_path": venv_path,
            "package": pkg,
        },
        status="success",
        message=f"Updated package '{pkg}' from source '{source}'.",
    )
    return render_runtime_summary(
        "FX Update Result",
        fields=[
            ("Status", "success"),
            ("Project", str(root_path)),
            ("Source", source),
            ("Package", pkg),
            ("Command", " ".join(argv)),
        ],
    )


@register(name="pull", description="Pull plugins from a git repository")
@option("--pull")
@argument("repo_url", type=str, help="Git repository URL or local git path")
@argument("root", type=str, default=".", help="Project root path")
@argument("ref", type=str, default="main", help="Git ref/branch/tag")
@argument("subdir", type=str, default="plugins", help="Plugin directory inside the repository")
@argument("force", type=bool, default=False, help="Overwrite existing plugin directories")
def pull_plugins(
    repo_url: str,
    root: str = ".",
    ref: str = "main",
    subdir: str = "plugins",
    force: bool = False,
) -> str:
    root_path = resolve_root(root)
    arguments = {
        "repo_url": repo_url,
        "root": str(root_path),
        "ref": ref,
        "subdir": subdir,
        "force": force,
    }

    try:
        plugin_layout = resolve_plugin_layout(root_path)
        plugin_layout.directory.mkdir(parents=True, exist_ok=True)
        init_path = plugin_layout.directory / "__init__.py"
        if not init_path.exists():
            init_path.write_text("", encoding="utf-8")

        clone_result = clone_repo(repo_url=repo_url, ref=ref)
        try:
            report = sync_plugins_from_checkout(
                checkout_root=clone_result.repo_path,
                subdir=subdir,
                target_plugins_dir=plugin_layout.directory,
                force=force,
            )
        finally:
            shutil.rmtree(clone_result.repo_path, ignore_errors=True)

        import_base = resolve_plugin_import_base(root_path)
        import_failures: list[str] = []
        original_sys_path = list(sys.path)
        try:
            if str(root_path) not in sys.path:
                sys.path.insert(0, str(root_path))
            src_root = root_path / "src"
            if src_root.exists() and str(src_root) not in sys.path:
                sys.path.insert(0, str(src_root))

            root_pkg = import_base.split(".")[0]
            stale_modules = [
                key
                for key in list(sys.modules)
                if key == root_pkg or key.startswith(f"{root_pkg}.")
            ]
            for key in stale_modules:
                sys.modules.pop(key, None)

            for alias in report.synced_aliases:
                dotted = f"{import_base}.{alias}"
                try:
                    importlib.invalidate_caches()
                    importlib.import_module(dotted)
                except Exception as exc:
                    import_failures.append(f"{dotted}: {exc}")
        finally:
            sys.path[:] = original_sys_path

        if import_failures:
            message = "Import validation failed for pulled plugins: " + "; ".join(import_failures)
            raise RuntimeError(message)

        plugins = plugin_registry(root_path)
        for alias in report.synced_aliases:
            package_path = f"{import_base}.{alias}"
            existing = plugins.get(alias=alias)
            created_at = existing.created_at if existing is not None else utc_now()
            plugins.upsert(
                project_root=str(root_path),
                alias=alias,
                package_path=package_path,
                enabled=True,
                link_file=str(plugin_layout.directory / alias / "__init__.py"),
                created_at=created_at,
                updated_at=utc_now(),
            )

        summary_parts = [
            f"created={len(report.created)}",
            f"updated={len(report.updated)}",
            f"skipped={len(report.skipped)}",
        ]
        summary = ", ".join(summary_parts)
        record_operation(
            root=root_path,
            command="pull",
            arguments=arguments,
            status="success",
            message=f"Pulled plugins successfully ({summary}).",
        )

        return render_runtime_summary(
            "FX Pull Result",
            fields=[
                ("Status", "success"),
                ("Project", str(root_path)),
                ("Repository", repo_url),
                ("Summary", summary),
            ],
            sections=[
                ("Created", report.created),
                ("Updated", report.updated),
                ("Skipped", report.skipped),
            ],
        )
    except Exception as exc:
        record_operation(
            root=root_path,
            command="pull",
            arguments=arguments,
            status="failure",
            message=str(exc),
        )
        raise

