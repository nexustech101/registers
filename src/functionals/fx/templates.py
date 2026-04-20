"""
Starter project templates for ``functionals.fx``.

Templates are stored as multiline strings and rendered by token replacement
inside ``functionals.fx.structure``.
"""

from __future__ import annotations


CLI_PYPROJECT_TEMPLATE = """[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "__DIST_NAME__"
version = "0.1.0"
description = "Todo CLI app structured by functionals.fx"
readme = "README.md"
requires-python = ">=3.10"
dependencies = [
    "decorates>=4.4.0"
]

[project.scripts]
__SCRIPT_NAME__ = "__PACKAGE_NAME__.__main__:main"

[project.optional-dependencies]
dev = [
    "pytest>=7.4"
]

[tool.setuptools.packages.find]
where = ["src"]
include = ["__PACKAGE_NAME__*"]

[tool.setuptools]
package-dir = {"" = "src"}
"""


DB_PYPROJECT_TEMPLATE = """[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "__DIST_NAME__"
version = "0.1.0"
description = "FastAPI + user management structured by functionals.fx"
readme = "README.md"
requires-python = ">=3.10"
dependencies = [
    "decorates>=4.4.0",
    "fastapi>=0.111",
    "uvicorn>=0.30"
]

[project.scripts]
__SCRIPT_NAME__ = "__PACKAGE_NAME__.__main__:main"

[project.optional-dependencies]
dev = [
    "pytest>=7.4",
    "httpx>=0.27"
]

[tool.setuptools.packages.find]
where = ["src"]
include = ["__PACKAGE_NAME__*"]

[tool.setuptools]
package-dir = {"" = "src"}
"""


CLI_README_TEMPLATE = """# __PROJECT_NAME__

Todo CLI starter project structured by `functionals.fx`.

## Run

```bash
python -m __PACKAGE_NAME__ --help
```

Interactive mode:

```bash
python -m __PACKAGE_NAME__
```

## Example commands

```bash
python -m __PACKAGE_NAME__ add "Buy groceries" "Milk, eggs, bread"
python -m __PACKAGE_NAME__ list
python -m __PACKAGE_NAME__ complete 1
```
"""


DB_README_TEMPLATE = """# __PROJECT_NAME__

FastAPI + user management starter project structured by `functionals.fx`.

## Run API

```bash
python -m __PACKAGE_NAME__
```

## Endpoints

- `GET /health`
- `POST /users`
- `GET /users`
- `GET /users/{user_id}`
- `DELETE /users/{user_id}`
"""


COMMON_GITIGNORE_TEMPLATE = """.venv/
__pycache__/
.pytest_cache/
.mypy_cache/
.ruff_cache/
*.pyc
*.pyo
*.pyd
*.sqlite
*.db
.DS_Store
"""


PACKAGE_INIT_TEMPLATE = """\"\"\"__PROJECT_NAME__ starter package.\"\"\"

__all__ = []
"""


OPS_PACKAGE_INIT_TEMPLATE = """\"\"\"Operational workflows for __PROJECT_NAME__.\"\"\""""


OPS_JOBS_INIT_TEMPLATE = """\"\"\"Centralized job registrations for __PROJECT_NAME__.\"\"\""""


OPS_HEARTBEAT_JOB_TEMPLATE = """from __future__ import annotations

import functionals.cron as cron


@cron.job(
    name="ops-heartbeat",
    trigger=cron.interval(minutes=30),
    target="local_async",
    deployment_file="ops/workflows/cron/ops-heartbeat.cron",
    tags=("ops", "health"),
)
def ops_heartbeat() -> str:
    return "ops heartbeat ok"
"""


OPS_DEPLOY_JOB_TEMPLATE = """from __future__ import annotations

import functionals.cron as cron


@cron.job(
    name="deploy-workflow",
    trigger=cron.event("manual"),
    target="github_actions",
    deployment_file="ops/workflows/ci/deploy-workflow.yml",
    tags=("deploy", "ci"),
)
def deploy_workflow(payload: dict | None = None) -> str:
    env_name = (payload or {}).get("env", "staging")
    return f"deploy requested for {env_name}"
"""


OPS_SCRIPT_TEMPLATE = """#!/usr/bin/env bash
set -euo pipefail
echo "[ops] Running deploy script for __PROJECT_NAME__"
"""


OPS_CRON_WORKFLOW_TEMPLATE = """# Managed by functionals.fx
# Example Linux cron line for manual reference:
# */30 * * * * cd __PROJECT_ROOT__ && fx cron trigger ops-heartbeat __PROJECT_ROOT__
"""


OPS_CI_WORKFLOW_TEMPLATE = """name: deploy-workflow
on:
  workflow_dispatch: {}
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Trigger local workflow registration
        run: fx cron run-workflow deploy-workflow . --payload '{"env":"staging"}'
"""


OPS_WINDOWS_WORKFLOW_TEMPLATE = """<Task>
  <Name>functionals-ops-heartbeat</Name>
  <Trigger>*/30 * * * *</Trigger>
  <Action>
    <Command>python</Command>
    <Arguments>-m functionals.fx.commands cron trigger ops-heartbeat .</Arguments>
  </Action>
</Task>
"""


CLI_MAIN_TEMPLATE = """from .todo import main


if __name__ == "__main__":
    main()
"""


CLI_TODO_TEMPLATE = """from __future__ import annotations

from time import strftime

import functionals.cli as cli
import functionals.db as db
from functionals.db import db_field
from pydantic import BaseModel

DB_PATH = "todos.db"
TABLE = "todos"


def now() -> str:
    return strftime("%Y-%m-%d %H:%M:%S")


@db.database_registry(DB_PATH, table_name=TABLE, key_field="id")
class TodoItem(BaseModel):
    id: int | None = None
    title: str = db_field(index=True)
    description: str = db_field(default="")
    status: str = db_field(default="pending")
    created_at: str = db_field(default_factory=now)
    updated_at: str = db_field(default_factory=now)


@cli.register(name="add", description="Create a todo item")
@cli.argument("title", type=str, help="Todo title")
@cli.argument("description", type=str, default="", help="Todo description")
@cli.option("--add")
@cli.option("-a")
def add_todo(title: str, description: str = "") -> str:
    todo = TodoItem(title=title, description=description)
    todo.save()
    return f"Added: {todo.title} (ID: {todo.id})"


@cli.register(name="list", description="List todo items")
@cli.option("--list")
@cli.option("-l")
def list_todos() -> str:
    todos = TodoItem.objects.all()
    if not todos:
        return "No todo items found."
    return "\\n".join(f"{t.id}: {t.title} [{t.status}]" for t in todos)


@cli.register(name="complete", description="Mark a todo item as completed")
@cli.argument("todo_id", type=int, help="Todo ID")
@cli.option("--complete")
@cli.option("-c")
def complete_todo(todo_id: int) -> str:
    todo = TodoItem.objects.get(id=todo_id)
    if not todo:
        return f"Todo item with ID {todo_id} not found."
    todo.status = "completed"
    todo.updated_at = now()
    todo.save()
    return f"Completed todo ID {todo_id}."


@cli.register(name="update", description="Update a todo item")
@cli.argument("todo_id", type=int, help="Todo ID")
@cli.argument("title", type=str, default=None, help="New title")
@cli.argument("description", type=str, default=None, help="New description")
@cli.option("--update")
@cli.option("-u")
def update_todo(todo_id: int, title: str | None = None, description: str | None = None) -> str:
    todo = TodoItem.objects.get(id=todo_id)
    if not todo:
        return f"Todo item with ID {todo_id} not found."
    if title is not None:
        todo.title = title
    if description is not None:
        todo.description = description
    todo.updated_at = now()
    todo.save()
    return f"Updated todo ID {todo_id}."


def main() -> None:
    cli.load_plugins("__PLUGIN_PACKAGE__", cli.get_registry())
    cli.run(
        shell_title="__PROJECT_NAME__ Console",
        shell_description="Manage tasks.",
        shell_colors=None,
        shell_banner=True,
        shell_usage=True,
    )
"""


CLI_TEST_TEMPLATE = """from __future__ import annotations

import __PACKAGE_NAME__.todo as todo


def test_main_is_defined() -> None:
    assert callable(todo.main)
"""


DB_MAIN_TEMPLATE = """import uvicorn


def main() -> None:
    uvicorn.run("__PACKAGE_NAME__.api:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
"""


DB_MODELS_TEMPLATE = """from __future__ import annotations

from time import strftime

import functionals.db as db
from functionals.db import db_field
from pydantic import BaseModel

DB_PATH = "users.db"


def now() -> str:
    return strftime("%Y-%m-%d %H:%M:%S")


@db.database_registry(DB_PATH, table_name="users", key_field="id", unique_fields=["email"])
class User(BaseModel):
    id: int | None = None
    name: str
    email: str
    password: str
    created_at: str = db_field(default_factory=now)
    updated_at: str = db_field(default_factory=now)
"""


DB_API_TEMPLATE = """from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel

from .models import User, now


class UserCreate(BaseModel):
    name: str
    email: str
    password: str


@asynccontextmanager
async def lifespan(_app: FastAPI):
    User.create_schema()
    try:
        yield
    finally:
        User.objects.dispose()


app = FastAPI(title="__PROJECT_NAME__ API", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/users", response_model=User, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate) -> User:
    return User.objects.create(
        name=payload.name,
        email=payload.email,
        password=payload.password,
        created_at=now(),
        updated_at=now(),
    )


@app.get("/users", response_model=list[User])
def list_users(limit: int = 50, offset: int = 0) -> list[User]:
    return User.objects.filter(order_by="-id", limit=limit, offset=offset)


@app.get("/users/{user_id}", response_model=User)
def get_user(user_id: int) -> User:
    user = User.objects.get(id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found.")
    return user


@app.delete("/users/{user_id}")
def delete_user(user_id: int) -> dict[str, str]:
    user = User.objects.get(id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found.")
    user.delete()
    return {"message": f"Deleted user {user_id}."}
"""


DB_TEST_TEMPLATE = """from __future__ import annotations

from fastapi.testclient import TestClient

from __PACKAGE_NAME__.api import app


def test_health_endpoint() -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
"""


def render_template(template: str, **values: str) -> str:
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace(f"__{key.upper()}__", value)
    return rendered
