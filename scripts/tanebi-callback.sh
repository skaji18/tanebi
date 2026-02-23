#!/usr/bin/env bash
# tanebi-callback.sh — TANEBIへの完了通知（固定API）
# Workerはこのスクリプトを叩くだけ。環境を問わず同じ呼び出し方。
#
# Usage:
#   bash scripts/tanebi-callback.sh <event_type> [key=value ...]
#
# 例:
#   bash scripts/tanebi-callback.sh worker.completed \
#     cmd_id=cmd_042 subtask_id=subtask_001 status=success
#   bash scripts/tanebi-callback.sh worker.progress \
#     cmd_id=cmd_042 progress=50
set -euo pipefail

CALLBACK_TYPE="${1:?usage: tanebi-callback.sh <event_type> [key=value ...]}"
shift

TANEBI_ROOT="${TANEBI_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
source "${TANEBI_ROOT}/scripts/tanebi_config.sh"

# key=value引数からcmd_idを抽出してcmd_dirを決定
CMD_ID=""
PAYLOAD_PARTS=()
for arg in "$@"; do
  key="${arg%%=*}"
  value="${arg#*=}"
  if [ "$key" = "cmd_id" ]; then
    CMD_ID="$value"
  fi
  PAYLOAD_PARTS+=("${key}: ${value}")
done

if [ -z "$CMD_ID" ]; then
  echo "[tanebi-callback] ERROR: cmd_id is required" >&2
  exit 1
fi

CMD_DIR="${TANEBI_WORK_DIR}/${CMD_ID}"

# payloadをYAML形式に変換
PAYLOAD="{"
first=true
for part in "${PAYLOAD_PARTS[@]}"; do
  if [ "$first" = true ]; then
    PAYLOAD+="$part"
    first=false
  else
    PAYLOAD+=", $part"
  fi
done
PAYLOAD+="}"

# emit_event.sh を呼び出し
bash "${TANEBI_ROOT}/scripts/emit_event.sh" "$CMD_DIR" "$CALLBACK_TYPE" "$PAYLOAD"
