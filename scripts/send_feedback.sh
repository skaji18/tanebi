#!/usr/bin/env bash
# Usage: bash scripts/send_feedback.sh <cmd_dir> <command> '<payload_yaml>'

set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/tanebi_config.sh"

CMD_DIR="${1:?usage: send_feedback.sh <cmd_dir> <command> '<payload>'}"
FEEDBACK_CMD="${2:?command required}"
PAYLOAD="${3:-{}}"

FEEDBACK_DIR="$CMD_DIR/feedback"
mkdir -p "$FEEDBACK_DIR"

SEQ=$(ls "$FEEDBACK_DIR"/*.yaml 2>/dev/null | wc -l | tr -d ' ')
SEQ=$(printf "%04d" "$SEQ")
FEEDBACK_FILE="$FEEDBACK_DIR/${SEQ}_${FEEDBACK_CMD}.yaml"

cat > "$FEEDBACK_FILE" <<YAML
command: $FEEDBACK_CMD
timestamp: $(date "+%Y-%m-%dT%H:%M:%S")
cmd_dir: $CMD_DIR
payload:
YAML
echo "$PAYLOAD" | sed 's/^/  /' >> "$FEEDBACK_FILE"

echo "[send_feedback] $FEEDBACK_CMD → $FEEDBACK_FILE"
