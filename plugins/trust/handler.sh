#!/usr/bin/env bash
# plugins/trust/handler.sh
# Interface: handler.sh on_init | on_event <event_type> <event_file> | on_destroy

set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../../scripts/tanebi_config.sh"

PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cmd="${1:-on_init}"

case "$cmd" in
  on_init)
    echo "[trust] Plugin initialized"
    ;;
  on_event)
    EVENT_TYPE="${2:-}"
    EVENT_FILE="${3:-}"
    # イベントファイルからpayloadを読む
    case "$EVENT_TYPE" in
      trust.check)
        # Personaの信頼スコアチェック（既存ロジックを移植）
        # on_task_assign 相当
        PERSONA_ID=$(python3 -c "
import yaml
with open('$EVENT_FILE') as f:
    e = yaml.safe_load(f)
print(e.get('payload', {}).get('persona_id', ''))
" 2>/dev/null || echo "")
        RISK=$(python3 -c "
import yaml
with open('$EVENT_FILE') as f:
    e = yaml.safe_load(f)
print(e.get('payload', {}).get('risk', 'normal'))
" 2>/dev/null || echo "normal")
        if [ -n "$PERSONA_ID" ]; then
          PERSONA_FILE="$TANEBI_PERSONA_DIR/${PERSONA_ID}.yaml"
          if [ -f "$PERSONA_FILE" ]; then
            SCORE=$(python3 -c "
import yaml
with open('$PERSONA_FILE') as f:
    p = yaml.safe_load(f)
print(p.get('performance', {}).get('trust_score', 50))
" 2>/dev/null || echo 50)
            if [ "$RISK" = "high" ] && [ "$SCORE" -lt 30 ] 2>/dev/null; then
              echo "[trust] DENIED: $PERSONA_ID score=$SCORE risk=$RISK"
              exit 1
            fi
            echo "[trust] ALLOWED: $PERSONA_ID score=$SCORE risk=$RISK"
          fi
        fi
        ;;
      worker.completed|evolution.completed)
        # on_task_complete 相当
        PERSONA_ID=$(python3 -c "
import yaml
with open('$EVENT_FILE') as f:
    e = yaml.safe_load(f)
print(e.get('payload', {}).get('persona_id', ''))
" 2>/dev/null || echo "")
        OUTCOME=$(python3 -c "
import yaml
with open('$EVENT_FILE') as f:
    e = yaml.safe_load(f)
print(e.get('payload', {}).get('outcome', 'success'))
" 2>/dev/null || echo "success")
        QUALITY=$(python3 -c "
import yaml
with open('$EVENT_FILE') as f:
    e = yaml.safe_load(f)
print(e.get('payload', {}).get('quality', 'GREEN'))
" 2>/dev/null || echo "GREEN")
        if [ -n "$PERSONA_ID" ]; then
          PERSONA_FILE="$TANEBI_PERSONA_DIR/${PERSONA_ID}.yaml"
          if [ -f "$PERSONA_FILE" ]; then
            # スコア更新
            if [ "$OUTCOME" = "success" ]; then
              case "$QUALITY" in
                GREEN) DELTA=5 ;;
                YELLOW) DELTA=2 ;;
                *) DELTA=0 ;;
              esac
            else
              DELTA=-10
            fi
            python3 -c "
import yaml
with open('$PERSONA_FILE') as f:
    p = yaml.safe_load(f)
perf = p.setdefault('performance', {})
score = perf.get('trust_score', 50) + $DELTA
score = max(0, min(100, score))
perf['trust_score'] = score
with open('$PERSONA_FILE', 'w') as f:
    yaml.dump(p, f, allow_unicode=True)
print('[trust] Updated trust_score to', score)
" 2>/dev/null
          fi
        fi
        ;;
    esac
    ;;
  on_destroy)
    echo "[trust] Plugin destroyed"
    ;;
esac
