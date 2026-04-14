"""
Run from the project root:
    python rename_package.py

Renames the package from 'registers' to 'registers' — both the
src/ directory tree and every text-file reference to the old name.
"""

import os
import shutil
from pathlib import Path

OLD = "registers"
NEW = "registers"

# ---------------------------------------------------------------------------
# File extensions to do text substitution in.
# Binary files (.pyc, images, etc.) are intentionally excluded.
# ---------------------------------------------------------------------------
TEXT_EXTENSIONS = {
    ".py", ".toml", ".yml", ".yaml", ".md", ".txt", ".cfg", ".ini", ".rst"
}

# ---------------------------------------------------------------------------
# Directories to skip entirely (generated artefacts / git internals).
# ---------------------------------------------------------------------------
SKIP_DIRS = {".git", "build", "__pycache__", ".pytest_cache", ".venv", "venv"}


def should_skip(path: Path) -> bool:
    return any(part in SKIP_DIRS for part in path.parts) and path != Path.cwd() / "script.py"


def rewrite_text_files(root: Path) -> None:
    """Replace every occurrence of OLD with NEW in all matching text files."""
    changed = []
    for path in root.rglob("*"):
        if path.is_dir() or should_skip(path):
            continue
        if path.suffix not in TEXT_EXTENSIONS:
            continue
        try:
            original = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue  # skip true binary files that slipped through

        updated = original.replace(OLD, NEW)
        if updated != original:
            path.write_text(updated, encoding="utf-8")
            changed.append(str(path))

    if changed:
        print(f"\nUpdated {len(changed)} file(s):")
        for f in sorted(changed):
            print(f"  {f}")
    else:
        print("\nNo text files needed updating.")


def rename_directories(root: Path) -> None:
    """
    Rename every directory named OLD to NEW, deepest-first so that
    renaming a child doesn't invalidate the parent's path.
    """
    # Collect all matching dirs before renaming anything
    targets = sorted(
        [p for p in root.rglob(OLD) if p.is_dir() and not should_skip(p)],
        key=lambda p: len(p.parts),
        reverse=True,   # deepest first
    )

    if not targets:
        print("No directories to rename.")
        return

    print(f"\nRenaming {len(targets)} director(y/ies):")
    for old_path in targets:
        new_path = old_path.parent / NEW
        if new_path.exists():
            print(f"  SKIP (already exists): {old_path} -> {new_path}")
            continue
        shutil.move(str(old_path), str(new_path))
        print(f"  {old_path} -> {new_path}")


def main() -> None:
    root = Path.cwd()
    print(f"Project root : {root}")
    print(f"Renaming     : '{OLD}' -> '{NEW}'")
    print("-" * 50)

    # Phase 1 — rename directories (deepest first)
    rename_directories(root)

    # Phase 2 — rewrite text file contents
    rewrite_text_files(root)

    print("\nDone. Next steps:")
    print("  1. Re-install the package:  pip install -e '.[dev]'")
    print("  2. Run the test suite:       pytest")
    print("  3. Stage everything:         git add -A")
    print(f"  4. Commit:                  git commit -m 'refactor: rename package {OLD} -> {NEW}'")
    print("  5. Push:                     git push")


if __name__ == "__main__":
    main()