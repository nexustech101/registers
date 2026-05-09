from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest
from pydantic import BaseModel
from sqlalchemy import DateTime, LargeBinary, Numeric, String, create_engine, event, inspect, text

from conftest import db_url
from registers.db import (
    DatabaseRegistry,
    MigrationError,
    PasswordHashPolicy,
    configure_password_policy,
    db_field,
    hash_password,
    prefetch,
    verify_and_upgrade_password,
)


def test_registry_transaction_binds_manager_crud_and_rolls_back(tmp_path):
    url = db_url(tmp_path)
    db = DatabaseRegistry()

    @db.database_registry(url, table_name="users", key_field="id", auto_create=False)
    class User(BaseModel):
        id: int | None = db_field(id_strategy="autoincrement", default=None)
        email: str

    @db.database_registry(url, table_name="orders", key_field="id", auto_create=False)
    class Order(BaseModel):
        id: int | None = db_field(id_strategy="autoincrement", default=None)
        user_id: int = db_field(foreign_key="users.id")
        total: Decimal

    db.create_all()

    with pytest.raises(RuntimeError, match="abort"):
        with db.transaction():
            user = User.objects.create(email="alice@example.com")
            Order.objects.create(user_id=user.id, total=Decimal("12.50"))
            assert User.objects.count() == 1
            assert Order.objects.count() == 1
            raise RuntimeError("abort")

    assert User.objects.count() == 0
    assert Order.objects.count() == 0


def test_manager_transaction_binds_manager_crud_and_rolls_back(tmp_path):
    url = db_url(tmp_path)

    db = DatabaseRegistry()

    @db.database_registry(url, table_name="users", key_field="id")
    class User(BaseModel):
        id: int | None = db_field(id_strategy="autoincrement", default=None)
        email: str

    with pytest.raises(RuntimeError):
        with User.objects.transaction():
            User.objects.create(email="alice@example.com")
            assert User.objects.count() == 1
            raise RuntimeError("rollback")

    assert User.objects.count() == 0


def test_registry_schema_lifecycle_diff_and_assertion(tmp_path):
    url = db_url(tmp_path)
    engine = create_engine(url, future=True)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE accounts (id INTEGER PRIMARY KEY, email VARCHAR(255) NOT NULL)"))
    engine.dispose()

    db = DatabaseRegistry()

    @db.database_registry(url, table_name="accounts", key_field="id", auto_create=False)
    class Account(BaseModel):
        id: int
        email: str
        name: str

    diff = db.diff_all()["accounts"]

    assert diff.ok is False
    assert diff.missing_columns == ["name"]
    assert db.check_all() is False
    with pytest.raises(MigrationError, match="Schema drift"):
        db.assert_schema_current()

    assert db.create_all() is None
    assert inspect(Account.objects._engine).has_table("registers_schema_migrations")


def test_db_field_column_metadata_controls_sqlalchemy_types(tmp_path):
    db = DatabaseRegistry()

    @db.database_registry(db_url(tmp_path), table_name="measurements", key_field="id")
    class Measurement(BaseModel):
        id: int | None = db_field(id_strategy="autoincrement", default=None)
        label: str = db_field(length=512)
        amount: Decimal = db_field(precision=12, scale=4)
        captured_at: datetime = db_field(timezone=True)
        payload: bytes
        explicit_payload: bytes = db_field(column_type=LargeBinary(2048))

    table = Measurement.objects._table

    assert isinstance(table.c.label.type, String)
    assert table.c.label.type.length == 512
    assert isinstance(table.c.amount.type, Numeric)
    assert table.c.amount.type.precision == 12
    assert table.c.amount.type.scale == 4
    assert isinstance(table.c.captured_at.type, DateTime)
    assert table.c.captured_at.type.timezone is True
    assert isinstance(table.c.payload.type, LargeBinary)
    assert isinstance(table.c.explicit_payload.type, LargeBinary)
    assert table.c.explicit_payload.type.length == 2048


def test_prefetch_batches_many_to_many_relationship_access(tmp_path):
    from registers.db import ManyToMany

    url = db_url(tmp_path)
    db = DatabaseRegistry()

    @db.database_registry(url, table_name="posts", key_field="id")
    class Post(BaseModel):
        id: int | None = db_field(id_strategy="autoincrement", default=None)
        title: str

    @db.database_registry(url, table_name="tags", key_field="id")
    class Tag(BaseModel):
        id: int | None = db_field(id_strategy="autoincrement", default=None)
        name: str

    @db.database_registry(url, table_name="post_tags", key_field="id")
    class PostTag(BaseModel):
        id: int | None = db_field(id_strategy="autoincrement", default=None)
        post_id: int = db_field(foreign_key="posts.id", index=True)
        tag_id: int = db_field(foreign_key="tags.id", index=True)

    Post.tags = ManyToMany(Tag, through=PostTag, source_key="post_id", target_key="tag_id")

    first = Post.objects.create(title="First")
    second = Post.objects.create(title="Second")
    python = Tag.objects.create(name="python")
    sql = Tag.objects.create(name="sql")
    PostTag.objects.bulk_create(
        [
            {"post_id": first.id, "tag_id": python.id},
            {"post_id": first.id, "tag_id": sql.id},
            {"post_id": second.id, "tag_id": sql.id},
        ]
    )

    posts = Post.objects.all(order_by="id")
    prefetch(posts, "tags")

    selects: list[str] = []

    @event.listens_for(Post.objects._engine, "before_cursor_execute")
    def _count_selects(_conn, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().lower().startswith("select"):
            selects.append(statement)

    assert [[tag.name for tag in post.tags] for post in posts] == [["python", "sql"], ["sql"]]
    assert selects == []


def test_password_policy_upgrade_helpers_are_configurable():
    previous = configure_password_policy(PasswordHashPolicy(scheme="pbkdf2_sha256", iterations=600_000))
    try:
        old_hash = hash_password("secret", policy=PasswordHashPolicy(scheme="pbkdf2_sha256", iterations=1_000))
        configure_password_policy(PasswordHashPolicy(scheme="pbkdf2_sha256", iterations=2_000))

        verified, upgraded = verify_and_upgrade_password("secret", old_hash)

        assert verified is True
        assert upgraded is not None
        assert upgraded != old_hash
        assert "$2000$" in upgraded
    finally:
        configure_password_policy(previous)
