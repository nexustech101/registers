from __future__ import annotations

import pytest
from pydantic import BaseModel

from conftest import db_url
from registers.db import (
    DatabaseRegistry,
    InvalidPrimaryKeyAssignmentError,
    InvalidQueryError,
    ModelRegistrationError,
    SchemaError,
    database_registry,
    db_field,
)


def test_autocreate_fk_registration_is_non_fatal_and_recovers(tmp_path):
    url = db_url(tmp_path, "fk_autocreate")

    @database_registry(url, table_name="refresh_sessions", key_field="id")
    class RefreshSession(BaseModel):
        id: int | None = db_field(id_strategy="autoincrement", default=None)
        user_id: int = db_field(foreign_key="users.id")
        token_jti: str

    # Decoration must not crash even though FK target is defined later.
    assert RefreshSession.schema_exists() is False

    @database_registry(url, table_name="users", key_field="id")
    class User(BaseModel):
        id: int | None = db_field(id_strategy="autoincrement", default=None)
        email: str

    # Later registration should create the now-resolvable FK graph.
    assert User.schema_exists() is True
    assert RefreshSession.schema_exists() is True


def test_create_schema_strict_fk_unresolved_raises_actionable_error(tmp_path):
    url = db_url(tmp_path, "fk_strict")

    @database_registry(url, table_name="refresh_sessions", key_field="id", auto_create=False)
    class RefreshSession(BaseModel):
        id: int | None = db_field(id_strategy="autoincrement", default=None)
        user_id: int = db_field(foreign_key="users.id")
        token_jti: str

    with pytest.raises(SchemaError, match="missing referenced table 'users'"):
        RefreshSession.create_schema()


def test_create_schema_fk_succeeds_after_both_models_registered(tmp_path):
    url = db_url(tmp_path, "fk_manual")

    @database_registry(url, table_name="users", key_field="id", auto_create=False)
    class User(BaseModel):
        id: int | None = db_field(id_strategy="autoincrement", default=None)
        email: str

    @database_registry(url, table_name="refresh_sessions", key_field="id", auto_create=False)
    class RefreshSession(BaseModel):
        id: int | None = db_field(id_strategy="autoincrement", default=None)
        user_id: int = db_field(foreign_key="users.id")
        token_jti: str

    User.create_schema()
    RefreshSession.create_schema()

    assert User.schema_exists() is True
    assert RefreshSession.schema_exists() is True


def test_upsert_primary_key_only_model_does_not_crash(tmp_path):
    @database_registry(db_url(tmp_path), table_name="pk_only", key_field="id")
    class KeyOnly(BaseModel):
        id: int

    created = KeyOnly.objects.create(id=1)
    updated = KeyOnly.objects.upsert(id=1)

    assert created.id == 1
    assert updated.id == 1
    assert KeyOnly.objects.count() == 1


def test_bulk_create_rejects_explicit_autoincrement_keys(tmp_path):
    @database_registry(db_url(tmp_path), table_name="users", key_field="id")
    class User(BaseModel):
        id: int | None = db_field(id_strategy="autoincrement", default=None)
        name: str

    with pytest.raises(InvalidPrimaryKeyAssignmentError):
        User.objects.bulk_create([{"id": 99, "name": "Alice"}])


def test_update_where_rejects_operator_style_update_fields(tmp_path):
    @database_registry(db_url(tmp_path), table_name="users", key_field="id")
    class User(BaseModel):
        id: int
        name: str

    User.objects.create(id=1, name="Alice")

    with pytest.raises(InvalidQueryError, match="plain field names"):
        User.objects.update_where({"id": 1}, **{"name__like": "A%"})


def test_filter_iterable_equality_requires_in_operator(tmp_path):
    @database_registry(db_url(tmp_path), table_name="users", key_field="id")
    class User(BaseModel):
        id: int
        name: str

    User.objects.bulk_create(
        [
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"},
        ]
    )

    with pytest.raises(InvalidQueryError, match="__in"):
        User.objects.filter(id=[1, 2])

    assert [row.id for row in User.objects.filter(id__in=[1, 2], order_by="id")] == [1, 2]


def test_filter_rejects_negative_limit_or_offset(tmp_path):
    @database_registry(db_url(tmp_path), table_name="users", key_field="id")
    class User(BaseModel):
        id: int
        name: str

    User.objects.create(id=1, name="Alice")

    with pytest.raises(InvalidQueryError, match="limit must be greater than or equal to 0"):
        User.objects.filter(limit=-1)

    with pytest.raises(InvalidQueryError, match="offset must be greater than or equal to 0"):
        User.objects.filter(offset=-10)


def test_dispose_is_idempotent(tmp_path):
    @database_registry(db_url(tmp_path), table_name="users", key_field="id")
    class User(BaseModel):
        id: int
        name: str

    User.objects.create(id=1, name="Alice")
    User.objects.dispose()
    User.objects.dispose()


def test_fk_orphan_write_raises_schema_error(tmp_path):
    url = db_url(tmp_path, "fk_integrity")

    @database_registry(url, table_name="users", key_field="id")
    class User(BaseModel):
        id: int | None = db_field(id_strategy="autoincrement", default=None)
        email: str

    @database_registry(url, table_name="refresh_sessions", key_field="id")
    class RefreshSession(BaseModel):
        id: int | None = db_field(id_strategy="autoincrement", default=None)
        user_id: int = db_field(foreign_key="users.id")
        token_jti: str

    User.objects.create(email="alice@example.com")

    with pytest.raises(SchemaError, match="Database integrity error"):
        RefreshSession.objects.create(user_id=9999, token_jti="bad-jti")


def test_instance_registry_decorator_happy_path(tmp_path):
    db = DatabaseRegistry()

    @db.database_registry(db_url(tmp_path), table_name="users", key_field="id")
    class User(BaseModel):
        id: int | None = db_field(id_strategy="autoincrement", default=None)
        email: str

    created = User.objects.create(email="alice@example.com")
    fetched = User.objects.require(created.id)

    assert fetched.email == "alice@example.com"
    assert db.all()[User] is User.objects


def test_two_registry_instances_can_manage_different_databases(tmp_path):
    db_one = DatabaseRegistry()
    db_two = DatabaseRegistry()

    @db_one.database_registry(db_url(tmp_path, "one"), table_name="users_one", key_field="id")
    class UserOne(BaseModel):
        id: int | None = db_field(id_strategy="autoincrement", default=None)
        email: str

    @db_two.database_registry(db_url(tmp_path, "two"), table_name="users_two", key_field="id")
    class UserTwo(BaseModel):
        id: int | None = db_field(id_strategy="autoincrement", default=None)
        email: str

    UserOne.objects.create(email="one@example.com")
    UserTwo.objects.create(email="two@example.com")

    assert UserOne.objects.count() == 1
    assert UserTwo.objects.count() == 1


def test_same_model_cannot_be_registered_by_multiple_instances(tmp_path):
    db_one = DatabaseRegistry()
    db_two = DatabaseRegistry()

    @db_one.database_registry(db_url(tmp_path, "one"), table_name="users", key_field="id")
    class User(BaseModel):
        id: int | None = db_field(id_strategy="autoincrement", default=None)
        email: str

    with pytest.raises(ModelRegistrationError, match="already registered by another"):
        db_two.database_registry(db_url(tmp_path, "two"), table_name="users", key_field="id")(User)
