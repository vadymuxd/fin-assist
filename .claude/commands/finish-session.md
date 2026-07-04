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

## 4. Update Memory Index

Page ID: `33f416f27566812a8b25fea944567cab`

**Current State block** — replace with:
> **Session NNN (YYYY-MM-DD):** [one-sentence summary of session state]. Pending: [next actions].

**Decision Log table** — add new rows at the TOP (newest first):
- Max ~120 chars per entry
- Before adding: scan all existing entries for semantic overlap — delete stale entries that are superseded by this session's decisions
- Format: `| DD Mon | [decision] | [Session NNN](url) |`

Entries worth keeping even when superseded: "we tried X and it failed because Y" — reasoning trails have audit value.

---

## 5. Update Agent Config

Page ID: `33f416f27566811aa994e1a3561adac7`

Update **only if something structural changed**:
- Phase completed or started → update **Current Phase** section
- Script built, renamed, or deprecated → update **Scripts table**
- New GHA schedule → update **Automation** section
- New tool or surface added

---

## 6. Update Notion Plan page

Page ID: `34f416f27566-81c4-8b99-ef184aa3c5c3`  
Fetch it first to see current state.

- Tick off any tasks completed this session (change `[ ]` to `[x]`)
- If a phase is now fully complete, mark it `✅ COMPLETE`
- If new tasks were discovered, add them under the right phase
- Update **Immediate Next Steps** list if priorities shifted
- Run `/planning` (`.claude/commands/planning.md`) to move any finished/shelved **Work in Focus** items out to Completed (or promote to a new Phase if substantial/recurring) — that section must only ever hold open items.

Notion is the single source of truth for the plan — there is no `PLAN.md` mirror to sync.

---

## 7. Update reference pages (only if their facts changed)

Fetch the page first, then update only the parts that changed.

| Reference | Page ID | Update when |
|---|---|---|
| Architecture | `33f416f275668180-9b7e-c70145a8c98f` | Technical architecture changed, new worker pattern, new data flow |
| Sheet Structure | `33f416f275668181-0b82c3-cfddebca3d9f` | Sheet tabs added/renamed/removed, column schema changed |
| Credentials | `33f416f2756681-0b9f60-da22e13c2246` | New secrets, new services, credential locations changed |
| Savings Context | `34d416f275668181-6b236-de36e284f4b1` | Savings accounts, pipeline, or goals changed |
| Mortgage Context | `352416f275668181-f7b9b6-c7d646a6605c` | Mortgage deal, monitoring setup, or perspectives changed |

---

## 8. Final check

- [ ] All git changes pushed
- [ ] Session entry created in Notion
- [ ] Memory Index Current State updated, stale entries removed
- [ ] Agent Config current phase accurate
- [ ] Plan tasks ticked in Notion
- [ ] Reference pages updated where facts changed

Tell the user: "Session wrapped. [1-sentence summary of what was recorded and what's next]."
