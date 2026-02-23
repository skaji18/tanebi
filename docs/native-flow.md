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
  │── EVOLVE（Core内部） ────────│                              │
```

### Step 1: REQUEST受取

ユーザーのタスク依頼を受け取る。

`EventStore.create_task()` を呼び出してタスクを初期化する。

ユーザー依頼内容を `work/cmd_NNN/request.md` に保存。

### Step 2: DECOMPOSE（Decomposerに委譲）

`templates/decomposer.md` を Read tool で読み取り、以下のプレースホルダーを展開して
Task tool の prompt として使用する:

- `{REQUEST_PATH}` → `work/cmd_NNN/request.md` の絶対パス
- `{PERSONA_LIST}` → `personas/active/` のYAMLファイル名一覧（拡張子なし）
- `{PLAN_PATH}` → `work/cmd_NNN/plan.md` の絶対パス
- `{CMD_ID}` → cmd_NNN
- `{TIMESTAMP}` → ISO8601形式の現在時刻

**イベント発火**: Decomposer起動前にdecompose.requestedイベントを発火する。

Task tool でDecomposerを起動し、出力 `work/cmd_NNN/plan.md` を待つ。

**イベント発火**: Decomposer完了後にtask.decomposedイベントを発火する。

### Step 3: EXECUTE（Worker群を並列起動）

`plan.md` を Read tool で読み、各サブタスクに対して以下を実行:

**Persona YAMLの読み取りとプレースホルダー展開:**

割り当てPersona YAML（`personas/active/{persona_id}.yaml`）を Read tool で読み取り、
`templates/worker_base.md` の以下のプレースホルダーを展開して Task tool の prompt として使用する:

- `{PERSONA_PATH}` → `personas/active/{persona_id}.yaml` の絶対パス
- `{PERSONA_NAME}` → `persona.identity.name`
- `{PERSONA_ARCHETYPE}` → `persona.identity.archetype`
- `{PERSONA_SPEECH_STYLE}` → `persona.identity.speech_style`
- `{PERSONA_DOMAINS}` → `persona.knowledge.domains` の一覧（name + proficiency）
- `{BEHAVIOR_RISK_TOLERANCE}` → `persona.behavior.risk_tolerance`
- `{BEHAVIOR_DETAIL_ORIENTATION}` → `persona.behavior.detail_orientation`
- `{BEHAVIOR_SPEED_VS_QUALITY}` → `persona.behavior.speed_vs_quality`
- `{FEW_SHOT_PATHS}` → `knowledge/few_shot_bank/{domain}/` 以下の関連ファイルパス一覧（なければ "なし"）
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

### Step 5: EVOLVE（進化ループ）

Aggregator完了後、進化エンジンを実行する。

**実装**（`tanebi.core.evolve`）: `run_evolution(task_id)` を呼び出す。

**進化完了後の確認:**

```bash
cat personas/active/{persona_id}.yaml
# → performance.total_tasks, success_rate, last_task_date が更新されているはず
# → evolution.last_evolution_event に今回のコマンドが追記されているはず
```

**進化エンジンが実行する6ステップ:**

1. **パフォーマンス更新**: `total_tasks`, `success_rate`, `last_task_date` を更新
2. **失敗補正**: 失敗したドメインの `proficiency` を -0.02 調整
3. **行動パラメータ調整**: GREEN/RED品質に基づき `risk_tolerance` を微調整
4. **適応度スコア計算**: `evolution.fitness_score` を更新。適応度 = w1*品質 + w2*完了率 + w3*効率 + w4*成長率（直近20タスクのスライディングウィンドウ）
5. **自動スナップショット**: `total_tasks` が5の倍数に達したら `personas/history/` にスナップショットを保存
6. **Few-Shot自動登録**: GREEN+success の結果を `knowledge/few_shot_bank/{domain}/` に登録（ドメインあたり最大100件（config.yaml の `few_shot_max_per_domain` で設定））

## 利用可能なPersona一覧の確認方法

```bash
ls personas/active/    # アクティブなPersona一覧
ls personas/library/   # ライブラリ（テンプレート・スナップショット）
```

Persona が存在しない種類のタスク → `generalist` として汎用Workerを起動。

**Decomposerへの指示**: `personas/active/` のYAMLファイル名を渡し、サブタスクの内容とPersonaのdomain知識を照合して最適なPersonaを選択させる。
