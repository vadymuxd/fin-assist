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

`PLAN.md` in repo root is a git-versioned mirror — kept in sync but Notion is the source of truth. **After completing phases or updating tasks:** update the Notion Plan page first, then sync to `PLAN.md`.

## After every meaningful decision or outcome

Add a detailed summary to the Sessions DB in Notion, then add a one-liner entry to Memory Index pointing to it. Update Agent Config if anything structural changed. Full instructions are in Agent Config.

## Safety rules (always apply, even if Notion is unavailable)

- **Never touch** these Google Sheet tabs: `Inv25+`, `Summary (+)`, `Money Flow (+)`, `Joint Spendings (+)`, `Personal Spendings (+)`, `Saving Transfers` (was `Savings (+)`), `Accounts (+)`, `Legend`, `Inv22-24`, `Earnings 2025`
- Scripts may only read/write: `Inv26 - Summary`, `Inv26 - Trend`, `InvTransactions`, `Alerts Config`, `Analysis Log`
- Scripts may **read** (not modify): `Savings Balance` — savings account balances time-series (Bank | Account | Type | Owner | monthly columns)
- `Inv26` tab has been renamed to `Inv26 - Summary`; `Inv26 - Trend` is a new tab created in Phase 3B
- Phase 3B complete: sheet structure, benchmarks, Trend tab, and transaction architecture finalised
