"""Compile repository Python files without executing them."""
from __future__ import annotations

import py_compile
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    errors: list[str] = []
    for path in ROOT.rglob("*.py"):
        if any(part in {".git", ".venv", "__pycache__"} for part in path.parts):
            continue
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as exc:
            errors.append(f"{path.relative_to(ROOT)}: {exc.msg}")
    if errors:
        print("Python syntax errors:")
        print("\n".join(f"- {error}" for error in errors))
        return 1
    print("Python snippets: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
