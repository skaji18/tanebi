#!/usr/bin/env bash
# TANEBI セットアップスクリプト
# 使い方: bash scripts/setup.sh
# clone後に1回実行すれば環境構築完了。
# 冪等: 2回以上実行しても安全。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TANEBI_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# === 1. Python バージョン確認 ===
echo "[setup] Checking Python version..."
python_bin="$(command -v python3 || true)"
if [ -z "$python_bin" ]; then
    echo "[setup] ERROR: python3 not found. Install Python 3.10+." >&2
    exit 1
fi

python_version="$("$python_bin" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
python_major="$("$python_bin" -c 'import sys; print(sys.version_info.major)')"
python_minor="$("$python_bin" -c 'import sys; print(sys.version_info.minor)')"

if [ "$python_major" -lt 3 ] || { [ "$python_major" -eq 3 ] && [ "$python_minor" -lt 10 ]; }; then
    echo "[setup] ERROR: Python 3.10+ required. Found: $python_version" >&2
    exit 1
fi
echo "[setup] Python $python_version OK"

# === 2. venv 作成（既存なら再利用） ===
VENV_DIR="$TANEBI_ROOT/.venv"
if [ -d "$VENV_DIR" ]; then
    echo "[setup] .venv/ already exists. Reusing."
else
    echo "[setup] Creating .venv/ ..."
    "$python_bin" -m venv "$VENV_DIR"
    echo "[setup] .venv/ created."
fi

PIP="$VENV_DIR/bin/pip"
TANEBI_BIN="$VENV_DIR/bin/tanebi"

# === 3. pip upgrade ===
echo "[setup] Upgrading pip..."
"$PIP" install --upgrade pip -q
echo "[setup] pip upgraded."

# === 4. パッケージインストール ===
echo "[setup] Installing tanebi[dev]..."
"$PIP" install -e "$TANEBI_ROOT[dev]" -q
echo "[setup] Package installed."

# === 5. Seed Persona 初期化 ===
TEMPLATES_DIR="$TANEBI_ROOT/personas/library/templates"
ACTIVE_DIR="$TANEBI_ROOT/personas/active"

mkdir -p "$ACTIVE_DIR"

copied=0
for seed in "$TEMPLATES_DIR"/*_seed.yaml; do
    [ -f "$seed" ] || continue
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

# === 6. ランタイムディレクトリ確認・作成 ===
echo "[setup] Ensuring runtime directories..."
mkdir -p "$TANEBI_ROOT/work"
mkdir -p "$TANEBI_ROOT/knowledge/episodes"
mkdir -p "$TANEBI_ROOT/knowledge/few_shot_bank"
mkdir -p "$TANEBI_ROOT/personas/history"
echo "[setup] Runtime directories OK."

# === 7. 動作確認 ===
echo "[setup] Verifying tanebi installation..."
"$TANEBI_BIN" --version
echo "[setup] tanebi CLI OK."

echo ""
echo "[setup] Done. $copied persona(s) initialized."
echo "Setup complete! Run 'source .venv/bin/activate' to activate the environment."
