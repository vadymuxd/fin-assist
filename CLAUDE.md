# Fin Assist — Claude Instructions

## At the start of every session, fetch these two pages:

1. **Agent Config** — your identity, current phase, safety rules, scripts, and what to update where
   → https://www.notion.so/33f416f27566811aa994e1a3561adac7

2. **Memory Index** — where things stand right now, plus a one-line-per-session index of past sessions
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

It covers: push git, analyse full chat, create Notion session entry, the short-term memory sweep (below), tick Plan tasks in Notion, update Architecture/Sheet Structure/other references where facts changed.

## Short-term memory — three places, one job each

Short-term memory lives in exactly three places. Each is **capped** and gets cleaned every session (`/finish-session` step 4). The failure mode to guard against is append-instead-of-replace.

| Place | Its one job | Cap |
|---|---|---|
| **Plan → Work in Focus** | Open work only | Zero finished items |
| **Memory Index → Current State** | Where things stand right now | ~1,200 chars, ONE session |
| **Memory Index → Sessions Index** | One summary row per *finished* session | 1 row/session, ~200 chars, ~12 months |
| **Agent Config** | Permanent identity + config only | No phases, no session state, ever |

Full narrative always goes to the **Sessions DB** — the only uncapped store. The three places above hold pointers, never prose. A completed phase is never a reason to edit Agent Config; most sessions should leave it untouched.

## After every meaningful decision or outcome (mid-session)

Two writes, every time:

1. **Sessions DB** — add the decision, with its reasoning, to *this session's* page. Every decision lives here and nowhere else.
2. **Memory Index → Current State** — refresh the single one-liner block so it summarises this session as it now stands. Overwrite in place; never append a second block.

**Never add a Sessions Index row mid-session.** That table gets exactly one row per session, written once at `/finish-session`. A new decision is not a new row — it goes to (1) and is reflected in (2).

Only touch Agent Config if something **permanent** changed (identity, key IDs, reference table, structural rule) — not phases or current work. Full instructions are in Agent Config.

## Git — commit AND push, every time, without asking

Pushing is part of making a change, not a separate decision. Never end a turn with a fix committed but unpushed, and never ask "want me to push?"

**Why:** the scheduled GitHub Actions workflows run whatever is on `main`. An unpushed fix means the automation keeps executing the broken code while the local repo looks correct — the bug then re-occurs on the next scheduled run. This has happened twice (1 Jul 2026: two commits unpushed, so Vercel had nothing to deploy; 5 Aug 2026: the mortgage-valuation fix `af06e87` found still unpushed from an earlier session, alongside five uncommitted doc files).

Never create a branch — work on `main`. Expect the remote to be ahead: the scheduled workflows push their own `chore: mortgage snapshot` commits, so `git pull --rebase --autostash origin main` before pushing is routine. Verify the push landed (`git status -sb` shows no "ahead"), not just the commit.

## Notifying Vadym when done OR blocked waiting on him

If Vadym asks to be notified/messaged/told — e.g. "notify me when done", "tell me when you're finished", "message me on Telegram" — follow `/notify` (`.claude/commands/notify.md`). This covers two moments, not just completion: (1) done — send a Telegram summary as the last step before ending your turn; (2) blocked — any time you're about to end your turn waiting on him (a clarifying question, a risky-action confirmation, a permission-approval prompt), send a short "⏸️ Need you: ..." ping first so he knows to come back to his Mac. Both use `python3 scripts/notify_telegram.py "<message>"`.

