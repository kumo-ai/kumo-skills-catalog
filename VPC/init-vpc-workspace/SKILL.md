---
name: init-vpc-workspace
metadata:
  version: "1.0.1"
description: Scaffold a new VPC/BYOC customer workspace from scratch. Creates repo structure, generates all config files, clones child repos, and registers in Notion.
allowed-tools: Bash Read Write Edit Grep Glob Agent
disable-model-invocation: true
---

# Initialize VPC Workspace

Scaffold a complete VPC/BYOC customer workspace in the current directory. Walk the user through each step interactively — they can skip any step. Generate all files directly (CLAUDE.md, runbook scripts, credentials, skills infra, etc.).

**Convention**: Workspace repos are named `<customer-short>-workspace` (e.g., `pandg-workspace`). The current directory name should follow this convention.

## Step 1: Customer Identity

Ask the user:
- "Customer name (e.g., Procter & Gamble):" → `CUSTOMER_NAME`
- "Short identifier (e.g., pandg — used in repo names and Notion):" → `CUSTOMER_SHORT`
- "Deployment type — BYOC or BYOK? (BYOC/BYOK):" → `DEPLOYMENT_TYPE` **(required — do not proceed until answered)**

If the user tries to skip `DEPLOYMENT_TYPE`, explain: "Deployment type is required for Notion registration. BYOC = Bring Your Own Cloud, BYOK = Bring Your Own Kubernetes."

Auto-derive `WORKSPACE_NAME` from the current directory basename. Verify it matches `<CUSTOMER_SHORT>-workspace`. If not, warn the user and ask if they want to proceed anyway.

## Step 2: GitHub Repo

Check if the current directory is already a git repo (`git rev-parse --git-dir`).

If not, ask: "Create a GitHub repo for this workspace? (yes/skip)"
- If yes:
  1. First, verify the user is authenticated with the GitHub CLI by running `gh auth status`. If not authenticated, ask the user to run `gh auth login` and wait for them to confirm before proceeding.
  2. Run `git init`, then `gh repo create kumo-ai/${CUSTOMER_SHORT}-workspace --private --source=. --push`
- If skip: just run `git init`

If already a git repo, note it and move on.

Store the remote URL (from `git remote get-url origin`) as `REPO_URL` for later use. Convert SSH URLs to HTTPS format for Notion links.

## Step 3: Cloud / Cluster Configuration

Ask the user: "Which cloud provider? (azure/aws/gcp/other/skip)" → `CLOUD_PROVIDER`

### If Azure:
Ask (each skippable):
- "Azure subscription ID:" → `AZURE_SUBSCRIPTION_ID`
- "AKS resource group name:" → `AKS_RESOURCE_GROUP`
- "AKS cluster name:" → `AKS_CLUSTER_NAME`

If all three are provided, generate `runbook/k8s.sh`:
```bash
az account set --subscription <AZURE_SUBSCRIPTION_ID>
az aks get-credentials --resource-group <AKS_RESOURCE_GROUP> --name <AKS_CLUSTER_NAME> --overwrite-existing
kubelogin convert-kubeconfig -l azurecli
```

### If AWS:
Ask (each skippable):
- "AWS region (e.g., us-east-1):" → `AWS_REGION`
- "EKS cluster name:" → `EKS_CLUSTER_NAME`
- "AWS profile (leave blank for default):" → `AWS_PROFILE`

If cluster name and region are provided, generate `runbook/k8s.sh`:
```bash
aws eks update-kubeconfig --region <AWS_REGION> --name <EKS_CLUSTER_NAME> <--profile AWS_PROFILE if provided>
```

### If GCP:
Ask (each skippable):
- "GCP project ID:" → `GCP_PROJECT_ID`
- "GKE cluster name:" → `GKE_CLUSTER_NAME`
- "GKE zone or region (e.g., us-central1-a):" → `GKE_LOCATION`

If all three are provided, generate `runbook/k8s.sh`:
```bash
gcloud container clusters get-credentials <GKE_CLUSTER_NAME> --project <GCP_PROJECT_ID> --region <GKE_LOCATION>
```

### If other:
Ask the user to describe how to obtain cluster credentials, then generate `runbook/k8s.sh` with the commands they provide.

### If skipped:
Create `runbook/` directory but leave `k8s.sh` empty with a TODO comment.

## Step 4: Corporate Proxy

Ask: "Does this customer use a corporate proxy? (yes/no/skip)"

If yes, ask:
- "Proxy URL (e.g., http://proxy.corp.com:8080):" → `PROXY_URL`
- "no_proxy list (comma-separated, e.g., localhost,.internal.com):" → `PROXY_NO_PROXY`

Generate `runbook/proxy.sh`:
```bash
export http_proxy=<PROXY_URL>
export https_proxy=<PROXY_URL>
export no_proxy=<PROXY_NO_PROXY>
```

If no/skip, do NOT create `proxy.sh`.

Store `HAS_PROXY` (yes/no) for CLAUDE.md generation.

## Step 5: Security Constraints (optional)

Ask: "Does this customer enforce specific pod security policies (e.g., Kyverno, OPA)? (yes/skip)"

If yes, ask: "Describe the constraints (paste multiline, then type END on a new line):"

Collect into `SECURITY_CONSTRAINTS`. This becomes a section in CLAUDE.md.

## Step 6: Version Upgrade Procedure (optional)

Ask: "Document a customer-specific version upgrade procedure? (yes/skip)"

If yes, ask: "Describe the steps (paste multiline, then type END on a new line):"

Collect into `UPGRADE_PROCEDURE`. This becomes a section in CLAUDE.md.

## Step 7: Repos

Ask the user to add repos one at a time. For each entry:

- "Repo (git URL or local directory name, enter when done):"
- "One-line description for docs:"

For each repo:
1. Extract the directory name: `basename <url> .git` for URLs, or the name itself for directories
2. If it's a URL AND the directory doesn't exist locally → `git clone <url>`
3. If it's a URL AND the directory already exists → skip clone, note "already exists"
4. If it's just a directory name → check if it exists, note status

Collect all repos as a list of `(name, description)` pairs for CLAUDE.md and .gitignore generation.

## Step 8: Generate Workspace Files

Create the full directory structure and files. Use the Write tool for each file.

### 8a: `.gitignore`

```
# Child git repos (tracked independently)
<name>/ for each repo from Step 7

# Claude Code local settings (not shared)
.claude/settings.local.json

# Skills catalog (cloned on-demand, not checked in)
.agents/skills-catalog/
.agents/skills/.gitignore
.claude/commands/.gitignore

# Credentials
credentials/.env
```

### 8b: `credentials/.env.example`

```
# <CUSTOMER_NAME> workspace credentials — DO NOT COMMIT
# Copy this file to .env and fill in your values.

# Kumo API key (from the Kumo UI under Settings > API Keys)
KUMO_API_KEY=

# REQUIRED: Notion integration token (from https://www.notion.so/my-integrations)
NOTION_API_KEY=

# VPC Customers database — do not change.
NOTION_DATABASE_ID=31fcc5e93e38803dbb9bc6ad7897e885
```

### 8c: `ops-guide/README.md`

```markdown
# Ops Guide

Operational knowledge for the <CUSTOMER_NAME> BYOC environment — contacts, escalation paths, and reference docs.

## Contacts

| Area | Who | Channel |
|------|-----|---------|
| Cluster access / Cloud | _TBD_ | _TBD_ |
| Kumo platform issues | _TBD_ | _TBD_ |
| Networking / egress | _TBD_ | _TBD_ |

## Escalation

_Add escalation paths and on-call info here._

## Reference Docs

_Add links to architecture diagrams, design docs, onboarding decks, etc._
```

### 8d: `.github/ISSUE_TEMPLATE/debug-log.yml`

```yaml
name: Debug Log
description: Track a debugging session or environment investigation
labels: [debug-log]
body:
  - type: dropdown
    id: environment
    attributes:
      label: Environment
      options:
        - <CUSTOMER_NAME>
        - Other
    validations:
      required: true
  - type: input
    id: component
    attributes:
      label: Component
      description: Which part of the system
      placeholder: e.g., egress, controlplane, dataplane
    validations:
      required: true
  - type: textarea
    id: symptoms
    attributes:
      label: Symptoms
      description: What was observed? Include error messages and logs.
    validations:
      required: true
  - type: textarea
    id: root-cause
    attributes:
      label: Root Cause / Findings
  - type: textarea
    id: resolution
    attributes:
      label: Resolution / Workaround
  - type: textarea
    id: context
    attributes:
      label: Session Context
      description: Commands run, config snippets, related files.
  - type: input
    id: upstream-issue
    attributes:
      label: Upstream Issue
      placeholder: e.g., https://github.com/kumo-ai/kumo/issues/12345
```

### 8e: `.claude/settings.json`

```json
{
  "allowedCommands": [
    "kubectl get:*",
    "kubectl describe:*",
    "kubectl logs:*",
    "kubectl exec:*",
    "gh pr view:*",
    "gh pr diff:*",
    "gh api:*",
    "docker run:*",
    "bash:*"
  ],
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "$CLAUDE_PROJECT_DIR/.agents/scripts/sync-skills-catalog.py --pull"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "$CLAUDE_PROJECT_DIR/.agents/scripts/sync-skills-catalog.py"
          }
        ]
      }
    ]
  }
}
```

### 8f: `.agents/scripts/sync-skills-catalog.py`

Download the sync script directly from the catalog repo:
```bash
mkdir -p .agents/scripts
curl -fsSL https://raw.githubusercontent.com/kumo-ai/kumo-skills-catalog/master/sync-skills-catalog.py \
  -o .agents/scripts/sync-skills-catalog.py
chmod +x .agents/scripts/sync-skills-catalog.py
```

If the download fails (e.g. no network), tell the user they can copy it manually from an existing workspace or the `kumo-skills-catalog` repo later.

### 8g: `.agents/skills/file-env-ticket/SKILL.md`

Generate the file-env-ticket skill, parameterized with the workspace repo name (`kumo-ai/<CUSTOMER_SHORT>-workspace`):

```markdown
---
name: file-env-ticket
description: File a debug-log issue in the <CUSTOMER_SHORT>-workspace issue catalog to track a debugging session or environment investigation.
allowed-tools: Bash Read Grep Glob Agent
---

# File Environment Ticket

Create a debug-log issue in `kumo-ai/<CUSTOMER_SHORT>-workspace` to catalog a debugging session or environment investigation for future searchability.

## Inputs

The user describes a problem, unexpected behavior, or improvement idea. They may provide:
- Error messages, logs, or screenshots
- Pod names, deployment names, or config snippets
- A description of what they expected vs what happened

## Steps

### 1. Gather evidence

Collect the minimum context needed to understand the issue without access to the environment:

- **Error output**: Exact error messages, log snippets, or stack traces. Redact customer-specific values (hostnames, IPs, secrets).
- **Reproduction steps**: What sequence of actions led to the problem? What version/image tag was involved?
- **Configuration**: Relevant config snippets (deployment YAML, env vars, kustomization entries) — inline in the ticket, not links.
- **Expected vs actual**: What should have happened? What happened instead?
- **Root cause** (if known): What was identified as the underlying issue?
- **Workaround** (if any): What was done to unblock?

### 2. Classify

Determine the **component** (e.g., egress, controlplane, dataplane, temporal, databricks, auth) and a short description for the title.

### 3. Create the catalog issue

```bash
gh issue create --repo kumo-ai/<CUSTOMER_SHORT>-workspace \
  --label "debug-log" \
  --title "[Component] Short description of investigation" \
  --body "$(cat <<'EOF'
## Symptoms
<what was observed>

## Evidence
<config, logs, YAML as fenced code blocks — redact secrets>

## Root Cause / Findings
<what was identified>

## Resolution / Workaround
<what was done>

## Session Context
<commands run, config checked, logs examined>

## Upstream Issue
<link to kumo-ai/kumo issue if one exists, or "None">
EOF
)"
```

### 4. Report back

Return the catalog issue URL to the user.

## Rules

- **Self-contained**: A developer with zero context should understand the ticket from reading it alone.
- **No env links**: Do not link to customer clusters or dashboards. Inline all evidence.
- **Redact**: Strip customer names, hostnames, IPs, and secrets.
- **Actionable**: If a fix is needed, the description should be concrete enough to start working.
- **Concise**: One problem per ticket.
```

### 8h: `.claude/commands/onboard.md`

Generate an onboard skill tailored to this customer. Include steps for:
1. Clone repos — check if each repo from Step 7 exists, offer to clone missing ones
2. Corporate proxy — only include if `HAS_PROXY` is yes
3. Cloud auth — ask user to authenticate with their cloud provider (based on `CLOUD_PROVIDER`)
4. Cluster access — run `bash runbook/k8s.sh` if it was generated
5. Credentials — copy `.env.example`, ask for Kumo API key, Notion keys
6. Notion registration — create entry in VPC Customers database if creds configured
7. Skills catalog — run `python3 .agents/scripts/sync-skills-catalog.py --init`

Each step skippable. Finish with a summary checklist.

### 8i: `setup.sh`

Generate a lightweight setup script for teammates joining an existing workspace. It should:
1. Clone any missing child repos (from the URLs collected in Step 7) — for each, check if directory exists before cloning
2. Credentials section (y/N gate): copy `.env.example`, ask for Kumo/Notion keys
3. Notion registration (if credentials present): ask the user for stage (POC / PROD / OTHERS), then create entry with customer name, repo URL, selected stage, and Deployment type

### 8j: `CLAUDE.md`

Generate the full CLAUDE.md assembled from all collected values. Structure:

```markdown
# <CUSTOMER_NAME> BYOC Environment

New here? Run `/onboard` to get set up interactively.

## Workspace Layout
<tree showing credentials/, ops-guide/, runbook/, setup.sh, and all repos from Step 7>

## Repos
<bullet for each repo: **name** — description>

Run `./setup.sh` after cloning this workspace to clone all child repos.

## Prerequisites

Before running any kubectl or k8s commands:
1. Ensure Twingate is turned off.
2. Authenticate with your cloud provider (e.g., `az login` for Azure, `aws sso login` for AWS, `gcloud auth login` for GCP).
<3. proxy line — only if HAS_PROXY is yes>

## Credentials
<same as current, generic>

## Cluster Access
<reference runbook/k8s.sh with cluster name and subscription>

<## Cluster Security Constraints — only if SECURITY_CONSTRAINTS was provided>
<## Version Upgrade Procedure — only if UPGRADE_PROCEDURE was provided>

## Notion Integration

`setup.sh` registers each workspace in the **VPC Customers** Notion database via the REST API. ...

## Issue Catalog

This repo's GitHub Issues (`kumo-ai/<CUSTOMER_SHORT>-workspace`) serves as a searchable knowledge base...

## Skill Discovery
<same as current, generic>
```

### 8k: Symlinks

Create:
- `AGENTS.md -> CLAUDE.md`
- `README.md -> CLAUDE.md`
- `.claude/commands/file-env-ticket.md -> ../../.agents/skills/file-env-ticket/SKILL.md`

## Step 9: Credentials

Ensure `credentials/.env` exists (copy from `.env.example`).

**Notion API key is mandatory** — the workspace cannot register in the VPC Customers database or function correctly without it. Do NOT allow the user to skip this:
- Ask for Notion API key → `NOTION_API_KEY` **(required — do not proceed until provided)**

If the user tries to skip, explain: "Notion API key is required for workspace registration and tracking. You can create a Notion integration at https://www.notion.so/my-integrations, or grab the shared token from 1Password: https://start.1password.com/open/i?a=BOTF4QWPWFAUNIAYMWXORJSXYI&v=bdkdupbwm4bjpv72pnbata5qba&i=kbgeh44526e4ojvmirzfnk5njq&h=team-kumo.1password.com"

The Notion database ID is always `31fcc5e93e38803dbb9bc6ad7897e885` (the shared VPC Customers database). Hardcode this as `NOTION_DATABASE_ID` — do not ask the user for it.

Other credentials are optional:
- Ask for Kumo API key (skippable) → `KUMO_API_KEY`

Write values into `credentials/.env`.

## Step 10: Ops Contacts

Ask: "Fill in ops contacts now? (yes/skip)"

If yes, ask for each contact area (who + channel), update `ops-guide/README.md`.

## Step 11: Notion Registration

Since `NOTION_API_KEY` was configured in Step 9, ask: "Register this workspace in the VPC Customers Notion database? (yes/skip)"

If yes:
1. Ask: "What stage is this customer in? (POC / PROD / OTHERS)" → `STAGE`
   - Only accept one of: `POC`, `PROD`, `OTHERS`. If the user enters something else, re-prompt.
2. Create a Notion page via REST API:
```bash
curl -s -X POST https://api.notion.com/v1/pages \
  -H "Authorization: Bearer $NOTION_API_KEY" \
  -H "Notion-Version: 2022-06-28" \
  -H "Content-Type: application/json" \
  -d '{
  "parent": {"database_id": "<NOTION_DATABASE_ID>"},
  "properties": {
    "Name": {"title": [{"text": {"content": "<CUSTOMER_SHORT>"}}]},
    "Context Repo": {"url": "<REPO_URL>"},
    "Stage": {"select": {"name": "<STAGE>"}},
    "Deployment": {"select": {"name": "<DEPLOYMENT_TYPE>"}}
  }
}'
```

Report the Notion page URL.

## Step 12: Skills Catalog

Ask: "Set up the shared skills catalog? (yes/skip)"

If yes:
1. Clone the catalog: `python3 .agents/scripts/sync-skills-catalog.py --init`
2. Show available skills: `python3 .agents/scripts/sync-skills-catalog.py --list`
3. Ask: "Which skills would you like to install? (enter names separated by spaces, or 'all' for everything, or 'skip')"
4. If they provide names, run: `python3 .agents/scripts/sync-skills-catalog.py --add <name1> <name2> ...`
5. If they say 'all', install every skill listed by `--list`.

## Step 13: Initial Commit

Ask: "Create initial commit and push? (yes/skip)"

If yes:
- `git add` all generated files (but NOT `credentials/.env`, child repo directories, or `.claude/settings.local.json`)
- Commit with message: `Initialize <CUSTOMER_SHORT> VPC workspace`
- Push to origin if remote is configured

## Step 14: Summary

Print a summary showing:
- What was configured (with values)
- What was skipped (with instructions for doing it later)
- Key next steps (az login, cluster access, etc.)
