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
  echo "MEMORY REMINDER: $THRESHOLD messages have been exchanged since the last memory update." >&2
  echo "Please review this session's key decisions and update memory/sessions/ and memory/MEMORY.md" >&2
  echo "if anything new was decided, built, or learned. Then continue with the user's request." >&2
  exit 2
else
  echo "$count" > "$COUNTER_FILE"
fi
