---
name: learn-diff
metadata:
  version: "0.1.0-alpha"
description: Walk through a GitHub PR for learning purposes — explaining code, answering inline comments, generating diagrams, and demonstrating bugs with runnable scripts.
allowed-tools: Bash Read Grep Glob Agent Write Edit AskUserQuestion WebFetch
---

# /learn-diff — Educational Diff Walkthrough

Invoked as `/learn-diff <PR-URL-or-number>`. This skill walks through a GitHub PR for learning purposes: explaining code, answering inline comments, generating ASCII workflow diagrams, and demonstrating bugs with runnable scripts. This is NOT a code review — the goal is to help the user understand the diff.

## Allowed Tools

Bash, Read, Grep, Glob, Agent, Write, Edit, AskUserQuestion, WebFetch

## Rules

- **Read-only** — never post comments, reviews, or approvals back to GitHub.
- Use `gh api` for structured JSON; reserve `gh pr diff` for the full diff.
- Demo scripts go in `/tmp/` and are cleaned up after narration.
- Language analogies are only used when the PR's language differs from the user's primary language.
- If the PR has >15 changed files, focus on the most significant changes and note the summarization.

## Workflow

### Step 1 — Parse PR Reference

Accept any of:
- Full URL: `https://github.com/owner/repo/pull/123`
- Short ref: `owner/repo#123`
- Bare number: detect owner/repo via `gh repo view --json nameWithOwner -q .nameWithOwner`

Extract `owner`, `repo`, and `pr_number`.

### Step 2 — Ask Primary Language

Use `AskUserQuestion` to ask:

> What is your primary programming language? (Used for analogies when explaining unfamiliar concepts.)

Options: Python, Java, Go, TypeScript, Other

Store the answer. If the PR language matches the user's language, skip analogies throughout.

### Step 3 — Fetch PR Data

Run these `gh` CLI calls **in parallel** via separate Bash tool calls:

1. **PR metadata:**
   ```
   gh api repos/{owner}/{repo}/pulls/{pr_number}
   ```
   Extract: title, body, user.login, head.ref, base.ref, additions, deletions, changed_files

2. **Full diff:**
   ```
   gh pr diff {pr_number} --repo {owner}/{repo}
   ```

3. **Inline review comments:**
   ```
   gh api repos/{owner}/{repo}/pulls/{pr_number}/comments --paginate
   ```
   Extract per comment: body, path, line, diff_hunk

4. **File list:**
   ```
   gh api repos/{owner}/{repo}/pulls/{pr_number}/files --paginate
   ```

### Step 4 — PR Summary

Output a structured summary:

```
## PR Summary
**Title:** ...
**Author:** ...
**Branch:** head → base
**Changes:** +N / -M across K files

### Files Changed
- `path/to/file.py` — short description of what changed
- ...
```

Write a 1-line description per file based on the diff hunks and filenames.

### Step 5 — Approach Assessment

Before diving into code details, evaluate whether the PR's approach is sound. Keep this step **precise and concise** — a few sentences per point, not an essay.

1. **Identify the problem** — From the PR description, linked issues, and the diff, state the core problem being solved in 1–2 sentences.
2. **Evaluate the approach** — Is this a proper fix or a workaround? Does it address the root cause or just a symptom?
3. **Consider alternatives** — Are there simpler, more robust, or more idiomatic approaches? Only mention alternatives that are meaningfully better — do not list alternatives for the sake of it.
4. **Surface trade-offs** — Note any trade-offs the approach introduces (e.g., performance vs. readability, scope of change vs. risk).

Output format:

```
## Approach Assessment
**Problem:** (1–2 sentence problem statement)
**Approach:** (what the PR does and whether it addresses the root cause)
**Alternatives:** (meaningfully better options, or "None — this approach is sound.")
**Trade-offs:** (key trade-offs, or "None of note.")
```

Skip this step for trivial changes (typo fixes, docs updates, dependency bumps).

### Step 6 — Process Inline Comments & Backward Compatibility

If the user left inline comments on the PR (from Step 3 data):
- Treat **each comment** as a question from the user.
- For each comment, show the relevant code context (from diff_hunk), then answer the question with a clear explanation.
- Use language analogies when appropriate (e.g., explain Python `asyncio.shield()` via Java `CompletableFuture`).

If there are **no** inline comments:
- Use `AskUserQuestion` to ask: "No inline comments found. What part of this PR would you like to understand?"

#### Backward Compatibility Check

For every changed file with behavioral code changes, evaluate backward compatibility and flag risks. Check for:

- **Public API changes** — renamed, removed, or re-typed functions, methods, classes, or endpoints that external callers may depend on.
- **Data format / schema changes** — altered serialization formats, database schemas, config file structures, or wire protocols that could break existing consumers or stored data.
- **Default behavior changes** — changed default values, argument ordering, or implicit behaviors that existing callers rely on without explicit arguments.
- **Dependency contract changes** — bumped dependency versions, removed transitive dependencies, or changed minimum version requirements.
- **Feature removal or deprecation** — removed flags, environment variables, CLI options, or config keys without a migration path.

Output a summary section:

```
## Backward Compatibility
- **Risk level:** None | Low | Medium | High
- **Findings:**
  - (list each finding, or "No backward compatibility issues detected.")
- **Recommendations:**
  - (migration steps, deprecation warnings, or versioning advice if applicable)
```

Skip this check for docs-only or test-only changes.

### Step 7 — ASCII Workflow Diagrams

Identify the 1–2 most critical control-flow changes in the PR. For each, generate a side-by-side BEFORE / AFTER ASCII diagram using box-drawing characters (`┌ ┐ └ ┘ │ ─ ├ ┤ ┬ ┴ ┼ ▼ ▶`).

Format:

```
BEFORE                              AFTER
┌──────────────────────┐            ┌──────────────────────┐
│  step description    │            │  step description    │
└──────────┬───────────┘            └──────────┬───────────┘
           │                                   │
           ▼                                   ▼
┌──────────────────────┐            ┌──────────────────────┐
│  next step           │            │  new/changed step    │
└──────────────────────┘            └──────────────────────┘
```

Constraints:
- Max 60 chars wide per column so they fit side-by-side.
- Output directly in conversation — do not write to a file.
- Skip this step if the PR has no meaningful control-flow changes (e.g., config or docs only).

### Step 8 — Reproducible Demo Script

If the PR contains behavioral code changes (not config/docs-only):

1. Write a self-contained Python script to `/tmp/pr_review_demo.py` that:
   - Simulates the **old behavior** (demonstrating the bug or limitation)
   - Simulates the **new behavior** (demonstrating the fix or improvement)
   - Uses only stdlib imports when possible
   - Prints clear labels: `=== OLD BEHAVIOR ===` / `=== NEW BEHAVIOR ===`

2. Run the script:
   ```
   python3 /tmp/pr_review_demo.py
   ```

3. Narrate the output line by line, explaining what each section shows.

4. Clean up:
   ```
   rm /tmp/pr_review_demo.py
   ```

Skip this step if the PR is config-only, docs-only, or the changes cannot be meaningfully simulated in a standalone script.

### Step 9 — Follow-Up

Use `AskUserQuestion` to ask:

> Do you have any more questions about this PR?

Options: "Yes, let me ask", "No, I'm done"

If yes, answer follow-up questions using the PR data already fetched. Loop until the user says they're done.
