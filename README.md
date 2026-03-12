# Kumo Skills Catalog

Reusable [agentskills.io](https://agentskills.io) skills for Claude Code and Codex agents working with Kumo infrastructure.

| Domain | Skill | Version | Description |
|--------|-------|---------|-------------|
| VPC | [init-vpc-workspace](VPC/init-vpc-workspace/SKILL.md) | `"1.0.1"` | Scaffold a new VPC/BYOC customer workspace from scratch. |
| VPC | [k8s-egress-diagnose](VPC/k8s-egress-diagnose/SKILL.md) | `"1.0.0"` | This skill should be used when the user reports pod connectivity issues, timeout errors reaching external endpoints, "connection timed out", "max retries exceeded", or network problems from within Kubernetes pods. |
| VPC | [vpc-temporal-health-check](VPC/vpc-temporal-health-check/SKILL.md) | `"1.0.0"` | Monitor Temporal cluster health, resource utilization, and performance metrics in a BYOC environment. |
| VPC | [vpc-temporal-ops](VPC/vpc-temporal-ops/SKILL.md) | `"1.0.0"` | Perform operational tasks on Temporal in a BYOC cluster — force Flux reconciliation, check HelmRelease status, watch rolling updates, and inspect pod annotations. |
| VPC | [vpc-temporal-workflow-query](VPC/vpc-temporal-workflow-query/SKILL.md) | `"1.0.0"` | Query and analyze Temporal workflows in a BYOC cluster — find timed-out, failed, running, or completed workflows, group by type/queue/date, and inspect workflow history. |
| VPC | [vpc-ucv-probe-diagnose](VPC/vpc-ucv-probe-diagnose/SKILL.md) | `"1.0.0"` | Diagnose Databricks Unity Catalog Volumes (UCV) probe results and correlate UCV failures with Temporal workflow timeouts. |
| github | [gh-issue-management](github/gh-issue-management/SKILL.md) | `"1.0.0"` | Manage GitHub issues using the gh CLI — create, assign, and organize parent/child (sub-issue) relationships. |
| github | [learn-diff](github/learn-diff/SKILL.md) | `"0.1.0-alpha"` | Walk through a GitHub PR for learning purposes — explaining code, answering inline comments, generating diagrams, and demonstrating bugs with runnable scripts. |
