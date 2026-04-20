"""
Project import/discovery helpers for cron job registration.
"""

from __future__ import annotations

import importlib
import importlib.util
import pkgutil
from pathlib import Path
import sys

from functionals.cron.decorators import get_registry, reset_registry


def discover_project_package(root: Path) -> str | None:
    src_root = root / "src"
    if not src_root.exists():
        return None

    app_pkg = src_root / "app" / "__init__.py"
    if app_pkg.exists():
        return "app"

    candidates = sorted(
        child.name
        for child in src_root.iterdir()
        if child.is_dir() and (child / "__init__.py").exists()
    )
    if len(candidates) == 1:
        return candidates[0]
    return None


def load_project_jobs(root: Path, *, clear_registry: bool = True) -> tuple[str | None, int]:
    """
    Import project modules so ``@cron.job`` decorators execute.
    """
    package_name = discover_project_package(root)
    if not package_name:
        return None, 0

    if clear_registry:
        reset_registry()

    original_sys_path = list(sys.path)
    loaded = 0
    try:
        src_root = root / "src"
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        if src_root.exists() and str(src_root) not in sys.path:
            sys.path.insert(0, str(src_root))

        importlib.invalidate_caches()

        stale = [
            key
            for key in list(sys.modules)
            if key == package_name or key.startswith(f"{package_name}.")
        ]
        for key in stale:
            sys.modules.pop(key, None)

        package = importlib.import_module(package_name)
        loaded += 1
        package_paths = getattr(package, "__path__", None)
        if package_paths is not None:
            prefix = f"{package_name}."
            for _, module_name, _ in pkgutil.walk_packages(package_paths, prefix=prefix):
                spec = importlib.util.find_spec(module_name)
                origin = getattr(spec, "origin", None)
                if not origin or not origin.endswith(".py"):
                    continue
                try:
                    content = Path(origin).read_text(encoding="utf-8")
                except OSError:
                    continue
                # Import only modules that look like they register cron jobs.
                if "functionals.cron" not in content and "@cron.job" not in content:
                    continue
                importlib.import_module(module_name)
                loaded += 1
    finally:
        sys.path[:] = original_sys_path

    return package_name, loaded


def registered_job_count() -> int:
    return len(get_registry())
