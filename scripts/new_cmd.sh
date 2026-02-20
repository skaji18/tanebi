#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/tanebi_config.sh"

WORK_DIR="$TANEBI_WORK_DIR"
mkdir -p "$WORK_DIR"

# 最大番号を取得
max_num=0
for dir in "$WORK_DIR"/cmd_*/; do
  if [ -d "$dir" ]; then
    num=$(basename "$dir" | sed 's/cmd_//')
    # 数値かどうか確認
    if echo "$num" | grep -qE '^[0-9]+$'; then
      num=$((10#$num))
      if [ "$num" -gt "$max_num" ]; then
        max_num="$num"
      fi
    fi
  fi
done

# 次の番号（ゼロパディング3桁）
next_num=$(printf "%03d" $((max_num + 1)))
cmd_dir="$WORK_DIR/cmd_${next_num}"

# ディレクトリ作成
mkdir -p "${cmd_dir}/results"

# テンプレートファイル作成
cat > "${cmd_dir}/request.md" <<'TMPL'
# Request: cmd_NNN

## Task Description
<!-- ユーザーの依頼内容をここに記載 -->

## Context
<!-- 関連コンテキスト、制約、参考情報 -->

## Acceptance Criteria
<!-- 完了条件 -->
TMPL

cat > "${cmd_dir}/plan.md" <<'TMPL'
# Plan: cmd_NNN

## Subtasks
<!-- Decomposerが生成したサブタスク一覧 -->

| ID | Description | Persona | Status |
|----|-------------|---------|--------|

## Execution Order
<!-- 依存関係と実行順序 -->

## Worker Assignments
<!-- 各Workerへの割り当て詳細 -->
TMPL

cat > "${cmd_dir}/report.md" <<'TMPL'
# Report: cmd_NNN

## Summary
<!-- Aggregatorが生成する統合サマリー -->

## Results
<!-- 各Workerの成果物パス一覧 -->

## Evolution Notes
<!-- 進化エンジンからのフィードバック（Week 2以降） -->
TMPL

# ヘッダーのcmd_NNNを実際の番号に置換
sed -i '' "s/cmd_NNN/cmd_${next_num}/g" "${cmd_dir}/request.md" "${cmd_dir}/plan.md" "${cmd_dir}/report.md"

echo "$cmd_dir"
