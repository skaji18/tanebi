# TANEBI Native Flow（claude_native: true）

このドキュメントは config.yaml の `claude_native: true` 時に読む。
Claude Code が tanebi CLI を通じてフローを制御する。

---

## 全ステップ共通ルール（CRITICAL）

- **TaskOutput tool 使用禁止**: 全てのサブエージェント（Decomposer / Worker / Checkpoint / Aggregator / Learner）に対して TaskOutput tool を使ってはならない。結果の読み取りもブロッキング待機も禁止。
- **完了確認はファイル存在確認のみ**: 各ステップの出力ファイル（plan.md / results/*.md / checkpoint.md / report.md / learn_result.md）が存在するかを `ls` で確認する。
- **パス受け渡し係原則**: オーケストレーターはサブエージェントの出力内容を直接読まない。パス（ポインター）のみを次のステップに渡す。

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

`decomposer` カスタムエージェントを `subagent_type` で指定し、Task tool で起動する。
プレースホルダー展開済みの payload を prompt（user message）として渡す:

```
task_id: cmd_NNN
request_path: /絶対パス/work/cmd_NNN/request.md
plan_output_path: /絶対パス/work/cmd_NNN/plan.round1.md
round: 1
learned_patterns_paths: knowledge/learned/ 以下の関連ファイルパス一覧（なければ "なし"）
```

**Task tool 起動パラメータ:**

- `subagent_type: "decomposer"` — カスタムエージェントを指定
- `prompt`: 上記 payload テキスト（プレースホルダー展開済み）
- **`run_in_background` は不要**: エージェント定義の `background: true` により自動的にバックグラウンド実行される

### 2-3. Decomposer 完了確認

```bash
# plan.round1.md が存在すれば Decomposer 完了
ls work/cmd_001/plan.round1.md
```

### 2-4. task.decomposed イベント発火

**Decomposer 自身がイベントを発火する。** エージェント定義に emit 手順が含まれているため、
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

`tanebi-worker` カスタムエージェントを `subagent_type` で指定し、Task tool で起動する。
プレースホルダー展開済みの payload を prompt（user message）として渡す:

```
task_id: cmd_NNN
subtask_id: subtask_001
subtask_description: サブタスクの説明
wave: 1
round: 1
output_path: /絶対パス/work/cmd_NNN/results/round1/subtask_001.md
learned_patterns_paths: knowledge/learned/{domain}/ 以下の関連ファイルパス一覧（なければ "なし"）
```

**Task tool 起動パラメータ:**

- `subagent_type: "tanebi-worker"` — カスタムエージェントを指定
- `prompt`: 上記 payload テキスト（プレースホルダー展開済み）
- **`run_in_background` は不要**: エージェント定義の `background: true` により自動的にバックグラウンド実行される
- **同一 wave 内のサブタスクは同一メッセージで複数 Task tool 呼び出し**（並列起動）
- Wave N が全て完了してから Wave N+1 を開始する

### 3-3. Worker 完了確認

```bash
# 出力ファイルの存在確認で Worker 完了を判定する
ls work/cmd_001/results/round1/subtask_001.md
ls work/cmd_001/results/round1/subtask_002.md
```

### 3-4. worker.completed イベント発火

**Worker 自身がイベントを発火する。** エージェント定義に emit 手順が含まれているため、
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

`checkpoint` カスタムエージェントを `subagent_type` で指定し、Task tool で起動する。
payload を prompt として渡す:

```
task_id: cmd_NNN
subtask_id: checkpoint_001
subtask_type: checkpoint
round: 1
wave: <最終wave+1>
request_path: /絶対パス/work/cmd_NNN/request.md
plan_path: /絶対パス/work/cmd_NNN/plan.round1.md
results_dir: /絶対パス/work/cmd_NNN/results/round1
output_path: /絶対パス/work/cmd_NNN/results/round1/checkpoint_001.md
```

- `subagent_type: "checkpoint"` — カスタムエージェントを指定
- **`run_in_background` は不要**: エージェント定義の `background: true` により自動的にバックグラウンド実行される

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

`aggregator` カスタムエージェントを `subagent_type` で指定し、Task tool で起動する。
プレースホルダー展開済みの payload を prompt（user message）として渡す:

```
task_id: cmd_NNN
results_dir: /絶対パス/work/cmd_NNN/results/round{N}/
report_path: /絶対パス/work/cmd_NNN/report.md
round: 1
```

**Task tool 起動パラメータ:**

- `subagent_type: "aggregator"` — カスタムエージェントを指定
- `prompt`: 上記 payload テキスト（プレースホルダー展開済み）
- **`run_in_background` は不要**: エージェント定義の `background: true` により自動的にバックグラウンド実行される

**パス受け渡し係原則（再確認）**: オーケストレーター自身は `results/` ファイルの内容を読まない。
Aggregator にディレクトリパスを渡すだけ。Aggregator が内容を読んで統合レポートを生成する。

### 4-3. Aggregator 完了確認

```bash
# report.md が存在すれば Aggregator 完了
ls work/cmd_001/report.md
```

### 4-4. task.aggregated イベント発火

**Aggregator 自身がイベントを発火する。** エージェント定義に emit 手順が含まれているため、
オーケストレーターは emit を行わない。Aggregator が完了していれば以下のイベントが存在するはず:

```yaml
# 確認（emit はしない、存在確認のみ）
# event: task.aggregated
# payload: report_path=work/cmd_001/report.md, quality_summary={}
```

---

## Step 5: LEARN（知識蓄積）

Aggregator 完了後、CoreListener が `task.aggregated` イベントを検知して `learn.requested` を自動発火する。
オーケストレーターは `learn.requested` を受け取り、Learner エージェントを Task tool で起動する。

### 5-1. learn.requested イベント（自動発火）

CoreListener が `task.aggregated` を処理すると `on_task_aggregated` が `learn.requested` を発火する。
オーケストレーターが手動で emit する必要はない。

発火される `learn.requested` の payload には以下のフィールドが含まれる:

```yaml
event: learn.requested
payload:
  task_id: cmd_NNN
  cmd_dir: work/cmd_NNN
  report_path: work/cmd_NNN/report.md
  results_dir: work/cmd_NNN/results/round1
  knowledge_dir: knowledge
  output_path: work/cmd_NNN/learn_result.md
  round: 1
```

### 5-2. Learner 起動（Task tool）

`learner` カスタムエージェントを `subagent_type` で指定し、Task tool で起動する。
`learn.requested` イベントの payload を **絶対パスに展開して** prompt として渡す:

```
task_id: cmd_NNN
cmd_dir: /絶対パス/work/cmd_NNN
report_path: /絶対パス/work/cmd_NNN/report.md
results_dir: /絶対パス/work/cmd_NNN/results/round1
knowledge_dir: /絶対パス/knowledge
output_path: /絶対パス/work/cmd_NNN/learn_result.md
round: 1
```

- `results_dir` — Worker結果ファイルが格納されているディレクトリ。Learner がここから全 Worker 出力を読み込む
- `knowledge_dir` — 知識ベースルートディレクトリ。シグナル書き出し・蒸留先として使用する
- `output_path` — **Learner 自身の結果出力先**。Learner は実行結果サマリーをこのパスに書き出す
- `round` — 実行ラウンド番号

**Task tool 起動パラメータ:**

- `subagent_type: "learner"` — カスタムエージェントを指定
- `prompt`: 上記 payload テキスト（全パス絶対パス展開済み）
- **`run_in_background` は不要**: エージェント定義の `background: true` により自動的にバックグラウンド実行される

### 5-3. Learner 完了確認

Learner は以下を実行する:
1. `report_path`（report.md）と `results_dir/` 以下の全 Worker 出力を読む
2. タスク全体から「学ぶべきパターン」を自身の知性で抽出する
3. domain 別にシグナル YAML を `{knowledge_dir}/signals/{domain}/` に書き出す
4. 蒸留トリガーチェック（N>=K）を実行し、**条件を満たせば Learner 自身が蒸留を実行する**（蒸留は Learner の責務）
5. 実行結果サマリーを `output_path` に書き出す
6. `learn.completed` イベントを発火する

```bash
# output_path が存在すれば Learner 完了
ls work/cmd_001/learn_result.md
```

### 5-4. learn.completed → completed

`learn.completed` が発火されると `determine_state()` が `"completed"` を返す。
タスクフロー完了。

**Learned Patterns の確認:**

```bash
ls knowledge/signals/    # 蓄積中シグナル（まだ蒸留前）
ls knowledge/learned/    # 蒸留済みパターン（ドメイン別）
```

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
  learn_result.md               # Learner の実行結果サマリー
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
