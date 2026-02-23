#!/usr/bin/env bash
# tanebi_lock.sh — TANEBIリソースロック（セマフォ）
# 同時に1エージェントのみTANEBIを実行可能にする
#
# Usage:
#   bash scripts/tanebi_lock.sh acquire <agent_id>  # exit 0=成功, exit 1=失敗
#   bash scripts/tanebi_lock.sh release <agent_id>  # exit 0=成功
#   bash scripts/tanebi_lock.sh status              # 現在のロック状態を表示
set -euo pipefail

TANEBI_ROOT="${TANEBI_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
LOCK_DIR="${TANEBI_ROOT}/.lock"
LOCK_FILE="${LOCK_DIR}/tanebi.lock"
TIMEOUT_MINUTES=30

mkdir -p "$LOCK_DIR"

ACTION="${1:?usage: tanebi_lock.sh <acquire|release|status> [agent_id]}"
AGENT_ID="${2:-}"

case "$ACTION" in
  acquire)
    [ -z "$AGENT_ID" ] && { echo "[lock] ERROR: agent_id required"; exit 1; }

    # 既存ロックの期限切れチェック
    if [ -f "$LOCK_FILE" ]; then
      LOCK_TIME=$(stat -f %m "$LOCK_FILE" 2>/dev/null || stat -c %Y "$LOCK_FILE" 2>/dev/null)
      NOW=$(date +%s)
      ELAPSED=$(( (NOW - LOCK_TIME) / 60 ))
      if [ "$ELAPSED" -ge "$TIMEOUT_MINUTES" ]; then
        echo "[lock] Stale lock detected (${ELAPSED}min). Removing."
        rm -f "$LOCK_FILE"
      fi
    fi

    # mkdir によるアトミックロック取得
    LOCK_MARKER="${LOCK_DIR}/tanebi.acquiring"
    if mkdir "${LOCK_MARKER}" 2>/dev/null; then
      # クリティカルセクション内で再チェック（スタール検出後の競合回避）
      if [ -f "$LOCK_FILE" ]; then
        HOLDER=$(head -1 "$LOCK_FILE")
        rmdir "${LOCK_MARKER}"
        echo "[lock] FAILED: Lock held by $HOLDER"
        exit 1
      fi
      echo "$AGENT_ID" > "$LOCK_FILE"
      echo "$(date -Iseconds)" >> "$LOCK_FILE"
      rmdir "${LOCK_MARKER}"
      echo "[lock] Acquired by $AGENT_ID"
      exit 0
    else
      # 他エージェントが取得中
      if [ -f "$LOCK_FILE" ]; then
        HOLDER=$(head -1 "$LOCK_FILE")
        echo "[lock] FAILED: Lock held by $HOLDER"
      else
        echo "[lock] FAILED: Lock contention"
      fi
      rmdir "${LOCK_MARKER}" 2>/dev/null || true
      exit 1
    fi
    ;;

  release)
    [ -z "$AGENT_ID" ] && { echo "[lock] ERROR: agent_id required"; exit 1; }

    if [ -f "$LOCK_FILE" ]; then
      HOLDER=$(head -1 "$LOCK_FILE")
      if [ "$HOLDER" = "$AGENT_ID" ]; then
        rm -f "$LOCK_FILE"
        echo "[lock] Released by $AGENT_ID"
        exit 0
      else
        echo "[lock] WARNING: Lock held by $HOLDER, not $AGENT_ID. Not releasing."
        exit 1
      fi
    else
      echo "[lock] No lock to release"
      exit 0
    fi
    ;;

  status)
    if [ -f "$LOCK_FILE" ]; then
      HOLDER=$(head -1 "$LOCK_FILE")
      ACQUIRED=$(tail -1 "$LOCK_FILE")
      echo "[lock] Held by: $HOLDER (since $ACQUIRED)"
    else
      echo "[lock] Available"
    fi
    ;;

  *)
    echo "[lock] Unknown action: $ACTION" >&2
    exit 1
    ;;
esac
