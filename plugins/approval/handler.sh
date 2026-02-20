#!/usr/bin/env bash
# plugins/approval/handler.sh
# Interface: handler.sh on_init | on_event <event_type> <event_file> | on_destroy

set -euo pipefail

PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$PLUGIN_DIR/../../scripts/tanebi_config.sh"

_read_payload() {
  local file="$1" key="$2"
  python3 -c "
import yaml
with open('$file') as f:
    e = yaml.safe_load(f)
print(e.get('payload', {}).get('$key', ''))
" 2>/dev/null || echo ""
}

_is_plan_review_enabled() {
  python3 -c "
import yaml
with open('$TANEBI_ROOT/config.yaml') as f:
    c = yaml.safe_load(f)
plugins = c.get('plugins', {})
approval = plugins.get('approval', {})
print('true' if approval.get('plan_review', True) else 'false')
" 2>/dev/null || echo "true"
}

cmd="${1:-on_init}"

case "$cmd" in
  on_init)
    echo "[approval] Approval gate initialized"
    ;;
  on_event)
    EVENT_TYPE="${2:-}"
    EVENT_FILE="${3:-}"
    case "$EVENT_TYPE" in
      task.decomposed)
        PLAN_REVIEW=$(_is_plan_review_enabled)
        if [ "$PLAN_REVIEW" = "false" ]; then
          echo "[approval] plan_review=false, auto-approving"
          exit 0
        fi
        CMD_DIR=$(_read_payload "$EVENT_FILE" cmd_dir 2>/dev/null || python3 -c "
import yaml
with open('$EVENT_FILE') as f:
    e = yaml.safe_load(f)
print(e.get('cmd_dir', ''))
" 2>/dev/null)
        PLAN_PATH=$(_read_payload "$EVENT_FILE" plan_path)
        echo ""
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "  [TANEBI Approval Gate] 計画を確認してください"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        if [ -f "$PLAN_PATH" ]; then
          cat "$PLAN_PATH"
        fi
        echo ""
        echo "承認する場合は続行してください。"
        echo "却下/修正の場合は Ctrl+C で中断し、send_feedback.sh を使用:"
        echo "  bash scripts/send_feedback.sh <cmd_dir> reject_plan '{}'"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        # feedback/ ディレクトリに approve_plan を自動書き出し（デフォルト承認）
        # 実際のHitL実装では read -p "承認しますか？[y/N]" で待機する
        # Phase 1では表示のみ（自動承認）
        ;;
      approval.requested)
        CMD_ID=$(_read_payload "$EVENT_FILE" cmd_id)
        REASON=$(_read_payload "$EVENT_FILE" reason)
        echo "[approval] ⚠️  Approval requested for $CMD_ID: $REASON"
        echo "[approval] Use: bash scripts/send_feedback.sh <cmd_dir> approve_wave '{}'"
        ;;
    esac
    ;;
  on_destroy)
    echo "[approval] Approval gate stopped"
    ;;
esac
