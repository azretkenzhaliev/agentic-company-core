#!/bin/bash
# The cmo's scheduling poll, macOS only (launchd): every 30 minutes it records the Board's Notion decisions for this
# ISO week and the next, and schedules each approved piece in Metricool (content-calendar skill, "After the
# Board's review", steps 1 and 4). The Board's only steps stay Approved in Notion and Publish in Metricool's app.
# It starts Claude only while some piece is due (scripts/marketing_schedule_gate.py says which, and why that
# can't miss an approved one); otherwise it logs one line and stops.
#
#   scripts/marketing_schedule_job.sh            one run (what launchd starts)
#   scripts/marketing_schedule_job.sh install    install and start the launchd job for this checkout
#   scripts/marketing_schedule_job.sh uninstall  stop and remove it
#
# The calendar is company.json's ("integrations"."marketing"."notion"."calendar"); without one it starts nothing.
# Runs from 08:00 to midnight, as the cmo on Sonnet (the steps are
# mechanical, and the hook allows only the exact staged arguments). Log: ~/Library/Logs/agentic-company/cmo-schedule.log.
set -euo pipefail

LABEL=com.agentic-company.cmo-schedule
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Logs/agentic-company/cmo-schedule.log"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
N=mcp__claude_ai_Notion__
M=mcp__claude_ai_Metricool_Social_Media_Management__

[ "$(uname)" = Darwin ] || { echo "the scheduling poll runs only on macOS (launchd)"; exit 0; }

case "${1:-run}" in
install)
  mkdir -p "$(dirname "$PLIST")" "$(dirname "$LOG")"
  cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>$REPO/scripts/marketing_schedule_job.sh</string></array>
  <key>StartInterval</key><integer>1800</integer>
  <key>StandardOutPath</key><string>$LOG</string>
  <key>StandardErrorPath</key><string>$LOG</string>
</dict></plist>
EOF
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$PLIST"
  echo "installed $LABEL: every 30 minutes, 08:00-24:00, from $REPO; log $LOG"
  exit 0 ;;
uninstall)
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  rm -f "$PLIST"
  echo "removed $LABEL"
  exit 0 ;;
run) ;;
*) sed -n 2,14p "$0" >&2; exit 2 ;;
esac

[ "$(date +%H)" -lt 8 ] && exit 0
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
cd "$REPO"

DATA_SOURCE=$(python3 -c 'import sys; sys.path.insert(0, "scripts"); import notion_approvals_sync as n; print(n.calendar(n.ROOT))')
[ -n "$DATA_SOURCE" ] || { echo "no calendar in company.json (integrations.marketing.notion.calendar): nothing polled"; exit 0; }

query() {
  printf '{"data": {"mode": "rows", "data_source_url": "%s", "filter": {"type": "group", "operator": "and", "filters": [{"type": "property", "property": "Week", "propertyType": "text", "operator": "string_is", "value": {"type": "exact", "value": "%s"}}]}, "limit": 100}}' "$DATA_SOURCE" "$1"
}

gate=0; due=$(python3 scripts/marketing_schedule_gate.py 2>&1) || gate=$?
due=${due##*$'\n'}  # its last line: a warning or a traceback comes first
[ "$gate" -eq 3 ] && { echo "=== $(date '+%Y-%m-%d %H:%M %z') scheduling poll skipped: $due"; exit 0; }

echo "=== $(date '+%Y-%m-%d %H:%M %z') scheduling poll"
if [ "$gate" -eq 0 ]; then echo "$due"; else echo "the gate failed (exit $gate), so the poll runs: $due"; fi
claude -p "Scheduling poll (scripts/marketing_schedule_job.sh, every 30 minutes). Do only this:
1. Load ${N}notion-query-data-sources with ToolSearch and call it twice, with exactly: $(query "$(date +%G-W%V)") and then $(query "$(date -v+7d +%G-W%V)"). The sync hook writes the approvals pages.
2. Candidates: rows at Status 'Ready for Board' whose row in knowledge/marketing/founder/<account>/approvals/<week>.md says Approved, and whose item id (<week in lower case>-<account>-<page slug>) isn't in workspaces/marketing/staged/scheduled.jsonl.
3. For each candidate, follow the content-calendar skill's step 4 after the Board's review: run tools/marketing/publish/stage_item.py on its KB page, call ${M}createScheduledPost with the printed arguments unchanged, and add one line to the row's Notion page body: 'Metricool post id: <id>, scheduled <date> <timezone>, autoPublish false.' If stage_item.py refuses or the hook blocks, add one line 'Not scheduled: <the reason, verbatim>' instead, unless the body already has that line.
4. Use no other writes. With no candidates, reply 'nothing to schedule' and stop. Otherwise end with a short REPORT." \
  --agent cmo --model sonnet --max-turns 40 \
  --allowedTools "ToolSearch,Bash,Read,${N}notion-query-data-sources,${N}notion-fetch,${N}notion-update-page,${M}createScheduledPost" \
  < /dev/null
