"""Validate the single source of truth for stage hours and week ranges."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "stage_01_python_basics": ("1-8", 48),
    "stage_02_rag_engineering": ("9-20", 72),
    "stage_03_agent_workflow": ("21-32", 72),
    "stage_04_production_ready": ("33-38", 36),
    "stage_05_full_project": ("39-50", 108),
    "stage_06_interview_prep": ("51-62", 72),
}


def main() -> int:
    errors: list[str] = []
    total = 0
    for directory, (week_range, hours) in EXPECTED.items():
        path = ROOT / directory / "每周计划.md"
        text = path.read_text(encoding="utf-8")
        declared = re.search(r"(?:总计|核心必修)\*\*[:：]\s*(\d+)小时", text)
        if not declared or int(declared.group(1)) != hours:
            errors.append(f"{path.relative_to(ROOT)}: expected {hours}h")
        heading = re.search(r"Stage \d+[^\n]*\((\d+)-(\d+)周\)", text)
        if heading and f"{heading.group(1)}-{heading.group(2)}" != week_range:
            errors.append(f"{path.relative_to(ROOT)}: unexpected week range")
        total += hours
    if total != 408:
        errors.append(f"stage total: expected 408h, got {total}h")
    if errors:
        print("Course metadata errors:")
        print("\n".join(f"- {error}" for error in errors))
        return 1
    print("Course metadata: OK (408 core hours, Week 1-62)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
