# Kumo Skills Catalog

Reusable [agentskills.io](https://agentskills.io) skills for Claude Code and Codex agents working with Kumo infrastructure.

| Domain | Skill | Version | Description |
|--------|-------|---------|-------------|
| VPC | [init-vpc-workspace](VPC/init-vpc-workspace/SKILL.md) | `"1.0.1"` | Scaffold a new VPC/BYOC customer workspace from scratch. |
| VPC | [k8s-egress-diagnose](VPC/k8s-egress-diagnose/SKILL.md) | `"1.0.0"` | This skill should be used when the user reports pod connectivity issues, timeout errors reaching external endpoints, "connection timed out", "max retries exceeded", or network problems from within Kubernetes pods. |
| github | [gh-issue-management](github/gh-issue-management/SKILL.md) | `"1.0.0"` | Manage GitHub issues using the gh CLI — create, assign, and organize parent/child (sub-issue) relationships. |
| github | [learn-diff](github/learn-diff/SKILL.md) | `"0.1.0-alpha"` | Walk through a GitHub PR for learning purposes — explaining code, answering inline comments, generating diagrams, and demonstrating bugs with runnable scripts. |
