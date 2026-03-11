#!/usr/bin/env python3
"""CI check: ensure every modified SKILL.md includes a version bump.

Compares the current branch against the base branch (default: origin/master)
and exits non-zero if any SKILL.md file has content changes without a
corresponding version change in its frontmatter.

Usage:
    python3 scripts/check-version-bump.py [base_ref]
"""

import re
import subprocess
import sys
from pathlib import Path

SEMVER_RE = re.compile(
    r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<pre>[0-9A-Za-z\-.]+))?(?:\+(?P<build>[0-9A-Za-z\-.]+))?$"
)


def get_changed_skill_files(base_ref: str) -> list[str]:
    """Return SKILL.md paths that changed between base_ref and HEAD."""
    result = subprocess.run(
        ["git", "diff", "--name-only", base_ref, "HEAD", "--", "**/SKILL.md"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [f for f in result.stdout.strip().splitlines() if f]


def extract_version(ref: str, filepath: str) -> str | None:
    """Extract the version field from a SKILL.md at a given git ref."""
    try:
        result = subprocess.run(
            ["git", "show", f"{ref}:{filepath}"],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        # File didn't exist at that ref (new skill) — no old version.
        return None

    m = re.match(r"^---\s*\n(.*?)\n---", result.stdout, re.DOTALL)
    if not m:
        return None
    for line in m.group(1).splitlines():
        key, _, value = line.partition(":")
        if key.strip() == "version":
            return value.strip()
    return None


def validate_version(version: str) -> bool:
    """Check that a version string is valid semver (with optional pre-release)."""
    return SEMVER_RE.match(version) is not None


def main():
    base_ref = sys.argv[1] if len(sys.argv) > 1 else "origin/master"

    changed = get_changed_skill_files(base_ref)
    if not changed:
        print("No SKILL.md files changed — nothing to check.")
        sys.exit(0)

    errors = []
    for filepath in changed:
        old_version = extract_version(base_ref, filepath)
        new_version = extract_version("HEAD", filepath)

        if new_version is None:
            errors.append(f"  {filepath}: missing 'version' field in frontmatter")
            continue

        if not validate_version(new_version):
            errors.append(
                f"  {filepath}: invalid version '{new_version}' — "
                f"must be valid semver (e.g. 1.2.3, 0.1.0-alpha)"
            )
            continue

        if old_version is not None and new_version == old_version:
            errors.append(
                f"  {filepath}: content changed but version is still {old_version} — "
                f"please bump the version"
            )

    if errors:
        print("Version check failed:\n")
        print("\n".join(errors))
        print(
            "\nEvery SKILL.md change must include a version bump.\n"
            "Use semver: MAJOR.MINOR.PATCH (e.g. 1.2.3) with optional "
            "pre-release suffix (e.g. 0.1.0-alpha)."
        )
        sys.exit(1)

    print(f"Version check passed — {len(changed)} skill(s) verified.")


if __name__ == "__main__":
    main()
