from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import BaseModel

from registers.db import (
    Agg,
    DatabaseRegistry,
    InvalidQueryError,
    Q,
    audit_actor,
    db_field,
    tenant_scope,
    unscoped,
)
from registers.db.testing import TestRegistry, assert_query_count, factory


def db_url(tmp_path, name: str = "test") -> str:
    return f"sqlite:///{tmp_path / f'{name}.db'}"


def test_manager_crud_query_projection_aggregate_and_pagination(tmp_path):
    db = DatabaseRegistry()

    @db.database_registry(db_url(tmp_path), table_name="users", key_field="id", unique_fields=["email"])
    class User(BaseModel):
        id: int | None = db_field(id_strategy="autoincrement", default=None)
        email: str
        name: str
        status: str
        role: str
        age: int

    alice = User.objects.create(email="a@example.com", name="Alice", status="active", role="admin", age=30)
    User.objects.bulk_create(
        [
            {"email": "b@example.com", "name": "Bob", "status": "trial", "role": "user", "age": 17},
            {"email": "c@example.com", "name": "Cara", "status": "disabled", "role": "user", "age": 40},
        ]
    )

    alice.update({"name": "Alicia", "age": 31})
    assert User.objects.require(alice.id).name == "Alicia"

    class Patch(BaseModel):
        name: str | None = None
        status: str | None = None

    alice.apply_patch(Patch(status="active"))
    assert User.objects.require(alice.id).status == "active"

    existing, created = User.objects.get_or_create(
        lookup={"email": "a@example.com"},
        defaults={"name": "Nope", "status": "disabled", "role": "user", "age": 1},
    )
    assert (existing.id, created) == (alice.id, False)
    new_user, created = User.objects.update_or_create(
        lookup={"email": "d@example.com"},
        defaults={"name": "Dina", "status": "active", "role": "user", "age": 28},
    )
    assert created is True
    updated, created = User.objects.update_or_create(
        lookup={"email": "d@example.com"},
        defaults={"name": "Dina+", "status": "trial", "role": "user", "age": 29},
    )
    assert (updated.id, updated.name, created) == (new_user.id, "Dina+", False)

    assert {user.email for user in User.objects.filter(Q(status="active") | Q(status="trial"))} == {
        "a@example.com",
        "b@example.com",
        "d@example.com",
    }
    assert {user.email for user in User.objects.exclude(status="disabled")} == {
        "a@example.com",
        "b@example.com",
        "d@example.com",
    }
    assert User.objects.select("email", "role", status="active") == [
        {"email": "a@example.com", "role": "admin"}
    ]
    assert User.objects.values_list("email", q=Q(role="admin")) == ["a@example.com"]
    assert User.objects.count_by("role") == {"admin": 1, "user": 3}
    assert User.objects.aggregate(Agg.count("id")) == 4
    assert User.objects.aggregate(total=Agg.count("id"), adults=Agg.count("id", age__gte=18)) == {
        "total": 4,
        "adults": 3,
    }

    page = User.objects.paginate(order_by="id", limit=2)
    assert [item.email for item in page.items] == ["a@example.com", "b@example.com"]
    assert page.has_next is True
    assert [item.email for item in User.objects.paginate(order_by="id", limit=2, cursor=page.next_cursor).items] == [
        "c@example.com",
        "d@example.com",
    ]

    assert User.objects.bulk_delete([alice.id]) == 1
    assert User.objects.bulk_delete(status="trial") == 2
    with pytest.raises(InvalidQueryError):
        User.objects.bulk_delete()
    assert User.objects.bulk_delete(dangerous_allow_full_table_delete=True) == 1


def test_soft_delete_timestamps_audit_tenancy_encryption_and_raw_sql(tmp_path):
    db = DatabaseRegistry()
    key = "local-test-key"

    @db.database_registry(
        db_url(tmp_path),
        table_name="notes",
        key_field="id",
        timestamps=True,
        soft_delete=True,
        audit_log=True,
        tenant_field="tenant_id",
        encryption_key=key,
    )
    class Note(BaseModel):
        id: int | None = db_field(id_strategy="autoincrement", default=None)
        tenant_id: str
        title: str
        secret: str = db_field(encrypted=True)
        created_at: datetime | None = None
        updated_at: datetime | None = None
        deleted_at: datetime | None = None

    with tenant_scope("acme"), audit_actor("alice"):
        note = Note.objects.create(title="Launch", secret="classified")
        assert note.tenant_id == "acme"
        assert note.created_at is not None
        assert note.updated_at is not None
        assert Note.objects.require(note.id).secret == "classified"
        with pytest.raises(InvalidQueryError):
            Note.objects.filter(secret="classified")

        note.update({"title": "Launch!"})
        assert Note.objects.delete(note.id) is True
        assert Note.objects.count() == 0
        assert Note.objects.filter(include_deleted=True)[0].deleted_at is not None
        restored = Note.objects.restore(note.id)
        assert restored.deleted_at is None
        assert Note.objects.hard_delete(note.id) is True

    with unscoped():
        rows = Note.objects.raw_dicts("SELECT operation, actor FROM notes_audit ORDER BY id")
    assert rows == [
        {"operation": "create", "actor": "alice"},
        {"operation": "update", "actor": "alice"},
        {"operation": "delete", "actor": "alice"},
        {"operation": "restore", "actor": "alice"},
        {"operation": "hard_delete", "actor": "alice"},
    ]

    with tenant_scope("beta"):
        old = Note.objects.create(title="Old", secret="x")
        Note.objects.delete(old.id)
        assert Note.objects.purge_deleted(before=datetime.now(timezone.utc) + timedelta(days=1)) == 1


@pytest.mark.asyncio
async def test_async_mode_exposes_awaitable_manager_methods(tmp_path):
    db = DatabaseRegistry()

    @db.database_registry(db_url(tmp_path), table_name="async_users", key_field="id", async_mode=True)
    class User(BaseModel):
        id: int | None = db_field(id_strategy="autoincrement", default=None)
        name: str

    async with User.objects.transaction():
        created = await User.objects.create(name="Alice")
        assert created.id is not None
    assert await User.objects.count() == 1
    assert (await User.objects.require(created.id)).name == "Alice"


def test_testing_helpers_factory_and_query_count(tmp_path):
    db = TestRegistry(db_url(tmp_path))

    @db.database_registry(table_name="users", key_field="id")
    class User(BaseModel):
        id: int | None = db_field(id_strategy="autoincrement", default=None)
        email: str
        name: str

    user_factory = factory(User, defaults={"name": "Test"})
    user = user_factory.create(email="a@example.com")
    assert user.name == "Test"
    assert user_factory.build(email="b@example.com").id is None
    assert len(user_factory.create_batch(2, email=lambda idx: f"{idx}@example.com")) == 2

    with assert_query_count(max=1):
        assert User.objects.count() == 3
