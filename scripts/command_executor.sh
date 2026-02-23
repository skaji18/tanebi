#!/usr/bin/env bash
# command_executor.sh — Executor reference implementation (subprocess mode)
# Reads *.requested events from Event Store, processes them, writes *.completed events
# config.yaml tanebi.execution からコマンドを読み取り、プレースホルダー置換後にshell exec
#
# Usage:
#   bash scripts/command_executor.sh [--dry-run] <port_name> [key=value ...]
#
# 例:
#   bash scripts/command_executor.sh event_emit \
#     event_type=task.created payload="{cmd_id: cmd_001}" work_dir=work cmd_id=cmd_001
#
#   bash scripts/command_executor.sh --dry-run worker_launch.execute \
#     subtask_file=work/cmd_001/subtask_001.md persona_file=personas/active/dev.yaml
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/tanebi_config.sh"

DRY_RUN=false
if [ "${1:-}" = "--dry-run" ]; then
  DRY_RUN=true
  shift
fi

PORT_NAME="${1:?usage: command_executor.sh [--dry-run] <port_name> [key=value ...]}"
shift

# ━━━ config.yaml からポートのコマンドを読み取り（python3+PyYAML）━━━
read_port_config() {
  local port_path="$1"
  local field="${2:-command}"
  python3 -c "
import yaml, sys
with open('${TANEBI_ROOT}/config.yaml') as f:
    cfg = yaml.safe_load(f)
execution = cfg.get('tanebi', {}).get('execution', {})
keys = '${port_path}'.split('.')
node = execution
for k in keys:
    if not isinstance(node, dict) or k not in node:
        sys.exit(1)
    node = node[k]
val = node.get('${field}', '') if isinstance(node, dict) else ''
if val is None:
    val = ''
print(val)
" 2>/dev/null
}

# ━━━ コマンド読み取り ━━━
CMD_TEMPLATE=$(read_port_config "$PORT_NAME" "command" 2>/dev/null || true)
if [ -z "${CMD_TEMPLATE:-}" ]; then
  echo "[command_executor] ERROR: No command configured for port: $PORT_NAME" >&2
  echo "[command_executor] Check config.yaml tanebi.execution.$PORT_NAME.command" >&2
  exit 1
fi

TIMEOUT_SEC=$(read_port_config "$PORT_NAME" "timeout" 2>/dev/null || echo "120")
TIMEOUT_SEC="${TIMEOUT_SEC:-120}"

# ━━━ builtin: プレフィックス検出 ━━━
if [[ "$CMD_TEMPLATE" == builtin:* ]]; then
  BUILTIN_NAME="${CMD_TEMPLATE#builtin:}"
  echo "[command_executor] ERROR: builtin:${BUILTIN_NAME} はshellから直接実行できません。" >&2
  echo "[command_executor] claude-nativeオーケストレーター（CLAUDE.md）から呼び出してください。" >&2
  echo "[command_executor] ヒント: subprocess用config.yaml では全ポートにshellコマンドを設定してください。" >&2
  exit 2  # exit 2 = builtin requires orchestrator (distinct from general errors)
fi

# ━━━ プレースホルダー置換 ━━━
CMD="$CMD_TEMPLATE"
for arg in "$@"; do
  key="${arg%%=*}"
  value="${arg#*=}"
  # 値をシングルクォートでエスケープ（シェルインジェクション対策）
  escaped_value=$(printf '%s' "$value" | sed "s/'/'\\\\''/g")
  CMD="${CMD//\{${key}\}/${escaped_value}}"
done

# 未解決プレースホルダー検出
if echo "$CMD" | grep -qE '\{[a-z_]+\}'; then
  UNRESOLVED=$(echo "$CMD" | grep -oE '\{[a-z_]+\}' | sort -u | tr '\n' ', ')
  echo "[command_executor] ERROR: Unresolved placeholders: $UNRESOLVED" >&2
  echo "[command_executor] Command: $CMD" >&2
  exit 1
fi

# ━━━ 実行（dry-run or 本番）━━━
if [ "$DRY_RUN" = true ]; then
  echo "[command_executor] Dry run:"
  echo "  Port:    $PORT_NAME"
  echo "  Command: $CMD"
  echo "  Timeout: ${TIMEOUT_SEC}s"
  exit 0
fi

timeout "$TIMEOUT_SEC" bash -c "unset CLAUDECODE CLAUDE_CODE_ENTRYPOINT; $CMD"
