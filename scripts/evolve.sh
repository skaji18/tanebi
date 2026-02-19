#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TANEBI_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

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
PERSONAS_DIR="$TANEBI_ROOT/personas/active"
CMD_ID=$(basename "$CMD_DIR")

if [ ! -d "$RESULTS_DIR" ]; then
  echo "[evolve] No results directory: $RESULTS_DIR" >&2
  exit 1
fi

echo "[evolve] Starting evolution for $CMD_ID"

# Python で YAML frontmatter を解析して Persona 更新
python3 "$SCRIPT_DIR/_evolve_helper.py" "$RESULTS_DIR" "$PERSONAS_DIR" "$CMD_ID"

echo "[evolve] Evolution complete for $CMD_ID"
