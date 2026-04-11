# Session 002 — Memory System Setup & Architecture Decisions
**Date:** April 2026
**Status:** Complete (memory config partially built; Notion sync deferred to next session)

---

## What was discussed

- Discovered the memory/ folder existed in the project directory but Claude's auto-memory path (`~/.claude/projects/.../memory/`) was empty — two separate locations, causing "file does not exist" errors
- Built the local memory infrastructure: CLAUDE.md, memory_reminder.sh hook, settings.json Stop hook, redirect at Claude auto-memory path
- Discussed how to bridge memory between Claude Code (Mac) and claude.ai (mobile Claude Project)
- Evaluated Google Drive MCP vs Notion MCP for shared memory
- Clarified the distinction between two separate Google connections: service account (scripts) vs interactive MCP (Claude in conversation)

## Key decisions

| Decision | Choice | Reason |
|----------|--------|--------|
| Shared memory store | Notion | Only option with full read+write MCP on both Claude Code and claude.ai |
| Google Drive MCP | Ruled out for memory | Read-only — only fetch and search tools, no write |
| Memory update trigger | Stop hook after 5 turns | Automatic, doesn't require manual prompting |
| Google Sheets (scripts) | Service account JSON | Already works; this is NOT an MCP concern |
| Google Sheets (Claude interactive) | Deferred | No reliable read/write MCP exists yet; custom wrapper planned later |
| Priority order | Memory config first, then Phase 2 design session | Need reliable context before design work |

## What was built this session

- `CLAUDE.md` in repo root — instructs Claude to load memory at session start, lists ground rules
- `scripts/memory_reminder.sh` — counter script, fires after 5 turns, resets counter
- `.claude/settings.json` — Stop hook wired to memory_reminder.sh
- `~/.claude/projects/.../memory/MEMORY.md` — redirect file so auto-memory doesn't write to wrong path
- Phase 6 section added to `PLAN.md` with all Notion sync tasks

## What was NOT done (do next session)

- Create Notion pages mirroring memory/topics/ structure
- Create Notion Sessions database
- Update Stop hook to sync to Notion after reminder
- Configure Notion MCP in claude.ai Settings → Integrations
- Write Claude Project system prompt
- Wire Claude Project to fetch from Notion

---

## Plan restructure

Phases reordered and extended:
- Phase 2: Memory & Assistant Continuity (was Phase 6 — moved up, must precede design session)
- Phase 3: Design Session (requires Phase 2 — Claude Project must exist first)
- Phase 4: Google Sheet
- Phase 5: Scripts & Automation
- Phase 6: App & UI — define why needed, what it does, how organised, then build
- Phase 7: Savings (Monzo, Chase, Starling, Revolut)
- Phase 8: Pensions (Nutmeg, workplace)
- Phase 9: Mortgage
- Phase 10: Budgeting & expenses (Emma Live Export, monthly/annual ceremonies)

## References
- Plan: `PLAN.md`
- Architecture: `memory/topics/architecture.md`
