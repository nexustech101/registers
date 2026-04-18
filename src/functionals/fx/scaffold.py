"""
Filesystem scaffolding helpers for ``functionals.fx``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class ScaffoldResult:
    created: tuple[Path, ...] = ()
    updated: tuple[Path, ...] = ()
    skipped: tuple[Path, ...] = ()
    entry_file: Path | None = None


def normalize_identifier(raw: str) -> str:
    cleaned = raw.strip().replace("-", "_")
    if not cleaned or not _IDENT_RE.match(cleaned):
        raise ValueError(
            f"Invalid name '{raw}'. Use a valid Python identifier (letters, digits, underscore)."
        )
    return cleaned


def ensure_package(path: Path, *, created: list[Path], skipped: list[Path]) -> None:
    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)
        created.append(path)

    init_file = path / "__init__.py"
    if init_file.exists():
        skipped.append(init_file)
    else:
        init_file.write_text("", encoding="utf-8")
        created.append(init_file)


def write_file(path: Path, content: str, *, force: bool, created: list[Path], updated: list[Path], skipped: list[Path]) -> None:
    if path.exists():
        if force:
            path.write_text(content, encoding="utf-8")
            updated.append(path)
        else:
            skipped.append(path)
        return

    path.write_text(content, encoding="utf-8")
    created.append(path)


def init_project_layout(*, root: Path, project_name: str, project_type: str, force: bool) -> ScaffoldResult:
    created: list[Path] = []
    updated: list[Path] = []
    skipped: list[Path] = []

    ensure_package(root / "plugins", created=created, skipped=skipped)
    (root / ".functionals").mkdir(parents=True, exist_ok=True)

    entry_path: Path
    if project_type == "cli":
        app_content = _app_template(project_name)
        entry_path = root / "app.py"
    elif project_type == "db":
        app_content = _db_project_template(project_name)
        entry_path = root / "models.py"
    else:
        raise ValueError("project_type must be either 'cli' or 'db'.")

    write_file(
        entry_path,
        app_content,
        force=force,
        created=created,
        updated=updated,
        skipped=skipped,
    )

    return ScaffoldResult(
        created=tuple(created),
        updated=tuple(updated),
        skipped=tuple(skipped),
        entry_file=entry_path,
    )


def create_module_layout(
    *,
    root: Path,
    module_type: str,
    module_name: str,
    force: bool,
) -> ScaffoldResult:
    created: list[Path] = []
    updated: list[Path] = []
    skipped: list[Path] = []

    normalized = normalize_identifier(module_name)
    module_dir = root / "plugins" / normalized
    ensure_package(root / "plugins", created=created, skipped=skipped)
    if not module_dir.exists():
        module_dir.mkdir(parents=True, exist_ok=True)
        created.append(module_dir)

    if module_type == "cli":
        module_path = module_dir / f"{normalized}.py"
        init_content = f"from .{normalized} import *\n"
        module_content = _cli_module_template(normalized)
    elif module_type == "db":
        module_path = module_dir / "models.py"
        init_content = "from .models import *\n"
        module_content = _db_module_template(normalized)
    else:
        raise ValueError("module_type must be either 'cli' or 'db'.")

    write_file(
        module_path,
        module_content,
        force=force,
        created=created,
        updated=updated,
        skipped=skipped,
    )
    write_file(
        module_dir / "__init__.py",
        init_content,
        force=force,
        created=created,
        updated=updated,
        skipped=skipped,
    )

    return ScaffoldResult(
        created=tuple(created),
        updated=tuple(updated),
        skipped=tuple(skipped),
        entry_file=module_path,
    )


def create_plugin_link(
    *,
    root: Path,
    package_path: str,
    alias: str,
    force: bool,
) -> ScaffoldResult:
    created: list[Path] = []
    updated: list[Path] = []
    skipped: list[Path] = []

    normalized_alias = normalize_identifier(alias)
    ensure_package(root / "plugins", created=created, skipped=skipped)
    alias_dir = root / "plugins" / normalized_alias
    if not alias_dir.exists():
        alias_dir.mkdir(parents=True, exist_ok=True)
        created.append(alias_dir)

    init_path = alias_dir / "__init__.py"
    init_content = f"from {package_path} import *\n"
    write_file(
        init_path,
        init_content,
        force=force,
        created=created,
        updated=updated,
        skipped=skipped,
    )

    return ScaffoldResult(
        created=tuple(created),
        updated=tuple(updated),
        skipped=tuple(skipped),
        entry_file=init_path,
    )


def discover_local_plugins(root: Path) -> list[str]:
    plugins_dir = root / "plugins"
    if not plugins_dir.exists():
        return []

    result: list[str] = []
    for candidate in sorted(plugins_dir.iterdir()):
        if not candidate.is_dir():
            continue
        if (candidate / "__init__.py").exists():
            result.append(candidate.name)
    return result


def _app_template(project_name: str) -> str:
    return (
        "from __future__ import annotations\n\n"
        "import functionals.cli as cli\n\n\n"
        "def main() -> None:\n"
        "    cli.load_plugins(\"plugins\", cli.get_registry())\n"
        "    cli.run(\n"
        f"        shell_title=\"{project_name} Console\",\n"
        "        shell_description=\"Project command console.\",\n"
        "        shell_colors=None,\n"
        "        shell_banner=True,\n"
        "        shell_usage=True,\n"
        "    )\n\n\n"
        "if __name__ == \"__main__\":\n"
        "    main()\n"
    )


def _db_project_template(project_name: str) -> str:
    base = re.sub(r"[^A-Za-z0-9_]+", "_", project_name.strip().replace("-", "_")).strip("_")
    safe = base or "project"
    if safe and safe[0].isdigit():
        safe = f"project_{safe}"
    table_name = safe.lower()
    class_name = "".join(part.capitalize() for part in table_name.split("_")) + "Record"
    db_name = f"{table_name}.db"
    return (
        "from __future__ import annotations\n\n"
        "from pydantic import BaseModel\n\n"
        "import functionals.db as db\n\n\n"
        f"@db.database_registry(\"{db_name}\", table_name=\"{table_name}\", key_field=\"id\")\n"
        f"class {class_name}(BaseModel):\n"
        "    id: int | None = None\n"
        "    name: str\n"
        "    created_at: str = \"\"\n"
    )


def _cli_module_template(module_name: str) -> str:
    kebab = module_name.replace("_", "-")
    return (
        "from __future__ import annotations\n\n"
        "import functionals.cli as cli\n\n\n"
        f"@cli.register(description=\"Run a command from '{module_name}' module\")\n"
        f"@cli.argument(\"subject\", type=str, help=\"Subject to process\")\n"
        f"@cli.option(\"--{kebab}-run\")\n"
        f"def {module_name}_run(subject: str) -> str:\n"
        f"    return f\"{module_name}: {{subject}}\"\n"
    )


def _db_module_template(module_name: str) -> str:
    class_name = "".join(part.capitalize() for part in module_name.split("_")) + "Record"
    return (
        "from __future__ import annotations\n\n"
        "from pydantic import BaseModel\n\n"
        "import functionals.db as db\n\n\n"
        f"@db.database_registry(\"{module_name}.db\", table_name=\"{module_name}\", key_field=\"id\")\n"
        f"class {class_name}(BaseModel):\n"
        "    id: int | None = None\n"
        "    name: str\n"
    )
