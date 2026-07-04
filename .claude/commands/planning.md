# /planning — Maintain the Notion Plan page

Trigger this when Vadym asks to clean up / reorganize the plan, move
finished items out of the way, turn an ongoing item into a proper phase, or
says things like "move done items to Completed", "make this a phase", "the
plan is getting cluttered". Also do this proactively, without being asked,
any time a "Work N" item you were tracking in **Work in Focus** reaches DONE
or SHELVED status — don't wait for Vadym to notice it's stale.

## The structure (as it exists today — verify against the live pages, this can drift)

**Plan** (`34f416f2-7566-81c4-8b99-ef184aa3c5c3`) has two kinds of content:

1. **Work in Focus** (top of the page) — Vadym's near-term "what do I need to
   check/decide soon" list. Informal `Work N. <description>` free-text items,
   added by Vadym directly in Notion or by Claude mid-session. **This section
   must only ever contain items that are still open.** The moment an item is
   DONE, SHELVED, or superseded, it does not belong here anymore — Vadym uses
   this section as his own to-do scan, and stale finished items defeat that.

2. **Phase NN — Title** sections — larger structured initiatives, numbered
   sequentially, appended at the bottom as new ones are created. Each phase
   has:
   - `**Why:**` — one paragraph, the motivation
   - `**Output:**` — one paragraph, what "done" looks like
   - A checklist of subtasks using a short lowercase code + number, e.g.
     `- [ ] **android.3** Icon + splash + app name`, so individual tasks are
     addressable in conversation and commits. Use `- [x]` for done items —
     **don't delete a completed phase's checklist**, a phase can be "done"
     with all boxes checked and just stay in Plan as historical context
     (Phase 20 does this — mostly moved to Completed by convention, but nothing
     forces it). When a phase becomes a genuinely ongoing/recurring loop
     (not a one-time build), keep it in Plan rather than Completed — Phase 23
     (recommendation-quality tuning) is the model: some tasks checked off,
     some still open, revisited monthly.

**Completed** (`35b416f2756680efb2ffdb635581c777`, sub-page of Plan) is the
archive. Two patterns already live there, both fine to keep using:
- **Full phase blocks** — `## Phase N — Title ✅` moved wholesale once
  entirely done, matching the exact heading/Why/Output/checklist format from
  Plan.
- **Ad-hoc work-item groups** — `## 🔧 Work Items — YYYY-MM-DD (Session NNN)`
  with one bullet per item: **Name — status ✅/SHELVED** one-line summary,
  linking to the Session page(s) for full detail rather than duplicating it.
  Use this for small `Work N` items that don't warrant their own Phase.

**Single-owner rule applies here too**: Plan/Completed hold pointers and
one-line-to-one-paragraph summaries only. Full mechanism/script/decision
detail lives on Scripts & Automation, Architecture, domain Context pages, or
Session pages — link to those, don't re-explain them in Plan.

## What to do

1. Fetch the live Plan page (and Completed if moving something) — never
   assume the structure above is still accurate; Vadym edits Plan directly in
   Notion too (e.g. adding new `Work N` items), so re-read before editing.
2. For each Work in Focus item that's finished:
   - **Small/one-off** → move to Completed under a dated Work Items group
     (create a new one if today's date/session isn't already there, otherwise
     append to it). Delete it from Work in Focus.
   - **Substantial and/or recurring** → promote to a new `Phase NN` at the
     bottom of Plan (next sequential number), Why/Output/checklist format,
     checking off what's done and leaving open items unchecked. Delete the
     Work in Focus entry once the phase exists. Don't also copy it to
     Completed — an ongoing phase belongs in Plan, not the archive.
3. If Vadym asks to reorganize existing Phases (renumber, merge, split,
   reorder, retitle) — do it directly on the live page. Keep task short-codes
   (`android.1`, `chat.2`, etc.) intact where the underlying task is
   unchanged, even if the phase number/position changes, so references in
   commits/sessions/memory still resolve.
4. Use `notion-update-page` with `update_content` (small, targeted
   old_str/new_str pairs) for edits within existing content, and
   `insert_content` with `position: {"type": "end"}` for appending new
   sections — safer than guessing exact whitespace for a mid-document
   insert. If an `update_content` call fails with "no matches found", re-fetch
   the page first; don't guess at reformatted whitespace/escaping.
5. After any structural change, follow the project's standard mid-session
   memory rule (Agent Config): log the outcome in the Sessions DB, add a
   Memory Index one-liner, and update Agent Config only if something
   structural (not just a Plan edit) changed.

## Notes

- Never silently drop content — every removal from Work in Focus must land
  somewhere (Completed or a new Phase) in the same edit pass.
- If you're unsure whether an item is "small" vs "substantial enough for a
  phase", default to: recurring/ongoing work (something with a monthly
  cadence, an open-ended tuning loop, multiple future sub-tasks) → Phase;
  a single fix/decision that's fully resolved → Completed work-item group.
