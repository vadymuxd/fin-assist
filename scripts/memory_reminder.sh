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
  echo "1. SESSIONS DB (Notion) — for anything meaningful decided or built:" >&2
  echo "   - Add a detailed summary to the Sessions DB as a new entry or update current session" >&2
  echo "   - Sessions DB data source ID: f87930bb-a785-4e6d-9859-71f6a975ae55" >&2
  echo "" >&2
  echo "2. MEMORY INDEX (Notion) — after updating Sessions DB:" >&2
  echo "   - Add a one-liner entry pointing to the session" >&2
  echo "   - Update 'Current State' section if phase or next steps changed" >&2
  echo "   - Memory Index page ID: 33f416f2-7566-812a-8b25-fea944567cab" >&2
  echo "" >&2
  echo "3. AGENT CONFIG (Notion) — only if something structural changed:" >&2
  echo "   - New script built or deprecated, phase changed, schedule changed, new tool added" >&2
  echo "   - Agent Config page ID: 33f416f2-7566-811a-a994-e1a3561adac7" >&2
  echo "" >&2
  echo "4. REFERENCE PAGES (Notion) — only if their specific facts changed:" >&2
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
