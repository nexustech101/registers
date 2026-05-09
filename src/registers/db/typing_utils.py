"""
Maps Python / Pydantic type annotations to SQLAlchemy column types.
Handles Optional, Union, constrained types, and JSON fallback.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, get_args, get_origin
from uuid import UUID

from pydantic import TypeAdapter
from sqlalchemy import JSON, Boolean, Date, DateTime, Float, Integer, LargeBinary, Numeric, String
from sqlalchemy.sql.type_api import TypeEngine

DEFAULT_VARCHAR_LENGTH = 255


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

def default_table_name(model_name: str) -> str:
    """``UserProfile`` → ``user_profiles``."""
    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", model_name).lower()
    return f"{snake}s"


def default_database_url(model_name: str) -> str:
    db_path = Path(f"{default_table_name(model_name)}.db").resolve()
    return f"sqlite:///{db_path.as_posix()}"


def normalize_database_url(database_url: str | Path) -> str:
    """Ensure the URL has a proper scheme; coerce bare paths to sqlite:///."""
    if isinstance(database_url, Path):
        return f"sqlite:///{database_url.resolve().as_posix()}"
    if "://" in str(database_url):
        return str(database_url)
    return f"sqlite:///{Path(str(database_url)).resolve().as_posix()}"


# ---------------------------------------------------------------------------
# Annotation introspection
# ---------------------------------------------------------------------------

def unwrap_annotation(annotation: Any) -> Any:
    """
    Strip Optional / Union wrappers to reach the concrete inner type.

    ``Optional[int]`` → ``int``, ``Union[str, None]`` → ``str``.
    Collection types (list, dict, …) are returned as-is so they map to JSON.
    """
    origin = get_origin(annotation)
    if origin is None:
        return annotation
    if origin in (list, dict, tuple, set, frozenset):
        return annotation
    args = [a for a in get_args(annotation) if a is not type(None)]
    if len(args) == 1:
        return unwrap_annotation(args[0])
    return annotation


def annotation_is_integer(annotation: Any) -> bool:
    resolved = unwrap_annotation(annotation)
    return resolved is int or (isinstance(resolved, type) and issubclass(resolved, int))


def annotation_is_uuid(annotation: Any) -> bool:
    resolved = unwrap_annotation(annotation)
    return resolved is UUID or (isinstance(resolved, type) and issubclass(resolved, UUID))


def field_allows_none(field: Any) -> bool:
    """Return True when the field's annotation includes NoneType."""
    annotation = field.annotation
    origin = get_origin(annotation)
    if origin is not None and type(None) in get_args(annotation):
        return True
    return field.default is None


# ---------------------------------------------------------------------------
# SQLAlchemy type mapping
# ---------------------------------------------------------------------------

# Ordered most-specific first so issubclass probes work correctly.
_DIRECT_MAP: list[tuple[type, type[TypeEngine] | Any]] = [
    (bool,     Boolean),
    (int,      Integer),
    (float,    Float),
    (Decimal,  Numeric),
    (datetime, DateTime),
    (date,     Date),
    (UUID,     lambda: String(36)),
    (str,      lambda: String(DEFAULT_VARCHAR_LENGTH)),
    (bytes,    LargeBinary),
]


def sqlalchemy_type_for_annotation(annotation: Any) -> TypeEngine[Any]:
    """Return the best SQLAlchemy column type for a Python type annotation."""
    resolved = unwrap_annotation(annotation)

    for python_type, type_factory in _DIRECT_MAP:
        if resolved is python_type:
            return type_factory()
        if isinstance(resolved, type) and issubclass(resolved, python_type):
            return type_factory()

    # Fall back to Pydantic JSON schema for Enum, Literal, custom types etc.
    schema = _json_schema_for(resolved)
    fmt    = schema.get("format", "")
    kind   = schema.get("type", "")

    if fmt in ("date-time", "datetime"):
        return DateTime()
    if fmt == "date":
        return Date()
    if fmt == "uuid":
        return String(36)
    if kind == "string":
        return String(DEFAULT_VARCHAR_LENGTH)
    if kind == "integer":
        return Integer()
    if kind == "number":
        return Float()
    if kind == "boolean":
        return Boolean()

    # Unknown / complex types stored as JSON text
    return JSON()


def sqlalchemy_type_for_field(annotation: Any, metadata: dict[str, Any] | None = None) -> TypeEngine[Any]:
    """Return the SQLAlchemy type for a model field, honoring db_field metadata."""
    metadata = metadata or {}
    explicit_type = metadata.get("db_column_type")
    if explicit_type is not None:
        if isinstance(explicit_type, TypeEngine):
            return explicit_type
        if isinstance(explicit_type, type) and issubclass(explicit_type, TypeEngine):
            return explicit_type()
        if callable(explicit_type):
            resolved = explicit_type()
            if isinstance(resolved, TypeEngine):
                return resolved
        raise TypeError("db_field(column_type=...) must be a SQLAlchemy TypeEngine, TypeEngine class, or factory.")

    resolved = unwrap_annotation(annotation)
    length = metadata.get("db_length")
    precision = metadata.get("db_precision")
    scale = metadata.get("db_scale")
    timezone = metadata.get("db_timezone")

    if resolved is str or (isinstance(resolved, type) and issubclass(resolved, str)):
        return String(length or DEFAULT_VARCHAR_LENGTH)
    if resolved is bytes or (isinstance(resolved, type) and issubclass(resolved, bytes)):
        return LargeBinary(length)
    if resolved is Decimal or (isinstance(resolved, type) and issubclass(resolved, Decimal)):
        return Numeric(precision=precision, scale=scale)
    if resolved is datetime or (isinstance(resolved, type) and issubclass(resolved, datetime)):
        return DateTime(timezone=bool(timezone))

    return sqlalchemy_type_for_annotation(annotation)


def _json_schema_for(annotation: Any) -> dict[str, Any]:
    try:
        return TypeAdapter(annotation).json_schema()
    except Exception:
        return {}
