#!/bin/bash
# memory_reminder.sh
# Counts Claude turns in a session. After THRESHOLD turns, reminds Claude to update memory.

COUNTER_FILE="/tmp/fin_assist_session_counter.txt"
THRESHOLD=5

count=$(cat "$COUNTER_FILE" 2>/dev/null || echo 0)
count=$((count + 1))

if [ "$count" -ge "$THRESHOLD" ]; then
  echo 0 > "$COUNTER_FILE"
  echo "" >&2
  echo "========================================" >&2
  echo "MEMORY REMINDER: $THRESHOLD messages exchanged since last memory update." >&2
  echo "========================================" >&2
  echo "" >&2
  echo "Please do the following before continuing:" >&2
  echo "" >&2
  echo "1. SESSIONS DB (Notion) — every decision and every new fact goes HERE:" >&2
  echo "   - Update THIS session's page (create it on the first update, then keep editing it)." >&2
  echo "   - This is the ONLY uncapped store. All narrative and all decisions belong here." >&2
  echo "   - Sessions DB data source ID: f87930bb-a785-4e6d-9859-71f6a975ae55" >&2
  echo "" >&2
  echo "2. MEMORY INDEX -> Current State (Notion) — REFRESH the one-liner:" >&2
  echo "   - Rewrite the single Current State block so it summarises THIS session as it" >&2
  echo "     stands right now. Overwrite it in place — do not append a second block." >&2
  echo "   - It holds exactly ONE session, ~1,200 chars. If you see two bullets, fix it." >&2
  echo "   - If the block still describes the PREVIOUS session, that session's Sessions Index" >&2
  echo "     row should already exist (written at its /finish-session). Check; if it is" >&2
  echo "     missing, add it now, then overwrite the block with this session's summary." >&2
  echo "   - Memory Index page ID: 33f416f2-7566-812a-8b25-fea944567cab" >&2
  echo "" >&2
  echo "   DO NOT add a Sessions Index row mid-session. That table gets exactly ONE row per" >&2
  echo "   session, written once at /finish-session. A decision made now is NOT a new row —" >&2
  echo "   it goes to the Session page (store 1) and into the refreshed one-liner above." >&2
  echo "" >&2
  echo "3. PLAN (Notion) — phases, next steps, and Work in Focus live here, nowhere else:" >&2
  echo "   - Work in Focus holds OPEN items only. Move finished ones out (see /planning)." >&2
  echo "   - Plan page ID: 34f416f2-7566-81c4-8b99-ef184aa3c5c3" >&2
  echo "" >&2
  echo "4. AGENT CONFIG (Notion) — permanent config ONLY. Usually: do nothing." >&2
  echo "   - Edit only for identity/profile, a key ID, a new reference page, or a structural rule." >&2
  echo "   - NEVER record phases, current work, next steps, or session state here." >&2
  echo "   - A phase starting or completing is NOT a reason to touch this page." >&2
  echo "   - Agent Config page ID: 33f416f2-7566-811a-a994-e1a3561adac7" >&2
  echo "" >&2
  echo "5. REFERENCE PAGES (Notion) — only if their specific facts changed:" >&2
  echo "   - User Profile:     33f416f2-7566-81f4-b5f7-dc7bbfb7e626" >&2
  echo "   - Architecture:     33f416f2-7566-8180-9b7e-c70145a8c98f" >&2
  echo "   - Credentials:      33f416f2-7566-810b-9f60-da22e13c2246" >&2
  echo "   - Sheet Structure:  33f416f2-7566-81b0-82c3-cfddebca3d9f" >&2
  echo "" >&2
  echo "Then continue with the user's request." >&2
  echo "========================================" >&2
  exit 2
else
  echo "$count" > "$COUNTER_FILE"
fi
