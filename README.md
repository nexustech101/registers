# Decorates

[![PyPI version](https://img.shields.io/pypi/v/decorates)](https://pypi.org/project/decorates/)
[![Python versions](https://img.shields.io/pypi/pyversions/decorates)](https://pypi.org/project/decorates/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![CLI](https://img.shields.io/badge/module-functionals.cli-blue)](#decoratescli)
[![DB](https://img.shields.io/badge/module-functionals.db-darkorange)](#decoratesdb)
[![Tests](https://img.shields.io/badge/tested-170%2B%20tests-brightgreen)](#testing)

Decorates is a production-oriented toolkit for two common Python surfaces:

- `functionals.cli` for module-first command registration, typed arguments, and built-in help
- `functionals.db` for Pydantic model persistence and additive schema operations on SQLAlchemy

The package emphasizes explicit APIs, predictable behavior, and test-backed reliability.

## Install

```bash
pip install decorates  # Package name is `decorates`; module name is `functionals`
```

## Quick Start Guide

1. Build one CLI command with a decorator.
2. Build one DB model with a decorator.
3. Use `Model.objects` for CRUD.

### CLI in 60 seconds

```python
import functionals.cli as cli
import functionals.db as db
from pydantic import BaseModel

@db.database_registry("users.db", table_name="users", key_field="id")
class User(BaseModel):
    id: int | None = None
    name: str

@cli.register(name="add", description="Create a user")
@cli.argument("name", type=str)
@cli.option("--add")
@cli.option("-a")
def add_user(name: str) -> str:
    user = User(name=name)
    user.save()
    return f"Created user {user.id}: {user.name}"

@cli.register(name="list", description="List users")
@cli.option("--list")
@cli.option("-l")
def list_users() -> str:
    users = User.objects.all()
    if not users:
        return "No users found."
    return "\n".join(f"{u.id}: {u.name}" for u in users)

if __name__ == "__main__":
    cli.run()
```

```bash
python users.py add "Alice"
python users.py --add "Bob"
python users.py list
python users.py --help
```

### Database + FastAPI in 5 minutes

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from functionals.db import (
    RecordNotFoundError,
    UniqueConstraintError,
    database_registry,
)

DB_URL = "sqlite:///shop.db"

# --- Models ---

@database_registry(DB_URL, table_name="customers", unique_fields=["email"])
class Customer(BaseModel):
    id: int | None = None
    name: str
    email: str

@database_registry(DB_URL, table_name="products")
class Product(BaseModel):
    id: int | None = None
    name: str
    price: float

@database_registry(DB_URL, table_name="orders")
class Order(BaseModel):
    id: int | None = None
    customer_id: int
    product_id: int
    quantity: int
    total: float

# --- App ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    for model in (Customer, Product, Order):
        model.create_schema()
    yield
    for model in (Customer, Product, Order):
        model.objects.dispose()

app = FastAPI(lifespan=lifespan)

# --- Routes ---

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

# Response
{"id": 1, "name": "Alice Johnson", "email": "alice@example.com"}


# GET /customers/1
curl "http://localhost:8000/customers/1"

# Response
{"id": 1, "name": "Alice Johnson", "email": "alice@example.com"}


# POST /products
curl -X POST "http://localhost:8000/products" \
  -H "Content-Type: application/json" \
  -d '{"name": "Wireless Keyboard", "price": 49.99}'

# Response
{"id": 1, "name": "Wireless Keyboard", "price": 49.99}


# POST /orders
curl -X POST "http://localhost:8000/orders" \
  -H "Content-Type: application/json" \
  -d '{"customer_id": 1, "product_id": 1, "quantity": 2}'

# Response
{"id": 1, "customer_id": 1, "product_id": 1, "quantity": 2, "total": 99.98}


# GET /orders/asc  (oldest first)
curl "http://localhost:8000/orders/asc?limit=20&offset=0"

# Response
[
  {"id": 1, "customer_id": 1, "product_id": 1, "quantity": 2, "total": 99.98}
]


# GET /orders/desc  (newest first)
curl "http://localhost:8000/orders/desc?limit=20&offset=0"

# Response
[
  {"id": 1, "customer_id": 1, "product_id": 1, "quantity": 2, "total": 99.98}
]
```

## Core Concepts

### `functionals.cli`

- Register functions with module-level decorators: `@register`, `@argument`, `@option`.
- Run command handlers through the module registry via `functionals.cli.run()`.
- Support positional + named argument forms (for non-bool args), with bool flags as `--flag`.
- Command aliases are declared with `@option("-x")` / `@option("--long")`.
- Built-in help command is always available: `help`, `--help`, and `-h`.
- Runtime wraps unexpected handler crashes as `CommandExecutionError` (with original exception chaining).
- Operational logs use standard Python logging namespaces under `functionals.cli.*`.

### `functionals.db`

- Register `BaseModel` classes with `@database_registry(...)`.
- Access all persistence through `Model.objects`.
- `id: int | None = None` gives database-managed autoincrement IDs.
- Schema helpers are available as class methods: `create_schema`, `drop_schema`, `schema_exists`, `truncate`.
- Unexpected SQLAlchemy runtime failures are normalized into `SchemaError` for cleaner, predictable error handling.
- Operational logs use standard Python logging namespaces under `functionals.db.*`.
- DB exceptions provide structured metadata (`exc.context`, `exc.to_dict()`) for production diagnostics.

## `functionals.db` Usage Snapshot

```python
# Filtering operators
Order.objects.filter(total__gte=100)
Customer.objects.filter(email__ilike="%@example.com")
Order.objects.filter(quantity__in=[1, 2, 3])

# Sorting and pagination
Order.objects.filter(order_by="-id", limit=20, offset=0)

# Bulk writes
Product.objects.bulk_create([...])
Product.objects.bulk_upsert([...])

# Additive migration helpers
Customer.objects.ensure_column("phone", str | None, nullable=True)
Customer.objects.rename_table("customers_archive")
```

After `rename_table(...)` succeeds, the same `Model.objects` manager and
schema helpers are immediately bound to the new table name.

If your model contains a field named `password`, password values are automatically hashed on write, and instances receive `verify_password(...)`.

## Documentation

- DB guide: `src/functionals/db/USAGE.md`
- CLI source API: `src/functionals/cli`
- DB source API: `src/functionals/db`

## Requirements

- Python 3.10+
- `pydantic>=2.0`
- `sqlalchemy>=2.0`

## Testing

- The default `pytest` suite includes SQLite coverage along with PostgreSQL/MySQL integration tests for rename-state behavior.
- Run Docker Desktop, or another compatible Docker engine, before executing the backend integration suite so the services in `docker-compose.test-db.yml` can boot successfully.
- The package is backed by a rigorous, production-focused test suite (170+ tests) covering unit behavior, edge cases, and multi-dialect integration scenarios.


## License

MIT
