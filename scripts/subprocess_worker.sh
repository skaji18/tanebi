#!/usr/bin/env bash
# TANEBI subprocess worker — decompose / execute mode
# command_executor.sh から呼ばれる。CLAUDECODE/CLAUDE_CODE_ENTRYPOINT は unset 済み。
# Usage:
#   subprocess_worker.sh decompose <request_file> <plan_output> <persona_list> <cmd_id>
#   subprocess_worker.sh execute <subtask_file> <output_path> [<persona_file>]
set -euo pipefail

TANEBI_ROOT="${TANEBI_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

MODE="${1:?mode required: decompose|execute}"
shift

case "$MODE" in
  decompose)
    REQUEST_FILE="${1:?request_file required}"
    PLAN_OUTPUT="${2:?plan_output required}"
    PERSONA_LIST="${3:-}"
    CMD_ID="${4:-}"

    mkdir -p "$(dirname "$PLAN_OUTPUT")"

    # templates/decomposer.md をシステムプロンプトとして渡す（CLAUDE.md orchestrator役割を上書き）
    SYSTEM_PROMPT=$(cat "$TANEBI_ROOT/templates/decomposer.md")

    {
      printf '# タスク分解リクエスト\n\n'
      printf 'CMD_ID: %s\n' "$CMD_ID"
      printf '利用可能なPersona一覧: %s\n' "$PERSONA_LIST"
      printf '計画の出力先: %s\n\n' "$PLAN_OUTPUT"
      printf '## リクエスト内容\n\n'
      cat "$REQUEST_FILE"
    } | claude -p \
      --model claude-sonnet-4-6 \
      --output-format text \
      --permission-mode acceptEdits \
      --system-prompt "$SYSTEM_PROMPT" \
      --allowed-tools Read,Write,Glob,Grep,Bash \
      > "$PLAN_OUTPUT"

    # task.decomposed イベント発火
    CMD_DIR_DERIVED=$(dirname "$PLAN_OUTPUT")
    bash "$TANEBI_ROOT/scripts/emit_event.sh" "$CMD_DIR_DERIVED" task.decomposed \
      "{cmd_dir: $CMD_DIR_DERIVED}"
    ;;

  execute)
    SUBTASK_FILE="${1:?subtask_file required}"
    OUTPUT_PATH="${2:?output_path required}"
    PERSONA_FILE="${3:-}"

    mkdir -p "$(dirname "$OUTPUT_PATH")"

    # templates/worker_base.md をシステムプロンプトとして渡す（CLAUDE.md orchestrator役割を上書き）
    SYSTEM_PROMPT=$(cat "$TANEBI_ROOT/templates/worker_base.md")

    {
      if [[ -n "$PERSONA_FILE" ]] && [[ -f "$PERSONA_FILE" ]]; then
        printf '## Persona情報\n\n'
        cat "$PERSONA_FILE"
        printf '\n\n'
      fi
      printf '## サブタスク定義\n\n'
      cat "$SUBTASK_FILE"
      printf '\n\n## 出力先\n\noutput_path: %s\n' "$OUTPUT_PATH"
    } | claude -p \
      --model claude-sonnet-4-6 \
      --output-format text \
      --permission-mode acceptEdits \
      --system-prompt "$SYSTEM_PROMPT" \
      --allowed-tools Read,Write,Glob,Grep,Bash \
      > "$OUTPUT_PATH"

    # worker.completed イベント発火
    CMD_DIR_DERIVED=$(dirname "$(dirname "$OUTPUT_PATH")")
    SUBTASK_ID=$(basename "${OUTPUT_PATH%.md}")
    bash "$TANEBI_ROOT/scripts/emit_event.sh" "$CMD_DIR_DERIVED" worker.completed \
      "$(printf 'status: success\nsubtask_id: %s\n' "$SUBTASK_ID")"
    ;;

  *)
    echo "Unknown mode: $MODE. Use: decompose|execute" >&2
    exit 1
    ;;
esac
