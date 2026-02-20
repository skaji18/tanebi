#!/usr/bin/env bash
# TANEBI Template Expander
# Usage: expand_template.sh <template_file> [key=value ...]
# Example: expand_template.sh templates/worker_base.md \
#   PERSONA_NAME="万能の開拓者" \
#   PERSONA_ID="generalist_v1" \
#   TASK_DESCRIPTION="APIを設計してください" \
#   CMD_ID="cmd_001"

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../../scripts/tanebi_config.sh"

# --- Helper Functions ---

# Persona YAMLから主要フィールドを抽出する（インデント深さ不問）
# Usage: extract_persona_field <yaml_file> <field_name>
# Example: extract_persona_field personas/active/generalist_v1.yaml name
extract_persona_field() {
  local yaml_file="$1"
  local field="$2"
  grep "^[[:space:]]*${field}:" "$yaml_file" | head -1 | sed 's/.*: *//' | tr -d '"'"'"
}

# sedのreplacement文字列用に特殊文字をエスケープする
_escape_sed_replacement() {
  printf '%s' "$1" | sed -e 's/[&\|]/\\&/g'
}

# --- Main ---

if [ $# -lt 1 ]; then
  echo "Usage: expand_template.sh <template_file> [key=value ...]" >&2
  exit 1
fi

TEMPLATE_FILE="$1"
shift

if [ ! -f "$TEMPLATE_FILE" ]; then
  echo "Error: Template file not found: $TEMPLATE_FILE" >&2
  exit 1
fi

content=$(cat "$TEMPLATE_FILE")

# 引数から key=value を展開
for arg in "$@"; do
  key="${arg%%=*}"
  val="${arg#*=}"
  escaped_val=$(_escape_sed_replacement "$val")
  # sed で {KEY} を val に置換（| を区切り文字に使用）
  content=$(echo "$content" | sed "s|{${key}}|${escaped_val}|g")
done

echo "$content"
