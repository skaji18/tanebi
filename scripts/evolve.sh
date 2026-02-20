#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/tanebi_config.sh"

if [ $# -lt 1 ]; then
  echo "Usage: $0 work/cmd_NNN" >&2
  exit 1
fi

CMD_DIR="$1"
# 相対パスの場合はTANEBI_ROOTからの相対として解釈
if [[ "$CMD_DIR" != /* ]]; then
  CMD_DIR="$TANEBI_ROOT/$CMD_DIR"
fi

RESULTS_DIR="$CMD_DIR/results"
PERSONAS_DIR="$TANEBI_PERSONA_DIR"
CMD_ID=$(basename "$CMD_DIR")

if [ ! -d "$RESULTS_DIR" ]; then
  echo "[evolve] No results directory: $RESULTS_DIR" >&2
  exit 1
fi

echo "[evolve] Starting evolution for $CMD_ID"

# evolution.started イベント発火
bash "$SCRIPT_DIR/emit_event.sh" "$CMD_DIR" evolution.started \
  "{\"cmd_id\": \"$CMD_ID\"}"

# Python evolution helper を実行し、出力をキャプチャしてイベント発火に使う
EVOLVE_LOG=$(mktemp /tmp/tanebi_evolve_XXXXXX.log)
trap 'rm -f "$EVOLVE_LOG"' EXIT

python3 "$SCRIPT_DIR/_evolve_helper.py" "$RESULTS_DIR" "$PERSONAS_DIR" "$CMD_ID" 2>&1 | tee "$EVOLVE_LOG"

# 出力を解析して per-update イベントを発火
FEW_SHOTS_ADDED=0
PERSONAS_UPDATED_LIST=""

while IFS= read -r line; do
  # Behavior adjustment: "  [evolve] Behavior: {persona_id} {field} {old} -> {new}"
  if [[ "$line" =~ \[evolve\]\ Behavior:\ ([^[:space:]]+)\ ([^[:space:]]+)\ ([^[:space:]]+)\ -\>\ ([^[:space:]]+) ]]; then
    PERSONA_ID="${BASH_REMATCH[1]}"
    FIELD="${BASH_REMATCH[2]}"
    OLD_VAL="${BASH_REMATCH[3]}"
    NEW_VAL="${BASH_REMATCH[4]}"
    PERSONAS_UPDATED_LIST="${PERSONAS_UPDATED_LIST:+$PERSONAS_UPDATED_LIST,}\"$PERSONA_ID\""
    bash "$SCRIPT_DIR/emit_event.sh" "$CMD_DIR" evolution.persona_updated \
      "{\"persona_id\": \"$PERSONA_ID\", \"field\": \"$FIELD\", \"old_value\": \"$OLD_VAL\", \"new_value\": \"$NEW_VAL\", \"reason\": \"behavior_adjustment\"}" || true
  fi

  # Failure correction: "  [evolve] Correction: {persona_id} {domain} proficiency -{delta}"
  if [[ "$line" =~ \[evolve\]\ Correction:\ ([^[:space:]]+)\ ([^[:space:]]+)\ proficiency\ (-[^[:space:]]+) ]]; then
    PERSONA_ID="${BASH_REMATCH[1]}"
    DOMAIN="${BASH_REMATCH[2]}"
    DELTA="${BASH_REMATCH[3]}"
    PERSONAS_UPDATED_LIST="${PERSONAS_UPDATED_LIST:+$PERSONAS_UPDATED_LIST,}\"$PERSONA_ID\""
    bash "$SCRIPT_DIR/emit_event.sh" "$CMD_DIR" evolution.persona_updated \
      "{\"persona_id\": \"$PERSONA_ID\", \"field\": \"${DOMAIN}.proficiency\", \"old_value\": \"?\", \"new_value\": \"?\", \"reason\": \"failure_correction (${DELTA})\"}" || true
  fi

  # Few-shot registration: "  [evolve] Registered few-shot: {domain}/{filename}"
  if [[ "$line" =~ \[evolve\]\ Registered\ few-shot:\ ([^/]+)/(.+) ]]; then
    DOMAIN="${BASH_REMATCH[1]}"
    FILENAME="${BASH_REMATCH[2]%.md}"
    FEW_SHOTS_ADDED=$((FEW_SHOTS_ADDED + 1))
    bash "$SCRIPT_DIR/emit_event.sh" "$CMD_DIR" evolution.few_shot_registered \
      "{\"domain\": \"$DOMAIN\", \"subtask_id\": \"$FILENAME\", \"quality\": \"GREEN\"}" || true
  fi
done < "$EVOLVE_LOG"

# 重複排除したPersonasリストを構築
UNIQUE_PERSONAS_JSON="[]"
if [ -n "$PERSONAS_UPDATED_LIST" ]; then
  UNIQUE_PERSONAS_JSON=$(python3 -c "
import json, sys
items = list(dict.fromkeys(sys.argv[1].split(',')))
items = [i.strip('\"') for i in items]
print(json.dumps(items))
" "$PERSONAS_UPDATED_LIST" 2>/dev/null || echo "[]")
fi

# evolution.completed イベント発火
bash "$SCRIPT_DIR/emit_event.sh" "$CMD_DIR" evolution.completed \
  "{\"cmd_id\": \"$CMD_ID\", \"personas_updated\": $UNIQUE_PERSONAS_JSON, \"few_shots_added\": $FEW_SHOTS_ADDED}"

echo "[evolve] Evolution complete for $CMD_ID"
