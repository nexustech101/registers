"""
Decorator-oriented cron job registry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import inspect
from typing import Any


VALID_EVENT_KINDS = {"manual", "file_change", "webhook"}
VALID_TARGETS = {
    "local_async",
    "linux_cron",
    "windows_task_scheduler",
    "github_actions",
}


@dataclass(frozen=True)
class TriggerSpec:
    kind: str
    config: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class JobEntry:
    name: str
    handler: Any
    handler_module: str
    handler_qualname: str
    trigger: TriggerSpec
    target: str
    deployment_file: str
    enabled: bool
    max_runtime: int
    tags: tuple[str, ...]
    overlap_policy: str = "skip"
    retry_policy: str = "none"


class CronRegistry:
    """Registry that stores job metadata captured by ``@cron.job``."""

    def __init__(self) -> None:
        self._jobs: dict[str, JobEntry] = {}

    def register(
        self,
        fn: Any,
        *,
        name: str | None,
        trigger: TriggerSpec,
        target: str = "local_async",
        deployment_file: str = "",
        enabled: bool = True,
        max_runtime: int = 0,
        tags: tuple[str, ...] | list[str] | None = None,
        overlap_policy: str = "skip",
        retry_policy: str = "none",
    ) -> JobEntry:
        if not callable(fn):
            raise TypeError("job() can only decorate callable functions.")
        if not isinstance(trigger, TriggerSpec):
            raise TypeError("job() requires a trigger created by cron.interval/cron.cron/cron.event.")

        entry_name = (name or "").strip() or fn.__name__.replace("_", "-")
        if not entry_name:
            raise ValueError("job() requires a non-empty job name.")
        if entry_name in self._jobs:
            raise ValueError(f"Cron job '{entry_name}' is already registered.")

        normalized_target = (target or "local_async").strip().lower()
        if normalized_target not in VALID_TARGETS:
            raise ValueError(
                "target must be one of: "
                + ", ".join(sorted(VALID_TARGETS))
            )

        normalized_overlap = (overlap_policy or "skip").strip().lower()
        if normalized_overlap != "skip":
            raise ValueError("overlap_policy currently supports only 'skip'.")

        normalized_retry = (retry_policy or "none").strip().lower()
        if normalized_retry != "none":
            raise ValueError("retry_policy currently supports only 'none'.")

        module = getattr(fn, "__module__", "") or ""
        qualname = getattr(fn, "__qualname__", "") or fn.__name__

        tag_values = tuple(tag.strip() for tag in (tags or ()) if tag and tag.strip())
        if max_runtime < 0:
            raise ValueError("max_runtime must be >= 0.")

        entry = JobEntry(
            name=entry_name,
            handler=fn,
            handler_module=module,
            handler_qualname=qualname,
            trigger=trigger,
            target=normalized_target,
            deployment_file=(deployment_file or "").strip(),
            enabled=bool(enabled),
            max_runtime=int(max_runtime),
            tags=tag_values,
            overlap_policy=normalized_overlap,
            retry_policy=normalized_retry,
        )
        self._jobs[entry.name] = entry
        return entry

    def get(self, name: str) -> JobEntry:
        if name not in self._jobs:
            raise KeyError(f"No cron job registered as '{name}'.")
        return self._jobs[name]

    def all(self) -> dict[str, JobEntry]:
        return dict(self._jobs)

    def clear(self) -> None:
        self._jobs.clear()

    def __len__(self) -> int:
        return len(self._jobs)


def interval(*, seconds: int = 0, minutes: int = 0, hours: int = 0) -> TriggerSpec:
    total = int(seconds) + int(minutes) * 60 + int(hours) * 3600
    if total <= 0:
        raise ValueError("interval() requires a positive duration.")
    return TriggerSpec(kind="interval", config={"seconds": total})


def _validate_cron_field(field: str, *, allow_zero: bool = True) -> None:
    if field == "*":
        return
    if field.startswith("*/") and field[2:].isdigit() and int(field[2:]) > 0:
        return
    parts = field.split(",")
    for part in parts:
        part = part.strip()
        if not part:
            raise ValueError("cron() contains an empty field segment.")
        if not part.isdigit():
            raise ValueError(f"Unsupported cron segment '{part}'.")
        value = int(part)
        if value < (0 if allow_zero else 1):
            raise ValueError(f"Invalid cron value '{value}'.")


def cron(expression: str, *, timezone: str = "local") -> TriggerSpec:
    expr = (expression or "").strip()
    fields = expr.split()
    if len(fields) != 5:
        raise ValueError("cron() expects a 5-field expression: m h dom mon dow.")
    minute, hour, dom, mon, dow = fields
    _validate_cron_field(minute)
    _validate_cron_field(hour)
    _validate_cron_field(dom, allow_zero=False)
    _validate_cron_field(mon, allow_zero=False)
    _validate_cron_field(dow)
    return TriggerSpec(kind="cron", config={"expression": expr, "timezone": timezone})


def event(kind: str, /, **config: Any) -> TriggerSpec:
    normalized = (kind or "").strip().lower()
    if normalized not in VALID_EVENT_KINDS:
        raise ValueError(
            "event() kind must be one of: " + ", ".join(sorted(VALID_EVENT_KINDS))
        )
    if normalized == "file_change":
        paths = config.get("paths", [])
        if not isinstance(paths, (list, tuple)) or not paths:
            raise ValueError("file_change events require non-empty 'paths'.")
    if normalized == "webhook":
        path = str(config.get("path", "")).strip()
        if not path.startswith("/"):
            raise ValueError("webhook events require a 'path' starting with '/'.")
    return TriggerSpec(kind=normalized, config=dict(config))


def maybe_awaitable(result: Any) -> bool:
    return inspect.isawaitable(result)
