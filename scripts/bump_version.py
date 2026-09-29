#!/usr/bin/env python3
"""Семантический бамп версии и финализация CHANGELOG.

Примеры:

    python scripts/bump_version.py --part minor
    python scripts/bump_version.py --version 1.0.0

Обновляет единый источник версии (backend/app/__init__.py), frontend/package.json
и переносит содержимое Unreleased в новую секцию CHANGELOG.md.
"""

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = ROOT / "backend" / "app" / "__init__.py"
PACKAGE_FILE = ROOT / "frontend" / "package.json"
LOCK_FILE = ROOT / "frontend" / "package-lock.json"
CHANGELOG_FILE = ROOT / "CHANGELOG.md"
REPO_URL = "https://github.com/syb1v/avito-toolkit"

VERSION_PATTERN = re.compile(r'^__version__ = "(\d+\.\d+\.\d+)"', re.M)
CHANGELOG_HEADING = "## [Unreleased]"


def read_current_version() -> str:
    match = VERSION_PATTERN.search(VERSION_FILE.read_text(encoding="utf-8"))
    if match is None:
        raise SystemExit(f"cannot find __version__ in {VERSION_FILE}")
    return match.group(1)


def bump_version(current: str, part: str) -> str:
    major, minor, patch = (int(part_) for part_ in current.split("."))
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def update_version_file(new_version: str) -> None:
    text = VERSION_FILE.read_text(encoding="utf-8")
    text = VERSION_PATTERN.sub(f'__version__ = "{new_version}"', text, count=1)
    VERSION_FILE.write_text(text, encoding="utf-8")


def update_package_file(new_version: str) -> None:
    package = json.loads(PACKAGE_FILE.read_text(encoding="utf-8"))
    package["version"] = new_version
    PACKAGE_FILE.write_text(
        json.dumps(package, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def update_lock_file(new_version: str) -> None:
    if not LOCK_FILE.exists():
        return
    lock = json.loads(LOCK_FILE.read_text(encoding="utf-8"))
    lock["version"] = new_version
    if isinstance(lock.get("packages"), dict) and "" in lock["packages"]:
        lock["packages"][""]["version"] = new_version
    LOCK_FILE.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")


def finalize_changelog(new_version: str, current_version: str) -> None:
    text = CHANGELOG_FILE.read_text(encoding="utf-8")
    if CHANGELOG_HEADING not in text:
        raise SystemExit(f"cannot find '{CHANGELOG_HEADING}' in {CHANGELOG_FILE}")
    release_heading = f"## [{new_version}] - {date.today().isoformat()}"
    text = text.replace(
        CHANGELOG_HEADING,
        f"{CHANGELOG_HEADING}\n\n{release_heading}",
        count=1,
    )
    unreleased_link = f"[Unreleased]: {REPO_URL}/compare/v{new_version}...HEAD"
    text = re.sub(r"^\[Unreleased\]:.*$", unreleased_link, text, count=1, flags=re.M)
    version_link = f"[{new_version}]: {REPO_URL}/compare/v{current_version}...v{new_version}"
    if f"[{new_version}]:" not in text:
        text = text.replace(unreleased_link, f"{unreleased_link}\n{version_link}", count=1)
    CHANGELOG_FILE.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Bump project version (semver)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--part", choices=["major", "minor", "patch"])
    group.add_argument("--version", dest="explicit_version")
    args = parser.parse_args()

    current = read_current_version()
    new_version = args.explicit_version or bump_version(current, args.part)
    if not re.fullmatch(r"\d+\.\d+\.\d+", new_version):
        parser.error(f"invalid semver version: {new_version}")

    update_version_file(new_version)
    update_package_file(new_version)
    update_lock_file(new_version)
    finalize_changelog(new_version, current)
    print(f"{current} -> {new_version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
