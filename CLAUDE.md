# TANEBI オーケストレーター

## TANEBIとは

**TANEBI（種火）** — 進化するマルチエージェント人格フレームワーク。
エージェントにタスクを重ねるたびに成長・特化する「人格（Persona）」を与え、チーム全体を複利的に賢くする。

claude-native アダプター（MVP）: `git clone → cd tanebi → claude` で起動。tmux不要、追加インフラ不要。

## アーキテクチャ概要

TANEBIは **Core**・**Event Store**・**Executor** の三者に分離される。

```
 TANEBI Core                     Event Store                    Executor
 ┌────────────────────┐     ┌─────────────────────┐     ┌────────────────────┐
 │                    │     │  Immutable Event Log │     │                    │
 │  Evolution Core    │     │                     │     │  *.requested を読み │
 │  Persona Store     │     │  *.requested →→→→→→→│→→→→→│  処理して           │
 │                    │     │                     │     │  *.completed を返す │
 │  ┌──────────────┐  │     │  *.completed ←←←←←←←│←←←←←│                    │
 │  │ flow決定ロジック│  │     │                     │     │  実装技術は自由:    │
 │  │ (次に何をするか│  │     │  タスク管理:         │     │  LLM / shell /     │
 │  │  を判断)      │  │     │    create_task()    │     │  Docker / Lambda / │
 │  └──────────────┘  │     │    list_tasks()     │     │  何でもよい        │
 │                    │     │    get_task_summary()│     │                    │
 │  ※ Core は        │     │                     │     │  ※ Executor は     │
 │    Executor を     │     │  events/            │     │    Core を知らない  │
 │    知らない        │     │    001_task.created  │     │                    │
 │                    │     │    002_decompose     │     │                    │
 │                    │     │      .requested     │     │                    │
 └────────────────────┘     └─────────────────────┘     └────────────────────┘
```

**設計上の重要な境界**:

- **Core と Executor の分離**: Core は `*.requested` イベントを発行し、Executor は `*.completed` イベントを返す。双方が相手の実装を一切知らない
- **Event Store は不変ログ + タスク管理**: イベントは事実として蓄積される。加えてタスクの作成・一覧・サマリー取得を担う
- **Executor は自由実装**: イベントスキーマさえ守れば、実装技術は問わない

## Event Store（`tanebi.event_store` 独立パッケージ・3つの責務）

Event Store は Core と Executor をつなぐ唯一の接点であり、以下の3つの責務を持つ:

1. **Core↔Executor間の通信ハブ**（イベント駆動）
2. **イベントの不変ログ**（記録・再現・分析）
3. **タスクindexの内部管理**（emit時に自動更新）

### メソッド

| メソッド | 説明 | 実装 |
|---------|------|------|
| `emit(task_id, event_type, payload)` | イベント発火。連番YAMLファイルとして追記 | `tanebi.event_store.emit_event()` |
| `create_task(task_id, request)` | タスク初期化。work dir作成 + `task.created` イベント自動発火 | `tanebi.event_store.create_task()` |
| `list_tasks()` | タスク一覧取得 | `tanebi.event_store.list_tasks()` |
| `get_task_summary(task_id)` | タスクサマリー取得（イベントログから集計） | `tanebi.event_store.get_task_summary()` |
| `rebuild_index()` | タスクインデックス再構築 | `tanebi.event_store.rebuild_index()` |

イベント定義は `events/schema.yaml` を参照

## セッション開始手順

1. config.yaml を読む（tanebi.execution, tanebi.checkpoint を確認）
2. config.yaml の claude_native の値を確認
   - true → docs/native-flow.md を読む
   - false → docs/listener-flow.md を読む
3. personas/active/ をカウント → 利用可能なPersona数を表示
4. work/ をカウント → 前回のコマンド数を表示
5. 「タスクを入力してください」と案内する

## パス受け渡し係原則（CRITICAL）

オーケストレーターは **Workerの出力内容を直接読まない**。

```
❌ 悪い例: Worker完了 → 内容を読む → Aggregatorに内容を渡す
✅ 良い例: Worker完了 → パスを記録 → Aggregatorにパス一覧を渡す
```

**理由**: オーケストレーターがWorker出力を全て読むとコンテキストが爆発する。
コンテキスト窓を管理するため、オーケストレーターはポインター（パス）のみを持つ。

## 実装参照マップ

Python実装の対応表:

| 機能 | Python実装 | 備考 |
|------|-----------|------|
| イベント発火 | `tanebi.event_store.emit_event()` | |
| タスク初期化 | `tanebi.event_store.create_task()` | |
| Worker→Core通知 | `tanebi.core.callback.handle_callback()` | |
| Persona操作 | `tanebi.core.persona_ops` | copy/merge/snapshot/list/restore |
| 設定読み込み | `tanebi.core.config` | |
| 進化エンジン | `tanebi.core.evolve` | Phase 5 完了 |
| 適応度計算 | `tanebi.core.fitness` | Phase 5 完了 |

## 参考ドキュメント

- フレームワーク全体設計は `docs/design.md` を参照
- Executor 実装方法は `docs/executor-design.md` を参照
