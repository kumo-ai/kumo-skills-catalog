---
name: file-feature-request
metadata:
  version: "1.0.0"
description: File a feature-request issue in the current VPC workspace repo, linked to an upstream kumo-ai/kumo issue. Use when the user wants to request a new feature, enhancement, or capability for a VPC/BYOC deployment.
allowed-tools: Bash Read Grep Glob Agent
---

# File Feature Request

Create a feature-request issue in the current workspace repo, linked to an upstream `kumo-ai/kumo` issue.

## Inputs

The user describes a feature they want. They may provide:
- A description of the desired behavior
- The upstream `kumo-ai/kumo` issue URL or number
- Component or area affected
- Business justification or user impact

## Steps

### 1. Detect the target repo

```bash
gh repo view --json nameWithOwner -q '.nameWithOwner'
```

This auto-detects the current workspace repo (e.g., `kumo-ai/sap-workspace`).

### 2. Collect and classify the upstream issue

An upstream `kumo-ai/kumo` issue is **required**. If the user did not provide one:

1. Ask the user for the upstream issue URL or number.
2. If the user provides a number, expand it to the full URL: `https://github.com/kumo-ai/kumo/issues/{number}`
3. Validate the issue exists and check its labels:

```bash
gh issue view {number} --repo kumo-ai/kumo --json title,url,state,labels \
  -q '{title: .title, state: .state, url: .url, labels: [.labels[].name]}'
```

If the issue does not exist, inform the user and ask them to provide a valid one. Do not proceed without a valid upstream issue.

**Check if the upstream issue is an epic** by looking for the `epic` label in the response. This determines the linking strategy in step 4.

### 3. Gather details

Collect enough context to write a clear, actionable feature request:

- **What**: What capability or behavior is being requested?
- **Why**: What problem does this solve or what value does it add for this deployment?
- **Component**: Which area is affected (e.g., controlplane, dataplane, egress, temporal, auth, UI)?
- **Acceptance criteria**: How will we know this is done? (optional — include if the user provides enough detail)

### 4. Create the feature-request issue

```bash
REPO=$(gh repo view --json nameWithOwner -q '.nameWithOwner')

gh issue create --repo "$REPO" \
  --label "feature-request" \
  --title "[Component] Short description of feature" \
  --body "$(cat <<'EOF'
## Summary
<1-2 sentence description of the requested feature>

## Motivation
<why this feature is needed for this deployment>

## Desired Behavior
<what the feature should do, concretely>

## Acceptance Criteria
<how we know it's done — bullet list>

## Upstream Issue
<full URL to kumo-ai/kumo issue or child issue created in step 5>
EOF
)"
```

### 5. Link to upstream

After creating the workspace issue, link it to the upstream `kumo-ai/kumo` issue. The strategy depends on whether the upstream issue is an epic.

#### Path A — Upstream is a regular issue (no `epic` label)

Add the workspace issue URL to the **Upstream Issue** section of the body. No further action needed.

#### Path B — Upstream is an epic (`epic` label present)

Create a **child issue** under the epic in `kumo-ai/kumo` that serves as a placeholder tracking the workspace request, then attach it as a sub-issue.

```bash
# 1. Create a child issue in kumo-ai/kumo referencing the workspace issue
WORKSPACE_ISSUE_URL="<url from step 4>"
CHILD_URL=$(gh issue create --repo kumo-ai/kumo \
  --title "[{CustomerName}] {Short description}" \
  --body "$(cat <<EOF
Tracking issue for a customer feature request.

**Workspace issue**: ${WORKSPACE_ISSUE_URL}

## Context
<1-2 sentence summary of what is being requested and why>
EOF
)" 2>&1)

# 2. Extract the child issue number from the URL
CHILD_NUMBER=$(echo "$CHILD_URL" | grep -o '[0-9]*$')

# 3. Get the child's database ID (required by the sub-issues API)
CHILD_DB_ID=$(gh api graphql -f query='query {
  repository(owner:"kumo-ai", name:"kumo") {
    issue(number:'"$CHILD_NUMBER"') { databaseId }
  }
}' -q '.data.repository.issue.databaseId')

# 4. Attach as sub-issue of the epic
gh api repos/kumo-ai/kumo/issues/{epic_number}/sub_issues \
  --method POST --input - <<< "{\"sub_issue_id\": $CHILD_DB_ID}"
```

Then update the workspace issue's **Upstream Issue** section to point to the child issue URL instead of the epic directly:

```bash
# Update the workspace issue body to reference the child
gh issue edit {workspace_issue_number} --repo "$REPO" \
  --body "$(updated body with child issue URL in Upstream Issue section)"
```

### 6. Report back

Return:
- The workspace feature-request issue URL
- If epic path: also the child issue URL created in `kumo-ai/kumo` and confirmation it was attached to the epic

## Rules

- **Upstream required**: Every feature request must link to a `kumo-ai/kumo` issue. If one doesn't exist yet, tell the user to create one first (or offer to create it using `gh issue create --repo kumo-ai/kumo`).
- **Self-contained**: A developer with zero context should understand the request from reading it alone.
- **No env links**: Do not link to customer clusters or dashboards. Inline all evidence.
- **Redact**: Strip customer names, hostnames, IPs, and secrets.
- **Actionable**: The description should be concrete enough to start scoping work.
- **One feature per ticket**: Keep requests focused.
