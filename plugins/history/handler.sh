#!/usr/bin/env bash
# plugins/history/handler.sh
# Interface: handler.sh on_init | on_event <event_type> <event_file> | on_destroy
# Indexes completed tasks into work/index.yaml for history browsing.

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
val = e.get('payload', {})
if isinstance(val, dict):
    print(val.get('$key', ''))
" 2>/dev/null || echo ""
}

index_completed_task() {
  local event_file="$1"
  local index_file="$TANEBI_ROOT/work/index.yaml"

  local cmd_id request_summary subtask_count report_path quality_summary
  cmd_id=$(_read_payload "$event_file" cmd_id)
  request_summary=$(_read_payload "$event_file" request_summary)
  subtask_count=$(_read_payload "$event_file" subtask_count)
  report_path=$(_read_payload "$event_file" report_path)
  quality_summary=$(_read_payload "$event_file" quality_summary)

  # Defaults
  : "${cmd_id:=unknown}"
  : "${request_summary:=}"
  : "${subtask_count:=0}"
  : "${report_path:=}"
  : "${quality_summary:=UNKNOWN}"

  python3 - "$index_file" "$cmd_id" "$request_summary" "$subtask_count" "$report_path" "$quality_summary" <<'PYEOF'
import yaml, sys, os
from datetime import datetime

index_file = sys.argv[1]
cmd_id = sys.argv[2]
request_summary = sys.argv[3]
subtask_count = int(sys.argv[4]) if sys.argv[4].isdigit() else 0
report_path = sys.argv[5]
quality_summary = sys.argv[6]

# Ensure parent directory exists
os.makedirs(os.path.dirname(index_file), exist_ok=True)

# Load or initialize
if os.path.exists(index_file):
    with open(index_file) as f:
        data = yaml.safe_load(f) or {}
else:
    data = {}

index = data.get('index', {})
if 'tasks' not in index or not isinstance(index.get('tasks'), list):
    index['tasks'] = []

now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

entry = {
    'cmd_id': cmd_id,
    'date': now,
    'request_summary': request_summary,
    'total_subtasks': subtask_count,
    'quality_summary': quality_summary,
    'report_path': report_path,
}

index['tasks'].append(entry)
index['last_updated'] = now
data['index'] = index

with open(index_file, 'w') as f:
    yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
PYEOF

  echo "[$(_ts)] [history] Indexed task: $cmd_id"
}

cmd="${1:-on_init}"

case "$cmd" in
  on_init)
    echo "[$(_ts)] [history] TANEBI History plugin initialized"
    ;;
  on_event)
    EVENT_TYPE="${2:-}"
    EVENT_FILE="${3:-}"
    case "$EVENT_TYPE" in
      task.aggregated)
        if [ -n "$EVENT_FILE" ] && [ -f "$EVENT_FILE" ]; then
          index_completed_task "$EVENT_FILE"
        else
          echo "[$(_ts)] [history] WARNING: No event file for task.aggregated" >&2
        fi
        ;;
    esac
    ;;
  on_destroy)
    echo "[$(_ts)] [history] History plugin stopped"
    ;;
esac
