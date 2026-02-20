#!/usr/bin/env bash
# plugins/progress/handler.sh
# Interface: handler.sh on_init | on_event <event_type> <event_file> | on_destroy

set -euo pipefail

PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$PLUGIN_DIR/../../scripts/tanebi_config.sh"

_ts() { date "+%H:%M:%S"; }

_read_payload() {
  local file="$1" key="$2"
  python3 -c "
import yaml
with open('$file') as f:
    e = yaml.safe_load(f)
print(e.get('payload', {}).get('$key', ''))
" 2>/dev/null || echo ""
}

cmd="${1:-on_init}"

case "$cmd" in
  on_init)
    echo "[$(_ts)] [progress] 🚀 TANEBI Progress Monitor initialized"
    ;;
  on_event)
    EVENT_TYPE="${2:-}"
    EVENT_FILE="${3:-}"
    case "$EVENT_TYPE" in
      task.created)
        CMD_ID=$(_read_payload "$EVENT_FILE" cmd_id)
        SUMMARY=$(_read_payload "$EVENT_FILE" request_summary)
        echo "[$(_ts)] [progress] 📋 Task created: $CMD_ID"
        echo "[$(_ts)] [progress]   Request: $SUMMARY"
        ;;
      task.decomposed)
        CMD_ID=$(_read_payload "$EVENT_FILE" cmd_id)
        COUNT=$(_read_payload "$EVENT_FILE" subtask_count)
        echo "[$(_ts)] [progress] 🔀 Decomposed: $CMD_ID → $COUNT subtasks"
        ;;
      worker.started)
        SUBTASK=$(_read_payload "$EVENT_FILE" subtask_id)
        PERSONA=$(_read_payload "$EVENT_FILE" persona_id)
        WAVE=$(_read_payload "$EVENT_FILE" wave)
        echo "[$(_ts)] [progress] ▶  Worker started: $SUBTASK (persona=$PERSONA, wave=$WAVE)"
        ;;
      worker.progress)
        SUBTASK=$(_read_payload "$EVENT_FILE" subtask_id)
        MSG=$(_read_payload "$EVENT_FILE" message)
        echo "[$(_ts)] [progress]    ⏳ $SUBTASK: $MSG"
        ;;
      worker.completed)
        SUBTASK=$(_read_payload "$EVENT_FILE" subtask_id)
        QUALITY=$(_read_payload "$EVENT_FILE" quality)
        echo "[$(_ts)] [progress] ✅ Worker done: $SUBTASK (quality=$QUALITY)"
        ;;
      wave.completed)
        WAVE=$(_read_payload "$EVENT_FILE" wave)
        COUNT=$(_read_payload "$EVENT_FILE" completed_count)
        echo "[$(_ts)] [progress] 🌊 Wave $WAVE completed: $COUNT workers"
        ;;
      task.aggregated)
        CMD_ID=$(_read_payload "$EVENT_FILE" cmd_id)
        REPORT=$(_read_payload "$EVENT_FILE" report_path)
        echo "[$(_ts)] [progress] 📊 Aggregated: $CMD_ID → $REPORT"
        ;;
      error.worker_failed)
        SUBTASK=$(_read_payload "$EVENT_FILE" subtask_id)
        REASON=$(_read_payload "$EVENT_FILE" reason)
        echo "[$(_ts)] [progress] ❌ Worker failed: $SUBTASK ($REASON)"
        ;;
    esac
    ;;
  on_destroy)
    echo "[$(_ts)] [progress] Progress monitor stopped"
    ;;
esac
