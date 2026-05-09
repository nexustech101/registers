"""
Module-level decorator surface for registers.db.

This stays backward-compatible by delegating to a default registry coordinator.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping, TypeVar

from pydantic import BaseModel

from registers.db.registry import DatabaseRegistry

ModelT = TypeVar("ModelT", bound=BaseModel)

_DEFAULT_DB_REGISTRY = DatabaseRegistry()


def database_registry(
    database_url: str | Path | None = None,
    *,
    table_name: str | None = None,
    key_field: str = "id",
    manager_attr: str = "objects",
    auto_create: bool = True,
    autoincrement: bool = False,
    unique_fields: list[str] | tuple[str, ...] = (),
    async_mode: bool = False,
    timestamps: bool = False,
    soft_delete: bool = False,
    audit_log: bool = False,
    audit_log_table: str | None = None,
    tenant_field: str | None = None,
    encryption_key: str | bytes | Callable[[], str | bytes] | None = None,
    log_queries: bool = False,
    slow_query_ms: int | None = None,
    engine_options: Mapping[str, Any] | None = None,
    read_replica_url: str | Path | None = None,
) -> Callable[[type[ModelT]], type[ModelT]]:
    """
    Decorate a Pydantic model and attach persistence manager as ``Model.objects``.

    Backed by a module-level default ``DatabaseRegistry`` coordinator.
    """
    return _DEFAULT_DB_REGISTRY.database_registry(
        database_url=database_url,
        table_name=table_name,
        key_field=key_field,
        manager_attr=manager_attr,
        auto_create=auto_create,
        autoincrement=autoincrement,
        unique_fields=unique_fields,
        async_mode=async_mode,
        timestamps=timestamps,
        soft_delete=soft_delete,
        audit_log=audit_log,
        audit_log_table=audit_log_table,
        tenant_field=tenant_field,
        encryption_key=encryption_key,
        log_queries=log_queries,
        slow_query_ms=slow_query_ms,
        engine_options=engine_options,
        read_replica_url=read_replica_url,
    )
