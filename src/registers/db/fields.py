from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any, Literal

from pydantic import Field

from registers.db.exceptions import ConfigurationError


_FK_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*$")
_VALID_ID_STRATEGIES: set[str] = {"manual", "autoincrement", "uuid4"}


def _require_bool(name: str, value: bool) -> bool:
    if not isinstance(value, bool):
        raise ConfigurationError(
            f"db_field({name}=...) must be a bool, got {type(value).__name__}."
        )
    return value


def _normalize_foreign_key(foreign_key: str | None) -> str | None:
    if foreign_key is None:
        return None
    if not isinstance(foreign_key, str):
        raise ConfigurationError(
            f"db_field(foreign_key=...) must be a string in 'table.column' format, "
            f"got {type(foreign_key).__name__}."
        )
    normalized = foreign_key.strip()
    if not normalized or not _FK_PATTERN.match(normalized):
        raise ConfigurationError(
            "db_field(foreign_key=...) must use 'table.column' format."
        )
    return normalized


def _normalize_id_strategy(
    id_strategy: Literal["manual", "autoincrement", "uuid4"] | None,
) -> str | None:
    if id_strategy is None:
        return None
    if not isinstance(id_strategy, str):
        raise ConfigurationError(
            "db_field(id_strategy=...) must be one of: "
            "'manual', 'autoincrement', 'uuid4'."
        )
    normalized = id_strategy.strip().lower()
    if normalized not in _VALID_ID_STRATEGIES:
        raise ConfigurationError(
            "db_field(id_strategy=...) must be one of: "
            "'manual', 'autoincrement', 'uuid4'."
        )
    return normalized


def _normalize_positive_int(name: str, value: int | None) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ConfigurationError(f"db_field({name}=...) must be a positive integer.")
    return value


def db_field(
    *,
    primary_key: bool = False,
    autoincrement: bool = False,
    unique: bool = False,
    index: bool = False,
    foreign_key: str | None = None,
    hash_password: bool = False,
    id_strategy: Literal["manual", "autoincrement", "uuid4"] | None = None,
    length: int | None = None,
    precision: int | None = None,
    scale: int | None = None,
    timezone: bool | None = None,
    column_type: Any = None,
    exclude_from_db: bool = False,
    encrypted: bool = False,
    **kwargs: Any,
) -> Field:
    normalized_foreign_key = _normalize_foreign_key(foreign_key)
    normalized_id_strategy = _normalize_id_strategy(id_strategy)
    normalized_length = _normalize_positive_int("length", length)
    normalized_precision = _normalize_positive_int("precision", precision)
    normalized_scale = _normalize_positive_int("scale", scale)
    if timezone is not None and not isinstance(timezone, bool):
        raise ConfigurationError(
            f"db_field(timezone=...) must be a bool when provided, got {type(timezone).__name__}."
        )

    return Field(
        json_schema_extra={
            "db_primary_key": _require_bool("primary_key", primary_key),
            "db_autoincrement": _require_bool("autoincrement", autoincrement),
            "db_unique": _require_bool("unique", unique),
            "db_index": _require_bool("index", index),
            "db_foreign_key": normalized_foreign_key,
            "db_hash_password": _require_bool("hash_password", hash_password),
            "db_id_strategy": normalized_id_strategy,
            "db_length": normalized_length,
            "db_precision": normalized_precision,
            "db_scale": normalized_scale,
            "db_timezone": timezone,
            "db_column_type": column_type,
            "db_exclude_from_db": _require_bool("exclude_from_db", exclude_from_db),
            "db_encrypted": _require_bool("encrypted", encrypted),
        },
        **kwargs,
    )


def get_db_field_metadata(field_info: Any) -> dict[str, Any]:
    """Return normalized db_field metadata from a Pydantic FieldInfo object."""
    metadata = getattr(field_info, "json_schema_extra", None)
    if not isinstance(metadata, Mapping):
        return {}

    return {
        "db_primary_key": bool(metadata.get("db_primary_key", False)),
        "db_autoincrement": bool(metadata.get("db_autoincrement", False)),
        "db_unique": bool(metadata.get("db_unique", False)),
        "db_index": bool(metadata.get("db_index", False)),
        "db_foreign_key": metadata.get("db_foreign_key"),
        "db_hash_password": bool(metadata.get("db_hash_password", False)),
        "db_id_strategy": metadata.get("db_id_strategy"),
        "db_length": metadata.get("db_length"),
        "db_precision": metadata.get("db_precision"),
        "db_scale": metadata.get("db_scale"),
        "db_timezone": metadata.get("db_timezone"),
        "db_column_type": metadata.get("db_column_type"),
        "db_exclude_from_db": bool(metadata.get("db_exclude_from_db", False)),
        "db_encrypted": bool(metadata.get("db_encrypted", False)),
    }
