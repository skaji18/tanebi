# TANEBI（種火）設計書

---

## 1. 思想・設計ポリシー

### 1.1 コア価値：進化する人格

```
種 火 — 小さな火種から、消えない炎へ。
The spark that never dies — agents that grow with every task.
```

TANEBIは**進化するマルチエージェント人格フレームワーク**である。エージェントにタスク実行を重ねるたびに成長・特化する「人格（Persona）」を与え、チーム全体を複利的に賢くする。

| 問題 | TANEBIの解法 |
|------|-------------|
| エージェントの記憶喪失 | 4層人格モデルで知識・行動特性・実績を永続化 |
| 最適配置の不在 | 適応度スコアに基づく自動マッチング |
| 品質の停滞 | 進化エンジンが成功パターンを強化、失敗パターンを記録 |
| 知識のサイロ化 | 共有知識バンクとパターン抽出で組織学習 |
| 環境ロックイン | Event Store を介した疎結合で実行環境を自由に選択 |

### 1.2 コアと外部の分離

TANEBIの設計は**コア（進化エンジン + Persona管理 + フロー決定）と外部（Executor + UI）の分離**を原則とする。

- **Core 層**: 進化エンジン、Persona Store、フロー決定ロジック、Module/Plugin 基盤。Event Store を介してのみ外部と通信する。Executor の実装を知らない
- **Executor**: `*.requested` イベントを処理し `*.completed` を返す外部実行環境。Task tool / subprocess / Docker 等、自由に差し替え可能
- **Module / Plugin**: Event Store 上のイベントを購読して動作する拡張。信頼チェック、進捗表示、承認ゲート等

**コアが強いからこそ Executor を自由にできる。**

### 1.3 設計原則

| # | 原則 | 説明 |
|---|------|------|
| P1 | 進化をコアに、他は交換可能 | 進化する知性を核に据える |
| P2 | プラグインは差し替え可能 | 信頼・認知工学・UIは後から差し込める |
| P3 | 方向性を早期に絞らない | どの方向にも行ける状態を維持 |
| P4 | 測定に基づく設計判断 | エビデンスベースの進化 |
| P5 | 二重進化（個体＋知識） | 個体進化と共有知識進化の統合 |

### 1.4 ゼロインフラ原則

```bash
git clone https://github.com/skaji18/tanebi
cd tanebi
claude
# CLAUDE.mdが自動ロード → TANEBIオーケストレーターとして起動
```

Claude Codeさえあれば動く。tmux不要、プロセス管理不要、追加インフラ不要。

---

## 2. アーキテクチャ概要

### 2.1 アーキテクチャ概要図

```
 TANEBI Core                     Event Store                    Executor
 ┌────────────────────┐     ┌─────────────────────┐     ┌────────────────────┐
 │                    │     │  Immutable Event Log │     │                    │
 │  Evolution Core    │     │                     │     │  *.requested を読み │
 │  Persona Store     │     │  *.requested →→→→→→→│→→→→→│  処理して           │
 │  component_loader  │     │                     │     │  *.completed を返す │
 │  Module / Plugin   │     │  *.completed ←←←←←←←│←←←←←│                    │
 │                    │     │                     │     │  実装技術は自由:    │
 │  ┌──────────────┐  │     │  events/            │     │  LLM / shell /     │
 │  │ flow決定ロジック│  │     │    001_task.created │     │  Docker / Lambda / │
 │  │ (次に何をするか│  │     │    002_decompose    │     │  何でもよい        │
 │  │  を判断)      │  │     │      .requested     │     │                    │
 │  └──────────────┘  │     │    003_task          │     │                    │
 │                    │     │      .decomposed     │     │                    │
 │  ※ Core は        │     │    ...               │     │  ※ Executor は     │
 │    Executor を     │     │                     │     │    Core を知らない  │
 │    知らない        │     │  ※ イベントは不変の   │     │                    │
 │                    │     │    事実として蓄積     │     │                    │
 └────────────────────┘     └─────────────────────┘     └────────────────────┘

 Module / Plugin 層（Core 内部の拡張）
 ┌──────────────────────────────────────────────────────────────────────────┐
 │  Module（組み込み）                        Plugin（ユーザ自由拡張）       │
 │  ┌──────────────────────────────────┐   ┌──────────────────────────┐   │
 │  │ type: core        type: ui       │   │ slack_notifier            │   │
 │  │ trust             progress       │   │ github_issue              │   │
 │  │ (将来: cognitive  approval       │   │ custom_logger / …         │   │
 │  │  quality, gov)    cost           │   └──────────────────────────┘   │
 │  │                   evolution      │                                  │
 │  │                   history        │   共通: plugin.yaml + handler.sh │
 │  └──────────────────────────────────┘         + イベント購読           │
 └──────────────────────────────────────────────────────────────────────────┘
```

**設計上の重要な境界**:

- **Core と Executor の分離**: TANEBI Core と Executor は Event Store を介してのみ通信する。
  Core は `*.requested` イベントを発行し、Executor は `*.completed` イベントを返す。
  双方が相手の実装を一切知らない。
- **Event Store は不変ログ**: イベントは事実として蓄積される。キューではなくログ。
  消費者（Core / Module / Plugin）はそれぞれ自分の処理位置を管理する。
- **Executor は自由実装**: イベントスキーマさえ守れば、Executor の実装技術は問わない。

### 2.2 各レイヤーの責務

#### Core 層（カーネル）

変更頻度が最も低く、TANEBI の存在意義そのもの。**ローカルファイルのみ操作し、Executor を一切知らない。**

| コンポーネント | 責務 | 実装 |
|--------------|------|------|
| component_loader | モジュール・プラグインの読み込み・イベント配信 | `scripts/component_loader.sh` |
| Event Store | イベントの不変ログ。Core・Module・Plugin・Executor 間の唯一の通信手段 | ファイルベースイベントログ (`work/cmd_NNN/events/`) |
| Persona Store | 人格 YAML の読み書き・バージョン管理 | `personas/` ディレクトリ |
| Evolution Core | エージェント個体の進化 + 共有知識の成長（Section 7 で詳述） | `scripts/evolve.sh` + `scripts/_fitness.py` |
| フロー決定ロジック | `*.completed` イベントを受けて次の `*.requested` イベントを発行する | 環境依存（LLM / スクリプト等） |

Core の役割は「次に何をするかを決める」こと。実際の実行は Executor に委ねる。

#### Event Store（通信基盤）

Core と Executor をつなぐ唯一の接点。詳細は Section 4.5。

| 特性 | 説明 |
|------|------|
| 不変性 | イベントは事実として追記される。書き換え・削除しない |
| ログ型 | キューではなくログ。複数の消費者が同じイベントを読める |
| カーソル管理 | 各消費者が自分の処理位置を管理する |
| 冪等性 | イベント ID による重複処理の防止（既存の idempotency_key を活用） |

#### Module / Plugin 層（拡張）

モジュール（組み込み）とプラグイン（自由拡張）を統一した規約で管理する。詳細は Section 3。

| 種別 | 説明 | 例 |
|------|------|---|
| Module (type: core) | フロー介入権を持つ組み込みコンポーネント | trust |
| Module (type: ui) | 表示・操作を担う組み込みコンポーネント | progress, approval, cost |
| Plugin | ユーザが自由に追加する拡張 | Slack通知, カスタムログ |

Module / Plugin は Event Store 上のイベントを購読して動作する。Core の内部実装を知らない。

#### Executor（外部実行環境）

`*.requested` イベントを処理し、`*.completed` イベントを返す。TANEBI Core の外側に位置する。

Executor の唯一の制約は **イベントスキーマを守ること**（Section 4.3）。
LLM で処理しても、シェルスクリプトで処理しても、コンテナで処理しても構わない。
TANEBI はリファレンス実装を同梱するが、それを使う義務はない。

---

## 3. モジュール・プラグインシステム

TANEBI の拡張ポイントには **モジュール** と **プラグイン** の2種類がある。
どちらも同じ技術的フレームワーク（plugin.yaml + handler.sh + イベント購読）で動作するが、位置づけが異なる。

### 3.1 モジュールとプラグインの違い

**モジュール（Module）** — アーキテクチャが定義した役割を担う組み込みコンポーネント。

- TANEBI のフロー上で特定の責務を持つ（セキュリティ判定、承認ゲート、進捗表示等）
- 役割は固定、実装（handler.sh の中身）は差し替え可能
- 無効化すると対応する機能が欠落する（例: trust 無効 → セキュリティチェックなし）

**プラグイン（Plugin）** — ユーザが自由に追加する拡張。

- イベントを購読して任意の処理を実行する
- TANEBI は存在を事前に知らない。後付けで追加・削除できる
- なくても TANEBI は正常に動作する

| | モジュール | プラグイン |
|---|---|---|
| 役割 | アーキテクチャが定義 | ユーザが自由に定義 |
| 例 | trust, approval, progress | Slack通知, GitHub Issue連携, カスタムログ |
| 有無の影響 | 機能欠落 | なくても動く |
| 追加方法 | 設計に組み込み済み | `plugins/` に配置するだけ |
| 技術的仕組み | plugin.yaml + handler.sh | plugin.yaml + handler.sh（同じ） |

**フロー制御について**: DECOMPOSE→EXECUTE→AGGREGATE→EVOLVE のフロー制御は Core 層の責務
（フロー決定ロジック）であり、Module ではない。Core が `*.completed` イベントを受けて
次の `*.requested` イベントを発行する。Section 4.1 参照。

#### 組み込みモジュール一覧

| モジュール | 種別 | 役割 |
|---|---|---|
| trust | core | タスク割り当て前のセキュリティ判定（allow/deny） |
| approval | ui | 計画承認ゲート・実行中の介入ポイント |
| progress | ui | Worker 実行状況のリアルタイム進捗表示 |
| cost | ui | トークン消費量の集計・表示 |
| evolution | ui | Persona 進化状況・fitness 推移の可視化 |
| history | ui | 過去タスクの検索・閲覧 |

#### プラグインの例（ユーザ作成）

```
plugins/slack_notifier/    → worker.completed 時に Slack に通知
plugins/github_issue/      → task.created 時に GitHub Issue を自動作成
plugins/custom_logger/     → 全イベントを独自フォーマットで記録
```

プラグインの作成方法は `plugins/_template/` を参照。

### 3.2 共通フレームワーク

モジュールもプラグインも、以下のファイル構成と規約に従う。

#### ディレクトリ構造

```
plugins/
├── trust/                  # Module (type: core) — セキュリティ判定
│   ├── plugin.yaml         # 定義ファイル（必須）
│   ├── handler.sh          # イベントハンドラ（必須）
│   └── config.yaml         # 設定（任意）
├── progress/               # Module (type: ui)  — 進捗表示
│   ├── plugin.yaml
│   ├── handler.sh
│   └── config.yaml
├── approval/               # Module (type: ui)  — 承認ゲート
│   └── ...
├── cost/                   # Module (type: ui)  — コスト集計
│   └── ...
├── evolution/              # Module (type: ui)  — 進化可視化
│   └── ...
├── history/                # Module (type: ui)  — 履歴検索
│   └── ...
├── slack_notifier/         # Plugin（ユーザ作成の例）
│   └── ...
└── _template/              # テンプレート（Module/Plugin 共通）
    ├── plugin.yaml
    └── handler.sh
```

Module もユーザ作成の Plugin も同じ `plugins/` ディレクトリに配置する。
component_loader は区別せず一律に読み込み・dispatch する。

#### plugin.yaml（必須）

```yaml
plugin:
  name: "plugin_name"              # 一意の名前 [a-z_]+
  version: "1.0.0"                 # セマンティックバージョン
  type: core                       # core | ui
  description: "1行の説明"

  subscribes_to:                   # 購読するイベント
    - event_type: "worker.completed"
      handler: "on_worker_done"    # handler.sh内の関数名

  feedback_commands: []            # UI → Core フィードバック（type: ui のみ）

  lifecycle:
    on_init: "init"                # 初期化
    on_event: "handle_event"       # イベント受信
    on_destroy: "cleanup"          # 終了処理

  # type: core のみ
  hooks:                           # コア処理への介入ポイント
    on_task_assign: "check_trust"  # allow/deny 権限あり
    on_task_complete: "update_score"

  # type: ui のみ
  display:
    type: terminal                 # terminal | file | web
    refresh_mode: event_driven     # event_driven | polling | manual
```

#### handler.sh（必須）

```bash
#!/usr/bin/env bash

init() {
  echo "[$(basename "$(dirname "$0")")] initialized"
}

handle_event() {
  local event_type="$1"
  local event_file="$2"
  # イベント処理
}

cleanup() {
  :
}
```

#### config.yaml での有効/無効切り替え

```yaml
# config.yaml
tanebi:
  plugins:
    trust:
      enabled: true
    progress:
      enabled: true
    approval:
      enabled: true
      plan_review: true
      wave_gate: false
    cost:
      enabled: false
    evolution:
      enabled: true
    history:
      enabled: false
```

### 3.3 type: core（コアモジュール）

コアモジュールはタスク実行フローに**介入**できる。

| 権限 | 説明 |
|------|------|
| allow/deny | `on_task_assign` フックでタスク割り当てをブロック可能 |
| on_task_complete | タスク完了後にスコア更新等の処理を実行 |
| on_session_start | セッション開始時に制約を注入 |

**介入の仕組み**: コアモジュールのフックは exit code で判定する。exit 0 = allow、exit 1 = deny。deny 時は Core のフロー決定ロジックが代替策を実行する。

**現在のコアモジュール**:
- **Trust Module**: 信頼スコアに基づく段階的権限委譲（Section 5.1）

※ フロー制御（DECOMPOSE→EXECUTE→AGGREGATE→EVOLVE）は Core 層の責務であり、Module ではない。

**将来のコアモジュール候補**:
- Cognitive Quality Module: 注意品質管理、コンテキスト劣化検知
- Governance Module: エージェント間の合意形成

### 3.4 type: ui（UIモジュール / プラグイン共通）

UIモジュール・プラグインはイベントを購読して表示・操作を行う。コアの内部実装を知らない。

| 権限 | 説明 |
|------|------|
| イベント購読 | Event Store からイベントを受信し表示 |
| Feedback Channel | コアに提案できるが**拒否権なし** |

**Feedback Channel**: UIからコアへの唯一の逆方向経路。型安全なコマンドのみ通過する。

```bash
# handler.sh内でフィードバックを送信
tanebi_feedback "approve_plan" '{"approved": true}'
```

**現在のUIモジュール**:
- progress / approval / cost / evolution / history（Section 5.2〜5.6）

**ユーザ作成のプラグイン**も type: ui として同じ仕組みで動作する。
ただしモジュールと異なり、TANEBI のアーキテクチャが存在を前提としない。

### 3.5 ライフサイクル（モジュール・プラグイン共通）

```
┌──────────┐
│ on_init  │ ← TANEBI起動時
└────┬─────┘
     ▼
┌──────────────────┐
│  Event Loop      │ ← Event Storeからイベント受信
│  on_event(t, f)  │
└────┬─────────────┘
     │  (TANEBI停止時)
     ▼
┌────────────┐
│ on_destroy │
└────────────┘
```

コアモジュールは Event Loop に加え、hooks フィールドで定義されたフックが Core のフロー決定ロジックから直接呼び出される。

---

## 4. イベント駆動アーキテクチャ

### 4.1 設計思想

TANEBI Core と Executor は **Event Store を介してのみ通信** する。

```
Core                        Event Store                      Executor
  │                              │                              │
  │── decompose.requested ──────▶│                              │
  │                              │◀── (Executorが読み取り) ─────│
  │                              │                              │  Decomposer実行
  │                              │◀── task.decomposed ──────────│
  │◀── (Coreが読み取り) ────────│                              │
  │                              │                              │
  │── execute.requested ────────▶│                              │
  │                              │◀── (Executorが読み取り) ─────│
  │                              │                              │  Worker実行
  │                              │◀── worker.completed ─────────│
  │◀── (Coreが読み取り) ────────│                              │
  │                              │                              │
```

- **Core は Executor を知らない**: `*.requested` イベントを発行するだけ。誰がどう処理するかは関知しない
- **Executor は Core を知らない**: `*.requested` イベントを読み、処理し、`*.completed` イベントを返すだけ
- **イベントスキーマが契約**: 名前・ペイロード構造は TANEBI が定義する。双方はこのスキーマだけを知っていればよい
- **transport層は関知しない**: ファイル / Redis / WebSocket 等は Event Store の実装詳細

### 4.2 イベントカタログ

イベントは大きく3種類に分かれる:

- **`*.requested`** — Core が Executor に処理を依頼するイベント（Core → Executor）
- **`*.completed` / `*.created` 等** — 処理結果を報告するイベント（Executor → Core、または Core 内部）
- **システムイベント** — Module / Plugin が購読する観測イベント

#### Core → Executor（依頼イベント）

| イベント名 | 発火元 | ペイロード |
|-----------|-------|-----------|
| `decompose.requested` | Core（task.created 受信後） | `{ cmd_id, request_path, persona_list, plan_output_path }` |
| `execute.requested` | Core（task.decomposed 受信後） | `{ cmd_id, subtask_id, subtask_file, persona_file, output_path, wave }` |
| `aggregate.requested` | Core（全 worker.completed 受信後） | `{ cmd_id, results_dir, report_path }` |

#### Executor → Core（完了イベント）

| イベント名 | 発火元 | ペイロード |
|-----------|-------|-----------|
| `task.created` | UI / CLI（リクエスト登録時） | `{ cmd_id, request_summary, timestamp }` |
| `task.decomposed` | Executor（Decomposer完了後） | `{ cmd_id, plan: { subtasks[], waves, persona_assignments[] } }` |
| `worker.started` | Executor（Worker起動時） | `{ cmd_id, subtask_id, persona_id, wave }` |
| `worker.progress` | Executor（Worker中間出力時） | `{ cmd_id, subtask_id, message, percent? }` |
| `worker.completed` | Executor（Worker完了時） | `{ cmd_id, subtask_id, status, quality, domain }` |
| `wave.completed` | Core（Wave内全Worker完了検知時） | `{ cmd_id, wave, results_summary }` |
| `task.aggregated` | Executor（Aggregator完了後） | `{ cmd_id, report_path, quality_summary }` |

#### 進化イベント

| イベント名 | 発火タイミング | ペイロード |
|-----------|--------------|-----------|
| `evolution.started` | evolve.sh開始時 | `{ cmd_id }` |
| `evolution.persona_updated` | Persona更新時 | `{ persona_id, field, old_value, new_value, reason }` |
| `evolution.few_shot_registered` | Few-Shot登録時 | `{ domain, subtask_id, quality }` |
| `evolution.completed` | evolve.sh完了時 | `{ cmd_id, personas_updated[], few_shots_added }` |

#### システムイベント

| イベント名 | 発火タイミング | ペイロード |
|-----------|--------------|-----------|
| `trust.check` | Trust Module判定時 | `{ persona_id, task_risk, decision: allow/deny }` |
| `cost.token_used` | トークン消費推定時 | `{ cmd_id, subtask_id?, tokens_estimated }` |
| `error.worker_failed` | Worker失敗時 | `{ cmd_id, subtask_id, error_detail }` |
| `approval.requested` | 承認待ち時 | `{ cmd_id, approval_type, data, timeout_seconds? }` |

### 4.3 イベントペイロードスキーマ

```yaml
# events/schema.yaml
events:
  # --- Core → Executor（依頼） ---
  decompose.requested:
    cmd_id: string
    request_path: string      # work/cmd_NNN/request.md
    persona_list: string      # カンマ区切りのPersona ID一覧
    plan_output_path: string  # work/cmd_NNN/plan.md
    timestamp: string

  execute.requested:
    cmd_id: string
    subtask_id: string
    subtask_file: string      # work/cmd_NNN/results/subtask_NNN.md の入力定義
    persona_file: string      # personas/active/{id}.yaml
    output_path: string       # work/cmd_NNN/results/subtask_NNN.md
    wave: integer
    timestamp: string

  aggregate.requested:
    cmd_id: string
    results_dir: string       # work/cmd_NNN/results/
    report_path: string       # work/cmd_NNN/report.md
    timestamp: string

  # --- Executor → Core（完了） ---
  task.created:
    cmd_id: string
    request_summary: string
    timestamp: string         # ISO8601

  task.decomposed:
    cmd_id: string
    plan:
      subtasks: array
      waves: integer
      persona_assignments: array

  worker.completed:
    cmd_id: string
    subtask_id: string
    status: enum[success, failure]
    quality: enum[GREEN, YELLOW, RED]
    domain: string

  # --- 内部観測イベント ---
  evolution.persona_updated:
    persona_id: string
    field: string             # e.g. "behavior.risk_tolerance"
    old_value: number
    new_value: number
    reason: string

  approval.requested:
    cmd_id: string
    approval_type: enum[plan_review, wave_gate, danger_op, budget_exceeded]
    data: object
    timeout_seconds: number?  # null = 無期限
```

### 4.4 Event Store 実装

ファイルベースの不変イベントログとして実装する。

```
work/cmd_NNN/events/
├── 001_task.created.yaml
├── 002_decompose.requested.yaml      # Core → Executor
├── 003_task.decomposed.yaml          # Executor → Core
├── 004_execute.requested.yaml        # Core → Executor
├── 005_worker.started.yaml
├── 006_worker.completed.yaml         # Executor → Core
├── ...
└── 015_evolution.completed.yaml
```

各ファイルのフォーマット:

```yaml
event:
  id: "evt_004"
  type: "execute.requested"
  timestamp: "2026-03-01T12:05:00Z"
  payload:
    cmd_id: "cmd_001"
    subtask_id: "subtask_001"
    subtask_file: "work/cmd_001/plan_subtasks/subtask_001.md"
    persona_file: "personas/active/backend_specialist_v2.yaml"
    output_path: "work/cmd_001/results/subtask_001.md"
    wave: 1
```

イベント発火:

```bash
bash scripts/emit_event.sh <cmd_dir> <event_type> '<payload_yaml>'
```

### 4.5 Event Store の特性

#### 不変性

イベントは追記のみ。書き換え・削除しない。連番ファイル名（`001_`, `002_`, ...）が順序を保証する。

#### 消費者カーソル

各消費者（Core / Module / Plugin / Executor）は自分がどこまで処理したかを管理する。
同じイベントを複数の消費者が読める。

直列実行の場合（LLM の会話フロー、一本通しのスクリプト等）、処理順序が自然に保証されるため
明示的なカーソル管理は不要。将来的に非同期化する場合にカーソルファイルを導入する。

#### 冪等性

イベント ID（`evt_NNN`）による重複処理の防止。既存の idempotency_key を活用する。

### 4.6 Feedback Channel

UIからコアへの逆方向通信。

#### 許可されるフィードバックコマンド

| コマンド | 送信元 | コアの応答 |
|---------|--------|----------|
| `approve_plan` | approval | Execute開始 |
| `reject_plan` | approval | 修正指示付きで再Decompose |
| `modify_plan` | approval | サブタスク追加/削除/変更 |
| `approve_wave` | approval | 次Wave開始 |
| `abort_task` | approval | タスク全体を中止 |
| `adjust_parameter` | evolution | 行動パラメータの手動調整 |

#### Feedback Channel 実装（claude-native）

```
work/cmd_NNN/feedback/
├── fb_001_approve_plan.yaml
└── fb_002_approve_wave.yaml
```

```yaml
feedback:
  id: "fb_001"
  command: "approve_plan"
  timestamp: "2026-03-01T12:06:00Z"
  source_component: "approval"
  payload:
    approved: true
    modifications: []
```

claude-nativeではClaude Codeのユーザー対話フローをFeedback Channelとして利用する。

---

## 5. 各モジュール仕様

### 5.1 Trust Module (type: core)

信頼スコアに基づく段階的権限委譲。

#### plugin.yaml

```yaml
plugin:
  name: "trust"
  version: "1.0.0"
  type: core
  description: "信頼スコアに基づく段階的権限委譲"

  subscribes_to:
    - event_type: "trust.check"
      handler: "log_trust_decision"

  lifecycle:
    on_init: "on_init"
    on_event: "handle_event"
    on_destroy: "cleanup"

  hooks:
    on_task_assign: "on_task_assign"
    on_task_complete: "on_task_complete"
```

#### handler動作

| フック | 入力 | 動作 | 出力 |
|--------|------|------|------|
| `on_init` | persona_yaml_path | trust_scoreが未設定なら50で初期化 | exit 0 |
| `on_task_assign` | persona_id, risk_level | trust_score < 30 かつ high-risk → deny | exit 0 (allow) / exit 1 (deny) |
| `on_task_complete` | persona_id, status, quality | スコア更新: GREEN +5, YELLOW +2, failure -10 | exit 0 |

#### 信頼スコアの更新ルール

| 結果 | delta |
|------|-------|
| success + GREEN | +5 |
| success + YELLOW | +2 |
| success + RED | +0 |
| failure | -10 |

スコア範囲: 0〜100。初期値: 50。

### 5.2 progress (type: ui)

Worker実行状況のリアルタイム表示。

#### plugin.yaml

```yaml
plugin:
  name: "progress"
  version: "1.0.0"
  type: ui
  description: "Worker実行状況のリアルタイム進捗表示"

  subscribes_to:
    - event_type: "task.decomposed"
      handler: "show_plan_summary"
    - event_type: "worker.started"
      handler: "mark_worker_active"
    - event_type: "worker.progress"
      handler: "update_worker_status"
    - event_type: "worker.completed"
      handler: "mark_worker_done"
    - event_type: "wave.completed"
      handler: "show_wave_summary"
    - event_type: "task.aggregated"
      handler: "show_final_summary"
    - event_type: "error.worker_failed"
      handler: "mark_worker_failed"

  feedback_commands: []

  display:
    type: terminal
    refresh_mode: event_driven
```

#### 表示例

```
━━━ TANEBI Progress: cmd_015 ━━━━━━━━━━━━━━━━━━━━━

Wave 1/3 ████████████████████ 100%
  ✅ subtask_001 (backend_specialist_v2) — GREEN
  ✅ subtask_002 (api_designer_v1)      — GREEN

Wave 2/3 ████████░░░░░░░░░░░░  40%
  🔄 subtask_004 (test_writer_v1)       — in progress
  ⏳ subtask_006 (docs_seed_v1)         — queued

Wave 3/3 ░░░░░░░░░░░░░░░░░░░░  waiting
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

#### 設定項目

| 項目 | デフォルト | 設定方法 |
|------|----------|---------|
| 出力フォーマット | ターミナルテーブル | `plugins/progress/config.yaml` |
| 表示する情報 | 全サブタスク | filter設定で絞り込み |
| 更新頻度 | イベント駆動 | polling に変更可 |

### 5.3 approval (type: ui)

計画承認ゲートと実行中の介入ポイント。

#### plugin.yaml

```yaml
plugin:
  name: "approval"
  version: "1.0.0"
  type: ui
  description: "計画承認ゲートと実行中介入ポイント"

  subscribes_to:
    - event_type: "task.decomposed"
      handler: "present_plan_for_approval"
    - event_type: "wave.completed"
      handler: "wave_gate_check"
    - event_type: "trust.check"
      handler: "show_trust_decision"
    - event_type: "approval.requested"
      handler: "handle_approval_request"

  feedback_commands:
    - command: "approve_plan"
      payload_schema: { approved: boolean, modifications: array? }
    - command: "reject_plan"
      payload_schema: { reason: string, retry: boolean }
    - command: "modify_plan"
      payload_schema: { changes: array }
    - command: "approve_wave"
      payload_schema: { wave: number, approved: boolean }
    - command: "abort_task"
      payload_schema: { reason: string }

  display:
    type: terminal
    refresh_mode: event_driven
```

#### 計画承認ゲート表示例

```
━━━ TANEBI Plan Review: cmd_015 ━━━━━━━━━━━━━━━━━━

📋 実行計画:

| # | サブタスク | Persona | Fitness | Wave |
|---|-----------|---------|---------|------|
| 1 | APIエンドポイント実装 | backend_specialist_v2 | 0.82 | 1 |
| 2 | ユニットテスト作成 | test_writer_v1 | 0.75 | 2 |

承認しますか？ [Y / n / modify]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

#### 設定項目

| 項目 | デフォルト | 設定キー |
|------|----------|---------|
| 計画承認 | 有効 | `plugins.approval.plan_review` |
| Wave間ゲート | 無効 | `plugins.approval.wave_gate` |
| 承認タイムアウト | 無期限 | `plugins.approval.timeout_seconds` |
| 危険操作確認 | 有効 | `plugins.approval.danger_op_confirm` |

### 5.4 cost (type: ui)

トークン消費量のトラッキングと表示。

#### plugin.yaml

```yaml
plugin:
  name: "cost"
  version: "1.0.0"
  type: ui
  description: "トークン消費量トラッキングと表示"

  subscribes_to:
    - event_type: "cost.token_used"
      handler: "accumulate_cost"
    - event_type: "worker.completed"
      handler: "finalize_subtask_cost"
    - event_type: "task.aggregated"
      handler: "show_task_cost_summary"
    - event_type: "evolution.completed"
      handler: "finalize_evolution_cost"

  feedback_commands:
    - command: "adjust_parameter"
      payload_schema: { key: "cost_budget", value: number }

  display:
    type: terminal
    refresh_mode: event_driven
```

#### コストサマリー表示例

```
━━━ TANEBI Cost Report: cmd_015 ━━━━━━━━━━━━━━━━━━

Token Usage (estimated):
  Decompose:  ~1,200 tokens
  Workers:    ~8,500 tokens
  Aggregate:  ~1,500 tokens
  Evolve:     ~300 tokens
  ─────────────────────
  Total:      ~11,500 tokens

Cumulative (this session): ~45,200 tokens
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

#### データ永続化

```yaml
# work/cmd_NNN/cost.yaml
cost:
  cmd_id: "cmd_015"
  timestamp: "2026-03-01T12:30:00Z"
  breakdown:
    decompose: 1200
    workers:
      subtask_001: 2800
      subtask_002: 2200
    aggregate: 1500
    evolve: 300
  total: 11500
```

#### 設定項目

| 項目 | デフォルト | 設定キー |
|------|----------|---------|
| 予算上限 | 無制限 | `plugins.cost.budget` |
| サブタスク別表示 | 有効 | `plugins.cost.show_per_subtask` |
| 累計集計 | 有効 | `plugins.cost.show_cumulative` |

### 5.5 evolution (type: ui)

Persona進化状況・fitness推移の可視化。

#### plugin.yaml

```yaml
plugin:
  name: "evolution"
  version: "1.0.0"
  type: ui
  description: "Persona進化状況・fitness推移の可視化"

  subscribes_to:
    - event_type: "evolution.started"
      handler: "show_evolution_start"
    - event_type: "evolution.persona_updated"
      handler: "show_persona_change"
    - event_type: "evolution.few_shot_registered"
      handler: "show_few_shot_update"
    - event_type: "evolution.completed"
      handler: "show_evolution_summary"

  feedback_commands:
    - command: "adjust_parameter"
      payload_schema: { persona_id: string, field: string, value: number }

  display:
    type: terminal
    refresh_mode: event_driven
```

#### 進化サマリー表示例

```
━━━ TANEBI Evolution Report: cmd_015 ━━━━━━━━━━━━━━

Persona Updates:

  backend_specialist_v2:
    fitness:    0.80 → 0.82 (+0.02)
    tasks:      55 → 57
    success:    0.87 → 0.89
    streak:     3 → 5
    ▸ reinforced: detail_orientation +0.05

Few-Shot Bank:
    + backend/subtask_001 (GREEN) → registered
    Bank size: backend=12, testing=8, frontend=3
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

#### 設定項目

| 項目 | デフォルト | 設定キー |
|------|----------|---------|
| 完了時サマリー表示 | 有効 | `plugins.evolution.show_on_complete` |
| 詳細表示 | 無効 | `plugins.evolution.verbose` |
| fitness推移表示 | 無効 | `plugins.evolution.show_fitness_trend` |

### 5.6 history (type: ui)

過去タスクの検索・閲覧。

#### plugin.yaml

```yaml
plugin:
  name: "history"
  version: "1.0.0"
  type: ui
  description: "過去タスクの検索・閲覧"

  subscribes_to:
    - event_type: "task.aggregated"
      handler: "index_completed_task"

  feedback_commands: []

  display:
    type: terminal
    refresh_mode: manual
```

#### インデックスファイル

```yaml
# work/index.yaml
tasks:
  - cmd_id: "cmd_015"
    date: "2026-03-01"
    request_summary: "APIエンドポイント実装"
    total_subtasks: 4
    succeeded: 4
    quality_summary: { GREEN: 3, YELLOW: 1, RED: 0 }
    domains: [backend, testing, docs]
    personas_used: [backend_specialist_v2, test_writer_v1, docs_seed_v1]
    cost_tokens: 11500
    report_path: "work/cmd_015/report.md"
```

#### CLIアクセス

```bash
tanebi history              # 直近タスク一覧
tanebi history cmd_015      # 特定タスク詳細
tanebi history --domain backend  # ドメインフィルタ
```

---

## 6. Persona 4層モデル

### 6.1 4層構造

```mermaid
graph TD
    L4["Layer 4: Identity（同一性）<br/>名前・口調・アーキタイプ・ベースモデル<br/>変更頻度: 月単位"]
    L3["Layer 3: Knowledge（知識）<br/>ドメイン習熟度・Few-Shot事例・アンチパターン<br/>変更頻度: タスク毎"]
    L2["Layer 2: Behavior（行動特性）<br/>リスク許容度・詳細志向度・速度vs品質<br/>変更頻度: 数タスク毎"]
    L1["Layer 1: Performance（実績）<br/>信頼スコア・成功率・品質平均・連勝記録<br/>変更頻度: タスク毎"]

    L4 --> L3 --> L2 --> L1

    style L4 fill:#4a90d9,color:#fff
    style L3 fill:#7ab648,color:#fff
    style L2 fill:#f5a623,color:#fff
    style L1 fill:#d0021b,color:#fff
```

### 6.2 Persona YAMLスキーマ

```yaml
# personas/active/agent_alpha_v3.yaml
persona:
  id: "agent_alpha_v3"
  base_model: "claude-sonnet-4-6"
  version: 3
  created_at: "2026-03-01T12:00:00"
  parent_version: "agent_alpha_v2"
  lineage: ["agent_alpha_v1", "agent_alpha_v2"]

  # Layer 4: Identity（同一性）
  identity:
    name: "鉄壁のDB職人"
    speech_style: "冷静沈着"
    archetype: specialist     # specialist | generalist | hybrid
    origin: evolved           # seeded | copied | merged | evolved

  # Layer 3: Knowledge（知識）
  knowledge:
    domains:
      - name: database_design
        proficiency: 0.87     # 0.0〜1.0
        task_count: 42
        last_updated: "2026-03-15"
      - name: api_design
        proficiency: 0.65
        task_count: 15
        last_updated: "2026-03-10"
    few_shot_refs:
      - "episodic:db:task042_migration_success"
      - "episodic:db:task067_index_optimization"
    anti_patterns:
      - pattern: "N+1クエリの見落とし"
        detected_count: 3
        correction: "JOINまたはeager loadを明示的に検討"

  # Layer 2: Behavior（行動特性）
  behavior:
    risk_tolerance: 0.4       # 0=保守的, 1=積極的
    detail_orientation: 0.85  # 0=概略重視, 1=細部重視
    speed_vs_quality: 0.3     # 0=品質最優先, 1=速度最優先
    autonomy_preference: 0.6
    communication_density: 0.7

  # Layer 1: Performance（実績）
  performance:
    trust_score: 72           # 0-100, Trust Module管理
    total_tasks: 57
    success_rate: 0.89
    avg_quality: GREEN
    specialization_index: 0.75
    streak:
      current: 5
      best: 12
    domain_success_rates:
      database_design: 0.95
      api_design: 0.80
      frontend: 0.45

  # Evolution Metadata
  evolution:
    generation: 3
    fitness_score: 0.82
    last_evolution_event:
      type: trait_reinforcement
      field: detail_orientation
      delta: +0.05
      trigger: "task_089: 詳細レビューで品質向上を確認"
      timestamp: "2026-03-15T14:00:00"
    mutations_log:
      - { gen: 1, type: seed, note: "初期シード" }
      - { gen: 2, type: reinforcement, field: "database_design.proficiency", delta: +0.12 }
      - { gen: 3, type: reinforcement, field: "detail_orientation", delta: +0.05 }
    crossover_history: []
```

### 6.3 粒度の定義

| 粒度 | 用途 | 含む層 | サイズ目安 |
|------|------|-------|----------|
| **Full** | 完全バックアップ・移植 | Layer 1-4 全て + Evolution Metadata | ~200行 YAML |
| **Portable** | 他エージェントへのコピー・合成 | Layer 2-4（Performance除外） | ~100行 YAML |
| **Seed** | 新エージェント初期化用 | Layer 4 + Behavior初期値のみ | ~30行 YAML |

Portable粒度がPerformanceを除外する理由: 信頼スコアや成功率は「そのエージェントがその環境で積んだ実績」であり、別のエージェントにコピーすべきでない。

### 6.4 ポータビリティ操作

| 操作 | 説明 |
|------|------|
| **Copy（Clone）** | Portable粒度で複製。Performanceは白紙スタート |
| **Merge** | 2体の人格を加重結合し新しい人格を生成（非破壊操作） |
| **Snapshot** | Full粒度で`personas/history/`に保存。5タスクごとに自動実行 |
| **Restore** | スナップショットからPersonaを復元 |
| **Library** | `personas/library/`にテンプレート/スナップショットを蓄積 |

---

## 7. 進化エンジン

### 7.1 二重進化アーキテクチャ

```mermaid
graph LR
    subgraph DualEvo["二重進化"]
        subgraph IE["Individual Evolution（個体）"]
            IE_ops["Selection / Mutation<br/>Crossover / Fitness Eval"]
        end
        subgraph KE["Knowledge Evolution（知識）"]
            KE_ops["Few-Shot Bank<br/>Episode Memory<br/>Knowledge GC<br/>Pattern Extraction"]
        end
        IE_ops -- "成功パターン →" --> KE_ops
        KE_ops -- "← 知識フィードバック" --> IE_ops
    end
    TC["タスク完了"] --> IE_ops
    TC --> KE_ops
```

**統合のメカニズム**:

1. **タスク完了時**（毎回）: Persona YAML更新 + Few-Shot Bank登録
2. **成功パターン検出時**: 特性のreinforcement + 共有知識に追加
3. **失敗検出時**: 特性のcorrection + anti_pattern追加 + ネガティブ事例登録
4. **月次進化イベント**: トップパフォーマーのCrossover + 世代別GC

### 7.2 適応度関数

```yaml
fitness_function:
  formula: |
    fitness = w1 * quality_score + w2 * completion_rate + w3 * efficiency + w4 * growth_rate

  weights:
    w1: 0.35    # 品質スコア（GREEN=1.0, YELLOW=0.5, RED=0.0）
    w2: 0.30    # タスク完了率
    w3: 0.20    # 効率（duration_estimate: short=1.0, medium=0.7, long=0.4）
    w4: 0.15    # 成長率（直近タスクの前半後半品質比較）

  window: 20    # 直近20タスクのスライディングウィンドウ
```

実装: `scripts/_fitness.py` の `calculate_fitness()` 関数。`work/cmd_*/results/*.md` のYAML frontmatterからタスク履歴を収集し、スライディングウィンドウで計算する。

### 7.3 Few-Shot Bank

成功事例を自動蓄積し、Workerに注入する共有知識ベース。

```
knowledge/few_shot_bank/
├── backend/
│   ├── task042_migration_success.md
│   └── task067_index_optimization.md
├── testing/
│   └── task055_e2e_pattern.md
└── frontend/
    └── task030_component_design.md
```

- **自動登録条件**: status=success かつ quality=GREEN
- **ドメインあたり上限**: config.yamlで設定（デフォルト100件）
- **Worker注入**: Decomposerがサブタスクのドメインに基づき関連Few-Shotを選択し、Workerテンプレートに注入

### 7.4 Persona自動更新フロー

`evolve.sh` が実行する6段階の進化ステップ:

| # | ステップ | 対象 | 説明 |
|---|---------|------|------|
| 1 | パフォーマンス更新 | `performance` | `total_tasks`, `success_rate`, `last_task_date` を更新 |
| 2 | 失敗補正 | `knowledge.domains` | 失敗ドメインの `proficiency` を -0.02 調整 |
| 3 | 行動パラメータ調整 | `behavior` | GREEN/RED品質に基づき `risk_tolerance` を微調整 |
| 4 | 適応度スコア計算 | `evolution.fitness_score` | `_fitness.py` で計算・更新 |
| 5 | 自動スナップショット | `personas/history/` | `total_tasks` が5の倍数で保存 |
| 6 | Few-Shot自動登録 | `knowledge/few_shot_bank/` | GREEN+success を登録 |

### 7.5 進化の速度（目安）

| フェーズ | タスク数 | 期待される変化 |
|---------|---------|-------------|
| 分化期 | 0-50 | ドメイン習熟度に差が出始める |
| 特化期 | 50-200 | specialization_index 0.5超のエージェントが出現 |
| 安定期 | 200+ | 各エージェントのニッチが確立。交叉が主な進化源 |

---

## 8. Executor インターフェース

### 8.1 設計思想

TANEBI Core は `*.requested` イベントを発行し、`*.completed` イベントを受け取る。
その間の実行を担うのが **Executor** である。

Core は Executor の実装を一切知らない。Event Store 上のイベントスキーマだけが契約。

| 設計原則 | 説明 |
|---------|------|
| AP-1: Core はイベントだけを知る | `*.requested` を発行し `*.completed` を待つ。実行方式を知らない |
| AP-2: Executor はイベントだけを知る | `*.requested` を読み処理し `*.completed` を返す。Core の内部を知らない |
| AP-3: イベントスキーマが契約 | Section 4.3 で定義されたスキーマが唯一の接点 |
| AP-4: Executor は自由に構成可能 | Task tool / subprocess / Docker / Lambda — 技術選択は Executor の裁量 |
| AP-5: データ交換はYAML契約 | イベントペイロードは全て YAML スキーマで定義 |

### 8.2 Executor の契約

Executor は以下の契約を守る:

1. **`*.requested` イベントを処理する**: Event Store から `decompose.requested`, `execute.requested`, `aggregate.requested` を読み取り、対応する処理を実行する
2. **`*.completed` イベントを返す**: 処理完了後、`task.decomposed`, `worker.completed`, `task.aggregated` 等を Event Store に書き込む
3. **イベントスキーマに従う**: Section 4.3 で定義されたペイロード構造を守る
4. **成果物をファイルとして残す**: plan.md, results/*.md, report.md 等をイベントで指定されたパスに書き出す

これだけが契約。どんな技術で処理するか、何を内部で使うかは Executor の自由。

TANEBI はリファレンス実装を `scripts/` に同梱するが、使用は任意。
環境別の構成例は `docs/adapter-guide.md` を参照。

### 8.3 エラーハンドリング

| イベント | 失敗時の挙動 | リカバリー |
|---------|------------|-----------|
| `decompose.requested` | plan.md 生成されない | ユーザーにエラー報告 |
| `execute.requested` | result YAML `status: failure` | Aggregator が集計。進化エンジンが失敗補正 |
| `aggregate.requested` | report.md 生成されない | ユーザーにエラー報告 |
| イベント発火失敗 | タイムアウト | 非致命的（ログ記録のみ） |

失敗は破棄されない。すべて記録され、進化エンジンのフィードバックループに組み込まれる。

---

## 9. プリセット構成

### 9.1 minimal

初心者・シンプル志向向け。

```yaml
# config.yaml
tanebi:
  plugins:
    preset: "minimal"
```

| プラグイン | 状態 | 備考 |
|-----------|------|------|
| trust | 有効 | コアモジュール。常時有効 |
| progress | 無効 | |
| approval | 有効 | plan_review のみ |
| cost | 無効 | |
| evolution | 無効 | 進化は裏で動くがUI非表示 |
| history | 無効 | |

### 9.2 standard

日常利用向け。進捗と承認のバランス型。

```yaml
tanebi:
  plugins:
    preset: "standard"
```

| プラグイン | 状態 | 備考 |
|-----------|------|------|
| trust | 有効 | |
| progress | 有効 | Persona情報表示あり |
| approval | 有効 | plan_review有効、wave_gate無効 |
| cost | 有効 | サブタスク別・累計表示 |
| evolution | 有効 | 完了時サマリー表示 |
| history | 無効 | CLIで手動確認 |

### 9.3 full

パワーユーザー向け。全機能有効。

```yaml
tanebi:
  plugins:
    preset: "full"
```

| プラグイン | 状態 | 備考 |
|-----------|------|------|
| trust | 有効 | |
| progress | 有効 | Few-Shot利用状況も表示 |
| approval | 有効 | plan_review + wave_gate有効 |
| cost | 有効 | Persona別コスト表示 |
| evolution | 有効 | 詳細+fitness推移表示 |
| history | 有効 | 自動インデックス+検索 |

### 9.4 config.yaml 完全構造

```yaml
tanebi:
  version: "1.0"

  # === モジュール・プラグイン設定 ===
  plugins:
    preset: "standard"         # minimal | standard | full | custom

    # custom時の個別設定
    trust:
      enabled: true
    progress:
      enabled: true
    approval:
      enabled: true
      plan_review: true
      wave_gate: false
      timeout_seconds: null
      danger_op_confirm: true
    cost:
      enabled: true
      budget: null
      show_per_subtask: true
      show_cumulative: true
    evolution:
      enabled: true
      show_on_complete: true
      verbose: false
    history:
      enabled: false
      auto_index: true

  # === パス設定 ===
  paths:
    work_dir: "work"
    persona_dir: "personas/active"
    library_dir: "personas/library"
    history_dir: "personas/history"
    knowledge_dir: "knowledge"
    few_shot_dir: "knowledge/few_shot_bank"
    episode_dir: "knowledge/episodes"

  # === 実行設定 ===
  execution:
    max_parallel_workers: 5
    worker_max_turns: 30
    default_model: "claude-sonnet-4-6"

  # === 進化エンジン設定 ===
  evolution:
    fitness_weights:
      quality_score: 0.35
      completion_rate: 0.30
      efficiency: 0.20
      growth_rate: 0.15
    fitness_window: 20
    few_shot_max_per_domain: 100
    snapshot_interval: 5
```

---

## 10. Post-MVPロードマップ

### Phase 1: 統一プラグインシステム基盤 + progress + approval

**目標**: プラグインフレームワークを実装し、progress と approval を動作させる。

**成果物**:
- `scripts/emit_event.sh` — イベント発火
- `scripts/component_loader.sh` — プラグイン読み込み・イベントルーティング
- `scripts/send_feedback.sh` — フィードバック送信
- `events/schema.yaml` — イベントスキーマ定義
- `plugins/progress/` — progressプラグイン
- `plugins/approval/` — approvalプラグイン
- `plugins/_template/` — テンプレート
- CLAUDE.md改修 — Decompose後の承認ゲート組み込み
- `templates/worker_base.md` 改修 — `worker.progress` イベント発火追加
- config.yaml改修 — `plugins` セクション追加

### Phase 2: cost + evolution可視化

**目標**: cost と evolution プラグインを実装し、TANEBIの独自価値を可視化する。

**成果物**:
- `plugins/cost/` — costプラグイン
- `plugins/evolution/` — evolutionプラグイン
- `scripts/estimate_cost.sh` — トークン推定
- `tanebi` CLI拡張 — `tanebi evolution`, `tanebi cost` サブコマンド
- `evolve.sh` 改修 — `evolution.*` イベント発火追加
- Persona YAMLスキーマ拡張 — `performance.cost_metrics` 追加
- `work/cmd_NNN/cost.yaml` — タスク毎コスト記録

**前提条件**: Phase 1 完了

### Phase 3.5: コマンド設定モデル基盤構築

**目標**: コマンド設定モデルの基盤を実装し、config.yamlのPort定義でアダプター構成を決定できるようにする。

**成果物**:
- `scripts/command_executor.sh` — コマンド実行エンジン（プレースホルダー置換 + shell exec）
- `scripts/tanebi-callback.sh` — Inbound Callbackスクリプト（Worker→TANEBIへの通知）
- config.yaml への `tanebi.ports` セクション追加
- `builtin:task_tool` メカニズム実装（claude-native用）
- docs/ 再構成（adapter-guide.md昇格）
- Python venv 基盤

**前提条件**: Phase 2 完了

### Phase 3 → Phase 4 に繰り上げ: history + CLI整備

**目標**: historyプラグインと `tanebi` CLIの充実。

**成果物**:
- `plugins/history/` — historyプラグイン
- `work/index.yaml` — タスク履歴インデックス
- `tanebi` CLI:
  - `tanebi history [cmd_id]`
  - `tanebi persona list / inspect / clone / merge`
  - `tanebi config <key> <value>`
  - `tanebi status`

**前提条件**: Phase 2 完了

### Phase 5: エラーリカバリー + エコシステム

**目標**: Worker失敗時の自動リトライ、サードパーティプラグインサポート。

**成果物**:
- エラーリカバリー: Worker失敗 → 同Persona再試行（最大1回） → generalistフォールバック
- Wave間ゲート本格実装: plan.yamlに `approval_gate: true` を宣言的定義
- Few-Shot Bank検索性向上: `knowledge/few_shot_bank/index.yaml` メタデータインデックス
- プラグインエコシステム:
  - `tanebi plugin install <url>`
  - `tanebi plugin create <name>`
  - プラグインバリデーター

**前提条件**: Phase 4 完了

---

## 11. ディレクトリ構造

```
tanebi/
├── CLAUDE.md                       # claude-native 用フロー決定ロジック
├── config.yaml                     # 全体設定
│
├── personas/
│   ├── active/                     # アクティブPersona
│   │   ├── generalist_v1.yaml
│   │   └── backend_specialist_v2.yaml
│   ├── library/                    # テンプレート・スナップショット
│   │   └── seeds/
│   │       ├── backend_seed.yaml
│   │       ├── frontend_seed.yaml
│   │       ├── testing_seed.yaml
│   │       ├── docs_seed.yaml
│   │       └── devops_seed.yaml
│   └── history/                    # 自動スナップショット
│
├── knowledge/
│   ├── few_shot_bank/              # 成功事例バンク
│   │   ├── backend/
│   │   ├── frontend/
│   │   └── testing/
│   └── episodes/                   # エピソード記録
│
├── work/                           # タスク作業ディレクトリ
│   ├── cmd_001/
│   │   ├── request.md              # ユーザー依頼
│   │   ├── plan.md                 # Decomposer出力
│   │   ├── results/                # Worker出力
│   │   │   ├── subtask_001.md
│   │   │   └── subtask_002.md
│   │   ├── report.md               # Aggregator統合レポート
│   │   ├── events/                 # イベントログ
│   │   │   ├── 001_task.created.yaml
│   │   │   └── ...
│   │   ├── feedback/               # フィードバック
│   │   └── cost.yaml               # コスト記録
│   └── index.yaml                  # タスク履歴インデックス
│
├── plugins/                        # モジュール + プラグイン（共通ディレクトリ）
│   ├── trust/                      # Module (core) — セキュリティ判定
│   │   ├── plugin.yaml
│   │   ├── handler.sh
│   │   └── config.yaml
│   ├── progress/                   # Module (ui) — 進捗表示
│   ├── approval/                   # Module (ui) — 承認ゲート
│   ├── cost/                       # Module (ui) — コスト集計
│   ├── evolution/                  # Module (ui) — 進化可視化
│   ├── history/                    # Module (ui) — 履歴検索
│   └── _template/                  # テンプレート（Module/Plugin 共通）
│
├── events/
│   └── schema.yaml                 # イベントスキーマ定義
│
├── templates/                      # Decomposer/Worker/Aggregator テンプレート
│   ├── decomposer.md
│   ├── worker_base.md
│   └── aggregator.md
│
├── scripts/
│   ├── new_cmd.sh                  # タスク作業ディレクトリ作成
│   ├── command_executor.sh         # Executor リファレンス実装（subprocess向け）
│   ├── subprocess_worker.sh        # subprocess用 Decomposer/Worker ブリッジ
│   ├── tanebi-callback.sh          # Inbound Callbackスクリプト
│   ├── evolve.sh                   # 進化エンジン実行（Core層）
│   ├── _evolve_helper.py           # 進化ヘルパー
│   ├── _fitness.py                 # 適応度関数
│   ├── persona_ops.sh              # Persona操作（clone/merge）
│   ├── emit_event.sh               # イベント発火（Event Store 書き込み）
│   ├── component_loader.sh         # モジュール/プラグインローダー（Core層）
│   ├── send_feedback.sh            # フィードバック送信
│   ├── estimate_cost.sh            # コスト推定
│   └── tanebi_config.sh            # パス定数
│
└── docs/
    ├── design.md                   # 本文書
    ├── adapter-guide.md            # アダプター構成ガイド（環境別config.yaml例）
    └── archive/                    # 旧設計文書アーカイブ
```
