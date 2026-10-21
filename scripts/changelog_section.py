"""Print the CHANGELOG.md section of one version (used for the release notes).

Usage: python3 scripts/changelog_section.py 2.2.5
Exits with an error when the section is missing, so a release never goes out
without notes.
"""

from __future__ import annotations

from pathlib import Path
import sys

CHANGELOG = Path(__file__).resolve().parent.parent / "CHANGELOG.md"


def section(version: str, text: str) -> str:
    """The body under '## <version>' up to the next '## ' heading."""
    lines = text.splitlines()
    out: list[str] = []
    inside = False
    for line in lines:
        if line.startswith("## "):
            if inside:
                break
            inside = line[3:].split()[0] == version
            continue
        if inside:
            out.append(line)
    body = "\n".join(out).strip()
    if not body:
        raise SystemExit(f"CHANGELOG.md has no section for {version}")
    return body


if __name__ == "__main__":
    print(section(sys.argv[1], CHANGELOG.read_text(encoding="utf-8")))
