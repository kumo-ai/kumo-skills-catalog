---
name: sync-notion-context
metadata:
  version: "1.0.0"
description: Sync the workspace's Notion page content into a local notion-context/ directory so Claude Code has full customer context without needing live API access. Idempotent — safe to run repeatedly.
allowed-tools: Bash Read Write Edit Grep Glob
---

# Sync Notion Context

Pull the workspace's Notion page (and its child pages) into `notion-context/` as Markdown files. This gives Claude Code full customer context locally, without requiring live Notion API calls during every session.

**Idempotent**: Running this skill multiple times overwrites existing files with the latest content. No duplicates, no stale data left behind.

## Prerequisites

- `credentials/.env` must exist and contain a valid `NOTION_API_KEY`
- The workspace must be registered in the VPC Customers Notion database (i.e., there is a page whose `Name` property matches `CUSTOMER_SHORT`)

## Steps

### 1. Load credentials

```bash
set -a
source credentials/.env
set +a
```

Verify `NOTION_API_KEY` is set and non-empty. If not, stop and tell the user:
"NOTION_API_KEY is missing. Run `/onboard` or add it to `credentials/.env`."

### 2. Identify the workspace page

Derive `CUSTOMER_SHORT` from the current directory name (strip `-workspace` suffix from basename).

Query the VPC Customers database to find the page for this workspace:

```bash
curl -s -X POST "https://api.notion.com/v1/databases/31fcc5e93e38803dbb9bc6ad7897e885/query" \
  -H "Authorization: Bearer $NOTION_API_KEY" \
  -H "Notion-Version: 2022-06-28" \
  -H "Content-Type: application/json" \
  -d '{
    "filter": {
      "property": "Name",
      "title": { "equals": "<CUSTOMER_SHORT>" }
    }
  }'
```

Extract the page ID from the first result. If no results, stop and tell the user:
"No Notion page found for '<CUSTOMER_SHORT>'. Run `/onboard` to register this workspace first."

Store the page ID as `ROOT_PAGE_ID`.

### 3. Prepare the output directory

```bash
mkdir -p notion-context
```

### 4. Fetch the root page properties

```bash
curl -s "https://api.notion.com/v1/pages/$ROOT_PAGE_ID" \
  -H "Authorization: Bearer $NOTION_API_KEY" \
  -H "Notion-Version: 2022-06-28"
```

Extract all properties (Name, Stage, Deployment, Context Repo, and any custom properties). Write them as YAML frontmatter in `notion-context/index.md`.

### 5. Fetch the root page content

```bash
curl -s "https://api.notion.com/v1/blocks/$ROOT_PAGE_ID/children?page_size=100" \
  -H "Authorization: Bearer $NOTION_API_KEY" \
  -H "Notion-Version: 2022-06-28"
```

Handle pagination: if `has_more` is `true`, follow `next_cursor` until all blocks are fetched.

Convert Notion blocks to Markdown and append to `notion-context/index.md` after the frontmatter. Use these conversion rules:

| Notion block type | Markdown output |
|---|---|
| `paragraph` | Plain text with inline formatting |
| `heading_1` | `# Heading` |
| `heading_2` | `## Heading` |
| `heading_3` | `### Heading` |
| `bulleted_list_item` | `- item` |
| `numbered_list_item` | `1. item` |
| `to_do` | `- [x]` or `- [ ]` |
| `toggle` | `<details><summary>` |
| `code` | Fenced code block with language |
| `quote` | `> blockquote` |
| `callout` | `> **icon** text` |
| `divider` | `---` |
| `table` | Markdown table |
| `image` | `![caption](url)` |
| `bookmark` | `[title](url)` |
| `link_to_page` | Note as internal link, fetch as child page |

For rich text, preserve:
- **Bold** → `**text**`
- *Italic* → `*text*`
- `Code` → `` `text` ``
- ~~Strikethrough~~ → `~~text~~`
- [Links](url) → `[text](url)`

### 6. Fetch child pages recursively

For any `child_page` blocks found in step 5 (or deeper), repeat the fetch-and-convert process:

1. Get the child page title from the block
2. Fetch its blocks (with pagination)
3. Write to `notion-context/<slugified-title>.md`
4. If the child page itself contains `child_page` blocks, recurse (up to 3 levels deep to avoid runaway recursion)

Use the page title slugified as the filename: lowercase, spaces → hyphens, strip non-alphanumeric characters except hyphens.

### 7. Fetch linked databases (if any)

If any `child_database` blocks are found, fetch all pages from that database:

```bash
curl -s -X POST "https://api.notion.com/v1/databases/<database_id>/query" \
  -H "Authorization: Bearer $NOTION_API_KEY" \
  -H "Notion-Version: 2022-06-28" \
  -H "Content-Type: application/json" \
  -d '{"page_size": 100}'
```

Write each database as a Markdown table in `notion-context/<slugified-database-title>.md`, with one row per page and columns for each property.

### 8. Clean up stale files

After syncing, remove any `.md` files in `notion-context/` that were NOT written during this sync. This ensures deleted Notion pages don't leave orphans.

To track this:
- Before starting, record the set of filenames that exist in `notion-context/`
- After writing all files, delete any files from the old set that were not written in this run

### 9. Write sync metadata

Write `notion-context/.last-sync` with:

```
synced_at: <ISO 8601 timestamp>
root_page_id: <ROOT_PAGE_ID>
customer: <CUSTOMER_SHORT>
files: <count of .md files written>
```

### 10. Update .gitignore

Check if `notion-context/` is already in `.gitignore`. If not, append it:

```bash
grep -qxF 'notion-context/' .gitignore || echo 'notion-context/' >> .gitignore
```

Notion content may contain sensitive customer data and should not be committed.

### 11. Report

Print a summary:

```
## Notion Context Sync

| Item | Value |
|------|-------|
| Customer | <CUSTOMER_SHORT> |
| Root page | <ROOT_PAGE_ID> |
| Pages synced | <count> |
| Databases synced | <count> |
| Stale files removed | <count> |
| Output | notion-context/ |

Files:
- notion-context/index.md
- notion-context/<child-page-1>.md
- ...
```

## Rules

- **Idempotent**: Every run produces the same output for the same Notion state. Files are overwritten, not appended. Stale files are removed.
- **No commits**: This skill writes to `notion-context/` which is gitignored. It never stages or commits files.
- **Credentials from .env**: Always read `NOTION_API_KEY` from `credentials/.env`. Never ask the user to paste API keys.
- **Pagination**: Always handle Notion API pagination. Pages can have more than 100 blocks.
- **Rate limits**: If the Notion API returns 429, wait for the `Retry-After` header duration and retry. Maximum 3 retries per request.
- **Redact nothing**: This is a local-only sync for Claude Code context. The full content is needed for accurate assistance. The gitignore ensures it stays local.
