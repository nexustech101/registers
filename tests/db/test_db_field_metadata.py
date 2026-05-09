from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel
from sqlalchemy import inspect, text

from conftest import db_url
from registers.db import (
    ConfigurationError,
    DuplicateKeyError,
    UniqueConstraintError,
    database_registry,
    db_field,
)


def test_db_field_index_creates_database_index(tmp_path):
    @database_registry(db_url(tmp_path), table_name="products", key_field="id")
    class Product(BaseModel):
        id: int
        sku: str = db_field(index=True)
        name: str

    indexes = inspect(Product.objects._engine).get_indexes(Product.objects.table_name)
    indexed_columns = {tuple(index["column_names"]) for index in indexes}

    assert ("sku",) in indexed_columns


def test_db_field_unique_enforces_constraint_without_unique_fields_option(tmp_path):
    @database_registry(db_url(tmp_path), table_name="users", key_field="id")
    class User(BaseModel):
        id: int
        email: str = db_field(unique=True)

    User.objects.create(id=1, email="alice@example.com")
    with pytest.raises(UniqueConstraintError):
        User.objects.create(id=2, email="alice@example.com")


def test_db_field_autoincrement_enables_generated_ids(tmp_path):
    @database_registry(db_url(tmp_path), table_name="users", key_field="id")
    class User(BaseModel):
        id: int | None = db_field(
            primary_key=True,
            id_strategy="autoincrement",
            default=None,
        )
        name: str

    u1 = User.objects.create(name="Alice")
    u2 = User.objects.create(name="Bob")

    assert (u1.id, u2.id) == (1, 2)


def test_db_field_uuid4_generates_binary_uuid_primary_key(tmp_path):
    @database_registry(db_url(tmp_path), table_name="accounts", key_field="id")
    class Account(BaseModel):
        id: UUID | None = db_field(id_strategy="uuid4", default=None)
        email: str

    account = Account.objects.create(email="alice@example.com")
    fetched = Account.objects.require(account.id)
    filtered = Account.objects.filter(id__in=[account.id])

    with Account.objects._engine.begin() as conn:
        raw_id = conn.execute(text("SELECT id FROM accounts")).scalar_one()

    assert isinstance(account.id, UUID)
    assert fetched.id == account.id
    assert filtered[0].id == account.id
    assert isinstance(raw_id, bytes)
    assert len(raw_id) == 16


def test_db_field_uuid4_accepts_explicit_uuid_and_enforces_pk_uniqueness(tmp_path):
    @database_registry(db_url(tmp_path), table_name="accounts", key_field="id")
    class Account(BaseModel):
        id: UUID | None = db_field(id_strategy="uuid4", default=None)
        email: str

    account_id = uuid4()
    Account.objects.create(id=account_id, email="alice@example.com")

    with pytest.raises(DuplicateKeyError):
        Account.objects.create(id=account_id, email="alice2@example.com")


def test_nullable_key_requires_explicit_id_strategy(tmp_path):
    with pytest.raises(ConfigurationError, match="explicit id strategy"):
        @database_registry(db_url(tmp_path), table_name="users", key_field="id")
        class User(BaseModel):
            id: int | None = None
            name: str


def test_db_field_id_strategy_rejects_invalid_configurations(tmp_path):
    with pytest.raises(ConfigurationError, match="id_strategy"):
        db_field(id_strategy="snowflake")  # type: ignore[arg-type]

    with pytest.raises(ConfigurationError, match="only supported on the key_field"):
        @database_registry(db_url(tmp_path), table_name="users", key_field="id")
        class User(BaseModel):
            id: int
            public_id: UUID | None = db_field(id_strategy="uuid4", default=None)

    with pytest.raises(ConfigurationError, match="manual"):
        @database_registry(db_url(tmp_path), table_name="manual_keys", key_field="id")
        class ManualKey(BaseModel):
            id: int | None = db_field(id_strategy="manual", default=None)

    with pytest.raises(ConfigurationError, match="requires a UUID key field"):
        @database_registry(db_url(tmp_path), table_name="sessions", key_field="id")
        class Session(BaseModel):
            id: str | None = db_field(id_strategy="uuid4", default=None)

    with pytest.raises(ConfigurationError, match="default=None"):
        @database_registry(db_url(tmp_path), table_name="tokens", key_field="id")
        class Token(BaseModel):
            id: UUID | None = db_field(id_strategy="uuid4")

    with pytest.raises(ConfigurationError, match="conflicts with autoincrement"):
        @database_registry(
            db_url(tmp_path),
            table_name="events",
            key_field="id",
            autoincrement=True,
        )
        class Event(BaseModel):
            id: UUID | None = db_field(id_strategy="uuid4", default=None)


def test_db_field_primary_key_must_match_configured_key_field(tmp_path):
    with pytest.raises(ConfigurationError, match="db_field\\(primary_key=True\\)"):
        @database_registry(db_url(tmp_path), table_name="sessions", key_field="id")
        class Session(BaseModel):
            id: int
            session_id: int = db_field(primary_key=True)


def test_db_field_foreign_key_requires_table_column_format():
    with pytest.raises(ConfigurationError, match="table.column"):
        db_field(foreign_key="users")

    with pytest.raises(ConfigurationError, match="table.column"):
        db_field(foreign_key="users.")

    with pytest.raises(ConfigurationError, match="table.column"):
        db_field(foreign_key="")


def test_db_field_rejects_non_boolean_flags():
    with pytest.raises(ConfigurationError, match="must be a bool"):
        db_field(index="yes")  # type: ignore[arg-type]

    with pytest.raises(ConfigurationError, match="must be a bool"):
        db_field(unique=1)  # type: ignore[arg-type]


def test_db_field_normalizes_foreign_key_whitespace(tmp_path):
    @database_registry(db_url(tmp_path), table_name="users", key_field="id")
    class User(BaseModel):
        id: int

    @database_registry(db_url(tmp_path), table_name="sessions", key_field="id")
    class Session(BaseModel):
        id: int
        user_id: int = db_field(foreign_key="  users.id   ")

    # Creation should succeed when FK metadata is normalized.
    User.objects.create(id=1)
    created = Session.objects.create(id=1, user_id=1)
    assert created.user_id == 1
