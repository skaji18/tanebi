#!/usr/bin/env bash
# Usage:
#   bash scripts/component_loader.sh init
#   bash scripts/component_loader.sh dispatch <event_type> <event_file>
#   bash scripts/component_loader.sh destroy

set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/tanebi_config.sh"

PLUGINS_DIR="$TANEBI_ROOT/plugins"
CONFIG_FILE="$TANEBI_ROOT/config.yaml"

# config.yaml から plugins 有効/無効を読む
is_plugin_enabled() {
  local plugin_name="$1"
  python3 - "$CONFIG_FILE" "$plugin_name" <<'PYEOF'
import yaml, sys
config_file = sys.argv[1]
plugin_name = sys.argv[2]
with open(config_file) as f:
    c = yaml.safe_load(f)
plugins = c.get('tanebi', {}).get('plugins', {})
plugin = plugins.get(plugin_name, {})
print('true' if plugin.get('enabled', True) else 'false')
PYEOF
}

# plugin.yaml の lifecycle から関数名を読む（plugin: ラッパーあり/なし両対応）
# 戻り値: 関数名文字列（未定義時は hook 名をフォールバック）
get_lifecycle_func() {
  local plugin_yaml="$1"
  local hook="$2"
  python3 - "$plugin_yaml" "$hook" <<'PYEOF'
import yaml, sys
plugin_yaml = sys.argv[1]
hook = sys.argv[2]
with open(plugin_yaml) as f:
    p = yaml.safe_load(f)
plugin_node = p.get('plugin', p)  # plugin: ラッパーあり/なし両対応
lifecycle = plugin_node.get('lifecycle', {})
if isinstance(lifecycle, dict):
    val = lifecycle.get(hook)
    if val and isinstance(val, str):
        print(val)
        sys.exit()
print(hook)  # フォールバック: hook 名をそのまま使用
PYEOF
}

# plugin.yaml の subscribes_to から event_type に対応するハンドラー関数名を返す
# 購読していない場合は空文字を返す（plugin: ラッパーあり/なし両対応）
get_event_handler() {
  local plugin_yaml="$1"
  local event_type="$2"
  python3 - "$plugin_yaml" "$event_type" <<'PYEOF'
import yaml, sys
plugin_yaml = sys.argv[1]
event_type = sys.argv[2]
with open(plugin_yaml) as f:
    p = yaml.safe_load(f)
plugin_node = p.get('plugin', p)  # plugin: ラッパーあり/なし両対応
subs = plugin_node.get('subscribes_to', [])
for s in subs:
    if isinstance(s, str) and s == event_type:
        print('on_event'); sys.exit()  # フラット文字列: フォールバックとして on_event を使用
    elif isinstance(s, dict) and s.get('event_type') == event_type:
        print(s.get('handler', 'on_event')); sys.exit()
# 購読なし: 空文字出力
PYEOF
}

cmd="${1:-help}"

case "$cmd" in
  init)
    echo "[component_loader] Initializing plugins..."
    for plugin_dir in "$PLUGINS_DIR"/*/; do
      [ -d "$plugin_dir" ] || continue
      plugin_name=$(basename "$plugin_dir")
      [[ "$plugin_name" == _* ]] && continue  # _template など skip
      plugin_yaml="$plugin_dir/plugin.yaml"
      handler="$plugin_dir/handler.sh"
      [ -f "$plugin_yaml" ] && [ -f "$handler" ] || continue
      enabled=$(is_plugin_enabled "$plugin_name" 2>/dev/null || echo "true")
      if [ "$enabled" = "true" ]; then
        init_func=$(get_lifecycle_func "$plugin_yaml" "on_init" 2>/dev/null || echo "on_init")
        bash "$handler" "$init_func" && echo "[component_loader] $plugin_name: initialized"
      else
        echo "[component_loader] $plugin_name: disabled, skip"
      fi
    done
    ;;
  dispatch)
    EVENT_TYPE="${2:?event_type required}"
    EVENT_FILE="${3:?event_file required}"
    for plugin_dir in "$PLUGINS_DIR"/*/; do
      [ -d "$plugin_dir" ] || continue
      plugin_name=$(basename "$plugin_dir")
      [[ "$plugin_name" == _* ]] && continue
      plugin_yaml="$plugin_dir/plugin.yaml"
      handler="$plugin_dir/handler.sh"
      [ -f "$plugin_yaml" ] && [ -f "$handler" ] || continue
      enabled=$(is_plugin_enabled "$plugin_name" 2>/dev/null || echo "true")
      [ "$enabled" = "true" ] || continue
      handler_func=$(get_event_handler "$plugin_yaml" "$EVENT_TYPE" 2>/dev/null || echo "")
      if [ -n "$handler_func" ]; then
        bash "$handler" "$handler_func" "$EVENT_TYPE" "$EVENT_FILE"
      fi
    done
    ;;
  destroy)
    for plugin_dir in "$PLUGINS_DIR"/*/; do
      [ -d "$plugin_dir" ] || continue
      plugin_name=$(basename "$plugin_dir")
      [[ "$plugin_name" == _* ]] && continue
      plugin_yaml="$plugin_dir/plugin.yaml"
      handler="$plugin_dir/handler.sh"
      [ -f "$handler" ] || continue
      destroy_func="on_destroy"
      if [ -f "$plugin_yaml" ]; then
        destroy_func=$(get_lifecycle_func "$plugin_yaml" "on_destroy" 2>/dev/null || echo "on_destroy")
      fi
      bash "$handler" "$destroy_func" 2>/dev/null || true
    done
    ;;
  *)
    echo "Usage: component_loader.sh init|dispatch <event_type> <event_file>|destroy"
    exit 1
    ;;
esac
