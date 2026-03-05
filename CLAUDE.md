# TANEBI オーケストレーター

TANEBIはマルチエージェント実行フレームワーク。このファイルはLLMオーケストレーター向けの行動指示である。

## ルーティング（CRITICAL — 全リクエストで最初に実行）

リクエストを受けたら、何よりも先に独立サブタスク数を数える。
設計・調査・ドキュメント・テストも1サブタスクとしてカウントする。「実装」だけがサブタスクではない。

- 0-1個 → `[直接応答]`
- 3個以上 → `[TANEBI]` — `tanebi new` でフロー開始
- 2個 → `docs/routing.md` のタイブレーカー参照

作業中に独立サブタスクが3つ以上あると判明した場合:
→ `[エスカレーション: 直接応答 → TANEBI]` で切り替える

ルーティング宣言は必ずユーザーに表示する:
```
[直接応答] 1ファイルの変更のため直接対応します。
[TANEBI] 4つの独立サブタスク（設計/実装/テスト/ドキュメント）が見えるためTANEBIフローで実行します。
```

## Python 実行環境

- python3コマンドの直接実行禁止
- tanebi CLI: `.venv/bin/tanebi <コマンド>`
- Python直接実行が必要な場合: `.venv/bin/python -m tanebi <コマンド>`
- テスト: `.venv/bin/pytest tests/ -v`

## フロー完遂原則（CRITICAL）

TANEBIフローは learn.completed まで必ず実行する。Aggregateで止めることは禁止。
Aggregate完了後、Learner の起動→完了確認→learn.completed 発火まで自動で進めること。
ユーザーに確認を取る必要はない。

## パス受け渡し係原則（CRITICAL）

オーケストレーターはWorkerの出力内容を直接読まない。パス（ポインター）のみを持つ。
理由: Worker出力を全て読むとコンテキストが爆発する。

## TaskOutput 使用禁止（CRITICAL）

全サブエージェント（Decomposer / Worker / Checkpoint / Aggregator / Learner）に対して **TaskOutput tool を使ってはならない**。
完了確認は出力ファイルの存在確認（`ls`）のみで行う。TaskOutput によるブロッキング待機・結果読み取りは禁止。

## セッション開始手順

1. `config.yaml` を読む（`tanebi.execution`, `tanebi.checkpoint` を確認）
2. `claude_native` の値に応じて `docs/native-flow.md` または `docs/listener-flow.md` を読む
3. `knowledge/learned/` の蓄積済みパターン数を表示
4. `work/` のコマンド数を表示
5. 「タスクや質問を入力してください」と案内

## 参照ドキュメント

- アーキテクチャ・Event Store・イベントスキーマ → `docs/design.md`
- ルーティング判定詳細 → `docs/routing.md`
- Executor 実装 → `docs/executor-design.md`
