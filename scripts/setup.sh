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

# === Python venv セットアップ (cmd_032) ===
echo "Python仮想環境をセットアップ中..."

# venv が存在するかチェック（冪等）
if [ -d "${TANEBI_ROOT}/.venv" ]; then
    echo "  .venv/ は既に存在します。スキップ。"
else
    echo "  .venv/ を作成します..."
    python3 -m venv "${TANEBI_ROOT}/.venv"
    echo "  .venv/ 作成完了。"
fi

# requirements.txt のインストール（差分インストール・冪等）
if [ -f "${TANEBI_ROOT}/requirements.txt" ]; then
    echo "  requirements.txt をインストール..."
    "${TANEBI_ROOT}/.venv/bin/pip" install -q -r "${TANEBI_ROOT}/requirements.txt"
    echo "  パッケージインストール完了。"
fi

echo "Python venv セットアップ完了。"
echo "  使用方法: source ${TANEBI_ROOT}/.venv/bin/activate"
echo "  または: ${TANEBI_ROOT}/.venv/bin/python3 script.py"

echo "[setup] Done. $copied persona(s) initialized."
