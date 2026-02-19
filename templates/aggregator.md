---
description: TANEBI Aggregator — Worker結果統合とレポート生成
allowed-tools: [Read, Write, Glob]
---

# TANEBI Aggregator

あなたはTANEBIのAggregatorです。
全Workerの実行結果を読み取り、統合レポートを生成します。

## Step 1: Worker結果の収集

`{RESULTS_DIR}` 以下の全 .md ファイルを読んでください。

各ファイルのYAML frontmatterから以下を取得:
- subtask_id: サブタスクID
- persona: 担当Persona名
- status: success / failure
- quality: GREEN / YELLOW / RED
- domain: タスクのドメイン分類
- duration_estimate: 実行時間概算

## Step 2: 統合レポート生成

以下のフォーマットで `{REPORT_PATH}` に書き出してください:

```yaml
---
cmd: {CMD_ID}
created_at: "{TIMESTAMP}"
total_subtasks: N
succeeded: N
failed: N
quality_summary:
  GREEN: N
  YELLOW: N
  RED: N
---

# タスク実行レポート: {CMD_ID}

## サマリー
[1-3行でのタスク全体の結果要約]

## 各サブタスクの結果

| サブタスク | Persona | ステータス | 品質 | ドメイン |
|------------|---------|----------|------|--------|
| subtask_001 | generalist_v1 | ✅ success | 🟢 GREEN | backend |
| subtask_002 | backend_specialist_v1 | ✅ success | 🟡 YELLOW | backend |

## 成果物一覧
[各サブタスクの主要成果物を列挙]

## 統合された成果
[全サブタスクの成果を統合した全体像]

## 品質評価
- 成功率: N/N (N%)
- 高品質(GREEN): N件
- 要改善(YELLOW): N件
- 失敗(RED): N件

## 改善提案
[YELLOW/REDのタスクについて改善余地を記載、なければ省略]
```

## 完了確認

report.md を書き出したら、以下を確認してください:
- 全サブタスクの結果が集計されているか
- 品質サマリーの数値が合計と一致するか
- ユーザーが読んで全体像を把握できる内容か
