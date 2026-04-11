# Fin Assist — Master Memory Index

This file is the entry point for any AI session working on this project.
Always read this first, then follow links to relevant topic files.

---

## How to use this memory system

- **MEMORY.md** (this file) — index only, one line per topic, links to detail files
- **memory/sessions/** — full log of each working session with decisions made
- **memory/topics/** — reference files on specific subjects (architecture, credentials, user profile, etc.)
- **PLAN.md** (repo root) — live build plan with checkboxes, always reflects current state

When starting a new session: read `MEMORY.md` → follow relevant topic links → read `PLAN.md` for current task state.

---

## User Profile
→ [memory/topics/user_profile.md](topics/user_profile.md)
Vadym's background, preferences, financial setup, tools used.

## Architecture Decisions
→ [memory/topics/architecture.md](topics/architecture.md)
Key decisions made: GitHub Actions vs always-on Mac, Telegram vs email, sheet structure, scope boundaries.

## Credentials & Config
→ [memory/topics/credentials.md](topics/credentials.md)
What exists, where it lives, what's still missing. Never stores actual secrets.

## Google Sheet Structure
→ [memory/topics/sheet_structure.md](topics/sheet_structure.md)
Existing tabs (do not touch) + new tabs being built (`Inv26`, `InvTransactions`).

## Sessions
→ [memory/sessions/session_001.md](sessions/session_001.md) — Foundations + infrastructure setup (Apr 2026)
→ [memory/sessions/session_002.md](sessions/session_002.md) — Memory system setup + MCP architecture decisions (Apr 2026)
