# TANEBI Native Flow（claude_native: true）

このドキュメントは config.yaml の `claude_native: true` 時に読む。
Claude Code が直接 Python API を呼び出してフローを制御する。

## タスク実行フロー（Core→EventStore→Executorフロー）

```
Core                        Event Store                      Executor
  │                              │                              │
  │── task.created ──────────────│                              │
  │                              │                              │
  │── decompose.requested ──────▶│                              │
  │                              │◀── (Executorが読み取り) ─────│
  │                              │                              │  Decomposer実行
  │                              │◀── task.decomposed ──────────│
  │◀── (Coreが読み取り) ────────│                              │
  │                              │                              │
  │── execute.requested ────────▶│  (Wave 1, 並列)              │
  │                              │◀── worker.started ───────────│
  │                              │◀── worker.completed ─────────│
  │◀── (Coreが読み取り) ────────│                              │
  │                              │                              │
  │── aggregate.requested ──────▶│                              │
  │                              │◀── task.aggregated ──────────│
  │◀── (Coreが読み取り) ────────│                              │
  │                              │                              │
  │── LEARN（Core内部） ─────────│                              │
```

### Step 1: REQUEST受取

ユーザーのタスク依頼を受け取る。

`EventStore.create_task()` を呼び出してタスクを初期化する。

ユーザー依頼内容を `work/cmd_NNN/request.md` に保存。

### Step 2: DECOMPOSE（Decomposerに委譲）

`templates/decomposer.md` を Read tool で読み取り、以下のプレースホルダーを展開して
Task tool の prompt として使用する:

- `{REQUEST_PATH}` → `work/cmd_NNN/request.md` の絶対パス
- `{LEARNED_PATTERNS_PATHS}` → `knowledge/learned/` 以下の関連パターンファイルパス一覧（なければ "なし"）
- `{PLAN_PATH}` → `work/cmd_NNN/plan.md` の絶対パス
- `{CMD_ID}` → cmd_NNN
- `{TIMESTAMP}` → ISO8601形式の現在時刻

**イベント発火**: Decomposer起動前にdecompose.requestedイベントを発火する。

Task tool でDecomposerを起動し、出力 `work/cmd_NNN/plan.md` を待つ。

**イベント発火**: Decomposer完了後にtask.decomposedイベントを発火する。

### Step 3: EXECUTE（Worker群を並列起動）

`plan.md` を Read tool で読み、各サブタスクに対して以下を実行:

**Learned Patterns の注入:**

`knowledge/learned/{domain}/` 以下の関連パターンファイルを Read tool で読み取り、
`templates/worker_base.md` の以下のプレースホルダーを展開して Task tool の prompt として使用する:

- `{LEARNED_PATTERNS_PATHS}` → `knowledge/learned/{domain}/` 以下の関連ファイルパス一覧（なければ "なし"）
- `{SUBTASK_ID}` → サブタスクID
- `{TASK_DESCRIPTION}` → サブタスクの説明
- `{OUTPUT_PATH}` → `work/cmd_NNN/results/{SUBTASK_ID}.md` の絶対パス

**Waveベースの並列実行:**

**イベント発火**: Worker起動前にexecute.requestedイベントを発火する。

**イベント発火**: 各Worker実行前後にイベントを発火する。

- 同一wave内のサブタスク → **同一メッセージで複数 Task tool 呼び出し**（並列起動）
- Wave N が全て完了してから Wave N+1 を開始
- 出力先: `work/cmd_NNN/results/{subtask_id}.md`

### Step 4: AGGREGATE（Aggregatorに委譲）

全Worker完了後、`templates/aggregator.md` を Read tool で読み取り、以下のプレースホルダーを展開して
Task tool の prompt として使用する:

- `{RESULTS_DIR}` → `work/cmd_NNN/results/` の絶対パス
- `{REPORT_PATH}` → `work/cmd_NNN/report.md` の絶対パス
- `{CMD_ID}` → cmd_NNN
- `{TIMESTAMP}` → ISO8601形式の現在時刻

**パス受け渡し係原則（再確認）**: オーケストレーター自身は `results/` ファイルの内容を読まない。
Aggregator にディレクトリパスを渡すだけ。Aggregator が内容を読んで統合レポートを生成する。

**イベント発火**: Aggregator起動前にaggregate.requestedイベントを発火する。

**イベント発火**: Aggregator完了後にtask.aggregatedイベントを発火する。

### Step 5: LEARN（知識蓄積）

Aggregator完了後、Learning Engine を実行する。

**実装**: `tanebi.core.signal`（シグナル検出・蓄積）→ `tanebi.core.distill`（パターン蒸留）→ `tanebi.core.inject`（パターン注入）の順に実行する。

**Learning Engine が実行する4ステップ:**

1. **Signal Detection**: タスク結果のシグナルを検出
   - success + GREEN → positive signal (weight 1.0)
   - success + YELLOW → weak signal (weight 0.5)
   - failure + RED → negative signal (weight 1.0)

2. **Accumulation**: ドメイン別シグナルを `knowledge/signals/{domain}/` に蓄積

3. **Distillation**（N≥K ルール）: 同一ドメインでK件以上のシグナルが収束したら
   汎化パターンに蒸留 → `knowledge/learned/{domain}/`


## Learned Patterns の確認方法

```bash
ls knowledge/learned/    # 蓄積済みパターン（ドメイン別）
ls knowledge/signals/    # 蓄積中シグナル（まだ蒸留前）
```

Learned Patterns が存在しない場合 → Worker は Learned Patterns なしで起動。
知識が蓄積されるにつれて自動的に注入されるようになる。
