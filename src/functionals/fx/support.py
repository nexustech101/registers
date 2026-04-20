"""
Shared rendering helpers for FX command plugins.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from collections.abc import Sequence

from functionals.fx.structure import StructureResult


def render_runtime_summary(
    title: str,
    *,
    fields: Sequence[tuple[str, Any]],
    sections: Sequence[tuple[str, Sequence[str]]] = (),
) -> str:
    lines = [title]
    for key, value in fields:
        lines.append(f"{key}: {value}")
    for key, items in sections:
        if not items:
            continue
        lines.append(f"{key}: {', '.join(items)}")
    return "\n".join(lines)


def render_structure_result(*, title: str, root: Path, result: StructureResult) -> str:
    lines = [title]
    if result.created:
        lines.append("Created:")
        lines.extend(f"  - {path.relative_to(root)}" for path in result.created)
    if result.updated:
        lines.append("Updated:")
        lines.extend(f"  - {path.relative_to(root)}" for path in result.updated)
    if result.skipped:
        lines.append("Skipped:")
        lines.extend(f"  - {path.relative_to(root)}" for path in result.skipped)
    return "\n".join(lines)

