#!/usr/bin/env python3
"""Печатает секцию CHANGELOG.md для указанной версии (для GitHub Release)."""

import re
import sys
from pathlib import Path

CHANGELOG_FILE = Path(__file__).resolve().parent.parent / "CHANGELOG.md"


def extract_section(text: str, version: str) -> str:
    pattern = re.compile(
        rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## \[|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(text)
    return match.group(1).strip() if match else ""


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: extract_changelog.py <version>", file=sys.stderr)
        return 2
    section = extract_section(CHANGELOG_FILE.read_text(encoding="utf-8"), sys.argv[1])
    if not section:
        section = "Изменения см. в CHANGELOG.md"
    print(section)
    return 0


if __name__ == "__main__":
    sys.exit(main())
