#!/usr/bin/env python3
"""Regenerate README.md from SKILL.md frontmatter across the catalog."""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HEADER = """\
# Kumo Skills Catalog

Reusable [agentskills.io](https://agentskills.io) skills for Claude Code and Codex agents working with Kumo infrastructure.

| Domain | Skill | Description |
|--------|-------|-------------|
"""


def parse_frontmatter(path: Path) -> dict:
    text = path.read_text()
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return {}
    fm = {}
    for line in m.group(1).splitlines():
        key, _, value = line.partition(":")
        if value:
            fm[key.strip()] = value.strip()
    return fm


def main():
    skills = []
    for skill_file in sorted(REPO_ROOT.rglob("SKILL.md")):
        rel = skill_file.relative_to(REPO_ROOT)
        parts = rel.parts  # e.g. ("github", "gh-issue-management", "SKILL.md")
        if len(parts) < 3:
            continue
        domain = parts[0]
        fm = parse_frontmatter(skill_file)
        name = fm.get("name", parts[1])
        description = fm.get("description", "")
        # Trim description to first sentence for table readability
        first_sentence = re.split(r"(?<=\.)\s", description, maxsplit=1)[0]
        skills.append((domain, name, str(rel), first_sentence))

    rows = []
    for domain, name, rel_path, desc in skills:
        rows.append(f"| {domain} | [{name}]({rel_path}) | {desc} |")

    readme = HEADER + "\n".join(rows) + "\n"
    readme_path = REPO_ROOT / "README.md"
    if readme_path.exists() and readme_path.read_text() == readme:
        print("README.md is already up to date.")
        return

    readme_path.write_text(readme)
    print("README.md updated.")


if __name__ == "__main__":
    main()
