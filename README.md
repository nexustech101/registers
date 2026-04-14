# registers

Decorator-driven tooling for Python:

- `registers.cli` for ergonomic command-line apps
- `registers.db` for Pydantic + SQLAlchemy persistence

The philosophy is simple: minimal setup, predictable behavior, and a fast path to shipping.

## Install

```bash
pip install registers
```

## Quick Start

1. Build one CLI command with a decorator.
2. Build one DB model with a decorator.
3. Use `Model.objects` for CRUD.

### CLI in 60 seconds

```python
from registers.cli import CommandRegistry

cli = CommandRegistry()


@cli.register(
    name="greet",
    description="Greet someone",
    options=["-g", "--greet"],
)
def greet(name: str) -> str:
    return f"Hello, {name}!"


if __name__ == "__main__":
    cli.run()
```

```bash
python app.py greet Alice
python app.py --greet Alice
python app.py g Alice
```

### Database + FastAPI in 5 minutes

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from registers.db import (
    RecordNotFoundError,
    UniqueConstraintError,
    database_registry,
)

DB_URL = "sqlite:///shop.db"


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


class CreateCustomer(BaseModel):
    name: str
    email: str


class CreateProduct(BaseModel):
    name: str
    price: float


class CreateOrder(BaseModel):
    customer_id: int
    product_id: int
    quantity: int


@asynccontextmanager
async def lifespan(app: FastAPI):
    for model in (Customer, Product, Order):
        model.create_schema()
    yield
    for model in (Customer, Product, Order):
        model.objects.dispose()


app = FastAPI(lifespan=lifespan)


@app.post("/customers", response_model=Customer, status_code=201)
def create_customer(payload: CreateCustomer):
    try:
        return Customer.objects.create(**payload.model_dump())
    except UniqueConstraintError:
        raise HTTPException(status_code=409, detail="Email already exists")


@app.get("/customers/{customer_id}", response_model=Customer)
def get_customer(customer_id: int):
    try:
        return Customer.objects.require(customer_id)
    except RecordNotFoundError:
        raise HTTPException(status_code=404, detail="Customer not found")


@app.post("/products", response_model=Product, status_code=201)
def create_product(payload: CreateProduct):
    return Product.objects.create(**payload.model_dump())


@app.post("/orders", response_model=Order, status_code=201)
def create_order(payload: CreateOrder):
    customer = Customer.objects.get(payload.customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")

    product = Product.objects.get(payload.product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    return Order.objects.create(
        customer_id=customer.id,
        product_id=product.id,
        quantity=payload.quantity,
        total=product.price * payload.quantity,
    )


@app.get("/orders", response_model=list[Order])
def list_orders(limit: int = 20, offset: int = 0):
    return Order.objects.filter(order_by="-id", limit=limit, offset=offset)
```

## Core Concepts

### `registers.cli`

- Register functions as commands with `@cli.register(...)`.
- Type annotations drive argument parsing.
- Optional command aliases with `options=["-x", "--long"]`.
- Optional DI (`DIContainer`) and middleware (`MiddlewareChain`).

### `registers.db`

- Register `BaseModel` classes with `@database_registry(...)`.
- Access all persistence through `Model.objects`.
- `id: int | None = None` gives database-managed autoincrement IDs.
- Schema helpers are available as class methods: `create_schema`, `drop_schema`, `schema_exists`, `truncate`.

## `registers.db` Usage Snapshot

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

If your model contains a field named `password`, password values are automatically hashed on write, and instances receive `verify_password(...)`.

## Documentation

- DB guide: `src/registers/db/USAGE.md`
- CLI source API: `src/registers/cli`
- DB source API: `src/registers/db`

## Requirements

- Python 3.10+
- `pydantic>=2.0`
- `sqlalchemy>=2.0`

## License

MIT
