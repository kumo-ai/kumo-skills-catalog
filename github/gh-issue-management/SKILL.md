---
name: gh-issue-management
description: Manage GitHub issues using the gh CLI — create, assign, and organize parent/child (sub-issue) relationships. Use when the user asks to create tickets, reparent issues, flatten hierarchies, or manage issue relationships. Includes a Customer Bug Report template specific to the kumoai/kumo repository.
allowed-tools: [Bash]
---

# GitHub Issue Management

Manage GitHub issues and their parent/child relationships using the `gh` CLI
and the GitHub REST API for sub-issues.

## Prerequisites

- `gh` CLI authenticated with `repo` scope
- Repository write/admin access

---

## Core Operations

### Create an issue

```bash
gh issue create --repo {owner}/{repo} \
  --title "{title}" \
  --body "{body}"
```

### Assign an issue

```bash
gh issue edit {number} --repo {owner}/{repo} --add-assignee {username}
```

### Add labels

```bash
gh issue edit {number} --repo {owner}/{repo} --add-label "{label}"
```

---

## Sub-Issue (Parent/Child) Relationships

GitHub's sub-issue feature uses the REST API, not the `gh issue` built-in
commands. All sub-issue operations require the **database ID** (integer), not
the node ID.

### Get the database ID of an issue

```bash
gh api graphql -f query='query {
  repository(owner:"{owner}", name:"{repo}") {
    issue(number:{number}) { databaseId }
  }
}'
```

For multiple issues at once:

```bash
gh api graphql -f query='query {
  repository(owner:"{owner}", name:"{repo}") {
    a: issue(number:111) { databaseId }
    b: issue(number:222) { databaseId }
    c: issue(number:333) { databaseId }
  }
}'
```

### Add a sub-issue (set parent-child relationship)

```bash
gh api repos/{owner}/{repo}/issues/{parent_number}/sub_issues \
  --method POST --input - <<< '{"sub_issue_id": {child_database_id}}'
```

### Remove a sub-issue from its parent

Note: the endpoint is `/sub_issue` (singular), not `/sub_issues`.

```bash
gh api repos/{owner}/{repo}/issues/{parent_number}/sub_issue \
  --method DELETE --input - <<< '{"sub_issue_id": {child_database_id}}'
```

### List sub-issues of a parent

```bash
# Just issue numbers and titles
gh api repos/{owner}/{repo}/issues/{parent_number}/sub_issues \
  --jq '.[] | "#\(.number) - \(.title)"'

# Just issue numbers
gh api repos/{owner}/{repo}/issues/{parent_number}/sub_issues \
  --jq '.[].number'
```

---

## Recipes

### Move a sub-issue from one parent to another

Must remove from old parent first — an issue can only have one parent.

```bash
# 1. Remove from old parent
gh api repos/{owner}/{repo}/issues/{old_parent}/sub_issue \
  --method DELETE --input - <<< '{"sub_issue_id": {child_database_id}}'

# 2. Add to new parent
gh api repos/{owner}/{repo}/issues/{new_parent}/sub_issues \
  --method POST --input - <<< '{"sub_issue_id": {child_database_id}}'
```

### Flatten: move all children of X to be direct children of Y

```bash
# 1. List children of the source parent
gh api repos/{owner}/{repo}/issues/{source_parent}/sub_issues \
  --jq '.[].number'

# 2. Batch-fetch database IDs via GraphQL
gh api graphql -f query='query {
  repository(owner:"{owner}", name:"{repo}") {
    a: issue(number:111) { databaseId }
    b: issue(number:222) { databaseId }
  }
}'

# 3. For each child: remove from source, add to target
gh api repos/{owner}/{repo}/issues/{source_parent}/sub_issue \
  --method DELETE --input - <<< '{"sub_issue_id": {dbid}}'
gh api repos/{owner}/{repo}/issues/{target_parent}/sub_issues \
  --method POST --input - <<< '{"sub_issue_id": {dbid}}'
```

### Create a Customer Bug Report

> **Note:** This template is specific to the `kumoai/kumo` repository. It
> mirrors the "Customer Bug Report" issue template defined in
> `kumo/.github/ISSUE_TEMPLATE/bug-report.md`. Do not use this template
> for other repositories — they have their own templates or none at all.

Use this when filing a customer-facing bug. Gather the details from the
user before creating the issue.

```bash
gh issue create --repo kumoai/kumo \
  --title "[{customer_name}] {short_description}" \
  --label "bug" \
  --body "$(cat <<'EOF'
**Prioritization**
Are you completely blocked?
- [{blocked}] Yes (and I tried any alternatives that can be tried, *e.g.* retrying, refreshing or trying different PQs.)
- [{not_blocked}] No

**Desired Resolution Timeframe**
When do you need this resolved by?
- [{asap}] ASAP
- [{three_days}] 3 business days
- [{five_days}] 5 business days
- [{can_wait}] Can wait longer

**Customer Type**
- [{paid}] Paid customer
- [{pov}] POV
- [{workshop}] Workshop
- [{free_trial}] Free trial

**Customer Visible Bug**
Has the customer seen this bug?
- [{seen_yes}] Yes, the customer has seen it.
- [{seen_no}] No, the customer hasn't seen it yet.
- [{seen_unsure}] Not sure, the customer might see it soon or might have seen it already.

**Description**

What is happening?
{what_is_happening}

What is the expected behavior?
{expected_behavior}

Extent of user impact?
{user_impact}

**Steps to Reproduce**
{steps_to_reproduce}

**Environment Details (Cmd + D)**
- Environment Name: {env_name}
- Version: {version}
- Version used for training: {training_version}
- Job id: {job_id}
- Link to the job page in the UI: {job_link}
- Grafana Link: {grafana_link}
- Temporal Link: {temporal_link}

**Attachments**
- Screenshots / Recordings: {screenshots}
- Slack Thread: {slack_thread}
- Logs: {logs}
EOF
)"
```

After creating the issue, add the appropriate priority label (`0 - Priority P0`,
`1 - Priority P1`, or `2 - Priority P2`) and an area label (`ux`,
`ml-algorithms`, `ml-infra`, or `data-platform`):

```bash
gh issue edit {number} --repo kumoai/kumo \
  --add-label "{priority_label}" \
  --add-label "{area_label}"
```

Use `x` for selected checkboxes and a space for unselected ones. For example,
if the customer is blocked and it's a paid customer: `blocked=x`,
`not_blocked= `, `paid=x`, `pov= `, etc.

### Create an issue and attach it as a sub-issue

```bash
# 1. Create the issue
gh issue create --repo {owner}/{repo} \
  --title "{title}" \
  --body "Part of #{parent_number}"

# 2. Get the new issue's number from the URL output, then its database ID
gh api graphql -f query='query {
  repository(owner:"{owner}", name:"{repo}") {
    issue(number:{new_number}) { databaseId }
  }
}'

# 3. Attach as sub-issue
gh api repos/{owner}/{repo}/issues/{parent_number}/sub_issues \
  --method POST --input - <<< '{"sub_issue_id": {new_database_id}}'
```

---

## Gotchas

- **Database ID vs Node ID**: The sub-issues API requires the integer
  `databaseId`, not the string `node_id` (e.g., `I_kwDO...`). Use the
  GraphQL query above to get it.
- **Integer type matters**: When passing `sub_issue_id`, use `--input -`
  with raw JSON to ensure it's sent as an integer. The `--field` / `-f`
  flags in `gh api` stringify values, causing `422` errors.
- **Single parent constraint**: An issue can only have one parent. You must
  remove it from the current parent before adding to a new one.
- **Singular vs plural endpoint**: Adding uses `/sub_issues` (plural),
  removing uses `/sub_issue` (singular).
- **Tasklist != Relationships**: Markdown tasklists (````[tasklist]`) in the
  issue body are a separate, older mechanism. The sub-issues REST API manages
  the native "Relationships" panel in the GitHub UI.
