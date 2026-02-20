# subprocess Adapter

## 概要
`claude -p` をサブプロセスとして起動してワーカーを実行するアダプター。

## claude-native との違い
| 観点 | claude-native | subprocess |
|------|--------------|------------|
| オーケストレーター | CLAUDE.md | orchestrator.sh |
| ワーカー起動 | Task tool | `claude -p` |
| 並列性 | Task tool制限内 | OSプロセスレベル |
| コンテキスト | 親セッションに蓄積 | 各ワーカー完全分離 |

## 使い方
```bash
# config.yaml で adapter_set を変更
# adapter_set: subprocess

# タスクを実行
bash scripts/tanebi "タスクの説明"
# または
bash adapters/subprocess/orchestrator.sh "タスクの説明"
```

## ファイル構成
- orchestrator.sh: メインオーケストレーター（5ステップ実行）
- run_worker.sh: claude -p ラッパー
- expand_template.sh: テンプレート展開
- parse_plan.sh: plan.md パーサー

## 制限事項
- claude CLIが必要（`claude --version` で確認）
- 非対話的実行のため、ワーカーの対話的な権限承認不可
- `--permission-mode acceptEdits` を使用
