from __future__ import annotations

from typing import Literal

from functionals.fx.commands import FX_VERSION, argument, option, register
from functionals.fx.state import (
    module_registry,
    plugin_registry,
    project_registry,
    record_operation,
    resolve_root,
    utc_now,
)
from functionals.fx.structure import (
    create_module_layout,
    create_plugin_link,
    discover_local_plugins,
    discover_project_package,
    init_project_layout,
    normalize_identifier,
    resolve_plugin_import_base,
    resolve_plugin_layout,
)
from functionals.fx.support import render_structure_result


@register(name="init", description="Initialize a cli or db project structure and fx control database")
@option("--init")
@argument("project_type", type=str, default="cli", help="Project type: cli or db")
@argument("project_name", type=str, default="", help="Project display name; defaults to root folder name")
@argument("root", type=str, default="", help="Project root path; defaults to <project_name> when provided")
@argument("force", type=bool, default=False, help="Overwrite structure files if they already exist")
def init(
    project_type: str = "cli",
    project_name: str = "",
    root: str = "",
    force: bool = False,
) -> str:
    normalized_type = project_type.strip().lower() or "cli"
    if normalized_type not in {"cli", "db"}:
        if root.strip():
            raise ValueError("project_type must be either 'cli' or 'db'.")
        # Backward-compatible shapes:
        #   fx init <project_name>
        #   fx init <project_name> <root>
        legacy_project_name = project_type
        legacy_root = project_name
        project_name = legacy_project_name
        root = legacy_root
        normalized_type = "cli"

    name = project_name.strip()
    root_input = root.strip()
    if not root_input:
        if name in {".", "./"}:
            root_input = "."
            name = ""
        else:
            root_input = name or "."
    root_path = resolve_root(root_input)
    root_path.mkdir(parents=True, exist_ok=True)
    if not name or name in {".", "./"}:
        name = root_path.name

    structure = init_project_layout(
        root=root_path,
        project_name=name,
        project_type=normalized_type,
        force=force,
    )

    projects = project_registry(root_path)
    existing = projects.get(root_path=str(root_path))
    created_at = existing.created_at if existing is not None else utc_now()
    projects.upsert(
        name=name,
        root_path=str(root_path),
        project_type=normalized_type,
        created_at=created_at,
        updated_at=utc_now(),
    )
    record_operation(
        root=root_path,
        command="init",
        arguments={
            "project_type": normalized_type,
            "project_name": name,
            "root": str(root_path),
            "force": force,
        },
        status="success",
        message=f"Initialized {normalized_type} project '{name}'.",
    )
    return render_structure_result(
        title=f"Initialized {normalized_type} project '{name}' at {root_path}",
        root=root_path,
        result=structure,
    )


@register(name="status", description="Show current project structure and registry status")
@option("--status")
@argument("root", type=str, default=".", help="Project root path")
def status(root: str = ".") -> str:
    root_path = resolve_root(root)
    project = project_registry(root_path).get(root_path=str(root_path))
    modules = module_registry(root_path).filter(project_root=str(root_path), order_by="module_name")
    plugins = plugin_registry(root_path).filter(project_root=str(root_path), order_by="alias")
    local_plugins = discover_local_plugins(root_path)
    package_name = discover_project_package(root_path)
    plugin_layout = resolve_plugin_layout(root_path)
    src_root = root_path / "src"
    todo_file = src_root / package_name / "todo.py" if package_name else None
    api_file = src_root / package_name / "api.py" if package_name else None
    models_file = src_root / package_name / "models.py" if package_name else None

    registered_aliases = [plugin.alias for plugin in plugins]
    missing_on_disk = sorted(set(registered_aliases) - set(local_plugins))
    untracked_on_disk = sorted(set(local_plugins) - set(registered_aliases))

    lines = [
        f"Root: {root_path}",
        f"Project record: {'present' if project else 'missing'}",
        f"Project type: {getattr(project, 'project_type', 'unknown') if project else 'unknown'}",
        f"pyproject.toml: {'present' if (root_path / 'pyproject.toml').exists() else 'missing'}",
        f"src package: {package_name or 'missing'}",
        f"legacy app.py: {'present' if (root_path / 'app.py').exists() else 'missing'}",
        f"todo.py: {'present' if (todo_file and todo_file.exists()) else 'missing'}",
        f"api.py: {'present' if (api_file and api_file.exists()) else 'missing'}",
        f"legacy models.py: {'present' if (root_path / 'models.py').exists() else 'missing'}",
        f"package models.py: {'present' if (models_file and models_file.exists()) else 'missing'}",
        f"plugins package: {'present' if (plugin_layout.directory / '__init__.py').exists() else 'missing'}",
        f"plugins import base: {plugin_layout.import_base}",
        f"Registered modules: {len(modules)}",
        f"Registered plugin links: {len(plugins)}",
        f"Local plugin packages: {len(local_plugins)}",
    ]

    if missing_on_disk:
        lines.append(f"Missing on disk: {', '.join(missing_on_disk)}")
    if untracked_on_disk:
        lines.append(f"Untracked on disk: {', '.join(untracked_on_disk)}")
    if not missing_on_disk and not untracked_on_disk:
        lines.append("Registry and filesystem plugin lists are aligned.")

    return "\n".join(lines)


def _module_add(
    module_type: Literal["cli", "db"],
    module_name: str,
    root: str = ".",
    force: bool = False,
) -> str:
    root_path = resolve_root(root)
    normalized = normalize_identifier(module_name)
    import_base = resolve_plugin_import_base(root_path)

    structure = create_module_layout(
        root=root_path,
        module_type=module_type,
        module_name=normalized,
        force=force,
    )

    modules = module_registry(root_path)
    package_path = f"{import_base}.{normalized}"
    existing = modules.get(package_path=package_path)
    created_at = existing.created_at if existing is not None else utc_now()
    modules.upsert(
        project_root=str(root_path),
        module_type=module_type,
        module_name=normalized,
        package_path=package_path,
        entry_file=str(structure.entry_file or ""),
        created_at=created_at,
        updated_at=utc_now(),
    )

    plugins = plugin_registry(root_path)
    existing_plugin = plugins.get(alias=normalized)
    plugin_created_at = existing_plugin.created_at if existing_plugin is not None else utc_now()
    link_file = str(structure.entry_file.parent / "__init__.py") if structure.entry_file is not None else ""
    plugins.upsert(
        project_root=str(root_path),
        alias=normalized,
        package_path=package_path,
        enabled=True,
        link_file=link_file,
        created_at=plugin_created_at,
        updated_at=utc_now(),
    )

    record_operation(
        root=root_path,
        command="module-add",
        arguments={
            "module_type": module_type,
            "module_name": normalized,
            "root": str(root_path),
            "force": force,
        },
        status="success",
        message=f"Structured {module_type} module '{normalized}'.",
    )
    return render_structure_result(
        title=f"Structured {module_type} module '{normalized}'",
        root=root_path,
        result=structure,
    )


def _module_list(root: str = ".") -> str:
    root_path = resolve_root(root)
    modules = module_registry(root_path).filter(project_root=str(root_path), order_by="module_name")
    if not modules:
        return "No modules registered for this project."

    lines = ["Registered modules:"]
    for entry in modules:
        lines.append(f"  {entry.module_name}  ({entry.module_type})  {entry.package_path}")
    return "\n".join(lines)


def _plugin_make(
    package_path: str,
    alias: str = "",
    root: str = ".",
    force: bool = False,
) -> str:
    root_path = resolve_root(root)
    resolved_alias = normalize_identifier(alias or package_path.split(".")[-1])

    structure = create_plugin_link(
        root=root_path,
        package_path=package_path,
        alias=resolved_alias,
        force=force,
    )

    plugins = plugin_registry(root_path)
    existing = plugins.get(alias=resolved_alias)
    created_at = existing.created_at if existing is not None else utc_now()
    plugins.upsert(
        project_root=str(root_path),
        alias=resolved_alias,
        package_path=package_path,
        enabled=True,
        link_file=str(structure.entry_file or ""),
        created_at=created_at,
        updated_at=utc_now(),
    )

    record_operation(
        root=root_path,
        command="plugin-link",
        arguments={
            "package_path": package_path,
            "alias": resolved_alias,
            "root": str(root_path),
            "force": force,
        },
        status="success",
        message=f"Linked plugin '{resolved_alias}' to {package_path}.",
    )
    return render_structure_result(
        title=f"Linked plugin '{resolved_alias}' -> {package_path}",
        root=root_path,
        result=structure,
    )


def _plugin_list(root: str = ".") -> str:
    root_path = resolve_root(root)
    plugins = plugin_registry(root_path).filter(project_root=str(root_path), order_by="alias")
    if not plugins:
        return "No plugins linked for this project."

    lines = ["Linked plugins:"]
    for entry in plugins:
        marker = "enabled" if entry.enabled else "disabled"
        lines.append(f"  {entry.alias}  ->  {entry.package_path}  ({marker})")
    return "\n".join(lines)


@register(name="module", description="Manage project modules (add, list)")
@option("--module")
@argument("action", type=str, help="Action: add or list")
@argument("module_type", type=str, default="", help="For add: module type (cli or db); for list: optional root path")
@argument("module_name", type=str, default="", help="For add: module identifier")
@argument("root", type=str, default=".", help="Project root path")
@argument("force", type=bool, default=False, help="For add: overwrite files if they already exist")
def module_manage(
    action: str,
    module_type: str = "",
    module_name: str = "",
    root: str = ".",
    force: bool = False,
) -> str:
    normalized_action = action.strip().lower()
    if normalized_action == "add":
        normalized_type = module_type.strip().lower()
        if normalized_type not in {"cli", "db"}:
            raise ValueError("module add requires module_type to be 'cli' or 'db'.")
        if not module_name.strip():
            raise ValueError("module add requires module_name.")
        module_type_value: Literal["cli", "db"] = "cli" if normalized_type == "cli" else "db"
        return _module_add(
            module_type=module_type_value,
            module_name=module_name,
            root=root,
            force=force,
        )

    if normalized_action == "list":
        root_arg = root
        module_type_arg = module_type.strip()
        if root == "." and not module_name.strip() and module_type_arg and module_type_arg not in {"cli", "db"}:
            root_arg = module_type_arg
        return _module_list(root=root_arg)

    raise ValueError("module action must be one of: add, list.")


@register(name="plugin", description="Manage plugin links (make, list)")
@option("--plugin")
@argument("action", type=str, help="Action: make or list")
@argument("package_path", type=str, default="", help="For make: importable package path; for list: optional root path")
@argument("alias", type=str, default="", help="For make: local alias under plugins/")
@argument("root", type=str, default=".", help="Project root path")
@argument("force", type=bool, default=False, help="For make: overwrite alias shim files if they already exist")
def plugin_manage(
    action: str,
    package_path: str = "",
    alias: str = "",
    root: str = ".",
    force: bool = False,
) -> str:
    normalized_action = action.strip().lower()
    if normalized_action in {"make", "link"}:
        if not package_path.strip():
            raise ValueError("plugin make requires package_path.")
        return _plugin_make(
            package_path=package_path,
            alias=alias,
            root=root,
            force=force,
        )

    if normalized_action == "list":
        root_arg = root
        package_arg = package_path.strip()
        if root == "." and not alias.strip() and package_arg:
            root_arg = package_arg
        return _plugin_list(root=root_arg)

    raise ValueError("plugin action must be one of: make, list.")


@register(name="version", description="Show fx version")
@option("--version")
@option("-V")
def show_version() -> str:
    return f"fx {FX_VERSION}"
