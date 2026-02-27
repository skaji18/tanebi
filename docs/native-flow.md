# TANEBI Native Flow（claude_native: true）

このドキュメントは config.yaml の `claude_native: true` 時に読む。
Claude Code が tanebi CLI を通じてフローを制御する。

---

## タスク実行フロー全体図

```
Core（Claude Code）                 Event Store                      Executor
  │                                      │                              │
  │── tanebi new "request" ─────────────▶│  task.created                │
  │                                      │                              │
  │── tanebi emit <id> decompose.requested ▶│                            │
  │                                      │◀── (Executorが読み取り) ────│
  │                                      │                              │  Decomposer実行
  │                                      │◀── task.decomposed ──────────│
  │── (plan.round1.md存在確認) ──────────│                              │
  │                                      │                              │
  │── tanebi emit <id> execute.requested ▶│  （wave 1, 並列）             │
  │                                      │◀── worker.started ───────────│
  │                                      │◀── worker.completed ─────────│
  │── (results/round1/*.md存在確認) ─────│                              │
  │                                      │                              │
  │── tanebi emit <id> checkpoint.requested ▶│                           │
  │                                      │◀── checkpoint.completed ─────│
  │── (結果判定) ─────────────────────────│                              │
  │                                      │                              │
  │── tanebi emit <id> aggregate.requested ▶│                            │
  │                                      │◀── task.aggregated ──────────│
  │── (report.md存在確認) ───────────────│                              │
  │                                      │                              │
  │── LEARN（signal→distill→inject） ───│                              │
```

---

## Step 1: REQUEST（タスク作成）

ユーザーの依頼を受け取り、tanebi にタスクを登録する。

```bash
.venv/bin/tanebi new "APIエンドポイントを実装してほしい"
```

コマンド成功後、タスク ID（例: `cmd_001`）が発行される。
ユーザー依頼内容は `work/cmd_NNN/request.md` に自動保存される。

```bash
# タスク状態確認
.venv/bin/tanebi status cmd_001
```

---

## Step 2: DECOMPOSE（Decomposerに委譲）

Decomposer を Task tool で起動し、タスクを分解させる。

### 2-1. decompose.requested イベント発火

```bash
.venv/bin/tanebi emit cmd_001 decompose.requested \
  request_path=work/cmd_001/request.md \
  plan_output_path=work/cmd_001/plan.round1.md \
  round=1
```

### 2-2. Decomposer 起動（Task tool）

`templates/decomposer.md` を Read tool で読み取り、以下のプレースホルダーを展開して
Task tool の prompt として使用する:

- `{REQUEST_PATH}` → `work/cmd_NNN/request.md` の絶対パス
- `{LEARNED_PATTERNS_PATHS}` → `knowledge/learned/` 以下の関連パターンファイルパス一覧（なければ "なし"）
- `{PLAN_PATH}` → `work/cmd_NNN/plan.round1.md` の絶対パス
- `{CMD_ID}` → cmd_NNN
- `{TIMESTAMP}` → ISO8601形式の現在時刻

**Task tool 起動ルール（必須）:**

- **`run_in_background: true` を必ず指定する**
  - フォアグラウンド実行は subagent の出力が親コンテキストに注入されるため禁止
  - パス受け渡し係原則: Decomposer の出力はファイル経由でやり取りする
- Step 2 は完了を待たずに **TaskOutput tool を使わない**
  - 完了確認はファイルの存在確認のみ

### 2-3. Decomposer 完了確認

```bash
# plan.round1.md が存在すれば Decomposer 完了
ls work/cmd_001/plan.round1.md
```

### 2-4. task.decomposed イベント発火

**Decomposer 自身がイベントを発火する。** テンプレートに emit 手順が含まれているため、
オーケストレーターは emit を行わない。Decomposer が完了していれば以下のイベントが存在するはず:

```yaml
# 確認コマンド（emit はしない、存在確認のみ）
# event: task.decomposed
# payload: plan_path=work/cmd_001/plan.round1.md, round=1
```

---

## Step 3: EXECUTE（Worker群を並列起動）

`plan.round1.md` を Read tool で読み、各サブタスクに対して Worker を起動する。

### 3-1. execute.requested イベント発火（サブタスクごと）

```bash
# サブタスク subtask_001 の実行を依頼
.venv/bin/tanebi emit cmd_001 execute.requested \
  subtask_id=subtask_001 \
  subtask_description="サブタスクの説明" \
  wave=1 \
  round=1 \
  output_path=work/cmd_001/results/round1/subtask_001.md

# サブタスク subtask_002 も同時に依頼（並列実行）
.venv/bin/tanebi emit cmd_001 execute.requested \
  subtask_id=subtask_002 \
  subtask_description="サブタスクの説明" \
  wave=1 \
  round=1 \
  output_path=work/cmd_001/results/round1/subtask_002.md
```

### 3-2. Worker 起動（Task tool 並列起動）

`templates/worker_base.md` を Read tool で読み取り、以下のプレースホルダーを展開:

- `{LEARNED_PATTERNS_PATHS}` → `knowledge/learned/{domain}/` 以下の関連ファイルパス一覧（なければ "なし"）
- `{SUBTASK_ID}` → サブタスクID
- `{TASK_DESCRIPTION}` → サブタスクの説明
- `{OUTPUT_PATH}` → `work/cmd_NNN/results/round1/{SUBTASK_ID}.md` の絶対パス

**Task tool 起動ルール（必須）:**

- **`run_in_background: true` を必ず指定する**（フォアグラウンド実行禁止）
  - フォアグラウンド実行はsubagentの結果が親オーケストレーターのコンテキストに自動注入されるため禁止
  - コンテキスト爆発の原因となり、パス受け渡し係原則に反する
- **同一 wave 内のサブタスクは同一メッセージで複数 Task tool 呼び出し**（並列起動）
- Wave N が全て完了してから Wave N+1 を開始する

### 3-3. Worker 完了確認

```bash
# 出力ファイルの存在確認で Worker 完了を判定する
ls work/cmd_001/results/round1/subtask_001.md
ls work/cmd_001/results/round1/subtask_002.md
```

**禁止事項:**

- TaskOutput tool で Worker 結果を読み取ること
- フォアグラウンド Task tool 呼び出し（`run_in_background: true` 省略）

### 3-4. worker.completed イベント発火

**Worker 自身がイベントを発火する。** テンプレートに emit 手順が含まれているため、
オーケストレーターは emit を行わない。Worker が完了していれば以下のイベントが存在するはず:

```yaml
# 確認（emit はしない、存在確認のみ）
# event: worker.completed
# payload: subtask_id=subtask_001, status=success, quality=GREEN, domain=backend, wave=1, round=1
```

---

## Step 3.5: CHECKPOINT（品質チェック）

全 Wave 完了後、Checkpoint Worker が実行結果の品質を検証する。
`config.yaml` の `checkpoint.mode` が `never` の場合はこの Step をスキップして Step 4 へ。

### Checkpoint の役割

- 全サブタスクの実行結果を評価し、pass/fail を判定する
- fail の場合、re-decompose して Round 2 以降を実行する（最大 `max_rounds` 回）
- pass の場合、Step 4（AGGREGATE）へ進む

### 3.5-1. checkpoint.requested イベント発火

```bash
.venv/bin/tanebi emit cmd_001 checkpoint.requested \
  subtask_id=checkpoint_001 \
  subtask_type=checkpoint \
  round=1 \
  wave=3 \
  request_path=work/cmd_001/request.md \
  plan_path=work/cmd_001/plan.round1.md \
  results_dir=work/cmd_001/results/round1 \
  output_path=work/cmd_001/results/round1/checkpoint_001.md
```

### 3.5-2. Checkpoint Worker 起動（Task tool）

`templates/checkpoint.md` を system prompt として Task tool で起動する。

```bash
# 完了確認: checkpoint 結果ファイルの存在確認
ls work/cmd_001/results/round1/checkpoint_001.md
```

Checkpoint Worker の出力例:
```yaml
verdict: pass | fail
subtask_verdicts:
  - subtask_id: subtask_001
    verdict: pass | fail
    attribution: execution | input | partial | ~
    reason: "判定理由"
summary: "全体の要約"
```

### 3.5-3. 結果分岐

- **verdict = pass** → Step 4（AGGREGATE）へ
- **verdict = fail かつ round < max_rounds** → `decompose.requested`（round+1, feedback付き）を発火してループ継続
- **verdict = fail かつ round >= max_rounds** → best effort で Step 4（AGGREGATE）へ

```bash
# pass の場合: Step 4 へ
.venv/bin/tanebi emit cmd_001 checkpoint.completed \
  round=1 \
  verdict=pass \
  failed_subtasks=[] \
  summary="全サブタスク pass"

# fail の場合: re-decompose（Round 2）
.venv/bin/tanebi emit cmd_001 decompose.requested \
  round=2 \
  request_path=work/cmd_001/request.md \
  plan_output_path=work/cmd_001/plan.round2.md
# → Step 3 に戻り round=2 で再実行
```

---

## Step 4: AGGREGATE（Aggregatorに委譲）

全 Worker 完了後、Aggregator を起動して統合レポートを生成する。

### 4-1. aggregate.requested イベント発火

```bash
.venv/bin/tanebi emit cmd_001 aggregate.requested \
  results_dir=work/cmd_001/results/round1 \
  report_path=work/cmd_001/report.md \
  round=1
```

### 4-2. Aggregator 起動（Task tool）

`templates/aggregator.md` を Read tool で読み取り、以下のプレースホルダーを展開:

- `{RESULTS_DIR}` → `work/cmd_NNN/results/round{N}/` の絶対パス
- `{REPORT_PATH}` → `work/cmd_NNN/report.md` の絶対パス
- `{CMD_ID}` → cmd_NNN
- `{TIMESTAMP}` → ISO8601形式の現在時刻

**Task tool 起動ルール（必須）:**

- **`run_in_background: true` を必ず指定する**
  - フォアグラウンド実行は subagent 出力が親コンテキストに注入されるため禁止

**パス受け渡し係原則（再確認）**: オーケストレーター自身は `results/` ファイルの内容を読まない。
Aggregator にディレクトリパスを渡すだけ。Aggregator が内容を読んで統合レポートを生成する。

### 4-3. Aggregator 完了確認

```bash
# report.md が存在すれば Aggregator 完了
ls work/cmd_001/report.md
```

### 4-4. task.aggregated イベント発火

**Aggregator 自身がイベントを発火する。** テンプレートに emit 手順が含まれているため、
オーケストレーターは emit を行わない。Aggregator が完了していれば以下のイベントが存在するはず:

```yaml
# 確認（emit はしない、存在確認のみ）
# event: task.aggregated
# payload: report_path=work/cmd_001/report.md, quality_summary={}
```

---

## Step 5: LEARN（知識蓄積）

Aggregator 完了後、Learning Engine を実行する。

**実装**: `tanebi.core.signal`（シグナル検出・蓄積）→ `tanebi.core.distill`（パターン蒸留）→ `tanebi.core.inject`（パターン注入）の順に実行する。

**Learning Engine が実行する4ステップ:**

1. **Signal Detection**: タスク結果のシグナルを検出
   - success + GREEN → positive signal (weight 1.0)
   - success + YELLOW → weak signal (weight 0.5)
   - failure + RED → negative signal (weight 1.0)

2. **Accumulation**: ドメイン別シグナルを `knowledge/signals/{domain}/` に蓄積

3. **Distillation**（N≥K ルール）: 同一ドメインでK件以上のシグナルが収束したら
   汎化パターンに蒸留 → `knowledge/learned/{domain}/`

4. **Injection**: 蒸留済みパターンを次回の Decomposer/Worker テンプレートに注入する。
   `{LEARNED_PATTERNS_PATHS}` プレースホルダーが該当ドメインのパスに展開される。

---

## ファイルパス構造

```
work/{task_id}/
  request.md                    # ユーザー依頼（不変）
  plan.round1.md                # Round 1 の Decomposer 出力
  plan.round2.md                # Round 2 の Decomposer 出力（redo 時）
  results/
    round1/
      subtask_001.md            # Round 1 の Worker 出力
      subtask_002.md
      checkpoint_001.md         # Round 1 の Checkpoint Worker 出力
    round2/
      subtask_001.md            # Round 2 の Worker 出力（redo 後）
  report.md                     # 最終 aggregate の出力（round 不問）
```

---

## Learned Patterns の確認方法

```bash
ls knowledge/learned/    # 蓄積済みパターン（ドメイン別）
ls knowledge/signals/    # 蓄積中シグナル（まだ蒸留前）
```

Learned Patterns が存在しない場合 → Worker は Learned Patterns なしで起動。
知識が蓄積されるにつれて自動的に注入されるようになる。

---

## tanebi CLI の実行方法

すべてのコマンドは `.venv/bin/tanebi` で直接実行する。`source .venv/bin/activate` は不要。

```bash
.venv/bin/tanebi new "..."
.venv/bin/tanebi emit ...
.venv/bin/tanebi status ...
```
