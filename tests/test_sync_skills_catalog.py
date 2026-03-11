#!/usr/bin/env python3
"""Unit tests for sync-skills-catalog.py.

Uses a temporary directory structure to simulate a project with a catalog,
so no real repos or network access are needed.
"""
import importlib.util
import json
import os
import sys
import textwrap
from io import StringIO
from pathlib import Path
from unittest import mock

import pytest

# ── Import the script as a module ────────────────────────────────────────────

SCRIPT_PATH = Path(__file__).resolve().parent.parent / "sync-skills-catalog.py"
spec = importlib.util.spec_from_file_location("sync_skills_catalog", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

parse_frontmatter = mod.parse_frontmatter
discover_catalog_skills = mod.discover_catalog_skills
read_manifest = mod.read_manifest
write_manifest = mod.write_manifest
sync_skills = mod.sync_skills
remove_skill_symlinks = mod.remove_skill_symlinks
reset_all = mod.reset_all
update_skills_gitignore = mod.update_skills_gitignore
update_commands_gitignore = mod.update_commands_gitignore


# ── Fixtures ─────────────────────────────────────────────────────────────────

SKILL_A_FRONTMATTER = """\
---
name: skill-alpha
metadata:
  version: "1.2.0"
description: Alpha skill for testing purposes.
allowed-tools: Bash Read
---

# Skill Alpha

Body text.
"""

SKILL_B_FRONTMATTER = """\
---
name: skill-beta
metadata:
  version: "0.3.1"
description: Beta skill with a longer description that exercises wrapping in the list display.
allowed-tools: Bash Grep Glob
---

# Skill Beta

Body text.
"""

SKILL_NO_VERSION = """\
---
name: skill-gamma
description: Gamma skill with no version field.
---

# Skill Gamma
"""


@pytest.fixture
def project(tmp_path):
    """Create a fake project root with a catalog containing two skills."""
    root = tmp_path / "project"
    root.mkdir()
    (root / ".git").mkdir()  # fake git marker
    (root / ".agents" / "skills").mkdir(parents=True)
    (root / ".claude" / "commands").mkdir(parents=True)

    # Catalog with two skills
    catalog = tmp_path / "catalog"
    catalog.mkdir()
    (catalog / "README.md").write_text("catalog")

    skill_a = catalog / "area" / "skill-alpha"
    skill_a.mkdir(parents=True)
    (skill_a / "SKILL.md").write_text(SKILL_A_FRONTMATTER)

    skill_b = catalog / "area" / "skill-beta"
    skill_b.mkdir(parents=True)
    (skill_b / "SKILL.md").write_text(SKILL_B_FRONTMATTER)

    skill_c = catalog / "other" / "skill-gamma"
    skill_c.mkdir(parents=True)
    (skill_c / "SKILL.md").write_text(SKILL_NO_VERSION)

    return root, catalog


# ── parse_frontmatter ────────────────────────────────────────────────────────

class TestParseFrontmatter:
    def test_basic_fields(self, tmp_path):
        p = tmp_path / "SKILL.md"
        p.write_text(SKILL_A_FRONTMATTER)
        fm = parse_frontmatter(p)
        assert fm["name"] == "skill-alpha"
        assert fm["metadata.version"] == "1.2.0"
        assert fm["description"] == "Alpha skill for testing purposes."
        assert fm["allowed-tools"] == "Bash Read"

    def test_nested_metadata(self, tmp_path):
        p = tmp_path / "SKILL.md"
        p.write_text(SKILL_B_FRONTMATTER)
        fm = parse_frontmatter(p)
        assert fm["metadata.version"] == "0.3.1"

    def test_no_version(self, tmp_path):
        p = tmp_path / "SKILL.md"
        p.write_text(SKILL_NO_VERSION)
        fm = parse_frontmatter(p)
        assert "metadata.version" not in fm
        assert "version" not in fm
        assert fm["description"] == "Gamma skill with no version field."

    def test_no_frontmatter(self, tmp_path):
        p = tmp_path / "SKILL.md"
        p.write_text("# Just a heading\nNo frontmatter here.\n")
        fm = parse_frontmatter(p)
        assert fm == {}


# ── discover_catalog_skills ──────────────────────────────────────────────────

class TestDiscoverCatalogSkills:
    def test_finds_all_skills(self, project):
        _, catalog = project
        skills = discover_catalog_skills(catalog)
        assert set(skills.keys()) == {"skill-alpha", "skill-beta", "skill-gamma"}

    def test_returns_correct_paths(self, project):
        _, catalog = project
        skills = discover_catalog_skills(catalog)
        assert (skills["skill-alpha"] / "SKILL.md").exists()
        assert (skills["skill-beta"] / "SKILL.md").exists()

    def test_ignores_git_dir(self, project):
        _, catalog = project
        git_skill = catalog / ".git" / "fake-skill"
        git_skill.mkdir(parents=True)
        (git_skill / "SKILL.md").write_text("---\nname: bad\n---\n")
        skills = discover_catalog_skills(catalog)
        assert "fake-skill" not in skills


# ── Manifest ─────────────────────────────────────────────────────────────────

class TestManifest:
    def test_empty_when_no_file(self, project):
        root, _ = project
        assert read_manifest(root) == set()

    def test_write_and_read(self, project):
        root, _ = project
        write_manifest(root, {"skill-alpha", "skill-beta"})
        result = read_manifest(root)
        assert result == {"skill-alpha", "skill-beta"}

    def test_ignores_comments_and_blanks(self, project):
        root, _ = project
        manifest = root / ".agents" / "skills" / "installed.txt"
        manifest.write_text("# comment\n\nskill-alpha\n\n# another\nskill-beta\n")
        result = read_manifest(root)
        assert result == {"skill-alpha", "skill-beta"}

    def test_write_clears_old(self, project):
        root, _ = project
        write_manifest(root, {"a", "b", "c"})
        write_manifest(root, {"x"})
        assert read_manifest(root) == {"x"}


# ── sync_skills ──────────────────────────────────────────────────────────────

class TestSyncSkills:
    def test_add_and_sync_creates_symlinks(self, project):
        root, catalog = project
        write_manifest(root, {"skill-alpha"})
        actions = sync_skills(root, catalog)

        link = root / ".agents" / "skills" / "skill-alpha"
        assert link.is_symlink()
        assert (link / "SKILL.md").exists()
        assert any("skill-alpha" in a for a in actions)

    def test_sync_creates_command_symlink(self, project):
        root, catalog = project
        write_manifest(root, {"skill-alpha"})
        sync_skills(root, catalog)

        cmd = root / ".claude" / "commands" / "skill-alpha.md"
        assert cmd.is_symlink()
        assert cmd.resolve().name == "SKILL.md"

    def test_sync_multiple_skills(self, project):
        root, catalog = project
        write_manifest(root, {"skill-alpha", "skill-beta"})
        sync_skills(root, catalog)

        assert (root / ".agents" / "skills" / "skill-alpha").is_symlink()
        assert (root / ".agents" / "skills" / "skill-beta").is_symlink()

    def test_sync_only_names_subset(self, project):
        root, catalog = project
        write_manifest(root, {"skill-alpha", "skill-beta"})
        actions = sync_skills(root, catalog, only_names={"skill-alpha"})

        assert (root / ".agents" / "skills" / "skill-alpha").is_symlink()
        # skill-beta should NOT be synced (not in only_names)
        assert not (root / ".agents" / "skills" / "skill-beta").is_symlink()

    def test_idempotent_sync(self, project):
        root, catalog = project
        write_manifest(root, {"skill-alpha"})
        sync_skills(root, catalog)
        actions = sync_skills(root, catalog)
        # Second run should show "ok" not "new"
        alpha_actions = [a for a in actions if "skill-alpha" in a]
        assert all("ok" in a for a in alpha_actions)

    def test_local_override_not_replaced(self, project):
        root, catalog = project
        # Create a real directory (local override) before syncing
        local = root / ".agents" / "skills" / "skill-alpha"
        local.mkdir(parents=True)
        (local / "SKILL.md").write_text("local override")

        write_manifest(root, {"skill-alpha"})
        actions = sync_skills(root, catalog)

        assert not local.is_symlink()
        assert (local / "SKILL.md").read_text() == "local override"
        assert any("local override" in a for a in actions)

    def test_missing_skill_skipped(self, project):
        root, catalog = project
        write_manifest(root, {"nonexistent-skill"})
        actions = sync_skills(root, catalog)
        assert any("not found" in a for a in actions)

    def test_gitignore_updated(self, project):
        root, catalog = project
        write_manifest(root, {"skill-alpha"})
        sync_skills(root, catalog)

        gi = root / ".agents" / "skills" / ".gitignore"
        assert gi.exists()
        content = gi.read_text()
        assert "skill-alpha" in content
        assert "installed.txt" in content


# ── remove_skill_symlinks ────────────────────────────────────────────────────

class TestRemoveSkillSymlinks:
    def test_remove_existing_symlink(self, project):
        root, catalog = project
        write_manifest(root, {"skill-alpha"})
        sync_skills(root, catalog)

        actions = remove_skill_symlinks(root, {"skill-alpha"})
        assert not (root / ".agents" / "skills" / "skill-alpha").exists()
        assert any("removed" in a for a in actions)

    def test_remove_also_removes_command_symlink(self, project):
        root, catalog = project
        write_manifest(root, {"skill-alpha"})
        sync_skills(root, catalog)

        remove_skill_symlinks(root, {"skill-alpha"})
        assert not (root / ".claude" / "commands" / "skill-alpha.md").exists()

    def test_remove_nonexistent_skips(self, project):
        root, _ = project
        actions = remove_skill_symlinks(root, {"no-such-skill"})
        assert any("not installed" in a for a in actions)

    def test_remove_local_skill_skips(self, project):
        root, _ = project
        local = root / ".agents" / "skills" / "my-local"
        local.mkdir(parents=True)
        actions = remove_skill_symlinks(root, {"my-local"})
        assert any("local skill" in a for a in actions)
        assert local.exists()


# ── Workflow: add then list then remove ──────────────────────────────────────

class TestAddListRemoveWorkflow:
    def test_add_list_remove_cycle(self, project):
        root, catalog = project

        # 1. Add two skills
        write_manifest(root, {"skill-alpha", "skill-beta"})
        sync_skills(root, catalog)
        assert read_manifest(root) == {"skill-alpha", "skill-beta"}
        assert (root / ".agents" / "skills" / "skill-alpha").is_symlink()
        assert (root / ".agents" / "skills" / "skill-beta").is_symlink()

        # 2. Remove one
        installed = read_manifest(root) - {"skill-alpha"}
        write_manifest(root, installed)
        remove_skill_symlinks(root, {"skill-alpha"})
        assert read_manifest(root) == {"skill-beta"}
        assert not (root / ".agents" / "skills" / "skill-alpha").exists()
        assert (root / ".agents" / "skills" / "skill-beta").is_symlink()

        # 3. Re-sync should only show skill-beta
        actions = sync_skills(root, catalog)
        beta_actions = [a for a in actions if "skill-beta" in a]
        assert len(beta_actions) > 0
        alpha_actions = [a for a in actions if "skill-alpha" in a and "new" in a]
        assert len(alpha_actions) == 0

    def test_add_remove_readd(self, project):
        root, catalog = project

        # Add
        write_manifest(root, {"skill-alpha"})
        sync_skills(root, catalog)
        assert (root / ".agents" / "skills" / "skill-alpha").is_symlink()

        # Remove
        write_manifest(root, set())
        remove_skill_symlinks(root, {"skill-alpha"})
        assert not (root / ".agents" / "skills" / "skill-alpha").exists()

        # Re-add
        write_manifest(root, {"skill-alpha"})
        actions = sync_skills(root, catalog)
        assert (root / ".agents" / "skills" / "skill-alpha").is_symlink()
        assert any("new" in a for a in actions)


# ── reset_all ────────────────────────────────────────────────────────────────

class TestResetAll:
    def test_reset_removes_all_symlinks(self, project):
        root, catalog = project
        write_manifest(root, {"skill-alpha", "skill-beta"})
        sync_skills(root, catalog)

        actions = reset_all(root)
        assert not (root / ".agents" / "skills" / "skill-alpha").exists()
        assert not (root / ".agents" / "skills" / "skill-beta").exists()
        assert read_manifest(root) == set()
        assert any("removed" in a for a in actions)

    def test_reset_then_list_shows_empty_manifest(self, project):
        root, catalog = project
        write_manifest(root, {"skill-alpha"})
        sync_skills(root, catalog)
        reset_all(root)
        assert read_manifest(root) == set()

    def test_reset_when_already_empty(self, project):
        root, _ = project
        actions = reset_all(root)
        assert any("nothing to remove" in a for a in actions)


# ── Gitignore helpers ────────────────────────────────────────────────────────

class TestGitignoreHelpers:
    def test_skills_gitignore_content(self, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        update_skills_gitignore(skills_dir, ["aaa", "zzz", "mmm"])
        content = (skills_dir / ".gitignore").read_text()
        lines = content.splitlines()
        assert "installed.txt" in lines
        # Sorted
        assert lines.index("aaa") < lines.index("mmm") < lines.index("zzz")

    def test_commands_gitignore_merges(self, tmp_path):
        cmd_dir = tmp_path / "commands"
        cmd_dir.mkdir()
        # Pre-existing entries
        (cmd_dir / ".gitignore").write_text("# old\nexisting.md\n")
        update_commands_gitignore(cmd_dir, ["new-skill"])
        content = (cmd_dir / ".gitignore").read_text()
        assert "existing.md" in content
        assert "new-skill.md" in content


# ── List display (human-readable output) ─────────────────────────────────────

class TestListDisplay:
    def test_list_output_format(self, project):
        """Test that --list produces correct human-readable output."""
        root, catalog = project
        write_manifest(root, {"skill-alpha"})

        catalog_skills = discover_catalog_skills(catalog)
        installed = read_manifest(root)

        entries = []
        for name in sorted(catalog_skills):
            skill_dir = catalog_skills[name]
            fm = parse_frontmatter(skill_dir / "SKILL.md")
            version = fm.get("metadata.version", fm.get("version", "—"))
            desc = fm.get("description", "")
            marker = "*" if name in installed else " "
            entries.append((marker, name, version, desc))

        # skill-alpha should be marked as installed
        alpha = [e for e in entries if e[1] == "skill-alpha"][0]
        assert alpha[0] == "*"
        assert alpha[2] == "1.2.0"

        # skill-beta not installed
        beta = [e for e in entries if e[1] == "skill-beta"][0]
        assert beta[0] == " "
        assert beta[2] == "0.3.1"

        # skill-gamma has no version → fallback
        gamma = [e for e in entries if e[1] == "skill-gamma"][0]
        assert gamma[2] == "—"

    def test_list_all_skills_present(self, project):
        _, catalog = project
        skills = discover_catalog_skills(catalog)
        assert len(skills) == 3
        assert "skill-alpha" in skills
        assert "skill-beta" in skills
        assert "skill-gamma" in skills


# ── main() via CLI simulation ────────────────────────────────────────────────

class TestMainCLI:
    def _run_main(self, argv, project_root, stdin_data=None):
        """Run main() with patched sys.argv, env, and optionally stdin."""
        captured = StringIO()
        captured_err = StringIO()
        with (
            mock.patch.object(sys, "argv", ["sync-skills-catalog.py"] + argv),
            mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(project_root)}),
            mock.patch.object(sys, "stdout", captured),
            mock.patch.object(sys, "stderr", captured_err),
            mock.patch.object(sys.stdin, "isatty", return_value=True),
        ):
            try:
                mod.main()
            except SystemExit:
                pass
        return captured.getvalue(), captured_err.getvalue()

    def test_help_flag(self, project):
        root, _ = project
        out, _ = self._run_main(["--help"], root)
        assert "Usage:" in out
        assert "--add" in out

    def test_reset_via_main(self, project):
        root, catalog = project
        write_manifest(root, {"skill-alpha"})
        sync_skills(root, catalog)
        out, _ = self._run_main(["--reset"], root)
        assert "reset" in out.lower()
        assert read_manifest(root) == set()
