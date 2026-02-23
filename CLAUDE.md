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

## オーケストレーターの役割

- ユーザー依頼を受け取り、Decomposer → Worker群 → Aggregator の流れを管制する
- **コンテキスト管理者**: Workerの出力内容を直接読まない。パス（ファイル場所）のみを扱う
- Persona の育成・進化を監督する
- **フロー決定ロジック**: `*.completed` イベントを受けて次の `*.requested` イベントを発行する

## Event Store（3つの責務）

Event Store は Core と Executor をつなぐ唯一の接点であり、以下の3つの責務を持つ:

1. **Core↔Executor間の通信ハブ**（イベント駆動）
2. **イベントの不変ログ**（記録・再現・分析）
3. **タスクindexの内部管理**（emit時に自動更新）

### メソッド

| メソッド | 説明 | 実装 |
|---------|------|------|
| `emit(task_id, event_type, payload)` | イベント発火。連番YAMLファイルとして追記 | `tanebi.core.event_store.emit_event()` |
| `create_task(task_id, request)` | タスク初期化。work dir作成 + `task.created` イベント自動発火 | `tanebi.core.event_store.create_task()` |
| `list_tasks()` | タスク一覧取得 | `tanebi.core.event_store.list_tasks()` |
| `get_task_summary(task_id)` | タスクサマリー取得（イベントログから集計） | `tanebi.core.event_store.get_task_summary()` |
| `rebuild_index()` | タスクインデックス再構築 | `tanebi.core.event_store.rebuild_index()` |

## Store抽象化（B-2）

TANEBIは3つの Store を Protocol として定義する。各 Store はデフォルトでファイル実装を提供し、`config.yaml` の `storage` セクションで実装を切り替え可能。

| Store | 役割 | デフォルト実装 |
|-------|------|---------------|
| **EventStore** | 追記ログ + タスク管理 | ファイルベース (`work/{task_id}/events/`) |
| **PersonaStore** | 人格データの永続化 (copy/merge/snapshot/list/restore) | ファイルベース (`personas/`) |
| **KnowledgeStore** | ドキュメント検索（今後定義） | ファイルベース (`knowledge/`) |

```yaml
# config.yaml storage セクション
storage:
  event_store:
    type: file            # file (default). 将来: redis, s3 等
  persona_store:
    type: file            # file (default)
  knowledge_store:
    type: file            # file (default)
```

## イベントカタログ（確定11種）

### 記録系

| イベント名 | 発火タイミング | ペイロード |
|-----------|--------------|-----------|
| `task.created` | `EventStore.create_task()` 呼び出し時 | `{ task_id, request_summary, timestamp }` |

### Core → Executor（依頼イベント）

| イベント名 | 発火元 | ペイロード |
|-----------|-------|-----------|
| `decompose.requested` | Core（task.created 後） | `{ task_id, request_path, persona_list, plan_output_path }` |
| `execute.requested` | Core（task.decomposed 後） | `{ task_id, subtask_id, subtask_file, persona_file, output_path, wave }` |
| `aggregate.requested` | Core（全 worker.completed 後） | `{ task_id, results_dir, report_path }` |

### Executor → Core（完了イベント）

| イベント名 | 発火元 | ペイロード |
|-----------|-------|-----------|
| `task.decomposed` | Executor（Decomposer完了後） | `{ task_id, plan: { subtasks[], waves, persona_assignments[] } }` |
| `worker.started` | Executor（Worker起動時） | `{ task_id, subtask_id, persona_id, wave }` |
| `worker.progress` | Executor（Worker中間出力時） | `{ task_id, subtask_id, message, percent? }` |
| `worker.completed` | Executor（Worker完了時） | `{ task_id, subtask_id, status, quality, domain }` |

### Core内部

| イベント名 | 発火タイミング | ペイロード |
|-----------|--------------|-----------|
| `wave.completed` | Core（Wave内全Worker完了検知時） | `{ task_id, wave, results_summary }` |
| `task.aggregated` | Executor（Aggregator完了後） | `{ task_id, report_path, quality_summary }` |

### 例外

| イベント名 | 発火タイミング | ペイロード |
|-----------|--------------|-----------|
| `error.worker_failed` | Worker失敗時 | `{ task_id, subtask_id, error_detail }` |

## セッション開始時の手順

```
1. config.yaml を読み込む
   - tanebi.execution を確認（max_parallel_workers / worker_max_turns / default_model）
   - tanebi.storage を確認（各 Store の実装タイプ）
2. personas/active/ をカウント → 利用可能なPersona数を表示
3. work/ をカウント → 前回のコマンド数を表示
4. 「タスクを入力してください」と案内する
```

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

`EventStore.create_task()` を呼び出してタスクを初期化する:

```python
# Python実装（tanebi.core.event_store）
from tanebi.core.event_store import EventStore

event_store = EventStore()
task_id = event_store.create_task(request_summary="<依頼内容の1行要約>")
# → work/cmd_NNN/ を作成 + task.created イベントを自動発火
```

ユーザー依頼内容を `work/cmd_NNN/request.md` に保存。

### Step 2: DECOMPOSE（Decomposerに委譲）

`templates/decomposer.md` を Read tool で読み取り、以下のプレースホルダーを展開して
Task tool の prompt として使用する:

- `{REQUEST_PATH}` → `work/cmd_NNN/request.md` の絶対パス
- `{PERSONA_LIST}` → `personas/active/` のYAMLファイル名一覧（拡張子なし）
- `{PLAN_PATH}` → `work/cmd_NNN/plan.md` の絶対パス
- `{CMD_ID}` → cmd_NNN
- `{TIMESTAMP}` → ISO8601形式の現在時刻

**イベント発火**: Decomposer起動前にdecompose.requestedイベントを発火する:

```python
event_store.emit_event(task_id, "decompose.requested", {
    "task_id": task_id,
    "request_path": f"work/{task_id}/request.md",
    "persona_list": "<Persona ID一覧>",
    "plan_output_path": f"work/{task_id}/plan.md"
})
```

Task tool でDecomposerを起動し、出力 `work/cmd_NNN/plan.md` を待つ。

**イベント発火**: Decomposer完了後にtask.decomposedイベントを発火する:

```python
event_store.emit_event(task_id, "task.decomposed", {
    "task_id": task_id,
    "plan": {"subtasks": [...], "waves": N, "persona_assignments": [...]}
})
```

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

**イベント発火**: Worker起動前にexecute.requestedイベントを発火する:

```python
event_store.emit_event(task_id, "execute.requested", {
    "task_id": task_id,
    "subtask_id": subtask_id,
    "subtask_file": f"work/{task_id}/results/{subtask_id}.md",
    "persona_file": f"personas/active/{persona_id}.yaml",
    "output_path": f"work/{task_id}/results/{subtask_id}.md",
    "wave": wave_num
})
```

**イベント発火**: 各Worker実行前後にイベントを発火する:

```python
# Worker開始前
event_store.emit_event(task_id, "worker.started", {
    "task_id": task_id, "subtask_id": subtask_id,
    "persona_id": persona_id, "wave": wave_num
})
```

- 同一wave内のサブタスク → **同一メッセージで複数 Task tool 呼び出し**（並列起動）
- Wave N が全て完了してから Wave N+1 を開始
- 出力先: `work/cmd_NNN/results/{subtask_id}.md`

```python
# Worker完了後
event_store.emit_event(task_id, "worker.completed", {
    "task_id": task_id, "subtask_id": subtask_id,
    "status": "success", "quality": "GREEN", "domain": domain
})
```

### Step 4: AGGREGATE（Aggregatorに委譲）

全Worker完了後、`templates/aggregator.md` を Read tool で読み取り、以下のプレースホルダーを展開して
Task tool の prompt として使用する:

- `{RESULTS_DIR}` → `work/cmd_NNN/results/` の絶対パス
- `{REPORT_PATH}` → `work/cmd_NNN/report.md` の絶対パス
- `{CMD_ID}` → cmd_NNN
- `{TIMESTAMP}` → ISO8601形式の現在時刻

**パス受け渡し係原則（再確認）**: オーケストレーター自身は `results/` ファイルの内容を読まない。
Aggregator にディレクトリパスを渡すだけ。Aggregator が内容を読んで統合レポートを生成する。

**イベント発火**: Aggregator起動前にaggregate.requestedイベントを発火する:

```python
event_store.emit_event(task_id, "aggregate.requested", {
    "task_id": task_id,
    "results_dir": f"work/{task_id}/results/",
    "report_path": f"work/{task_id}/report.md"
})
```

**イベント発火**: Aggregator完了後にtask.aggregatedイベントを発火する:

```python
event_store.emit_event(task_id, "task.aggregated", {
    "task_id": task_id,
    "report_path": f"work/{task_id}/report.md",
    "quality_summary": {"GREEN": n, "YELLOW": m, "RED": k}
})
```

### Step 5: EVOLVE（進化ループ）

Aggregator完了後、進化エンジンを実行する。

**現行実装**（Phase 5でPython化予定）:

```bash
bash scripts/evolve.sh work/{CMD_ID}
```

**Python化後の実装**（`tanebi.core.evolve`）:

```python
from tanebi.core.evolve import run_evolution
run_evolution(task_id)
```

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

## パス受け渡し係原則（CRITICAL）

オーケストレーターは **Workerの出力内容を直接読まない**。

```
❌ 悪い例: Worker完了 → 内容を読む → Aggregatorに内容を渡す
✅ 良い例: Worker完了 → パスを記録 → Aggregatorにパス一覧を渡す
```

**理由**: オーケストレーターがWorker出力を全て読むとコンテキストが爆発する。
コンテキスト窓を管理するため、オーケストレーターはポインター（パス）のみを持つ。

## 利用可能なPersona一覧の確認方法

```bash
ls personas/active/    # アクティブなPersona一覧
ls personas/library/   # ライブラリ（テンプレート・スナップショット）
```

Persona が存在しない種類のタスク → `generalist` として汎用Workerを起動。

**Decomposerへの指示**: `personas/active/` のYAMLファイル名を渡し、サブタスクの内容とPersonaのdomain知識を照合して最適なPersonaを選択させる。

### Persona自動選択（適応度ベース）

各サブタスクのドメインに対して、最も適応度の高いPersonaを自動選択する:

1. サブタスクのドメインを特定（例: backend, frontend, testing等）
2. `personas/active/` の全Personaを確認
3. 各Personaの `evolution.fitness_score` を読む
4. 同ドメイン対応のPersonaのうち、fitness_score が最高のものを選択
5. fitness_scoreが未設定（新規Persona）の場合は0.5として扱う
6. 適合するPersonaがない場合はgeneralist_v1をフォールバックとして使用

Decomposerが `personas/active/*.yaml` を読む際、`knowledge.domains` の照合に加えて
`evolution.fitness_score` を参照し、同ドメインで複数候補がある場合はスコア最高のPersonaを優先する。

## 実装参照マップ

旧シェルスクリプトからPython実装への対応表:

| 旧実装 | Python実装 | 備考 |
|--------|-----------|------|
| `scripts/emit_event.sh` | `tanebi.core.event_store.emit_event()` | イベント発火 |
| `scripts/new_cmd.sh` | `tanebi.core.event_store.create_task()` | EventStoreに吸収 |
| `scripts/tanebi-callback.sh` | `tanebi.core.callback.handle_callback()` | Worker→Core通知 |
| `scripts/persona_ops.sh` | `tanebi.core.persona_ops` | copy/merge/snapshot/list/restore |
| `scripts/tanebi_config.sh` | `tanebi.core.config` | 設定読み込み |
| `scripts/evolve.sh` | `tanebi.core.evolve`（Phase 5） | 進化エンジン |
| `scripts/_fitness.py` | `tanebi.core.fitness`（Phase 5） | 適応度計算 |
| `scripts/component_loader.sh` | 削除 | Module/Pluginは将来の拡張 |
| `scripts/send_feedback.sh` | `tanebi.core.event_store.emit_event()` | EventStoreに統合 |

## 将来の拡張

Module/Plugin システムは将来の拡張ポイントである。EventStore のイベントを購読する形で後付け可能な設計となっている。現時点では実装しない。想定される将来の Module: Trust, Progress, Approval, Cost, Evolution。

## 参考ドキュメント

- フレームワーク全体設計は `docs/design.md` を参照
- Executor 実装ガイドは `docs/adapter-guide.md` を参照
- 実装ロードマップ（Python化）は `docs/roadmap.md` を参照
