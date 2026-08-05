# /finish-session — End-of-session wrap-up

Run this at the end of every working session. Go through each step in order.

---

## 1. Push any pending git changes

```
git status
git push   # if there are unpushed commits
```

If there are uncommitted local edits, ask the user before committing.

---

## 2. Analyse the full session

Read the entire conversation from the top. Identify:

- Every decision made (technical, architectural, data, UX)
- Every file created, modified, or deleted
- Every bug fixed and its root cause
- Scripts built, retired, or renamed
- Phase tasks completed (map to Notion Plan task IDs like `eng.6`, `data.1`, etc.)
- Outstanding items / next steps
- Anything that changes Architecture, Sheet Structure, Credentials, or Agent Config

---

## 3. Create a Session entry in Notion Sessions DB

Collection ID: `f87930bb-a785-4e6d-9859-71f6a975ae55`

Number the session sequentially (check Memory Index for the last session number).

Fields to fill:
- **Session** — "Session NNN"
- **date:Date:start** — today's ISO date
- **Summary** — one sentence, what changed
- **Decisions Made** — numbered list of all decisions
- **Next Steps** — concrete next actions

Page content — write a full narrative with sections:
- What happened / why
- Technical decisions + rationale
- Files changed
- Verified / tested
- Pending

---

## 4. Short-term memory sweep (the three places)

Short-term memory lives in exactly three places, each with **one job**. Every
session, review all three and remove what is done. The failure mode this step
exists to prevent is **append-instead-of-replace** — every place below has a
hard cap, and nothing new goes in until what it displaces has been moved out or
deleted.

| Place | Its one job | Cap |
|---|---|---|
| **Plan → Work in Focus** | Open work only — what Vadym needs to check/decide soon | Open items only, zero finished ones |
| **Memory Index → Current State** | Where things stand *right now*, one block | ~1,200 chars, ONE session |
| **Memory Index → Sessions Index** | A table of contents: one summary row per *finished* session | 1 row per session, ~200 chars, ~12 months |
| **Agent Config** | Permanent identity + config ONLY | No phases, no session state, ever |

Full detail always lives on the **Session page** — it is uncapped and is the
only place narrative belongs. The three places above hold pointers, never prose.

### 4a. Memory Index — Current State

Page ID: `33f416f27566812a8b25fea944567cab`

This block describes the present, not the past. It holds **exactly one session** —
by now it should already describe *this* session, because it gets refreshed in
place every time the memory reminder fires mid-session. Here you are writing its
final version, not creating it from scratch.

1. **Replace in place** (never prepend, never demote — the outgoing session's
   Sessions Index row was written at *its* `/finish-session`, so nothing is lost
   by overwriting):

> **Session NNN (YYYY-MM-DD)** — [2–3 sentences: what changed and where things stand]. **Open:** [unresolved threads, or "none"]. → [Session NNN](url)

2. If the block exceeds ~1,200 chars, it has narrative in it that belongs on the
   Session page. Cut it down.
3. **Check:** the `## Current State` section must contain **one bullet**. If it
   has two, a mid-session refresh appended instead of overwriting — fix it now.
4. **Safety net:** if the block you are replacing describes an *earlier* session,
   that session's `/finish-session` was skipped. Confirm it has a Sessions Index
   row and add one if not, before overwriting.

### 4b. Memory Index — Sessions Index

This table is a **session-level table of contents**, not a decision log. It
answers "what was that session about, and where do I read more" — nothing else.

- **Exactly one row per session. Never two.** A session with five decisions
  still gets one row. If you find a session with more than one row, merge them.
- **Only for finished sessions.** The row is written here, at `/finish-session`,
  and never mid-session. A session in progress has no row.
- **No individual decisions.** Every decision belongs on the Session page
  (step 3). If you're tempted to add a second row for "one more decision", that
  is the mistake this rule exists to prevent — put it in the Session page instead.
- Add the new row at the TOP (newest first):
  `| DD Mon | [what the session was about] | [Session NNN](url) |`
- Max ~200 chars. One line, no paragraphs, no code walkthroughs.
- **No open items.** Unresolved threads go to Plan → Work in Focus, not here.
  Rows describe what was settled, not what's pending.
- Before adding: scan existing rows for semantic overlap; delete stale rows
  superseded by this session.
- **Prune the tail:** drop rows older than ~12 months unless they are still
  load-bearing (an active convention, or a "tried X, failed because Y"
  reasoning trail — those have audit value and stay).

### 4c. Agent Config — permanent config only

Page ID: `33f416f27566811aa994e1a3561adac7`

**Do NOT record phases, current work, next steps, or session state here.**
Those live in Plan (forward-looking) and Memory Index (present state). If you
find any on this page, delete them and leave a pointer to Plan.

Update this page **only** when something permanent changed:
- Identity, role, tone, or Vadym's profile
- A key ID changed, or a new reference page was added to the Reference table
- A data-store role or self-maintenance rule changed
- A new tool or surface was added to the system

A completed phase is **not** a reason to touch this page. Most sessions should
leave Agent Config untouched — that is the expected outcome, not a miss.

### 4d. Plan — Work in Focus

Run `/planning` (`.claude/commands/planning.md`) to move every finished or
shelved `Work N` item out to Completed (or promote it to a Phase if
substantial/recurring). This section must end the session holding **open items
only**. If nothing is open, leave it empty — an empty section is correct.

---

## 5. Update Notion Plan page

Page ID: `34f416f27566-81c4-8b99-ef184aa3c5c3`  
Fetch it first to see current state.

- Tick off any tasks completed this session (change `[ ]` to `[x]`)
- If a phase is now fully complete, mark it `✅ COMPLETE`
- If new tasks were discovered, add them under the right phase
- Update **Immediate Next Steps** list if priorities shifted

Work in Focus is handled in step 4d — don't duplicate that here.

Notion is the single source of truth for the plan — there is no `PLAN.md` mirror to sync.

---

## 6. Update reference pages (only if their facts changed)

Fetch the page first, then update only the parts that changed.

| Reference | Page ID | Update when |
|---|---|---|
| Architecture | `33f416f275668180-9b7e-c70145a8c98f` | Technical architecture changed, new worker pattern, new data flow |
| Sheet Structure | `33f416f275668181-0b82c3-cfddebca3d9f` | Sheet tabs added/renamed/removed, column schema changed |
| Credentials | `33f416f2756681-0b9f60-da22e13c2246` | New secrets, new services, credential locations changed |
| Savings Context | `34d416f275668181-6b236-de36e284f4b1` | Savings accounts, pipeline, or goals changed |
| Mortgage Context | `352416f275668181-f7b9b6-c7d646a6605c` | Mortgage deal, monitoring setup, or perspectives changed |

---

## 7. Final check

- [ ] All git changes pushed
- [ ] Session entry created in Notion (full narrative lives here, nowhere else)
- [ ] Memory Index **Current State holds exactly one bullet**, describing this session
- [ ] Memory Index Sessions Index: **exactly one new row for this session**, overlapping/stale rows deleted, tail pruned, no session listed twice
- [ ] Agent Config: **untouched**, unless something permanent changed (phases are never a reason)
- [ ] Plan **Work in Focus holds open items only** — finished ones moved to Completed or promoted to a Phase
- [ ] Plan tasks ticked in Notion
- [ ] Reference pages updated where facts changed

Tell the user: "Session wrapped. [1-sentence summary of what was recorded and what's next]."
