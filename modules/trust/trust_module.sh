#!/usr/bin/env bash
set -euo pipefail

# TANEBI Trust Module — 信頼スコアに基づく段階的権限委譲
# Usage:
#   trust_module.sh on_init <persona_yaml_path>
#   trust_module.sh on_task_assign <persona_id> <task_risk_level>
#   trust_module.sh on_task_complete <persona_id> <status> <quality>

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TANEBI_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PERSONAS_DIR="$TANEBI_ROOT/personas/active"

# --- Helper: read trust_score from persona YAML ---
read_trust_score() {
  local yaml_path="$1"
  local score
  score=$(grep -E '^\s+trust_score:' "$yaml_path" 2>/dev/null | head -1 | sed 's/.*trust_score:\s*//' | tr -d ' "')
  if [ -z "$score" ]; then
    echo ""
  else
    echo "$score"
  fi
}

# --- Hook 1: on_init ---
# Initialize trust_score to 50 if not present
on_init() {
  local persona_path="$1"

  if [ ! -f "$persona_path" ]; then
    echo "[trust] ERROR: Persona file not found: $persona_path" >&2
    exit 1
  fi

  local score
  score=$(read_trust_score "$persona_path")

  if [ -z "$score" ]; then
    # trust_score not found — add it under performance section using python3 for reliable YAML insertion
    python3 -c "
import sys
path = sys.argv[1]
with open(path) as f:
    lines = f.readlines()
new_lines = []
inserted = False
for line in lines:
    new_lines.append(line)
    if not inserted and line.strip().startswith('performance:'):
        new_lines.append('    trust_score: 50\n')
        inserted = True
if not inserted:
    new_lines.append('\n  performance:\n    trust_score: 50\n')
with open(path, 'w') as f:
    f.writelines(new_lines)
" "$persona_path"
    echo "[trust] Initialized trust_score=50 for $(basename "$persona_path")"
  else
    echo "[trust] trust_score already exists ($score) for $(basename "$persona_path")"
  fi
}

# --- Hook 2: on_task_assign ---
# Check if persona is trusted enough for the task risk level
# Exit 0 = allowed, Exit 1 = denied
on_task_assign() {
  local persona_id="$1"
  local risk_level="$2"
  local persona_path="$PERSONAS_DIR/${persona_id}.yaml"

  if [ ! -f "$persona_path" ]; then
    echo "[trust] ERROR: Persona not found: $persona_path" >&2
    exit 1
  fi

  local score
  score=$(read_trust_score "$persona_path")

  if [ -z "$score" ]; then
    echo "[trust] WARNING: trust_score not initialized for $persona_id, treating as 50" >&2
    score=50
  fi

  if [ "$risk_level" = "high" ] && [ "$score" -lt 30 ]; then
    echo "[trust] DENIED: $persona_id (trust_score=$score) cannot accept high-risk task (requires >= 30)" >&2
    exit 1
  fi

  echo "[trust] ALLOWED: $persona_id (trust_score=$score) for $risk_level-risk task"
  exit 0
}

# --- Hook 3: on_task_complete ---
# Update trust_score based on task result
# success + GREEN: +5, success + YELLOW: +2, success + RED: +0, failure: -10
# Bounds: 0-100
on_task_complete() {
  local persona_id="$1"
  local status="$2"
  local quality="$3"
  local persona_path="$PERSONAS_DIR/${persona_id}.yaml"

  if [ ! -f "$persona_path" ]; then
    echo "[trust] ERROR: Persona not found: $persona_path" >&2
    exit 1
  fi

  local score
  score=$(read_trust_score "$persona_path")

  if [ -z "$score" ]; then
    echo "[trust] WARNING: trust_score not initialized for $persona_id, initializing to 50" >&2
    score=50
  fi

  local delta=0
  if [ "$status" = "failure" ]; then
    delta=-10
  elif [ "$status" = "success" ]; then
    case "$quality" in
      GREEN)  delta=5 ;;
      YELLOW) delta=2 ;;
      RED)    delta=0 ;;
      *)      delta=0 ;;
    esac
  fi

  local new_score=$(( score + delta ))
  # Clamp to 0-100
  if [ "$new_score" -gt 100 ]; then new_score=100; fi
  if [ "$new_score" -lt 0 ]; then new_score=0; fi

  # Update in persona YAML
  if grep -q 'trust_score:' "$persona_path"; then
    sed -i '' "s/trust_score:.*/trust_score: $new_score/" "$persona_path"
  else
    # trust_score not present — add it using python3
    python3 -c "
import sys
path, val = sys.argv[1], sys.argv[2]
with open(path) as f:
    lines = f.readlines()
new_lines = []
inserted = False
for line in lines:
    new_lines.append(line)
    if not inserted and line.strip().startswith('performance:'):
        new_lines.append(f'    trust_score: {val}\n')
        inserted = True
if not inserted:
    new_lines.append(f'\n  performance:\n    trust_score: {val}\n')
with open(path, 'w') as f:
    f.writelines(new_lines)
" "$persona_path" "$new_score"
  fi

  echo "[trust] Updated $persona_id: trust_score $score -> $new_score (delta=$delta, status=$status, quality=$quality)"
}

# --- Main dispatcher ---
if [ $# -lt 1 ]; then
  echo "Usage: trust_module.sh <hook> [args...]" >&2
  echo "  on_init <persona_yaml_path>" >&2
  echo "  on_task_assign <persona_id> <task_risk_level>" >&2
  echo "  on_task_complete <persona_id> <status> <quality>" >&2
  exit 1
fi

HOOK="$1"
shift

case "$HOOK" in
  on_init)
    [ $# -lt 1 ] && { echo "Usage: trust_module.sh on_init <persona_yaml_path>" >&2; exit 1; }
    on_init "$1"
    ;;
  on_task_assign)
    [ $# -lt 2 ] && { echo "Usage: trust_module.sh on_task_assign <persona_id> <task_risk_level>" >&2; exit 1; }
    on_task_assign "$1" "$2"
    ;;
  on_task_complete)
    [ $# -lt 3 ] && { echo "Usage: trust_module.sh on_task_complete <persona_id> <status> <quality>" >&2; exit 1; }
    on_task_complete "$1" "$2" "$3"
    ;;
  *)
    echo "[trust] Unknown hook: $HOOK" >&2
    exit 1
    ;;
esac
