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

# subscribes_to に event_type が含まれるかチェック
check_subscription() {
  local plugin_yaml="$1"
  local event_type="$2"
  python3 - "$plugin_yaml" "$event_type" <<'PYEOF'
import yaml, sys
plugin_yaml = sys.argv[1]
event_type = sys.argv[2]
with open(plugin_yaml) as f:
    p = yaml.safe_load(f)
subs = p.get('subscribes_to', [])
for s in subs:
    if isinstance(s, str) and s == event_type:
        print('yes'); sys.exit()
    elif isinstance(s, dict) and s.get('event_type') == event_type:
        print('yes'); sys.exit()
print('no')
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
        bash "$handler" on_init && echo "[component_loader] $plugin_name: initialized"
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
      subscribes=$(check_subscription "$plugin_yaml" "$EVENT_TYPE" 2>/dev/null || echo "no")
      if [ "$subscribes" = "yes" ]; then
        bash "$handler" on_event "$EVENT_TYPE" "$EVENT_FILE"
      fi
    done
    ;;
  destroy)
    for plugin_dir in "$PLUGINS_DIR"/*/; do
      [ -d "$plugin_dir" ] || continue
      plugin_name=$(basename "$plugin_dir")
      [[ "$plugin_name" == _* ]] && continue
      handler="$plugin_dir/handler.sh"
      [ -f "$handler" ] && bash "$handler" on_destroy 2>/dev/null || true
    done
    ;;
  *)
    echo "Usage: component_loader.sh init|dispatch <event_type> <event_file>|destroy"
    exit 1
    ;;
esac
