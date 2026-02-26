# Checkpoint 設計書

生成日: 2026-02-23
根拠: design.md Section 4 のフロー拡張。ユーザー仕様に基づく設計。

---

## 1. 概要・アーキテクチャ

本文書は TANEBI のフローに **Checkpoint（品質チェックフェーズ）** を追加する設計を定める。
Checkpoint は「実行結果の品質を検証し、不合格なら再分解・再実行するループ機構」である。

design.md が定めた原則（Core と Executor の疎結合、イベントスキーマが唯一の契約）を維持しつつ、
ループ対応の品質チェックフェーズを追加する。

### 1.1 設計判断サマリー

| 判断 | 結論 | 理由 |
|------|------|------|
| Checkpoint の実行主体 | **通常の Worker と同じ ExecutorListener** | 既存の実行機構を再利用。新しい Executor 不要 |
| Checkpoint の識別方法 | **plan.md 内の `type: checkpoint`** | Decomposer が plan 生成時に自動追加 |
| ループ制御 | **round フィールドでイベントを世代管理** | イベントログの不変性を維持しつつ世代を区別 |
| Verdict 集約 | **flow.py が checkpoint worker の出力をパース** | Core 層の責務。Executor は知らない |
| 失敗時の再分解 | **checkpoint_feedback 付き decompose.requested** | フィードバックループで品質改善を誘導 |

### 1.2 フロー全体図

```
decompose → execute(wave 1..N)
  → checkpoint wave（1〜N人の checkpoint worker が並列実行）
  → flow.py が verdict 集約
      → pass → aggregate → done
      → fail → decompose.requested(round=2, feedback付き)
              → execute → checkpoint → ...
              → max_rounds で打ち止め → aggregate（best effort）
```

### 1.3 フロー詳細図

```
                   ┌─────────────────────────────────────────────────────┐
                   │                    Round N                          │
                   │                                                     │
task.created ──▶ decompose.requested ──▶ task.decomposed                │
                   │  (round=N,                    │                     │
                   │   checkpoint_feedback※)       │                     │
                   │   ※round≧2のみ                ▼                    │
                   │                         execute.requested (wave 1)  │
                   │                               │                     │
                   │                               ▼                    │
                   │                         worker.completed (wave 1)   │
                   │                               │                     │
                   │                               ▼                    │
                   │                         wave.completed (wave 1)     │
                   │                               │                     │
                   │                          [次wave?] ──yes──▶ execute │
                   │                               │no                   │
                   │                               ▼                    │
                   │                   checkpoint.requested              │
                   │                               │                     │
                   │                               ▼                    │
                   │               checkpoint worker(s) 並列実行          │
                   │                               │                     │
                   │                               ▼                    │
                   │                   checkpoint.completed               │
                   │                               │                     │
                   │                     ┌────────┴────────┐            │
                   │                     │                  │            │
                   │                  [pass]             [fail]          │
                   │                     │                  │            │
                   │                     ▼                  ▼            │
                   │            aggregate.requested   [max_rounds?]      │
                   │                     │                  │            │
                   │                     ▼              yes─▶ aggregate  │
                   │                   done            no─▶ round N+1 ──┘
                   └─────────────────────────────────────────────────────┘
```

---

## 2. Round 概念

### 2.1 Round とは

Round はタスク実行の世代番号である。初回実行は round=1。
Checkpoint が fail を返した場合、round をインクリメントして再分解・再実行する。

### 2.2 設計ルール

| ルール | 説明 |
|--------|------|
| 全イベント payload に `round: int` | デフォルト値は 1。既存イベントとの後方互換性を維持 |
| round のインクリメント | `checkpoint.completed(status=fail)` 時に flow.py が round+1 で `decompose.requested` を発火 |
| `_all_workers_complete()` のフィルタリング | `(round, wave)` ペアで完了チェック。異なる round のイベントを混同しない |
| `list_events()` | 全 round のイベントを返す（不変ログ）。フィルタリングは呼び出し側の責務 |

### 2.3 イベントの round フィールド

```yaml
# 既存イベントへの追加フィールド
execute.requested:
  payload:
    task_id: string
    subtask_id: string
    wave: integer
    round: integer    # NEW: デフォルト 1

worker.completed:
  payload:
    task_id: string
    subtask_id: string
    status: enum[success, failure]
    wave: integer
    round: integer    # NEW: デフォルト 1

# 新規イベントの round フィールドは Section 10 参照
```

### 2.4 後方互換性

`round` フィールドが省略された場合、デフォルト値 1 として扱う。
これにより Checkpoint 未対応の既存タスクのイベントログも正しく処理できる。

---

## 3. ファイルパス戦略

### 3.1 ディレクトリ構造

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
      ...
  report.md                     # 最終 aggregate の出力
  events/
    001_task.created.yaml
    002_decompose.requested.yaml
    ...
```

### 3.2 設計意図

| 判断 | 理由 |
|------|------|
| plan を `plan.round{N}.md` で分離 | 各 round の計画を独立保存。比較・振り返りが容易 |
| results を `round{N}/` で分離 | 同一 subtask_id が round をまたいで存在するため、ディレクトリで分離 |
| report.md は単一 | 最終 aggregate の出力のみ。途中 round の集約は不要 |
| request.md は不変 | ユーザー依頼は round をまたいで変わらない |

### 3.3 パス生成ルール

```python
def plan_path(cmd_dir: Path, round: int) -> Path:
    return cmd_dir / f"plan.round{round}.md"

def result_path(cmd_dir: Path, round: int, subtask_id: str) -> Path:
    return cmd_dir / "results" / f"round{round}" / f"{subtask_id}.md"

def checkpoint_result_path(cmd_dir: Path, round: int, checkpoint_id: str) -> Path:
    return cmd_dir / "results" / f"round{round}" / f"{checkpoint_id}.md"
```

---

## 4. Checkpoint Subtask の仕組み

### 4.1 概要

Checkpoint subtask は通常の subtask と同じ Worker 実行機構で動作する。
違いは plan.md 内での `type: checkpoint` フラグのみ。

### 4.2 Decomposer の役割

Decomposer は plan 生成時に checkpoint subtask を自動追加する。
checkpoint subtask は通常 wave の次（最終 wave + 1）に配置される。

```yaml
# plan.round1.md の例
plan:
  subtasks:
    - id: subtask_001
      description: "API エンドポイント実装"
      wave: 1
      type: normal              # デフォルト（省略可）
    - id: subtask_002
      description: "テスト作成"
      wave: 2
      type: normal
    - id: checkpoint_001
      description: "全サブタスクの品質チェック"
      wave: 3                   # 最終 wave + 1
      type: checkpoint          # Checkpoint 識別フラグ
  waves: 3
  has_checkpoint: true          # Checkpoint wave の有無
```

### 4.3 Checkpoint wave の識別

flow.py は `wave.completed` 時に次の wave が checkpoint wave かどうかを判定する。

```python
def _is_checkpoint_wave(plan: dict, wave: int) -> bool:
    """指定 wave が checkpoint wave かどうかを判定する。"""
    subtasks = plan.get("subtasks", [])
    wave_subtasks = [s for s in subtasks if s.get("wave") == wave]
    return all(s.get("type") == "checkpoint" for s in wave_subtasks) and len(wave_subtasks) > 0
```

### 4.4 Checkpoint worker 数

Checkpoint worker は 1〜N 人が並列実行される。
Decomposer が plan 内に複数の checkpoint subtask を定義することで並列数を制御する。

```yaml
# 複数 checkpoint worker の例（多数決用）
  - id: checkpoint_001
    description: "品質チェック（評価者A）"
    wave: 3
    type: checkpoint
  - id: checkpoint_002
    description: "品質チェック（評価者B）"
    wave: 3
    type: checkpoint
  - id: checkpoint_003
    description: "品質チェック（評価者C）"
    wave: 3
    type: checkpoint
```

---

## 5. Checkpoint テンプレート

### 5.1 概要

`templates/checkpoint.md` は checkpoint worker への指示テンプレートである。
通常の `worker_base.md` の代わりに checkpoint subtask の system prompt として使用される。

### 5.2 テンプレート設計

```markdown
# Checkpoint Worker

あなたは品質チェッカーです。全サブタスクの実行結果を評価し、
各サブタスクについて verdict（合否判定）を YAML 形式で出力してください。

## 評価基準

1. タスクの要件を満たしているか
2. コードの品質（テスト・型安全性・エラーハンドリング）
3. 成果物の完全性（ファイルの存在・内容の妥当性）

## 出力フォーマット

以下の YAML フォーマットで出力してください。
出力は ```yaml ブロック内に記述してください。

verdict: pass | fail
subtask_verdicts:
  - subtask_id: subtask_001
    verdict: pass | fail
    attribution: execution | input | partial | ~
    reason: "判定理由"
  - subtask_id: subtask_002
    verdict: pass | fail
    attribution: execution | input | partial | ~
    reason: "判定理由"
summary: "全体の要約（1〜2文）"

## attribution の意味

| 値 | 意味 | Learning Engine への影響 |
|----|------|--------------------------|
| execution | Worker の実行品質が原因 | negative シグナルとして記録 |
| input | 入力（依頼・計画）の品質が原因 | スキップ（入力品質の問題） |
| partial | 部分的な問題 | weak_negative シグナルとして記録（weight 0.5） |
| ~ (null) | verdict=pass の場合 | 影響なし |
```

### 5.3 Checkpoint worker への入力

ExecutorListener が checkpoint subtask を処理する際、以下を user prompt として渡す:

```
## 元のリクエスト
{request.md の内容}

## 実行計画
{plan.round{N}.md の内容}

## サブタスク実行結果
### subtask_001
{results/round{N}/subtask_001.md の内容}

### subtask_002
{results/round{N}/subtask_002.md の内容}
```

### 5.4 出力フォーマット例

```yaml
verdict: fail
subtask_verdicts:
  - subtask_id: subtask_001
    verdict: fail
    attribution: execution
    reason: "テストカバレッジ不足。主要なエッジケースが未テスト"
  - subtask_id: subtask_002
    verdict: pass
    attribution: ~
    reason: ~
summary: "1/2 subtask が fail。subtask_001 のテストカバレッジが不十分"
```

---

## 6. Verdict 集約ポリシー

### 6.1 概要

複数の checkpoint worker が存在する場合、flow.py が各 worker の verdict を集約して
最終判定（pass/fail）を決定する。集約ポリシーは config.yaml で設定する。

### 6.2 ポリシー定義

| ポリシー | 条件 | ユースケース |
|----------|------|-------------|
| `any_fail` | 1人でも fail → redo（**デフォルト**） | 厳格な品質要求。1つでも問題があればやり直し |
| `majority` | 過半数 fail → redo | 多数決方式。複数 checkpoint worker 時の合意形成 |
| `all_fail` | 全員 fail → redo | 寛容な品質基準。全員が問題視した場合のみやり直し |

### 6.3 集約ロジック

```python
def aggregate_verdicts(
    checkpoint_results: list[dict],
    policy: str = "any_fail",
) -> tuple[str, list[dict]]:
    """Checkpoint worker の verdict を集約する。

    Args:
        checkpoint_results: 各 checkpoint worker の出力（パース済み）
        policy: 集約ポリシー ("any_fail" | "majority" | "all_fail")

    Returns:
        (final_verdict, failed_subtasks)
        final_verdict: "pass" | "fail"
        failed_subtasks: fail 判定された subtask の詳細リスト
    """
    fail_count = sum(1 for r in checkpoint_results if r.get("verdict") == "fail")
    total = len(checkpoint_results)

    if total == 0:
        return "pass", []

    if policy == "any_fail":
        is_fail = fail_count > 0
    elif policy == "majority":
        is_fail = fail_count > total / 2
    elif policy == "all_fail":
        is_fail = fail_count == total
    else:
        is_fail = fail_count > 0  # デフォルトは any_fail

    final_verdict = "fail" if is_fail else "pass"

    # 全 checkpoint worker から failed subtask を収集
    failed_subtasks = []
    for result in checkpoint_results:
        for sv in result.get("subtask_verdicts", []):
            if sv.get("verdict") == "fail":
                failed_subtasks.append(sv)

    return final_verdict, failed_subtasks
```

---

## 7. Re-decompose フィードバック

### 7.1 概要

Checkpoint が fail を返した場合、flow.py は `checkpoint_feedback` 付きの
`decompose.requested` イベントを発火する。Decomposer はフィードバックを参考に
改善された plan を生成する。

### 7.2 フィードバック payload 設計

```yaml
decompose.requested:
  task_id: cmd_001
  round: 2
  request_path: "work/cmd_001/request.md"
  plan_output_path: "work/cmd_001/plan.round2.md"
  checkpoint_feedback:
    previous_round: 1
    verdict_policy: any_fail
    failed_subtasks:
      - subtask_id: subtask_001
        attribution: execution
        reason: "テストカバレッジ不足"
      - subtask_id: subtask_003
        attribution: input
        reason: "要件定義が曖昧で実装方針が定まらなかった"
    summary: "2/3 subtask が fail。テストカバレッジとAPI設計の見直しが必要"
    previous_plan_path: "work/cmd_001/plan.round1.md"
    previous_results_dir: "work/cmd_001/results/round1/"
```

### 7.3 Decomposer の振る舞い

round ≧ 2 の `decompose.requested` を受け取った Decomposer は:

1. `checkpoint_feedback` を読む
2. `previous_plan_path` で前回の計画を参照する
3. `attribution` に基づいて改善策を決定する:
   - `execution`: 同じ subtask をより詳細な指示で再定義
   - `input`: subtask の分割・要件の明確化
   - `partial`: 部分修正の指示を追加
4. pass した subtask はそのまま維持（不要な再実行を避ける）
5. 改善された plan を `plan.round{N}.md` に出力する

### 7.4 フィードバックの制限

- `max_rounds` 到達時はフィードバックを送らず、直接 `aggregate.requested` を発火する
- aggregate は最善の round の結果を使用する（best effort）

---

## 8. Config 設計

### 8.1 追加フィールド

```yaml
tanebi:
  # ... 既存設定 ...

  checkpoint:
    mode: auto          # always | auto | never
    max_rounds: 3       # 最大ループ回数
    verdict_policy: any_fail   # any_fail | majority | all_fail
```

### 8.2 各フィールドの説明

| フィールド | 型 | デフォルト | 説明 |
|-----------|-----|-----------|------|
| `mode` | string | `auto` | Checkpoint の実行モード |
| `max_rounds` | integer | `3` | 最大 round 数。この数に達したら fail でも aggregate する |
| `verdict_policy` | string | `any_fail` | Verdict 集約ポリシー |

### 8.3 mode の挙動

| mode | 挙動 |
|------|------|
| `always` | 全タスクで Checkpoint を実行する |
| `auto` | Decomposer が plan に `has_checkpoint: true` を含めた場合のみ実行 |
| `never` | Checkpoint をスキップ。従来と同じフロー（decompose → execute → aggregate） |

### 8.4 mode による分岐

```python
def _should_checkpoint(config: dict, plan: dict) -> bool:
    """Checkpoint を実行すべきかを判定する。"""
    mode = config.get("checkpoint", {}).get("mode", "auto")
    if mode == "always":
        return True
    if mode == "never":
        return False
    # auto: plan に has_checkpoint があれば実行
    return plan.get("has_checkpoint", False)
```

---

## 9. Learning Engine への影響

### 9.1 概要

Checkpoint の結果は Learning Engine にフィードバックされる。
最終 round の結果を基準とし、途中 round の失敗は attribution に応じてシグナルを記録する。

### 9.2 シグナル記録ルール

| 状況 | Learning Engine への影響 |
|------|--------------------------|
| 最終 round の成功結果 | positive シグナルとして記録（quality, domain 等） |
| 途中 round の失敗 — `attribution: execution` | negative シグナルとして記録（Worker の実行品質が原因） |
| 途中 round の失敗 — `attribution: input` | スキップ（入力品質の問題。Worker のシグナルではない） |
| 途中 round の失敗 — `attribution: partial` | weak_negative シグナルとして記録（weight 0.5） |

### 9.3 Learned Patterns への影響

| 状況 | knowledge/learned/ への登録 |
|------|----------------------------|
| 最終 round の成功結果 | **シグナル蓄積対象**（蒸留条件 N≥K 到達時にパターン生成） |
| 途中 round の結果 | **対象外**（改善途中の不完全な結果） |
| 全 round 失敗（best effort aggregate） | **対象外** |

### 9.4 avoid パターンへの影響

Checkpoint の fail 理由は avoid パターンとして蓄積できる:

```yaml
# knowledge/learned/{domain}/avoid_NNN.yaml
id: avoid_001
type: avoid
domain: testing
pattern: "テストカバレッジ不足"
detail: "主要なエッジケースを含むテストを明示的に記述する"
source: "checkpoint_round1_cmd_001"
```

---

## 10. イベントカタログ更新

### 10.1 概要

既存 11 種 + checkpointイベント 2 種 + distillイベント 2 種 = **15 種**のイベントとなる。

### 10.2 新規イベント

#### checkpoint.requested

| 項目 | 値 |
|------|-----|
| 説明 | Core が Checkpoint wave の実行を Executor に依頼する |
| 発火元 | Core（最終通常 wave 完了後） |
| 方向 | Core → Event Store（Executor 読取） |

```yaml
checkpoint.requested:
  description: "CoreがCheckpoint waveの実行を依頼するイベント"
  direction: "Core → Event Store（Executor読取）"
  payload:
    task_id: string
    subtask_id: string        # checkpoint subtask の ID
    subtask_type: checkpoint  # ExecutorListener が分岐するためのフラグ
    round: integer
    wave: integer
    request_path: string      # request.md のパス
    plan_path: string         # plan.round{N}.md のパス
    results_dir: string       # results/round{N}/ のパス
    output_path: string       # checkpoint 結果の出力先
    timestamp: string
```

**注**: `checkpoint.requested` は `execute.requested` と同じ ExecutorListener が処理する。
payload に `subtask_type: checkpoint` を含め、ExecutorListener が分岐する。

**flow.py によるパース** (`_emit_checkpoint_completed`):
1. `checkpoint.requested` イベントから `wave` 番号を特定
2. 同 wave の `worker.completed` を収集し、各 checkpoint worker の `checkpoint_output` から `verdict` を抽出
3. `_aggregate_verdicts(checkpoint_results, policy)` で最終判定を集約
4. `checkpoint.completed` イベントとして `verdict`, `failed_subtasks`, `summary` を emit

#### checkpoint.completed

| 項目 | 値 |
|------|-----|
| 説明 | flow.py が全 checkpoint worker の verdict を集約した後に発火する |
| 発火元 | Core（flow.py の verdict 集約後） |
| 方向 | Core 内部 |

```yaml
checkpoint.completed:
  description: "Checkpoint verdict集約完了"
  direction: "Core内部"
  payload:
    task_id: string
    round: integer
    verdict: enum[pass, fail]   # flow.py 実装に合わせて verdict を使用
    failed_subtasks:            # fail 判定の subtask 詳細
      - subtask_id: string
        attribution: enum[execution, input, partial]
        reason: string
    summary: string
```

**flow.py によるパース** (`on_checkpoint_completed`):
1. `verdict = payload.get("verdict", "pass")` で合否を取得
2. `verdict == "pass"` または `round >= max_rounds` → `aggregate.requested` を emit（best-effort集計）
3. `verdict == "fail"` かつ `round < max_rounds` → `decompose.requested`（round+1, `checkpoint_feedback` 付き）を emit してループを継続

### 10.3 ExecutorListener の分岐

```python
def handle(self, task_id: str, event_type: str, payload: dict):
    if event_type == "decompose.requested":
        self._run_decompose(task_id, payload)
    elif event_type in ("execute.requested", "checkpoint.requested"):
        subtask_type = payload.get("subtask_type", "normal")
        if subtask_type == "checkpoint":
            self._run_checkpoint(task_id, payload)
        else:
            self._run_execute(task_id, payload)
    elif event_type == "aggregate.requested":
        self._run_aggregate(task_id, payload)

def _run_checkpoint(self, task_id: str, payload: dict):
    """Checkpoint worker を実行する。"""
    # checkpoint テンプレートを system prompt として使用
    system_prompt = read_template("checkpoint.md")
    # 全 subtask の結果を user prompt として組み立て
    user_prompt = build_checkpoint_prompt(payload)

    result = run_claude_p(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )

    self.event_store.emit(task_id, "worker.completed", {
        "task_id": task_id,
        "subtask_id": payload["subtask_id"],
        "subtask_type": "checkpoint",
        "status": "success",
        "wave": payload["wave"],
        "round": payload["round"],
        "checkpoint_output": parse_checkpoint_output(result),
    })
```

---

## 11. State 拡張（determine_state()）

### 11.1 新規状態

既存の状態に加え、以下の 3 状態を追加する:

| 状態 | 説明 | 遷移先 |
|------|------|--------|
| `checkpoint_executing` | Checkpoint wave 実行中 | `checkpoint_complete` |
| `checkpoint_complete` | 全 checkpoint worker 完了、verdict 判定待ち | `needs_aggregate` or `needs_redo` |
| `needs_redo` | Checkpoint fail、re-decompose 待ち | `needs_decompose`（round+1） |

### 11.2 状態遷移図

```
needs_decompose ──▶ decomposing ──▶ needs_execute
                                          │
                                          ▼
                                      executing
                                          │
                                          ▼
                                    wave_complete
                                          │
                              ┌───────────┴───────────┐
                              │                       │
                         [次wave?]              [checkpoint?]
                              │yes                    │yes
                              ▼                       ▼
                         needs_execute     checkpoint_executing
                                                      │
                                                      ▼
                                              checkpoint_complete
                                                      │
                                            ┌────────┴────────┐
                                            │                  │
                                         [pass]             [fail]
                                            │                  │
                                            ▼            [max_rounds?]
                                      needs_aggregate          │
                                            │             yes──▶ needs_aggregate
                                            ▼             no──▶ needs_redo
                                        aggregating               │
                                            │                      ▼
                                            ▼               needs_decompose
                                        completed              (round+1)
```

### 11.3 determine_state() の拡張

```python
def determine_state(cmd_dir: Path) -> str:
    """イベントログから現在の状態を判定する。"""
    cmd_dir = Path(cmd_dir)
    events = list_events(cmd_dir)
    if not events:
        return "unknown"

    last_type = events[-1].get("event_type", "")

    if last_type == "task.created":
        return "needs_decompose"
    if last_type == "decompose.requested":
        return "decomposing"
    if last_type == "task.decomposed":
        return "needs_execute"
    if last_type in ("execute.requested", "worker.started"):
        return "executing"
    if last_type == "worker.completed":
        payload = events[-1].get("payload", {})
        wave = payload.get("wave", 1)
        round_ = payload.get("round", 1)
        if _all_workers_complete(events, wave, round_):
            # checkpoint wave かどうかを判定
            if payload.get("subtask_type") == "checkpoint":
                return "checkpoint_complete"
            return "wave_complete"
        return "executing"
    if last_type == "wave.completed":
        return "needs_next_wave_or_aggregate"
    if last_type == "checkpoint.requested":
        return "checkpoint_executing"
    if last_type == "checkpoint.completed":
        verdict = events[-1].get("payload", {}).get("verdict")
        if verdict == "pass":
            return "needs_aggregate"
        else:
            return "needs_redo"
    if last_type == "aggregate.requested":
        return "aggregating"
    if last_type == "task.aggregated":
        return "completed"
    return "unknown"
```

### 11.4 `_all_workers_complete()` の拡張

```python
def _all_workers_complete(events: list[dict], wave: int, round: int = 1) -> bool:
    """(round, wave) ペアでworkerの完了チェック。"""
    expected = sum(
        1
        for e in events
        if e.get("event_type") in ("execute.requested", "checkpoint.requested")
        and e.get("payload", {}).get("wave") == wave
        and e.get("payload", {}).get("round", 1) == round
    )
    actual = sum(
        1
        for e in events
        if e.get("event_type") in ("worker.completed", "error.worker_failed")
        and e.get("payload", {}).get("wave") == wave
        and e.get("payload", {}).get("round", 1) == round
    )
    return expected > 0 and actual >= expected
```

### 11.5 on_wave_completed() の拡張

```python
def on_wave_completed(cmd_dir: Path, payload: dict) -> None:
    """wave.completed に反応。次 wave が checkpoint wave なら
    checkpoint.requested を発火し、それ以外は従来通り。"""
    cmd_dir = Path(cmd_dir)
    current_wave = payload.get("wave", 1)
    round_ = payload.get("round", 1)
    task_id = payload.get("task_id", cmd_dir.name)
    next_wave = current_wave + 1

    plan = _read_plan(cmd_dir, round_)
    next_subtasks = _parse_wave_subtasks_from_plan(plan, next_wave)

    if not next_subtasks:
        # 次 wave なし → checkpoint mode チェック
        config = _load_config()
        if _should_checkpoint(config, plan) and round_ <= config_max_rounds(config):
            # Checkpoint wave を自動追加（plan に checkpoint がなくても mode=always なら）
            emit_event(cmd_dir, "checkpoint.requested", {
                "task_id": task_id,
                "subtask_id": f"checkpoint_{round_:03d}",
                "subtask_type": "checkpoint",
                "round": round_,
                "wave": next_wave,
                "request_path": str(cmd_dir / "request.md"),
                "plan_path": str(cmd_dir / f"plan.round{round_}.md"),
                "results_dir": str(cmd_dir / "results" / f"round{round_}"),
                "output_path": str(cmd_dir / "results" / f"round{round_}" / f"checkpoint_{round_:03d}.md"),
            }, validate=False)
        else:
            # Checkpoint なし → aggregate
            emit_event(cmd_dir, "aggregate.requested", {
                "task_id": task_id,
                "results_dir": str(cmd_dir / "results" / f"round{round_}"),
                "report_path": str(cmd_dir / "report.md"),
                "round": round_,
            }, validate=False)
    elif _is_checkpoint_wave(plan, next_wave):
        # 次 wave が checkpoint wave
        for subtask in next_subtasks:
            emit_event(cmd_dir, "checkpoint.requested", {
                "task_id": task_id,
                "subtask_id": subtask["id"],
                "subtask_type": "checkpoint",
                "round": round_,
                "wave": next_wave,
                "request_path": str(cmd_dir / "request.md"),
                "plan_path": str(cmd_dir / f"plan.round{round_}.md"),
                "results_dir": str(cmd_dir / "results" / f"round{round_}"),
                "output_path": str(cmd_dir / "results" / f"round{round_}" / f"{subtask['id']}.md"),
            }, validate=False)
    else:
        # 通常の次 wave
        for subtask in next_subtasks:
            emit_event(cmd_dir, "execute.requested", {
                "task_id": task_id,
                "subtask_id": subtask["id"],
                "subtask_description": subtask.get("description", ""),
                "wave": next_wave,
                "round": round_,
                "output_path": str(cmd_dir / "results" / f"round{round_}" / f"{subtask['id']}.md"),
            }, validate=False)
```

### 11.6 on_checkpoint_completed() — 新規ハンドラ

```python
def on_checkpoint_completed(cmd_dir: Path, payload: dict) -> None:
    """checkpoint.completed に反応。pass → aggregate、fail → redo or aggregate(best effort)。"""
    cmd_dir = Path(cmd_dir)
    task_id = payload.get("task_id", cmd_dir.name)
    round_ = payload.get("round", 1)
    verdict = payload.get("verdict", "pass")

    config = _load_config()
    max_rounds = config.get("checkpoint", {}).get("max_rounds", 3)

    if verdict == "pass":
        # 合格 → aggregate
        emit_event(cmd_dir, "aggregate.requested", {
            "task_id": task_id,
            "results_dir": str(cmd_dir / "results" / f"round{round_}"),
            "report_path": str(cmd_dir / "report.md"),
            "round": round_,
        }, validate=False)
    elif round_ >= max_rounds:
        # max_rounds 到達 → best effort aggregate
        logging.warning(
            "Max rounds (%d) reached for task %s. Aggregating best effort.",
            max_rounds, task_id,
        )
        emit_event(cmd_dir, "aggregate.requested", {
            "task_id": task_id,
            "results_dir": str(cmd_dir / "results" / f"round{round_}"),
            "report_path": str(cmd_dir / "report.md"),
            "round": round_,
            "best_effort": True,
        }, validate=False)
    else:
        # fail → re-decompose
        next_round = round_ + 1
        emit_event(cmd_dir, "decompose.requested", {
            "task_id": task_id,
            "round": next_round,
            "request_path": str(cmd_dir / "request.md"),
            "plan_output_path": str(cmd_dir / f"plan.round{next_round}.md"),
            "checkpoint_feedback": {
                "previous_round": round_,
                "verdict_policy": payload.get("verdict_policy", "any_fail"),
                "failed_subtasks": payload.get("failed_subtasks", []),
                "summary": payload.get("summary", ""),
                "previous_plan_path": str(cmd_dir / f"plan.round{round_}.md"),
                "previous_results_dir": str(cmd_dir / "results" / f"round{round_}"),
            },
        }, validate=False)
```

---

## 12. 実装対象ファイル

### Phase（Checkpoint 実装）で作成するもの

| ファイル | 内容 |
|---------|------|
| `templates/checkpoint.md` | Checkpoint worker テンプレート |
| `tests/unit/test_checkpoint_flow.py` | Checkpoint フローテスト |

### Phase で変更するもの

| ファイル | 変更内容 |
|---------|---------|
| `src/tanebi/core/flow.py` | `determine_state()` 拡張、`on_checkpoint_completed()` 追加、`_all_workers_complete()` の round 対応、`on_wave_completed()` の checkpoint 分岐 |
| `src/tanebi/executor/listener.py` | `checkpoint.requested` ハンドリング、`_run_checkpoint()` 追加 |
| `events/schema.yaml` | `checkpoint.requested` + `checkpoint.completed` の 2 イベント追加 |
| `config.yaml` | `checkpoint` セクション追加 |
| `docs/design.md` | Section 4.2 イベントカタログ更新（11→13種）、Section 8.1 config 更新 **（※ 本設計書からの参照のみ。design.md 本体の変更は別タスク）** |

### 変更しないもの

| ファイル | 理由 |
|---------|------|
| `src/tanebi/core/event_store.py` | EventStore は純粋なログ。Checkpoint を知らない |
| `src/tanebi/api.py` | Public API は変更不要。status() は EventStore から集計するだけ |
| `src/tanebi/executor/worker.py` | `run_claude_p()` はそのまま利用可能 |

---

## 13. 設計上の注意事項

### 13.1 不変ログの原則維持

Checkpoint ループで round が増えても、イベントログは追記のみ。
過去の round のイベントは削除・変更しない。これにより:

- 全 round の履歴を後から分析可能
- Learning Engine が attribution に基づく正確なフィードバックを行える
- デバッグ時に品質改善の過程を追跡可能

### 13.2 Checkpoint 無効時の後方互換性

`checkpoint.mode: never` の場合、従来と完全に同じフローが動作する。
`round` フィールドのデフォルト値が 1 のため、既存イベントとの互換性も保たれる。

### 13.3 claude-native モードでの動作

claude-native モードでは Claude セッションが Core と Executor を兼ねるため、
CLAUDE.md のハンドラテーブルに以下を追加する:

```markdown
| checkpoint.requested | 全 subtask 結果を読み → 品質評価 → checkpoint 出力 → worker.completed を emit |
| checkpoint.completed(pass) | aggregate.requested を emit |
| checkpoint.completed(fail) | round < max_rounds なら decompose.requested(round+1) を emit / 達したら aggregate.requested |
```
