#!/usr/bin/env bash
# plugins/evolution/handler.sh
# Interface: handler.sh on_init | on_event <event_type> <event_file> | on_destroy
# Visualizes Persona evolution progress in real-time.

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
    v = val.get('$key', '')
    if isinstance(v, list):
        print(', '.join(str(x) for x in v))
    else:
        print(v)
" 2>/dev/null || echo ""
}

cmd="${1:-on_init}"

case "$cmd" in
  on_init)
    echo "[$(_ts)] [evolution] 🧬 TANEBI Evolution Monitor initialized"
    ;;
  on_event)
    EVENT_TYPE="${2:-}"
    EVENT_FILE="${3:-}"
    case "$EVENT_TYPE" in
      evolution.started)
        CMD_ID=$(_read_payload "$EVENT_FILE" cmd_id)
        echo "[$(_ts)] [evolution] 🧬 Evolution started: ${CMD_ID:-?}"
        echo "[$(_ts)] [evolution]   Analyzing task results and updating Personas..."
        ;;
      evolution.persona_updated)
        PERSONA=$(_read_payload "$EVENT_FILE" persona_id)
        FIELD=$(_read_payload "$EVENT_FILE" field)
        OLD=$(_read_payload "$EVENT_FILE" old_value)
        NEW=$(_read_payload "$EVENT_FILE" new_value)
        REASON=$(_read_payload "$EVENT_FILE" reason)
        echo "[$(_ts)] [evolution] 🔄 Persona updated: ${PERSONA:-?}"
        echo "[$(_ts)] [evolution]   ${FIELD:-field}: ${OLD:-?} → ${NEW:-?}  (${REASON:-auto})"
        ;;
      evolution.few_shot_registered)
        DOMAIN=$(_read_payload "$EVENT_FILE" domain)
        SUBTASK=$(_read_payload "$EVENT_FILE" subtask_id)
        QUALITY=$(_read_payload "$EVENT_FILE" quality)
        echo "[$(_ts)] [evolution] 📚 Few-Shot registered: ${DOMAIN:-?}/${SUBTASK:-?} (quality=${QUALITY:-?})"
        ;;
      evolution.completed)
        CMD_ID=$(_read_payload "$EVENT_FILE" cmd_id)
        PERSONAS=$(_read_payload "$EVENT_FILE" personas_updated)
        FEW_SHOTS=$(_read_payload "$EVENT_FILE" few_shots_added)
        echo "[$(_ts)] [evolution] ═══════════════════════════════════"
        echo "[$(_ts)] [evolution] ✅ Evolution completed: ${CMD_ID:-?}"
        echo "[$(_ts)] [evolution] ───────────────────────────────────"
        echo "[$(_ts)] [evolution]   Personas updated: ${PERSONAS:-none}"
        echo "[$(_ts)] [evolution]   Few-Shots added:  ${FEW_SHOTS:-0}"
        echo "[$(_ts)] [evolution] ═══════════════════════════════════"
        ;;
    esac
    ;;
  on_destroy)
    echo "[$(_ts)] [evolution] Evolution monitor stopped"
    ;;
esac
