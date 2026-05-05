# Registers

[![PyPI version](https://img.shields.io/pypi/v/registers)](https://pypi.org/project/registers/)
[![Python versions](https://img.shields.io/pypi/pyversions/registers)](https://pypi.org/project/registers/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Module](https://img.shields.io/badge/module-registers-green)](#registers)
[![FX Tool](https://img.shields.io/badge/tool-fx--tool-black)](https://github.com/nexustech101/fx-tool)
![Tests](https://img.shields.io/badge/tests-250%2B%20unit%20tests-brightgreen)

Registers is a DX-first Python framework for building:

- CLI tooling systems
- Data and API services
- Scheduled/event automation workflows

It uses decorators for command, model, and job definitions, and pairs with `fx-tool`, the project manager for scaffolding, running, validating, and operating Registers projects.

This framework is for teams and developers who want one coherent toolkit for backend development and DevOps workflows instead of stitching together many unrelated layers. Build, manage, and deploy at the speed of thought.

## Why Registers

- Fast setup: generate ready-to-run CLI or DB/API projects with `fx init`.
- Unified patterns: decorators for commands (`cli`), models (`db`), and jobs (`cron`).
- Operational workflow support via `fx-tool`: run, install, update, pull plugins, and manage cron runtime.
- Plugin architecture: organize command suites into modules and load them cleanly.
- Production-minded behavior: structured state, health checks, operation history, and test coverage.
- Projects that use `registers.cli` module come with a built-in interactive shell.

## Install

```bash
pip install registers
```

Install the project manager (`fx-tool`) as a companion:

```bash
pip install fx-tool
# or from source
pip install git+https://github.com/nexustech101/fx.git
```

You can also clone directly from the repo `nexustech101/fx`:

```bash
git clone https://github.com/nexustech101/fx.git
```

## Quick Start Guide

1. Build one CLI command with a decorator.
2. Build one DB model with a decorator.
3. Use `Model.objects` for CRUD.

### CLI in minutes

```python
from __future__ import annotations

from enum import StrEnum
from time import strftime
from pydantic import BaseModel

from registers import (
    CommandRegistry,
    DatabaseRegistry,
    db_field
)

cli = CommandRegistry()
db = DatabaseRegistry()

DB_PATH = "todos.db"
TABLE = "todos"
NOW = lambda: strftime("%Y-%m-%d %H:%M:%S")


class TodoStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"


@db.database_registry(DB_PATH, table_name=TABLE, key_field="id")
class TodoItem(BaseModel):
    id: int | None = None
    title: str = db_field(index=True)
    description: str = db_field(default="")
    status: TodoStatus = db_field(default=TodoStatus.PENDING.value)
    created_at: str = db_field(default_factory=NOW)
    updated_at: str = db_field(default_factory=NOW)


@cli.register(name="add", description="Create a todo item")
@cli.argument("title", type=str, help="Todo title")
@cli.argument("description", type=str, default="", help="Todo description")
@cli.alias("--add")
@cli.alias("-a")
def add_todo(title: str, description: str = "") -> str:
    todo = TodoItem(title=title, description=description)
    todo.save()
    return f"Added: {todo.title} (ID: {todo.id})"


@cli.register(name="list", description="List todo items")
@cli.alias("--list")
@cli.alias("-l")
def list_todos() -> str:
    todos = TodoItem.objects.all()
    if not todos:
        return "No todo items found."
    return "\n".join(f"{t.id}: {t.title} [{t.status}]" for t in todos)


@cli.register(name="complete", description="Mark a todo item as completed")
@cli.argument("todo_id", type=int, help="Todo ID")
@cli.alias("--complete")
@cli.alias("-c")
def complete_todo(todo_id: int) -> str:
    todo = TodoItem.objects.get(id=todo_id)
    if not todo:
        return f"Todo item with ID {todo_id} not found."

    todo.status = TodoStatus.COMPLETED.value
    todo.updated_at = NOW()
    todo.save()
    return f"Completed todo ID {todo_id}."


@cli.register(name="update", description="Update a todo item")
@cli.argument("todo_id", type=int, help="Todo ID")
@cli.argument("title", type=str, default=None, help="New title")
@cli.argument("description", type=str, default=None, help="New description")
@cli.alias("--update")
@cli.alias("-u")
def update_todo(todo_id: int, title: str | None = None, description: str | None = None) -> str:
    todo = TodoItem.objects.get(id=todo_id)
    if not todo:
        return f"Todo item with ID {todo_id} not found."

    todo.title = title or ""
    todo.description = description or ""
    todo.updated_at = NOW()
    todo.save()
    return f"Updated todo ID {todo_id}."


if __name__ == "__main__":
    cli.run(
        shell_title="Todo Console",
        shell_description="Manage tasks.",
        shell_colors=None,
        shell_banner=True,
        shell_usage=True,  # Prints usage menu on startup
    )
```

Run it as follows:

```bash
# Add
python todo.py add "Buy groceries" "Milk, eggs, bread"
python todo.py --add "Buy groceries" "Milk, eggs, bread"
python todo.py -a "Buy groceries" "Milk, eggs, bread"
python todo.py add --title "Buy groceries" --description "Milk, eggs, bread"

# List
python todo.py list
python todo.py --list
python todo.py -l

# Complete
python todo.py complete 1
python todo.py --complete 1
python todo.py -c 1

# Update
python todo.py update 1 "Read two books" "Finish both novels this week"
python todo.py update 1 --title "Read two books" --description "Finish both novels this week"
python todo.py --update 1 --title "Read two books"
```

Or:

```bash
# Run directly for interactive mode
python todo.py
```
Interactive mode:

![Screenshot](img1.png)

`fx-tool` is the recommended way to manage Registers projects end-to-end.
Think of it as the project operations companion for Registers, similar to how
`pip` supports Python package workflows or how `npm` supports Node package workflows.
For full `fx` usage, see the `fx-tool` docs in the separate repo.


For larger plugin-based CLIs, explicit plugin registry composition is supported:

```python
from __future__ import annotations

from cli.commands.billing import cli as billing_cli
from cli.commands.ops import cli as ops_cli
from cli.commands.sessions import cli as sessions_cli
from cli.commands.users import cli as users_cli

from registers import CommandRegistry


registry = CommandRegistry()
try:
    registry.register_plugin(billing_cli)
    registry.register_plugin(users_cli)
    registry.register_plugin(ops_cli)
    registry.register_plugin(sessions_cli)
except Exception as exc:
    raise SystemError(f"Failed to load CLI plugins: {exc}")


def main() -> None:
    try:
        return registry.run(
            print_result=True,
            shell_title="User Account Admin CLI",
            shell_description="Manage user accounts and auth sessions.",
            shell_usage=True,
        )
    except Exception as exc:
        raise SystemError(f"CLI execution failed: {exc}") from exc


if __name__ == "__main__":
    main()
```

### Database + FastAPI in 5 minutes

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from registers import (
    DatabaseRegistry,
    db_field,
    RecordNotFoundError,
    UniqueConstraintError,
)

DB_URL = "sqlite:///shop.db"
db = DatabaseRegistry()

# ---- Models ----

@db.database_registry(DB_URL, table_name="customers", unique_fields=["email"])
class Customer(BaseModel):
    id: int | None = None
    name: str
    email: str

@db.database_registry(DB_URL, table_name="products")
class Product(BaseModel):
    id: int | None = None
    name: str
    price: float

@db.database_registry(DB_URL, table_name="orders")
class Order(BaseModel):
    id: int | None = None
    customer_id: int
    product_id: int
    quantity: int
    total: float

# ---- App ----

@asynccontextmanager
async def lifespan(app: FastAPI):
    for model in (Customer, Product, Order):
        model.create_schema()
    yield
    for model in (Customer, Product, Order):
        model.objects.dispose()

app = FastAPI(lifespan=lifespan)

# ---- Routes ----

@app.post("/customers", response_model=Customer, status_code=201)
def create_customer(name: str, email: str):
    return Customer.objects.create(name=name, email=email)

@app.get("/customers/{customer_id}", response_model=Customer)
def get_customer(customer_id: int):
    return Customer.objects.require(customer_id)

@app.post("/products", response_model=Product, status_code=201)
def create_product(name: str, price: float):
    return Product.objects.create(name=name, price=price)

@app.post("/orders", response_model=Order, status_code=201)
def create_order(customer_id: int, product_id: int, quantity: int):
    product = Product.objects.require(product_id)
    return Order.objects.create(
        customer_id=customer_id,
        product_id=product_id,
        quantity=quantity,
        total=product.price * quantity,
    )

@app.get("/orders/desc", response_model=list[Order])
def list_orders_desc(limit: int = 20, offset: int = 0):  # Filter by oldest   (1, 2, 3,..., n)
    return Order.objects.filter(order_by="id", limit=limit, offset=offset)

@app.get("/orders/asc", response_model=list[Order])
def list_orders_asc(limit: int = 20, offset: int = 0):  # Filter by newest  (n,..., 3, 2, 1)
    return Order.objects.filter(order_by="-id", limit=limit, offset=offset)
```

```bash
# POST /customers
curl -X POST "http://localhost:8000/customers" \
  -H "Content-Type: application/json" \
  -d '{"name": "Alice Johnson", "email": "alice@example.com"}'

# GET /customers/1
curl "http://localhost:8000/customers/1"

# POST /products
curl -X POST "http://localhost:8000/products" \
  -H "Content-Type: application/json" \
  -d '{"name": "Wireless Keyboard", "price": 49.99}'

# POST /orders
curl -X POST "http://localhost:8000/orders" \
  -H "Content-Type: application/json" \
  -d '{"customer_id": 1, "product_id": 1, "quantity": 2}'

# GET /orders/asc  (oldest first)
curl "http://localhost:8000/orders/asc?limit=20&offset=0"

# GET /orders/desc  (newest first)
curl "http://localhost:8000/orders/desc?limit=20&offset=0"
```

## Cron + Workflow Operations

Use `registers.cron` decorators to define manual, interval, cron, webhook, and
file-change jobs. A normal `registers.cli` script can install a `cron` command
to list, run, status-check, and persist the jobs it defines; `fx-tool` remains
an aliasal operator companion for project/workflow orchestration.

Both cron registration styles are supported:

```python
# Module-level style
from registers import CronRegistry

cron = CronRegistry()

@cron.job
def rebuild(payload: dict | None = None) -> str:
    return f"rebuilt:{bool((payload or {}).get('dry_run'))}"


@cron.watch("src/**/*.py", debounce_seconds=1.0)
def rebuild_on_source_change(event: dict) -> str:
    return f"changed:{event['payload']['path']}"


@cron.job(
    name="nightly",
    trigger=cron.cron("0 2 * * *"),
    target="local_async",
    retry_policy="exponential",
    retry_max_attempts=5,
    retry_backoff_seconds=10,
    retry_max_backoff_seconds=180,
    retry_jitter_seconds=2,
)
def nightly() -> str:
    return "ok"


print(cron.run("rebuild", payload={"dry_run": True}))
cron.register("nightly", root=".", apply=False)
```

Self-contained CLI management:

```python
from registers import (
    CommandRegistry,
    CronRegustry
)

cli = CommandRegistry()
cron = CronRegistry()


@cron.job(name="nightly", trigger=cron.cron("0 2 * * *"))
def nightly() -> str:
    return "ok"


cron.install_cli()


if __name__ == "__main__":
    cli.run()
```

```bash
python app.py cron jobs
python app.py cron run nightly .
python app.py cron register nightly . --target auto --apply
```

`--target auto` installs the appropriate platform scheduler target and the
persistent command calls back into the same script with `cron run`.

Retry-capable jobs are moved to `dead_letter` state when max attempts are exhausted.
File-change jobs use the `watchdog` Python library under the daemon runtime.

## Architecture

- `registers.cli`
  Decorator-driven command registration (module facade + explicit registry instances), parser/dispatch, interactive shell, and plugin loading.

- `registers.db`
  Decorator-driven persistence for Pydantic models with SQLAlchemy-backed storage and model manager patterns.

- `registers.cron`
  Decorator-driven interval/cron/event jobs with async runtime and deployment artifact generation.

- `fx-tool` (separate package)
  Project manager and operations CLI for Registers workflows (scaffolding, runtime ops, cron lifecycle, and workflow orchestration).

## Who This Is For

- Backend engineers building internal tools and service utilities.
- Platform and DevOps engineers standardizing automation workflows.
- Teams building plugin-based command ecosystems for shared operations.
- AI tooling teams that need a clear path from local workflows to managed automation.
- Any engineer who needs a fast and robust solution to data intensive applications.

## Documentation

- Project architecture spec: `PROJECT_SPEC.md`
- CLI manual: `src/registers/cli/USAGE.md`
- DB manual: `src/registers/db/USAGE.md`
- FX tool docs (separate package): `https://github.com/nexustech101/fx-tool`
- Cron manual: `src/registers/cron/USAGE.md` (if present in your version)

## Roadmap and Planned Extensions

Registers is production-ready today and actively expanding into agentic tooling workflows. Planned additions include:

- MCP support:
  A decorator-based framework for defining and operating MCP servers.

- Worktree data capabilities:
  Structured storage/retrieval of project workspace state for tooling and automation contexts.

- Data-structure library for AI tooling:
  Graph and tree primitives (including knowledge graph patterns) for efficient lookup, relationship modeling, hierarchy traversal, and large-project representation.

- LLM tooling decorators:
  Decorator-driven tool definitions and memory/knowledge wiring for agent workflows.

These additions are designed to work with the current `fx-tool + cli + db + cron` architecture rather than replace it.

## Requirements

- Python 3.10+
- `pydantic>=2.0`
- `sqlalchemy>=2.0`

## Testing

- The default `pytest` suite includes SQLite coverage along with PostgreSQL/MySQL integration tests for rename-state behavior.
- Run Docker Desktop, or another compatible Docker engine, before executing the backend integration suite so the services in `docker-compose.test-db.yml` can boot successfully.
- The package is backed by a rigorous, production-focused test suite (200+ tests) covering unit behavior, edge cases, and multi-dialect integration scenarios.


## License

MIT
