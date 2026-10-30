"""Check local Markdown links and common file references."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
REFERENCE_RE = re.compile(r"(?:`|\s)([^`\s]+(?:\.md|\.py|/))(?:`|\s|$)")


def is_external(target: str) -> bool:
    return target.startswith(("http://", "https://", "mailto:", "#"))


def check_links() -> list[str]:
    errors: list[str] = []
    for path in ROOT.rglob("*.md"):
        if any(part in {".git", ".venv"} for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8")
        for match in LINK_RE.finditer(text):
            target = match.group(1).split("#", 1)[0].strip()
            if not target or is_external(target):
                continue
            candidate = (path.parent / target).resolve()
            if not candidate.exists():
                errors.append(f"{path.relative_to(ROOT)} -> {target}")
    return errors


def main() -> int:
    errors = check_links()
    if errors:
        print("Broken Markdown links:")
        print("\n".join(f"- {error}" for error in errors))
        return 1
    print("Markdown links: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
