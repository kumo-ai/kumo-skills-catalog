---
name: annotate-iterate
metadata:
  version: "0.1.0-alpha"
description: Iterate on a written artifact (doc, design spec, RFC, runbook) using inline `annotate:` markers as a review channel. Defines a stable protocol for first-pass replies, follow-ups, resolution, and promotion of inline answers into the document body — so the user can review by editing the doc directly and the agent's behavior is predictable across rounds.
allowed-tools: Bash Read Edit Write Grep Glob WebFetch
---

# /annotate-iterate — Inline Annotation Iteration Protocol

Use this skill when the user reviews a written artifact by adding `annotate:` markers inline and expects the agent to (a) answer each annotation by editing the file in place, and (b) follow a predictable protocol when the user adds follow-ups or marks items resolved.

This is a **collaboration shape**, not a one-shot task. The skill should stay loaded for the duration of the review iteration on a given file.

## When this fires

The user's signal is one of:

- A markdown file modified out-of-band (visible in `<system-reminder>` showing the modified file) where the user has inserted lines starting with `annotate:` or `// annotate:` or `> **annotate:**`.
- An explicit prompt like "look at my annotations", "address the annotates in `<file>`", "I have follow-ups in `<file>`".
- The user typing `/annotate-iterate <file>` to enter the iteration loop on a specific file.
- **Auto-promote**: the agent's own response in chat is substantive enough that the user is likely to want to annotate it (see next section).

If the user's annotation hasn't been wrapped in a blockquote yet (it's just a bare `annotate: …` line), the agent's first job is to wrap it and add the answer below it (see "First-pass" below).

## Auto-promote long chat responses to a file

A chat-only reply can't be annotated. When the agent is about to produce a response that the user is likely to want to review section-by-section, **write it to `temp_doc/<topic-slug>.md` first**, then send a short pointer in chat instead of pasting the full body. This sets the artifact up for the four operations below.

**Promote when any of these hold:**

- ≥3 distinct top-level subsections, OR
- ≥300 words of prose body, OR
- Contains a numbered sequence ≥4 items meant as actionable steps, OR
- The user's prompt phrasing implies review ("draft", "write up", "put together", "give me a runbook/spec/plan").

**Don't promote** for direct factual answers, code-only replies, or short clarifications — chat is fine there.

### File and folder conventions

- **Path**: `<repo-root>/temp_doc/<topic-slug>.md`. Keep names lowercase, words separated by `_` or `-`. Topic-derived names only — never date-prefixed (`multicat_bench_ec2_runbook.md`, not `2026-04-25-runbook.md`); the user greps by topic.
- **Folder is per-repo**: `temp_doc/` lives at the repo root the user is working in, not at `~/temp_doc`. Keeps annotations colocated with the work.

### gitignore hygiene (do this once per repo, before the first write)

The folder must be ignored so review-in-progress drafts never land in commits or get indexed by search/code-graph tooling.

1. Check the repo's root `.gitignore` for an entry covering `temp_doc/`.
2. If absent, append a single line: `/temp_doc/` (anchored to repo root with `/` so a same-named folder elsewhere in the tree isn't accidentally ignored).
3. If the repo has no `.gitignore`, create one with `/temp_doc/` as the only entry — don't presume to add other patterns.
4. Mention the gitignore edit in the chat pointer so the user knows what changed.

### Chat pointer shape

Once the file is written, the chat reply should be a few lines, not the full doc:

```
Drafted at temp_doc/<slug>.md (~<N> lines). Quick recap of what's in it:
- <one-line per section>
- ...
Annotate inline as you read; happy to revise based on your notes.
```

That's enough for the user to decide whether to open the file. The full body lives in the file from this point on.

## The four operations

The protocol has four operations the agent must distinguish between. Misidentifying which operation applies is the most common failure mode.

### 1. First-pass answer

**Trigger**: A bare `annotate: <question>` line in the doc with no agent response below it.

**Behavior**:

1. Investigate what's needed to answer (read code, run grep, fetch URLs the user references). Do this work; don't punt the question back.
2. Replace the bare line with a blockquote that quotes the question (in **bold**) and provides the answer below:

```markdown
> **annotate: <user's question, lightly cleaned up>**
>
> <answer body — can be multi-paragraph, can include sub-headings using `> ###`>
```

3. Don't add `[resolved]` or any other status marker — the user adds those.
4. Match the surrounding doc's tone. Runbooks get terse, design docs get more discursive, code review notes stay short.

### 2. Follow-up

**Trigger**: A new `annotate: <follow-up>` (or `Annotate: …`, `// annotate (follow-up):`) line appended *under* an existing answered annotation block, without the prior block being resolved or deleted.

**Behavior — load-bearing rule**:

> **Preserve the prior question and the prior answer verbatim.** Append a new annotation line and a new delta-answer below the old material in the same blockquote. Do **not** rewrite the original answer to incorporate the follow-up.

Concrete shape after the agent's response:

```markdown
> **annotate: <original question>**
> **annotate (follow-up): <new question>**
>
> <original answer, untouched>
>
> <delta answer that responds specifically to the follow-up, referring back to the original where relevant>
```

The reasoning: the user is reviewing by reading their own annotations top-to-bottom. Rewriting the original answer hides what was already accepted and makes them re-review settled material. Appending preserves the audit trail.

If the follow-up makes a previous claim wrong, **don't silently fix it** — flag the contradiction explicitly in the delta ("the prior answer assumed X; the follow-up surfaces that this is wrong because…").

### 3. Resolution

**Trigger**: The user says "X is resolved" / "first two are resolved" / appends `[resolved]` to a specific annotation / asks to "delete the resolved ones".

**Behavior**:

- Delete the **entire** blockquote (annotation + answer) cleanly, leaving no marker behind. The doc should read as if the annotation never existed.
- Don't substitute a "this was discussed" stub. If the answer was load-bearing, the user will tell you to promote it (operation 4) — they didn't.
- If the user resolves only some annotations in a multi-line block, split the block: keep the unresolved ones, drop the resolved ones.
- Multi-resolve at once is common ("first two resolved, follow-up on the third"). Do them in one edit pass.

### 4. Promotion

**Trigger**: The user asks to "move this into the body" / "put X into a section" / "this should be a real subsection, not an annotation" / "promote the recommendations from the annotation". Sometimes implicit — "this got too long for an annotation".

**Behavior**:

1. Identify the substantive content inside the annotation block that should graduate (recommendations, sequences, plans, specs).
2. Lift it into a properly-numbered section in the document body. Match the doc's existing section style (numbering, header level).
3. In the original annotation block, leave **either** (a) a thin pointer ("Net: see §N below for the migration sequence.") at the end of the annotation's answer, **or** (b) nothing if the promoted content was the entire answer and the question reads cleanly without it.
4. Do not duplicate text — if it lives in the body, remove it from the annotation.

## Worked example (from the canonical session)

User starts with three bare annotations in `multicat_bench_ec2_runbook.md`:

```
annotate: what does this `generate_diverse.py` do?
annotate: these are not two sets of data?
annotate: I think there's a benchmark framework pre-existed and a TUI to inspect its performance. Are we leveraging that?
```

Round 1 (first-pass): Agent investigates each, wraps each into a blockquote, writes an answer below.

Round 2 (resolution + follow-up): User says "first two resolved, third has follow-up: `Annotate: PR #184 used different strategy …`".

Agent:
- Deletes annotation 1 and annotation 2 blocks entirely.
- For annotation 3: keeps the original question and answer verbatim, appends the new follow-up question and a delta answer below.

Round 3 (promotion): User says "the recommended follow-up sequence should be in the body, not in the annotation".

Agent:
- Lifts the "Recommended follow-up sequence" out of the answer and creates `## 9. Graduate to the regression framework` in the runbook body.
- Replaces the moved content in the annotation with a one-line pointer ("Net: this PR's runbook is the path of least resistance for the one-shot characterization. The right long-term home is Path 2 with the small extensions outlined in §9 below.").

## Style rules

- **Quote the question in bold.** It anchors what's being answered. Don't paraphrase the user's wording into something they didn't write.
- **Preserve `[resolved]` markers** the user adds, until they ask you to delete the block.
- **Don't add `// annotate:` shape** the user didn't use. Match their syntax (`annotate:`, `// annotate:`, `> **annotate:**` — the user picks).
- **One blockquote per logical thread.** A follow-up belongs in the same blockquote as the original; a brand-new question gets its own blockquote.
- **Investigate before answering.** If the question references a file, PR, or external resource, look at it. Annotations exist because the user wants the agent's investigation work, not a recap of what they already know.
- **Keep delta answers focused.** A follow-up answer should reference back to the original, not restate it. "Adding to the prior point: X" is the right shape.
- **Don't editorialize about the protocol.** When operating, just operate. The user shouldn't need to read meta-commentary about how you're handling annotations.

## Anti-patterns

- ❌ Rewriting the original answer to fold in a follow-up. (See operation 2.)
- ❌ Leaving "[resolved]" stubs after a resolution. (See operation 3.)
- ❌ Promoting content into the body without removing it from the annotation. Duplication rots.
- ❌ Replying with "I'll address your annotations" without actually editing the file. The doc IS the channel.
- ❌ Asking the user where to put a promoted section before doing the obvious thing. If the section number / placement is clear from context, just do it; offer to move it after.
- ❌ Adding `[resolved]` yourself when first answering. The user adds that signal.

## What this skill does NOT do

- It doesn't scan the entire doc for `TODO` / `FIXME` markers — those are different signals with different protocols.
- It doesn't replace code review (`/review`, `/security-review`).
- It doesn't post anything back to GitHub; the doc is the artifact.
- It doesn't decide what's worth a follow-up vs. a fresh annotation — that's the user's call.

## Notes for the agent's response style

When operating under this skill, after each round, the user-facing summary should be terse:

- One line per annotation operated on, naming the operation ("answered", "resolved + deleted", "follow-up appended", "promoted to §N").
- No long meta-narration. The doc itself is the record of what changed.
- If a question required real investigation, briefly state what was checked ("read PR #184 description, checked `diskgraph-datagenerator/configs/`, confirmed `perf_explorer.sh` is the TUI"). Don't hide the work, but don't dwell on it.
