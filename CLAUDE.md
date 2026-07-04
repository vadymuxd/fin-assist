# Fin Assist — Claude Instructions

## At the start of every session, fetch these two pages:

1. **Agent Config** — your identity, current phase, safety rules, scripts, and what to update where
   → https://www.notion.so/33f416f27566811aa994e1a3561adac7

2. **Memory Index** — decision log of everything meaningful that's been decided or built
   → https://www.notion.so/33f416f27566812a8b25fea944567cab

Agent Config tells you when to fetch reference pages (User Profile, Architecture, Credentials, Sheet Structure, Sessions) — only load those when the topic requires it.

## Roadmap

The phase-by-phase build plan lives in Notion (authoritative, mobile-accessible):
→ https://www.notion.so/34f416f2756681c48b99ef184aa3c5c3

Fetch this page when the user asks about roadmap, phases, scope, or "what's next."

Notion is the **single source of truth** for the plan. **After completing phases or updating tasks:** update the Notion Plan page directly. (There is no `PLAN.md` mirror — it has been retired.)

**Work in Focus** (top of the Plan page) is Vadym's near-term "what to check/decide soon" scan — it must only ever contain open items. The moment a `Work N` item there is DONE or SHELVED, move it out (to Completed, or promote to its own Phase if it's substantial/recurring) — see `/planning` (`.claude/commands/planning.md`) for the full structure and procedure. Run `/planning` whenever Vadym asks to clean up/reorganize the plan, or proactively whenever a Work in Focus item you were tracking finishes.

## Finishing a session

When the user says **"finish the session"** (or similar), run `/finish-session` — a slash command defined in `.claude/commands/finish-session.md`.

It covers: push git, analyse full chat, create Notion session entry, update Memory Index (prune stale entries), update Agent Config current phase + scripts, tick Plan tasks in Notion, update Architecture/Sheet Structure/other references where facts changed.

## After every meaningful decision or outcome (mid-session)

Add a detailed summary to the Sessions DB in Notion, then add a one-liner entry to Memory Index pointing to it. Update Agent Config if anything structural changed. Full instructions are in Agent Config.

## Notifying Vadym when done OR blocked waiting on him

If Vadym asks to be notified/messaged/told — e.g. "notify me when done", "tell me when you're finished", "message me on Telegram" — follow `/notify` (`.claude/commands/notify.md`). This covers two moments, not just completion: (1) done — send a Telegram summary as the last step before ending your turn; (2) blocked — any time you're about to end your turn waiting on him (a clarifying question, a risky-action confirmation, a permission-approval prompt), send a short "⏸️ Need you: ..." ping first so he knows to come back to his Mac. Both use `python3 scripts/notify_telegram.py "<message>"`.

