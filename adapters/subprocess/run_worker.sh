#!/usr/bin/env bash
# Usage: run_worker.sh <prompt_file> <output_path> [model] [allowed_tools]
# 展開済みプロンプトファイルを受け取り、claude -p で実行して結果をファイルに書き出す

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../../scripts/tanebi_config.sh"

PROMPT_FILE="${1:?prompt_file required}"
OUTPUT_PATH="${2:?output_path required}"
MODEL="${3:-sonnet}"
# ワーカーはファイル読み書きが必要なためEdit/Read/Writeを許可
ALLOWED_TOOLS="${4:-Edit,Read,Write}"

# ログファイル
LOG_PATH="${OUTPUT_PATH%.md}.log"

# ネストセッション検出を回避（サブプロセスワーカーは独立セッション）
unset CLAUDECODE

# claude -p でワーカー起動
# --permission-mode acceptEdits: ファイル編集を自動承認
# --allowed-tools: 必要最小限のツール
claude -p "$(cat "$PROMPT_FILE")" \
  --model "$MODEL" \
  --output-format text \
  --permission-mode acceptEdits \
  --allowed-tools "$ALLOWED_TOOLS" \
  > "$OUTPUT_PATH" 2>"$LOG_PATH"

exit_code=$?

if [ $exit_code -ne 0 ]; then
  echo "[run_worker] ERROR: worker failed (exit $exit_code). See $LOG_PATH" >&2
  exit $exit_code
fi

echo "[run_worker] Done: $OUTPUT_PATH"
