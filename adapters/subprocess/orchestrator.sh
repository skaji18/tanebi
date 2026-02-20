#!/usr/bin/env bash
# TANEBI Subprocess Orchestrator
# Usage:
#   bash adapters/subprocess/orchestrator.sh "タスクの説明"
#   bash adapters/subprocess/orchestrator.sh --request work/cmd_NNN/request.md
#
# 5ステップ: REQUEST → DECOMPOSE → EXECUTE → AGGREGATE → EVOLVE

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../../scripts/tanebi_config.sh"

# 引数解析
REQUEST=""
CMD_DIR=""
if [ "${1:-}" = "--request" ]; then
  REQUEST_FILE="${2:?--request requires a file path}"
  REQUEST=$(cat "$REQUEST_FILE")
  CMD_DIR="$(cd "$(dirname "$REQUEST_FILE")" && pwd)"
else
  REQUEST="${1:?usage: orchestrator.sh <request_text> or --request <file>}"
fi

# Step 1: REQUEST — ワークディレクトリ作成
if [ -z "$CMD_DIR" ]; then
  CMD_DIR=$(bash "$TANEBI_ROOT/scripts/new_cmd.sh")
  # request.md に依頼内容を書き込み
  cat > "$CMD_DIR/request.md" <<EOF
# Request: $(basename "$CMD_DIR")

## Task Description
$REQUEST
EOF
fi
CMD_ID=$(basename "$CMD_DIR")
echo "[orchestrator] CMD_ID: $CMD_ID"
echo "[orchestrator] CMD_DIR: $CMD_DIR"

# Step 2: DECOMPOSE — Decomposerテンプレートを展開して claude -p に渡す
DECOMPOSE_PROMPT="$CMD_DIR/decompose_prompt.md"
PERSONA_LIST=$(ls "$TANEBI_PERSONA_DIR"/*.yaml 2>/dev/null | xargs -I{} basename {} .yaml | tr '\n' ', ' | sed 's/,$//')
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

bash "$SCRIPT_DIR/expand_template.sh" \
  "$TANEBI_ROOT/templates/decomposer.md" \
  "REQUEST_PATH=$CMD_DIR/request.md" \
  "PLAN_PATH=$CMD_DIR/plan.md" \
  "CMD_ID=$CMD_ID" \
  "PERSONA_LIST=$PERSONA_LIST" \
  "TIMESTAMP=$TIMESTAMP" \
  > "$DECOMPOSE_PROMPT"

# リクエスト本文を追記（decomposerが直接参照できるように）
cat >> "$DECOMPOSE_PROMPT" <<REQEOF

## Request

$REQUEST
REQEOF

PLAN_MD="$CMD_DIR/plan.md"
echo "[orchestrator] Step 2: Decomposing..."
bash "$SCRIPT_DIR/run_worker.sh" "$DECOMPOSE_PROMPT" "${CMD_DIR}/decompose_output.md" sonnet "Read,Write,Glob"

# plan.md が Write ツールで書き出された場合はそれを使用、なければ stdout 出力をコピー
if [ ! -f "$PLAN_MD" ] || [ ! -s "$PLAN_MD" ]; then
  if [ -f "${CMD_DIR}/decompose_output.md" ] && [ -s "${CMD_DIR}/decompose_output.md" ]; then
    cp "${CMD_DIR}/decompose_output.md" "$PLAN_MD"
  else
    echo "[orchestrator] ERROR: plan.md was not generated" >&2
    exit 1
  fi
fi
echo "[orchestrator] plan.md generated: $PLAN_MD"

# Step 3: EXECUTE — plan.md をパースしてwave単位で並列実行
echo "[orchestrator] Step 3: Executing workers..."
mkdir -p "$CMD_DIR/results"

WAVES=$(bash "$SCRIPT_DIR/parse_plan.sh" "$PLAN_MD" | awk -F'\t' '{print $3}' | sort -n | uniq)

if [ -z "$WAVES" ]; then
  echo "[orchestrator] WARNING: No subtasks found in plan.md"
fi

for wave in $WAVES; do
  echo "[orchestrator] Wave $wave..."
  pids=()
  subtask_ids=()

  while IFS=$'\t' read -r subtask_id persona wave_num description depends_on; do
    [ "$wave_num" != "$wave" ] && continue

    PERSONA_YAML="$TANEBI_PERSONA_DIR/${persona}.yaml"
    PERSONA_NAME=$(grep "^[[:space:]]*name:" "$PERSONA_YAML" 2>/dev/null | head -1 | sed 's/.*: *//' | tr -d '"'"'" || echo "$persona")

    WORKER_PROMPT="$CMD_DIR/${subtask_id}_prompt.md"
    bash "$SCRIPT_DIR/expand_template.sh" \
      "$TANEBI_ROOT/templates/worker_base.md" \
      "PERSONA_NAME=$PERSONA_NAME" \
      "PERSONA_ID=$persona" \
      "PERSONA_PATH=$PERSONA_YAML" \
      "TASK_DESCRIPTION=$description" \
      "CMD_ID=$CMD_ID" \
      "SUBTASK_ID=$subtask_id" \
      "OUTPUT_PATH=$CMD_DIR/results/${subtask_id}.md" \
      "FEW_SHOT_PATHS=" \
      > "$WORKER_PROMPT"

    OUTPUT="$CMD_DIR/results/${subtask_id}.md"

    # バックグラウンドで並列起動
    bash "$SCRIPT_DIR/run_worker.sh" "$WORKER_PROMPT" "$OUTPUT" sonnet &
    pids+=($!)
    subtask_ids+=("$subtask_id")

  done < <(bash "$SCRIPT_DIR/parse_plan.sh" "$PLAN_MD")

  # 全ワーカーの完了を待つ
  for i in "${!pids[@]}"; do
    wait "${pids[$i]}" && echo "[orchestrator] ${subtask_ids[$i]} done" \
      || echo "[orchestrator] WARNING: ${subtask_ids[$i]} failed (exit $?)"
  done
done

# Step 4: AGGREGATE — Worker結果を統合レポートに
echo "[orchestrator] Step 4: Aggregating..."
AGG_PROMPT="$CMD_DIR/aggregate_prompt.md"

bash "$SCRIPT_DIR/expand_template.sh" \
  "$TANEBI_ROOT/templates/aggregator.md" \
  "RESULTS_DIR=$CMD_DIR/results" \
  "REPORT_PATH=$CMD_DIR/report.md" \
  "CMD_ID=$CMD_ID" \
  "TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")" \
  > "$AGG_PROMPT"

# Worker結果をプロンプトに追記
{
  echo ""
  echo "## Worker Results"
  echo ""
  for f in "$CMD_DIR/results/"*.md; do
    [ -f "$f" ] || continue
    echo ""
    echo "### $(basename "$f")"
    echo ""
    cat "$f"
  done
} >> "$AGG_PROMPT"

REPORT_MD="$CMD_DIR/report.md"
bash "$SCRIPT_DIR/run_worker.sh" "$AGG_PROMPT" "${CMD_DIR}/aggregate_output.md" sonnet "Read,Write,Glob"

# report.md が Write ツールで書き出された場合はそれを使用
if [ ! -f "$REPORT_MD" ] || [ ! -s "$REPORT_MD" ]; then
  if [ -f "${CMD_DIR}/aggregate_output.md" ] && [ -s "${CMD_DIR}/aggregate_output.md" ]; then
    cp "${CMD_DIR}/aggregate_output.md" "$REPORT_MD"
  fi
fi
echo "[orchestrator] report.md generated: $REPORT_MD"

# Step 5: EVOLVE — Persona進化
echo "[orchestrator] Step 5: Evolving..."
bash "$TANEBI_ROOT/scripts/evolve.sh" "$CMD_DIR" || echo "[orchestrator] WARNING: evolve.sh failed (non-fatal)"

echo "[orchestrator] Complete! CMD_ID: $CMD_ID"
echo "[orchestrator] Report: $REPORT_MD"
