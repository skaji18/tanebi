# TANEBI Listener Flow（claude_native: false）

このドキュメントは config.yaml の `claude_native: false` 時に読む。
CLI コマンドを使ってタスクを投入し、Listener が全フローを自動処理する。

詳細アーキテクチャは [executor-design.md](executor-design.md) を参照。

## 基本操作

### Listener 起動（必須・別ターミナルで常駐）
```bash
cd ~/projects/tanebi
tanebi listener start
```

これを起動していないと decompose / execute / aggregate が一切処理されない。

### 起動確認
```bash
tanebi status
```

Listener が稼働中の場合、イベント処理状況が表示される。

### タスク投入
```bash
tanebi new "<request>"
```

### 状態確認
```bash
tanebi status [<task_id>]
```

### Event直接発火（デバッグ・上級者向け）
```bash
tanebi emit <task_id> <event_type> [key=value ...]
```
Executor向けAPIとしてeventを直接発火できる。

## Listener 内部構造

Listener は3つのコンポーネントから成る:

```
tanebi listener start
  └─ EventRouter（CLI: listener_cmd.py）
       ├─ watchdog Observer
       │    ├─ CoreListener（src/tanebi/core/listener.py）
       │    │    └─ *.completed イベントを監視 → フロー制御（tanebi.core.flow）
       │    └─ ExecutorListener（src/tanebi/executor/listener.py）
       │         └─ *.requested イベントを監視 → claude -p でサブタスク実行
       └─ watchdog が FSEvents（macOS）/ inotify（Linux）でファイル変更を検知
```

| コンポーネント | 役割 | 監視対象 |
|-------------|------|---------|
| **CoreListener** | フロー制御（*.completed → 次の *.requested を発行） | `*.completed.yaml` |
| **ExecutorListener** | サブタスク実行（claude -p 呼び出し） | `*.requested.yaml` |
| **watchdog** | ファイルシステム変更通知 | `work/{task_id}/events/` |

## フロー

```
tanebi new "FizzBuzzを実装して"
  │
  ▼
[EventStore] 001_task.created.yaml
  │
  ├─ CoreListener 検知 → 002_decompose.requested.yaml を emit
  │
  ├─ ExecutorListener 検知 → claude -p (decomposer.md) 実行
  │     └─ 003_task.decomposed.yaml を emit
  │
  ├─ CoreListener 検知 → 004_execute.requested.yaml (wave 1) を emit
  │
  ├─ ExecutorListener 検知 → claude -p (worker_base.md) 実行
  │     └─ 005_worker.completed.yaml を emit
  │
  ├─ CoreListener 検知 → [CHECKPOINT] → 006_aggregate.requested.yaml を emit
  │
  └─ ExecutorListener 検知 → claude -p (aggregator.md) 実行
        └─ 007_task.aggregated.yaml を emit → 完了
```

Listener が decompose → execute → aggregate を自動処理する。
Claude Code の介入は不要。タスク完了後に status で結果を確認せよ。

## エラー確認

```bash
# Listener のログ出力を確認
tanebi listener start  # コンソールに ERROR: ... が出力される

# イベントファイルを直接確認
ls work/<task_id>/events/
cat work/<task_id>/events/*.yaml
```

`*.claimed` ファイルが存在するが対応する `*.completed` がない場合は、
Executor が処理中または異常終了している。

## 注意事項

- Listener は常駐プロセス。タスク処理中は終了しないこと
- `claude_native: true` 時は Listener 不要（Claude session が直接処理する）
- 複数の Executor が同じイベントを処理しないよう claiming メカニズムが機能する
