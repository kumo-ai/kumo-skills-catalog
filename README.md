# Kumo Skills Catalog

Reusable [agentskills.io](https://agentskills.io) skills for Claude Code and Codex agents working with Kumo infrastructure.

## Installation

From your project root:

```bash
curl -fsSL https://raw.githubusercontent.com/kumo-ai/kumo-skills-catalog/master/install.sh | bash
```

### Managing skills

After installation, use the sync script directly:

```bash
# List available skills
python3 .agents/scripts/sync-skills-catalog.py --list

# Install skills
python3 .agents/scripts/sync-skills-catalog.py --add <skill-name>

# Remove skills
python3 .agents/scripts/sync-skills-catalog.py --remove <skill-name>

# Pull latest updates
python3 .agents/scripts/sync-skills-catalog.py --pull

# Uninstall everything
python3 .agents/scripts/sync-skills-catalog.py --reset
```

Installed skills are symlinked into `.agents/skills/` and registered as Claude Code slash commands in `.claude/commands/`.

## Available Skills

| Domain | Skill | Version | Description |
|--------|-------|---------|-------------|
| VPC | [file-feature-request](VPC/file-feature-request/SKILL.md) | `"1.0.0"` | File a feature-request issue in the current VPC workspace repo, linked to an upstream kumo-ai/kumo issue. |
| VPC | [init-vpc-workspace](VPC/init-vpc-workspace/SKILL.md) | `"1.0.1"` | Scaffold a new VPC/BYOC customer workspace from scratch. |
| VPC | [k8s-egress-diagnose](VPC/k8s-egress-diagnose/SKILL.md) | `"1.0.0"` | This skill should be used when the user reports pod connectivity issues, timeout errors reaching external endpoints, "connection timed out", "max retries exceeded", or network problems from within Kubernetes pods. |
| VPC | [vpc-temporal-doctor](VPC/vpc-temporal-doctor/SKILL.md) | `"1.0.0"` | Diagnose Temporal health in a BYOC cluster — query workflows by status, analyze timeouts and failures, check resource utilization, and surface performance problems. |
| github | [gh-issue-management](github/gh-issue-management/SKILL.md) | `"1.0.0"` | Manage GitHub issues using the gh CLI — create, assign, and organize parent/child (sub-issue) relationships. |
| github | [learn-diff](github/learn-diff/SKILL.md) | `"0.1.0-alpha"` | Walk through a GitHub PR for learning purposes — explaining code, answering inline comments, generating diagrams, and demonstrating bugs with runnable scripts. |
| pptx | [pptx](pptx/SKILL.md) | `"1.0.0"` | Create, edit, or read .pptx PowerPoint files using PptxGenJS. Use when the user asks for a presentation, slide deck, or mentions a .pptx file. Includes the full authoring workflow with visual QA. |
