#!/usr/bin/env bash
# plugins/_template/handler.sh
# カスタムプラグインのテンプレート
# Interface: handler.sh on_init | on_event <event_type> <event_file> | on_destroy

set -euo pipefail

PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$PLUGIN_DIR/../../scripts/tanebi_config.sh"

cmd="${1:-on_init}"
EVENT_TYPE="${2:-}"
EVENT_FILE="${3:-}"

case "$cmd" in
  on_init)
    echo "[my_plugin] initialized"
    ;;
  on_event)
    echo "[my_plugin] received event: $EVENT_TYPE"
    # イベントファイルを読む例:
    # python3 -c "import yaml; e=yaml.safe_load(open('$EVENT_FILE')); print(e)"
    ;;
  on_destroy)
    echo "[my_plugin] destroyed"
    ;;
esac
