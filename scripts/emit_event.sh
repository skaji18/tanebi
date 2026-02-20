#!/usr/bin/env bash
# Usage: bash scripts/emit_event.sh <cmd_dir> <event_type> '<payload_yaml>'
# work/cmd_NNN/events/ に連番YAMLファイルを書き出し、component_loader.sh dispatch を呼ぶ

set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/tanebi_config.sh"

CMD_DIR="${1:?usage: emit_event.sh <cmd_dir> <event_type> '<payload>'}"
EVENT_TYPE="${2:?event_type required}"
_default_payload='{}'
PAYLOAD="${3:-$_default_payload}"

EVENTS_DIR="$CMD_DIR/events"
mkdir -p "$EVENTS_DIR"

# 連番ファイル名
SEQ=$( (ls "$EVENTS_DIR"/*.yaml 2>/dev/null || true) | wc -l | tr -d ' ')
SEQ=$(printf "%04d" "$SEQ")
EVENT_FILE="$EVENTS_DIR/${SEQ}_${EVENT_TYPE//\./_}.yaml"

# イベントYAML書き出し
cat > "$EVENT_FILE" <<YAML
event_type: $EVENT_TYPE
timestamp: $(date "+%Y-%m-%dT%H:%M:%S")
cmd_dir: $CMD_DIR
payload:
YAML
# payloadを追記（インデント）
echo "$PAYLOAD" | sed 's/^/  /' >> "$EVENT_FILE"

echo "[emit_event] $EVENT_TYPE → $EVENT_FILE"

# component_loader.sh dispatch
bash "$TANEBI_ROOT/scripts/component_loader.sh" dispatch "$EVENT_TYPE" "$EVENT_FILE"
