#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TANEBI_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

TEMPLATES_DIR="$TANEBI_ROOT/personas/library/templates"
ACTIVE_DIR="$TANEBI_ROOT/personas/active"

mkdir -p "$ACTIVE_DIR"

# templates/ → active/ にSeed Personaをコピー（既存は上書きしない）
copied=0
for seed in "$TEMPLATES_DIR"/*_seed.yaml; do
  [ -f "$seed" ] || continue
  # seed名からactive名に変換: generalist_seed.yaml → generalist_v1.yaml
  base=$(basename "$seed" _seed.yaml)
  target="$ACTIVE_DIR/${base}_v1.yaml"
  if [ ! -f "$target" ]; then
    cp "$seed" "$target"
    echo "[setup] Created persona: $target"
    copied=$((copied + 1))
  else
    echo "[setup] Already exists: $target (skipped)"
  fi
done

# 必要なランタイムディレクトリを作成
mkdir -p "$TANEBI_ROOT/work"
mkdir -p "$TANEBI_ROOT/knowledge/episodes"
mkdir -p "$TANEBI_ROOT/knowledge/few_shot_bank"
mkdir -p "$TANEBI_ROOT/personas/history"

echo "[setup] Done. $copied persona(s) initialized."
