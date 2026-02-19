---
name: gh-issue-management
description: Manage GitHub issues using the gh CLI — create, assign, and organize parent/child (sub-issue) relationships. Use when the user asks to create tickets, reparent issues, flatten hierarchies, or manage issue relationships.
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
