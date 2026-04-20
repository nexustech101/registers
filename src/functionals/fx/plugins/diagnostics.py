from __future__ import annotations

import importlib
import sys

from functionals.fx.commands import argument, option, register
from functionals.fx.state import operation_registry, project_registry, record_operation, resolve_root
from functionals.fx.structure import (
    discover_local_plugins,
    discover_project_package,
    resolve_plugin_import_base,
    resolve_plugin_layout,
)


@register(name="health", description="Validate structure health and plugin importability")
@option("--health")
@option("--doctor")
@argument("root", type=str, default=".", help="Project root path")
def health(root: str = ".") -> str:
    root_path = resolve_root(root)
    failures: list[str] = []
    project = project_registry(root_path).get(root_path=str(root_path))
    project_type = getattr(project, "project_type", "")
    package_name = discover_project_package(root_path)
    import_base = resolve_plugin_import_base(root_path)
    plugin_layout = resolve_plugin_layout(root_path)
    has_legacy_cli = (root_path / "app.py").exists()
    has_legacy_db = (root_path / "models.py").exists()
    has_package_cli = bool(package_name and (root_path / "src" / package_name / "todo.py").exists())
    has_package_db = bool(
        package_name
        and (root_path / "src" / package_name / "models.py").exists()
        and (root_path / "src" / package_name / "api.py").exists()
    )
    if not project_type:
        project_type = "db" if (has_legacy_db or has_package_db) and not (has_legacy_cli or has_package_cli) else "cli"

    if project_type == "cli":
        if not (has_legacy_cli or has_package_cli):
            failures.append("Missing CLI starter (app.py or src/<package>/todo.py).")
    elif project_type == "db":
        if not (has_legacy_db or has_package_db):
            failures.append("Missing DB starter (models.py or src/<package>/models.py + api.py).")
    else:
        failures.append(f"Unsupported project type '{project_type}'.")

    if not (plugin_layout.directory / "__init__.py").exists():
        failures.append(f"Missing plugins package at {plugin_layout.directory}.")

    if not (root_path / "pyproject.toml").exists() and not (has_legacy_cli or has_legacy_db):
        failures.append("Missing pyproject.toml.")

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

        for alias in discover_local_plugins(root_path):
            dotted = f"{import_base}.{alias}"
            try:
                importlib.invalidate_caches()
                importlib.import_module(dotted)
            except Exception as exc:
                failures.append(f"Import failed for {dotted}: {exc}")
    finally:
        sys.path[:] = original_sys_path

    status_value = "success" if not failures else "failure"
    message = "Project checks passed." if not failures else "; ".join(failures)
    record_operation(
        root=root_path,
        command="health",
        arguments={"root": str(root_path), "project_type": project_type},
        status=status_value,
        message=message,
    )

    if not failures:
        return "Health checks passed."
    return "Health checks failed:\n" + "\n".join(f"  - {failure}" for failure in failures)


@register(name="history", description="Show recent fx operation history")
@option("--history")
@argument("limit", type=int, default=20, help="Maximum number of operations to show")
@argument("root", type=str, default=".", help="Project root path")
def history(limit: int = 20, root: str = ".") -> str:
    root_path = resolve_root(root)
    rows = operation_registry(root_path).filter(project_root=str(root_path), order_by="-id", limit=limit)
    if not rows:
        return "No operation history found."

    lines = ["Recent operations:"]
    for row in rows:
        lines.append(f"  [{row.id}] {row.created_at}  {row.command}  {row.status}")
        if row.message:
            lines.append(f"      {row.message}")
    return "\n".join(lines)

