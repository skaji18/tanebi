#!/usr/bin/env bash
# plugins/cost/handler.sh
# Interface: handler.sh on_init | on_event <event_type> <event_file> | on_destroy
# Tracks token usage per task and displays cost summaries.

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

_get_cost_file() {
  local cmd_id="$1"
  echo "$TANEBI_WORK_DIR/$cmd_id/cost.yaml"
}

_init_cost_yaml() {
  local cmd_id="$1"
  local cost_file
  cost_file="$(_get_cost_file "$cmd_id")"
  local cmd_dir
  cmd_dir="$(dirname "$cost_file")"
  mkdir -p "$cmd_dir"
  if [ ! -f "$cost_file" ]; then
    cat > "$cost_file" <<YAML
cost:
  cmd_id: "$cmd_id"
  timestamp: "$(date "+%Y-%m-%dT%H:%M:%S")"
  breakdown:
    decompose:
      tokens: 0
    workers: []
    aggregate:
      tokens: 0
    evolve:
      tokens: 0
  total_tokens: 0
YAML
  fi
}

accumulate_cost() {
  local cmd_id="$1"
  local subtask_id="$2"
  local tokens="$3"
  local cost_file
  cost_file="$(_get_cost_file "$cmd_id")"
  _init_cost_yaml "$cmd_id"

  python3 - "$cost_file" "$subtask_id" "$tokens" <<'PYEOF'
import yaml, sys

cost_file = sys.argv[1]
subtask_id = sys.argv[2]
tokens = int(sys.argv[3]) if sys.argv[3].isdigit() else 0

with open(cost_file) as f:
    data = yaml.safe_load(f)

cost = data['cost']
workers = cost['breakdown'].setdefault('workers', [])

found = False
for w in workers:
    if w.get('subtask_id') == subtask_id:
        w['tokens'] = w.get('tokens', 0) + tokens
        found = True
        break
if not found:
    workers.append({'subtask_id': subtask_id, 'tokens': tokens})

total = (cost['breakdown'].get('decompose', {}).get('tokens', 0) +
         sum(w.get('tokens', 0) for w in workers) +
         cost['breakdown'].get('aggregate', {}).get('tokens', 0) +
         cost['breakdown'].get('evolve', {}).get('tokens', 0))
cost['total_tokens'] = total

with open(cost_file, 'w') as f:
    yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
PYEOF
  echo "[$(_ts)] [cost] 💰 Token accumulated: $cmd_id/$subtask_id +$tokens tokens"
}

show_cost_summary() {
  local cmd_id="$1"
  local cost_file
  cost_file="$(_get_cost_file "$cmd_id")"

  if [ ! -f "$cost_file" ]; then
    echo "[$(_ts)] [cost] No cost data for $cmd_id"
    return
  fi

  python3 - "$cost_file" <<'PYEOF'
import yaml, sys

with open(sys.argv[1]) as f:
    data = yaml.safe_load(f)

cost = data['cost']
bd = cost['breakdown']
total = cost.get('total_tokens', 0)

print(f"[cost] ═══════════════════════════════════")
print(f"[cost] 💰 Cost Summary: {cost['cmd_id']}")
print(f"[cost] ───────────────────────────────────")
print(f"[cost]   Decompose:  {bd.get('decompose', {}).get('tokens', 0):>8,} tokens")
for w in bd.get('workers', []):
    sid = w.get('subtask_id', '?')
    toks = w.get('tokens', 0)
    print(f"[cost]   {sid:<20} {toks:>6,} tokens")
print(f"[cost]   Aggregate:  {bd.get('aggregate', {}).get('tokens', 0):>8,} tokens")
print(f"[cost]   Evolve:     {bd.get('evolve', {}).get('tokens', 0):>8,} tokens")
print(f"[cost] ───────────────────────────────────")
print(f"[cost]   TOTAL:      {total:>8,} tokens  (~{total // 4:,} chars)")
print(f"[cost] ═══════════════════════════════════")
PYEOF
}

cmd="${1:-on_init}"

case "$cmd" in
  on_init)
    echo "[$(_ts)] [cost] 💰 TANEBI Cost Monitor initialized"
    ;;
  on_event)
    EVENT_TYPE="${2:-}"
    EVENT_FILE="${3:-}"
    case "$EVENT_TYPE" in
      cost.token_used)
        CMD_ID=$(_read_payload "$EVENT_FILE" cmd_id)
        SUBTASK_ID=$(_read_payload "$EVENT_FILE" subtask_id)
        TOKENS=$(_read_payload "$EVENT_FILE" tokens_estimated)
        if [ -n "$CMD_ID" ]; then
          accumulate_cost "$CMD_ID" "${SUBTASK_ID:-unknown}" "${TOKENS:-0}"
        fi
        ;;
      worker.completed)
        SUBTASK_ID=$(_read_payload "$EVENT_FILE" subtask_id)
        echo "[$(_ts)] [cost] ✅ Subtask cost finalized: ${SUBTASK_ID:-?}"
        ;;
      task.aggregated)
        CMD_ID=$(_read_payload "$EVENT_FILE" cmd_id)
        if [ -n "$CMD_ID" ]; then
          show_cost_summary "$CMD_ID"
        fi
        ;;
      evolution.completed)
        CMD_ID=$(_read_payload "$EVENT_FILE" cmd_id)
        if [ -n "$CMD_ID" ]; then
          echo "[$(_ts)] [cost] 🧬 Evolution cost finalized for $CMD_ID"
          show_cost_summary "$CMD_ID"
        fi
        ;;
    esac
    ;;
  on_destroy)
    echo "[$(_ts)] [cost] Cost monitor stopped"
    ;;
esac
