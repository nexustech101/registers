# `functionals.fx` Usage

`functionals.fx` is a project management CLI built on:
- `functionals.cli` for command registration, parsing, help, and interactive shell
- `functionals.db` for local control-plane state in `.fx/fx.db`

It helps you initialize project structures, add module/plugin structure, validate wiring, and track operation history.
It also provides a centralized cron workspace and workflow registry for DevOps-style automation.

## Run `fx`

After installing the package locally:

```bash
pip install -e .
```

Use either entrypoint:

```bash
fx --version
fx help
python -m functionals.fx help
```

Interactive mode:

```bash
fx --interactive
```

## Quick Start

Initialize a CLI project in a new directory named after the project:

```bash
fx init cli MyService
```

Initialize a CLI project in the current directory:

```bash
fx init cli MyService .
```

Initialize a DB-first project:

```bash
fx init db DataService .
```

Add a CLI module:

```bash
fx module add cli users .
```

Add a DB module:

```bash
fx module add db billing .
```

Link an external plugin package to a local alias:

```bash
fx plugin make my_app.plugins.analytics analytics .
```

Check health and status:

```bash
fx status .
fx health .
fx history 20 .
```

Run/install/update/pull:

```bash
# Run inferred project entrypoint
fx run .

# Editable install in active environment
fx install .
fx install . --extras dev
fx install . --venv .venv --extras dev

# Update decorates package
fx update .                          # default source=pypi
fx update . --source git --repo https://github.com/nexustech101/functionals.git --ref main
fx update . --source path --path ../framework

# Pull plugins from git
fx pull https://github.com/example/plugins-repo.git . --ref main --subdir plugins

# Cron runtime management
fx cron start .
fx cron status .
fx cron jobs .
fx cron trigger nightly-build .
fx cron generate .
fx cron apply .
fx cron stop .

# Cron workspace + workflow registration
fx cron workspace .
fx cron register deploy-workflow . --workflow-file ops/workflows/ci/deploy.yml --job nightly-build --target github_actions
fx cron workflows .
fx cron run-workflow deploy-workflow . --payload '{"env":"prod"}'
```

## Structure Output

`fx init cli` creates a professional package layout:

```text
pyproject.toml
README.md
.gitignore
src/app/__init__.py
src/app/__main__.py
src/app/todo.py
src/app/plugins/__init__.py
src/app/ops/__init__.py
src/app/ops/jobs/__init__.py
src/app/ops/jobs/heartbeat.py
src/app/ops/jobs/deploy.py
ops/scripts/deploy.sh
ops/workflows/cron/ops-heartbeat.cron
ops/workflows/ci/deploy-workflow.yml
ops/workflows/windows/ops-heartbeat.xml
tests/test_todo_cli.py
.fx/fx.db
```

`fx init db` creates a FastAPI + user-management package layout:

```text
pyproject.toml
README.md
.gitignore
src/app/__init__.py
src/app/__main__.py
src/app/api.py
src/app/models.py
src/app/plugins/__init__.py
src/app/ops/__init__.py
src/app/ops/jobs/__init__.py
src/app/ops/jobs/heartbeat.py
src/app/ops/jobs/deploy.py
ops/scripts/deploy.sh
ops/workflows/cron/ops-heartbeat.cron
ops/workflows/ci/deploy-workflow.yml
ops/workflows/windows/ops-heartbeat.xml
tests/test_user_api.py
.fx/fx.db
```

`fx module add cli <name>` creates:

```text
<plugins_package>/<name>/__init__.py
<plugins_package>/<name>/<name>.py
```

`fx module add db <name>` creates:

```text
<plugins_package>/<name>/__init__.py
<plugins_package>/<name>/models.py
```

`fx plugin make <package_path> <alias>` creates:

```text
<plugins_package>/<alias>/__init__.py
```

with:

```python
from <package_path> import *
```

## Command Reference

- `fx init [cli|db] [project_name] [root] [--force]`
  - Initialize project structure + project record.
  - Backward compatibility: `fx init <project_name>` defaults to `cli`.
- `fx status [root]`
  - Show structure, registry, and local plugin alignment.
- `fx module <add|list> [module_type|root] [module_name] [root] [--force]`
  - `add`: structure a module and register it.
  - `list`: list registered modules.
- `fx plugin <make|list> [package_path|root] [alias] [root] [--force]`
  - `make`: create a local plugin alias shim and register it.
  - `list`: list linked plugins.
- `fx run [root] [--host] [--port] [--reload]`
  - Run project entrypoint based on detected project type.
- `fx install [root] [venv_path] [extras]`
  - Run editable install (`pip install -e`) in active env or optional venv.
- `fx update [root] [source] [repo] [ref] [path] [venv_path] [package]`
  - Update package from `pypi`, `git`, or local `path`.
- `fx pull <repo_url> [root] [ref] [subdir] [--force]`
  - Pull plugins from git repo into the local plugins package.
- `fx cron <action> [subject] [root] [--workers] [--foreground] [--target] [--payload] [--workflow-file] [--job] [--command] [--metadata]`
  - Manage cron daemon lifecycle, jobs, manual triggers, and deployment adapters.
  - Actions: `start`, `stop`, `status`, `jobs`, `trigger`, `generate`, `apply`, `workspace`, `register`, `workflows`, `run-workflow`.
  - `workspace` prepares centralized DevOps folders (`ops/workflows`, `src/app/ops/jobs`, etc.).
  - `register` links an external workflow file to either a cron job (`--job`) or command (`--command`), with optional JSON metadata (`--metadata`).
  - `workflows` lists centralized workflow registrations from `.fx/fx.db`.
  - `run-workflow` executes a registered workflow by enqueuing its linked job or running its linked command.
- `fx --version` / `fx -V`
  - Print the current `fx` version.
- `fx health [root]`
  - Validate core structure files and plugin importability.
- `fx history [limit] [root]`
  - Show recent `fx` operations recorded in local state DB.

## Local State

`fx` stores metadata in:

```text
.fx/fx.db
```

Tracked entities include:
- project metadata
- module registry
- plugin links
- workflow registry and runtime telemetry for cron operations
- command operation history

## Notes

- For `init`, when `root` is omitted and `project_name` is provided, `root` defaults to `project_name`.
- For other commands, `root` defaults to `.`.
- New projects always use `src/app` as the application package.
- `<plugins_package>` resolves to `src/app/plugins` for package-style projects and `plugins/` for legacy layouts.
- `module_name` and `alias` must be valid Python identifiers (hyphens are normalized to underscores).
- `--force` overwrites structure files where supported.
- `health` imports plugins from the local `plugins` package to verify runtime loadability.
- `worktree` is currently spec-defined in `fx_specs.md` and intentionally not implemented yet.
