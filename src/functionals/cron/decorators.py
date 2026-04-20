"""
Public decorator API for ``functionals.cron``.
"""

from __future__ import annotations

from typing import Any

from functionals.cron.registry import CronRegistry, TriggerSpec


_default_registry = CronRegistry()  # Singleton registry instance for the module


def job(
    name: str | None = None,
    *,
    trigger: TriggerSpec,
    target: str = "local_async",
    deployment_file: str = "",
    enabled: bool = True,
    max_runtime: int = 0,
    tags: tuple[str, ...] | list[str] | None = None,
    overlap_policy: str = "skip",
    retry_policy: str = "none",
):
    """Register a decorated callable as a cron job."""

    def decorator(fn: Any) -> Any:
        _default_registry.register(
            fn,
            name=name,
            trigger=trigger,
            target=target,
            deployment_file=deployment_file,
            enabled=enabled,
            max_runtime=max_runtime,
            tags=tags,
            overlap_policy=overlap_policy,
            retry_policy=retry_policy,
        )
        return fn

    return decorator


# Utility functions to access and manage the singleton registry instance
def get_registry() -> CronRegistry:
    return _default_registry


# This function is primarily for testing purposes to reset the registry state
def reset_registry() -> None:
    _default_registry.clear()
