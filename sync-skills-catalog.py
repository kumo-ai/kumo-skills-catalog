#!/usr/bin/env python3
"""
Sync skills from the skills catalog into .agents/skills/.

Creates symlinks for catalog skills that the user has explicitly installed.
Local skills (real directories) always take precedence over catalog skills.

Modes:
  --pull        Pull latest catalog then re-sync installed skills.
                (Used by SessionStart hook. Silently skips if catalog not cloned.)
  --init        Clone catalog if missing, then pull + sync installed skills.
  --list        List all available skills in the catalog.
  --add <name>  Install one or more skills from the catalog.
  --remove <name>  Uninstall one or more catalog skills.
  --reset       Remove all catalog-sourced symlinks and clear the manifest.
  (no args)     Re-sync installed skills only (used by PostToolUse hook).
  (stdin)       Hook mode — reads JSON from stdin, filters by command.

Works with both Claude Code and Codex.
"""
import json
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

CATALOG_REPO_NAME = "kumo-skills-catalog"
CATALOG_CLONE_URL = "https://github.com/kumo-ai/kumo-skills-catalog.git"


def get_project_root():
    # 1. Explicit env var (set by Claude Code / Codex)
    if "CLAUDE_PROJECT_DIR" in os.environ:
        return Path(os.environ["CLAUDE_PROJECT_DIR"])
    # 2. Walk up from the script's location to find a git root with .agents/
    candidate = Path(__file__).resolve().parent
    while candidate != candidate.parent:
        if (candidate / ".git").exists() and (candidate / ".agents").is_dir():
            return candidate
        candidate = candidate.parent
    # 3. Walk up from cwd
    candidate = Path.cwd()
    while candidate != candidate.parent:
        if (candidate / ".git").exists() and (candidate / ".agents").is_dir():
            return candidate
        candidate = candidate.parent
    # 4. Last resort
    return Path.cwd()


def find_catalog(project_root: Path) -> Path | None:
    """Locate the skills catalog repo.

    Search order:
    1. .agents/skills-catalog (in-repo clone, preferred)
    2. Breadth-first scan of $HOME (max depth 3) for kumo-skills-catalog
    """
    in_repo = project_root / ".agents" / "skills-catalog"
    if in_repo.is_dir() and (in_repo / "README.md").exists():
        return in_repo

    home = Path.home()
    for depth in range(1, 4):
        pattern = "/".join(["*"] * depth) + f"/{CATALOG_REPO_NAME}"
        for candidate in home.glob(pattern):
            if candidate.is_dir() and (candidate / "README.md").exists():
                return candidate

    return None


def parse_frontmatter(skill_md: Path) -> dict:
    """Extract YAML frontmatter fields from a SKILL.md file.

    Handles one level of nesting (e.g. metadata.version) by flattening
    nested keys with a dot separator.
    """
    text = skill_md.read_text()
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return {}
    fm = {}
    current_parent = None
    for line in m.group(1).splitlines():
        # Detect indented child lines (e.g. "  version: 1.0")
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if indent > 0 and current_parent and ":" in stripped:
            key, _, value = stripped.partition(":")
            if value.strip():
                fm[f"{current_parent}.{key.strip()}"] = value.strip().strip('"')
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        if not key:
            continue
        if value.strip():
            fm[key] = value.strip()
            current_parent = None
        else:
            # Key with no value — start of a nested block
            current_parent = key
    return fm


def discover_catalog_skills(catalog_root: Path) -> dict[str, Path]:
    """Find all SKILL.md files in catalog, return {skill_name: skill_dir}."""
    skills = {}
    for skill_md in catalog_root.rglob("SKILL.md"):
        if ".git" in skill_md.parts:
            continue
        skill_dir = skill_md.parent
        skill_name = skill_dir.name
        skills[skill_name] = skill_dir
    return skills


# ── Manifest ─────────────────────────────────────────────────────────────────

def get_manifest_path(project_root: Path) -> Path:
    return project_root / ".agents" / "skills" / "installed.txt"


def read_manifest(project_root: Path) -> set[str]:
    """Read the set of explicitly installed skill names."""
    manifest = get_manifest_path(project_root)
    if not manifest.exists():
        return set()
    names = set()
    for line in manifest.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            names.add(line)
    return names


def write_manifest(project_root: Path, names: set[str]):
    """Write the installed skills manifest."""
    manifest = get_manifest_path(project_root)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Installed catalog skills — managed by sync-skills-catalog.py",
        "# Do not edit manually. Use --add / --remove / --reset.",
    ]
    lines.extend(sorted(names))
    lines.append("")
    manifest.write_text("\n".join(lines))


# ── Gitignore helpers ────────────────────────────────────────────────────────

def update_skills_gitignore(skills_dir: Path, symlinked_names: list[str]):
    gitignore = skills_dir / ".gitignore"
    lines = [
        "# Auto-generated by sync-skills-catalog.py",
        "# Catalog-sourced skill symlinks — do not edit manually",
        "installed.txt",
    ]
    lines.extend(sorted(symlinked_names))
    lines.append("")
    gitignore.write_text("\n".join(lines))


def update_commands_gitignore(commands_dir: Path, generated_names: list[str]):
    gitignore = commands_dir / ".gitignore"
    existing_generated = set()
    if gitignore.exists():
        for line in gitignore.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                existing_generated.add(line)

    all_generated = sorted(set(f"{n}.md" for n in generated_names) | existing_generated)
    if not all_generated:
        return

    lines = [
        "# Auto-generated by sync-skills-catalog.py",
        "# Catalog-sourced command symlinks — do not edit manually",
    ]
    lines.extend(all_generated)
    lines.append("")
    gitignore.write_text("\n".join(lines))


# ── Sync ─────────────────────────────────────────────────────────────────────

def sync_commands(project_root: Path,
                  catalog_skills: dict[str, Path],
                  symlinked_names: list[str]) -> list[str]:
    """Create .claude/commands/<name>.md symlinks for installed catalog skills."""
    commands_dir = project_root / ".claude" / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)
    skills_dir = project_root / ".agents" / "skills"

    actions = []
    generated_names = []

    for name in sorted(symlinked_names):
        target = commands_dir / f"{name}.md"
        skill_md = skills_dir / name / "SKILL.md"

        if not skill_md.exists():
            continue

        if target.exists() and not target.is_symlink():
            actions.append(f"  cmd  skip {name} (local override)")
            continue

        rel_path = os.path.relpath(skill_md, commands_dir)

        if target.is_symlink():
            if os.readlink(target) == rel_path:
                generated_names.append(name)
                actions.append(f"  cmd  ok   {name}")
                continue
            target.unlink()

        target.symlink_to(rel_path)
        generated_names.append(name)
        actions.append(f"  cmd  new  {name}.md -> {rel_path}")

    update_commands_gitignore(commands_dir, generated_names)
    return actions


def sync_skills(project_root: Path, catalog_root: Path,
                only_names: set[str] | None = None) -> list[str]:
    """Symlink installed catalog skills into .agents/skills/.

    If only_names is given, only sync those. Otherwise sync all installed.
    """
    skills_dir = project_root / ".agents" / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)

    catalog_skills = discover_catalog_skills(catalog_root)
    installed = read_manifest(project_root)

    # Determine which skills to sync
    target_names = only_names if only_names is not None else installed

    actions = []
    symlinked_names = []

    for name in sorted(target_names):
        if name not in catalog_skills:
            actions.append(f"  skip {name} (not found in catalog)")
            continue

        catalog_path = catalog_skills[name]
        target = skills_dir / name

        if target.exists() and not target.is_symlink():
            actions.append(f"  skip {name} (local override)")
            continue

        if target.is_symlink():
            symlinked_names.append(name)
            current = target.resolve()
            if current == catalog_path.resolve():
                actions.append(f"  ok   {name}")
                continue
            target.unlink()

        rel_path = os.path.relpath(catalog_path, skills_dir)
        target.symlink_to(rel_path)
        if name not in symlinked_names:
            symlinked_names.append(name)
        actions.append(f"  new  {name} -> {rel_path}")

    # Also include already-symlinked skills not in target_names (for gitignore)
    for entry in skills_dir.iterdir():
        if entry.is_symlink() and entry.name not in symlinked_names:
            symlinked_names.append(entry.name)

    update_skills_gitignore(skills_dir, symlinked_names)
    cmd_actions = sync_commands(project_root, catalog_skills, symlinked_names)
    actions.extend(cmd_actions)

    return actions


def remove_skill_symlinks(project_root: Path, names: set[str]) -> list[str]:
    """Remove symlinks for given skill names."""
    skills_dir = project_root / ".agents" / "skills"
    commands_dir = project_root / ".claude" / "commands"
    actions = []

    for name in sorted(names):
        skill_link = skills_dir / name
        cmd_link = commands_dir / f"{name}.md"

        if skill_link.is_symlink():
            skill_link.unlink()
            actions.append(f"  removed {name}")
        elif skill_link.exists():
            actions.append(f"  skip {name} (local skill, not a symlink)")
            continue
        else:
            actions.append(f"  skip {name} (not installed)")
            continue

        if cmd_link.is_symlink():
            cmd_link.unlink()

    return actions


def reset_all(project_root: Path) -> list[str]:
    """Remove all catalog-sourced symlinks and clear the manifest."""
    skills_dir = project_root / ".agents" / "skills"
    commands_dir = project_root / ".claude" / "commands"
    actions = []

    # Remove all symlinks in skills dir
    if skills_dir.exists():
        for entry in skills_dir.iterdir():
            if entry.is_symlink():
                name = entry.name
                entry.unlink()
                # Also remove corresponding command symlink
                cmd_link = commands_dir / f"{name}.md"
                if cmd_link.is_symlink():
                    cmd_link.unlink()
                actions.append(f"  removed {name}")

    # Clear manifest
    write_manifest(project_root, set())

    # Update gitignores
    update_skills_gitignore(skills_dir, [])
    if commands_dir.exists():
        update_commands_gitignore(commands_dir, [])

    if not actions:
        actions.append("  (nothing to remove)")

    return actions


# ── Clone / Pull ─────────────────────────────────────────────────────────────

def clone_catalog(project_root: Path) -> Path | None:
    target = project_root / ".agents" / "skills-catalog"
    try:
        result = subprocess.run(
            ["git", "clone", CATALOG_CLONE_URL, str(target)],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0 and target.is_dir():
            return target
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def pull_catalog(catalog_root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(catalog_root), "pull", "--ff-only"],
            capture_output=True, text=True, timeout=15,
        )
        output = result.stdout.strip()
        if "Already up to date" in output:
            return None
        return output
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


# ── Main ─────────────────────────────────────────────────────────────────────

HELP_TEXT = """\
Usage: sync-skills-catalog.py [OPTIONS]

Manage skills from the shared kumo-skills-catalog.

Options:
  --init              Clone the catalog (if missing) and sync installed skills.
  --pull              Pull latest catalog, then re-sync installed skills.
  --list              List all available skills in the catalog.
  --add <name> ...    Install one or more skills from the catalog.
  --remove <name> ... Uninstall one or more catalog skills.
  --reset             Remove all catalog symlinks and clear the manifest.
  --help, -h          Show this help message.
  (no args)           Re-sync installed skills only.

Examples:
  sync-skills-catalog.py --init
  sync-skills-catalog.py --list
  sync-skills-catalog.py --add k8s-egress-diagnose init-vpc-workspace
  sync-skills-catalog.py --remove k8s-egress-diagnose
  sync-skills-catalog.py --reset
"""


def main():
    if "--help" in sys.argv or "-h" in sys.argv:
        print(HELP_TEXT, end="")
        return

    pull_mode = "--pull" in sys.argv
    init_mode = "--init" in sys.argv
    list_mode = "--list" in sys.argv
    add_mode = "--add" in sys.argv
    remove_mode = "--remove" in sys.argv
    reset_mode = "--reset" in sys.argv

    # If invoked as a hook (stdin is piped), read JSON context
    hook_mode = not sys.stdin.isatty()
    if hook_mode and not any([pull_mode, init_mode, list_mode, add_mode,
                               remove_mode, reset_mode]):
        try:
            input_data = json.load(sys.stdin)
        except (json.JSONDecodeError, EOFError):
            input_data = {}

        command = input_data.get("tool_input", {}).get("command", "")
        catalog_keywords = ["skills-catalog", "kumo-skills-catalog"]
        if not any(kw in command for kw in catalog_keywords):
            sys.exit(0)

    project_root = get_project_root()

    # ── Reset ────────────────────────────────────────────────────────────
    if reset_mode:
        actions = reset_all(project_root)
        print("Skills catalog reset:")
        for a in actions:
            print(a)
        return

    # ── Find or clone catalog ────────────────────────────────────────────
    catalog = find_catalog(project_root)
    pull_summary = None

    if not catalog and init_mode:
        catalog = clone_catalog(project_root)
        if catalog:
            pull_summary = "cloned"

    if not catalog:
        if hook_mode or pull_mode:
            sys.exit(0)
        if init_mode:
            print("Failed to clone skills catalog.", file=sys.stderr)
            sys.exit(1)
        print("Skills catalog not found. Run with --init to clone it.",
              file=sys.stderr)
        sys.exit(1)

    # Pull latest if requested (--pull, --init, or --list always pull)
    if (pull_mode or init_mode or list_mode) and not pull_summary:
        pull_summary = pull_catalog(catalog)

    catalog_skills = discover_catalog_skills(catalog)

    # ── List ─────────────────────────────────────────────────────────────
    if list_mode:
        installed = read_manifest(project_root)
        if not catalog_skills:
            print("No skills found in catalog.")
            return

        # Gather metadata for each skill
        entries = []
        for name in sorted(catalog_skills):
            skill_dir = catalog_skills[name]
            fm = parse_frontmatter(skill_dir / "SKILL.md")
            version = fm.get("metadata.version", fm.get("version", "—"))
            desc = fm.get("description", "")
            marker = "*" if name in installed else " "
            entries.append((marker, name, version, desc))

        # Column widths
        name_w = max(len(e[1]) for e in entries)
        ver_w = max(len(e[2]) for e in entries)
        # Description wraps to fit within 80 cols
        desc_w = max(20, 80 - 4 - name_w - 3 - ver_w - 3)
        indent = " " * (4 + name_w + 3 + ver_w + 3)

        print("Available skills in catalog (* = installed):\n")
        for marker, name, version, desc in entries:
            wrapped = textwrap.wrap(desc, width=desc_w) or [""]
            first_line = wrapped[0]
            print(f"  {marker} {name:<{name_w}}   {version:<{ver_w}}   {first_line}")
            for cont in wrapped[1:]:
                print(f"{indent}{cont}")
        return

    # ── Add ──────────────────────────────────────────────────────────────
    if add_mode:
        idx = sys.argv.index("--add")
        names_to_add = set(sys.argv[idx + 1:])
        if not names_to_add:
            print("Usage: --add <skill-name> [skill-name ...]", file=sys.stderr)
            sys.exit(1)

        # Validate names exist in catalog
        missing = names_to_add - set(catalog_skills)
        if missing:
            print(f"Not found in catalog: {', '.join(sorted(missing))}", file=sys.stderr)
            print(f"Run --list to see available skills.", file=sys.stderr)
            sys.exit(1)

        installed = read_manifest(project_root)
        installed |= names_to_add
        write_manifest(project_root, installed)

        actions = sync_skills(project_root, catalog, names_to_add)
        new_count = sum(1 for a in actions if "new" in a)
        print(f"Added {len(names_to_add)} skill(s):")
        for a in actions:
            print(a)
        return

    # ── Remove ───────────────────────────────────────────────────────────
    if remove_mode:
        idx = sys.argv.index("--remove")
        names_to_remove = set(sys.argv[idx + 1:])
        if not names_to_remove:
            print("Usage: --remove <skill-name> [skill-name ...]", file=sys.stderr)
            sys.exit(1)

        installed = read_manifest(project_root)
        installed -= names_to_remove
        write_manifest(project_root, installed)

        actions = remove_skill_symlinks(project_root, names_to_remove)
        # Refresh gitignores
        remaining_symlinks = []
        skills_dir = project_root / ".agents" / "skills"
        if skills_dir.exists():
            for entry in skills_dir.iterdir():
                if entry.is_symlink():
                    remaining_symlinks.append(entry.name)
        update_skills_gitignore(skills_dir, remaining_symlinks)

        print(f"Removed {len(names_to_remove)} skill(s):")
        for a in actions:
            print(a)
        return

    # ── Sync (default / hook / pull / init) ──────────────────────────────
    actions = sync_skills(project_root, catalog)

    summary = "\n".join(actions)
    new_count = sum(1 for a in actions if a.startswith("  new"))

    if hook_mode or pull_mode or init_mode:
        if new_count > 0 or pull_summary:
            parts = []
            if pull_summary:
                parts.append("Skills catalog updated.")
            if new_count > 0:
                parts.append(
                    f"{new_count} new skill(s) registered.\n{summary}"
                )
            event = "SessionStart" if pull_mode else "PostToolUse"
            output = {
                "hookSpecificOutput": {
                    "hookEventName": event,
                    "additionalContext": " ".join(parts),
                }
            }
            print(json.dumps(output))
        sys.exit(0)
    else:
        if pull_summary:
            print(f"Pulled: {pull_summary}")
        print("Skills catalog sync:")
        print(summary or "  (no installed skills)")


if __name__ == "__main__":
    main()
