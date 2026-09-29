#!/usr/bin/env python3
"""Проверяет согласованность версий: backend, frontend и CHANGELOG."""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = ROOT / "backend" / "app" / "__init__.py"
PACKAGE_FILE = ROOT / "frontend" / "package.json"
CHANGELOG_FILE = ROOT / "CHANGELOG.md"

VERSION_PATTERN = re.compile(r'^__version__ = "(\d+\.\d+\.\d+)"', re.MULTILINE)


def main() -> int:
    backend_match = VERSION_PATTERN.search(VERSION_FILE.read_text(encoding="utf-8"))
    if backend_match is None:
        print("FAIL: не найдена версия в backend/app/__init__.py", file=sys.stderr)
        return 1
    backend_version = backend_match.group(1)

    package_version = json.loads(PACKAGE_FILE.read_text(encoding="utf-8"))["version"]
    changelog = CHANGELOG_FILE.read_text(encoding="utf-8")

    errors: list[str] = []
    if package_version != backend_version:
        errors.append(
            f"frontend/package.json {package_version} != backend {backend_version}"
        )
    if f"## [{backend_version}]" not in changelog:
        errors.append(f"в CHANGELOG.md нет секции ## [{backend_version}]")
    if "## [Unreleased]" not in changelog:
        errors.append("в CHANGELOG.md нет секции ## [Unreleased]")

    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(f"OK: версия {backend_version} согласована (backend, frontend, CHANGELOG)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
