"""
db_registry
~~~~~~~~~~~
Decorator-driven persistence registry for Pydantic models.

Quick start
-----------

::

    from pydantic import BaseModel
    from registers.db import database_manager

    @database_registry(
        "sqlite:///users.db",
        table_name="users",
        key_field="id",
        autoincrement=True,
        unique_fields=["email"],
    )
    class User(BaseModel):
        id: int | None = None
        name: str
        email: str

    # All persistence lives on the manager
    user  = User.objects.create(name="Alice", email="alice@example.com")
    users = User.objects.all()
    user.save()
    user.delete()

    # Schema helpers
    User.create_schema()
    User.schema_exists()
"""

from registers.db.decorators import database_registry
from registers.db.engine import dispose_all, dispose_engine, get_engine
from registers.db.exceptions import (
    ConfigurationError,
    DuplicateKeyError,
    ImmutableFieldError,
    InvalidPrimaryKeyAssignmentError,
    InvalidQueryError,
    MigrationError,
    ModelRegistrationError,
    RecordNotFoundError,
    RegistryError,
    RelationshipError,
    SchemaError,
    UniqueConstraintError,
)
from registers.db.registry import DatabaseRegistry
from registers.db.relations import BelongsTo, HasMany, HasManyThrough
from registers.db.schema import SchemaManager
from registers.db.metadata import RegistryConfig
from registers.db.fields import db_field
from registers.db.security import hash_password, is_password_hash, verify_password

__all__ = [
    # Core
    "database_registry",
    "DatabaseRegistry",
    "db_field",
    "hash_password",
    "is_password_hash",
    "verify_password",
    # Relationships
    "HasMany",
    "BelongsTo",
    "HasManyThrough",
    # Schema evolution
    "SchemaManager",
    # Engine management
    "get_engine",
    "dispose_engine",
    "dispose_all",
    # Config
    "RegistryConfig",
    # Exceptions
    "RegistryError",
    "ConfigurationError",
    "ModelRegistrationError",
    "SchemaError",
    "MigrationError",
    "RelationshipError",
    "DuplicateKeyError",
    "InvalidPrimaryKeyAssignmentError",
    "ImmutableFieldError",
    "UniqueConstraintError",
    "RecordNotFoundError",
    "InvalidQueryError",
]
