#!/usr/bin/env bash
# TANEBI パス解決ユーティリティ
# Usage: source scripts/tanebi_config.sh
# 実行後: $TANEBI_ROOT, $TANEBI_PERSONA_DIR 等が使える

# TANEBI_ROOT を解決（bash: BASH_SOURCE, zsh: $0）
if [ -n "${BASH_VERSION:-}" ]; then
  TANEBI_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
else
  TANEBI_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
fi

# config.yaml からキーを読むヘルパー（yaml/外部ツール不要）
_tanebi_cfg() {
  local key="$1"
  local default="${2:-}"
  local val
  val=$(grep "^\s*${key}:" "$TANEBI_ROOT/config.yaml" 2>/dev/null \
        | head -1 | sed 's/.*: *//' | tr -d '"'"'" | tr -d ' ')
  echo "${val:-$default}"
}

export TANEBI_ROOT
export TANEBI_ADAPTER_SET="$(_tanebi_cfg 'adapter_set' 'claude-native')"
export TANEBI_WORK_DIR="$TANEBI_ROOT/$(_tanebi_cfg 'work_dir' 'work')"
export TANEBI_PERSONA_DIR="$TANEBI_ROOT/$(_tanebi_cfg 'persona_dir' 'personas/active')"
export TANEBI_LIBRARY_DIR="$TANEBI_ROOT/$(_tanebi_cfg 'library_dir' 'personas/library')"
export TANEBI_HISTORY_DIR="$TANEBI_ROOT/$(_tanebi_cfg 'history_dir' 'personas/history')"
export TANEBI_KNOWLEDGE_DIR="$TANEBI_ROOT/$(_tanebi_cfg 'knowledge_dir' 'knowledge')"
export TANEBI_FEW_SHOT_DIR="$TANEBI_ROOT/$(_tanebi_cfg 'few_shot_dir' 'knowledge/few_shot_bank')"
export TANEBI_EPISODE_DIR="$TANEBI_ROOT/$(_tanebi_cfg 'episode_dir' 'knowledge/episodes')"
export TANEBI_TEMPLATES_DIR="$TANEBI_ROOT/$(_tanebi_cfg 'templates_dir' 'templates')"
export TANEBI_MODULES_DIR="$TANEBI_ROOT/$(_tanebi_cfg 'modules_dir' 'modules')"
