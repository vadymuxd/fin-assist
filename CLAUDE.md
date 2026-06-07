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

## Finishing a session

When the user says **"finish the session"** (or similar), run `/finish-session` — a slash command defined in `.claude/commands/finish-session.md`.

It covers: push git, analyse full chat, create Notion session entry, update Memory Index (prune stale entries), update Agent Config current phase + scripts, tick Plan tasks in Notion, update Architecture/Sheet Structure/other references where facts changed.

## After every meaningful decision or outcome (mid-session)

Add a detailed summary to the Sessions DB in Notion, then add a one-liner entry to Memory Index pointing to it. Update Agent Config if anything structural changed. Full instructions are in Agent Config.

