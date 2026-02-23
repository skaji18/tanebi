# TANEBI Executor 実装ガイド

> Event Store スキーマ準拠 / 環境別実装リファレンス

> 日付: 2026-02-22

---

## 1. 概要 — Executor とは

### 1.1 TANEBI の三者分離アーキテクチャ

TANEBI は **Core**・**Event Store**・**Executor** の三者に明確に分離されている。

```
 TANEBI Core                     Event Store                    Executor
 ┌────────────────────┐     ┌─────────────────────┐     ┌────────────────────┐
 │                    │     │  Immutable Event Log │     │                    │
 │  Evolution Core    │     │                     │     │  *.requested を読み │
 │  Persona Store     │     │  *.requested →→→→→→→│→→→→→│  処理して           │
 │  Event Store API   │     │                     │     │  *.completed を返す │
 │                    │     │  *.completed ←←←←←←←│←←←←←│                    │
 │  フロー決定ロジック │     │  events/            │     │  実装技術は自由:    │
 │  （次に何をするか  │     │    001_task.created  │     │  LLM / shell /     │
 │   を判断）         │     │    002_decompose     │     │  Docker / Lambda / │
 │                    │     │      .requested      │     │  何でもよい        │
 │  ※ Core は        │     │    003_task          │     │                    │
 │    Executor を     │     │      .decomposed     │     │  ※ Executor は     │
 │    知らない        │     │    ...               │     │    Core を知らない  │
 └────────────────────┘     └─────────────────────┘     └────────────────────┘
```

- **Core** は何をするか（フロー決定）を知っている。どうやるかは知らない。
- **Executor** は何をするかは知らない。`*.requested` イベントを処理して `*.completed` を返すだけ。
- **Event Store** が両者をつなぐ唯一の接点。

**コアが強いからこそ Executor を自由にできる。** Core の進化エンジン・Persona 管理・フロー決定は Executor の実装技術に依存しない。そのため Executor を Task tool / subprocess / Docker / Lambda 等に自由に差し替えられる。

### 1.2 Executor の役割

Executor は次の3種のイベントを処理する責務を持つ:

| 入力イベント | 処理内容 | 出力イベント |
|------------|---------|------------|
| `decompose.requested` | ユーザー依頼をサブタスクに分解 | `task.decomposed` |
| `execute.requested` | 1つのサブタスクを実行 | `worker.completed` |
| `aggregate.requested` | 全サブタスク結果を集約 | `task.aggregated` |

Executor は LLM で処理しても、シェルスクリプトで処理しても、コンテナで処理しても構わない。
TANEBI はリファレンス実装として `scripts/command_executor.sh` + `scripts/subprocess_worker.sh` を同梱するが、これを使う義務はない。

### 1.3 設計原則（AP-1〜AP-5）

本ドキュメントは以下の設計原則に基づく。詳細は `docs/design.md` Section 8.1 を参照。

| # | 原則 | 説明 |
|---|------|------|
| **AP-1** | **Core はイベントだけを知る** | `*.requested` を発行し `*.completed` を待つ。実行方式を知らない |
| **AP-2** | **Executor はイベントだけを知る** | `*.requested` を読み処理し `*.completed` を返す。Core の内部を知らない |
| **AP-3** | **イベントスキーマが契約** | `events/schema.yaml` で定義されたスキーマが唯一の接点 |
| **AP-4** | **Executor は自由に構成可能** | Task tool / subprocess / Docker / Lambda — 技術選択は Executor の裁量 |
| **AP-5** | **データ交換は YAML 契約** | イベントペイロードは全て YAML スキーマで定義 |

### 1.4 本ドキュメントの対象読者

- TANEBI の Executor を独自環境（Docker / Lambda / Cloud Run 等）で実装したい開発者
- subprocess リファレンス実装（`command_executor.sh` + `subprocess_worker.sh`）を理解したい開発者
- TANEBI のイベント駆動フローを理解したい開発者

**前提知識**: `docs/design.md` の Section 2・4・8 を先に読むことを推奨する。

---

## 2. Executor 契約

### 2.1 4 つの契約

Executor は以下の4つの契約を守らなければならない。それ以外は自由。

**1. `*.requested` イベントを処理する**

Event Store から `decompose.requested`・`execute.requested`・`aggregate.requested` を読み取り、対応する処理を実行する。

**2. `*.completed` イベントを返す**

処理完了後、`task.decomposed`・`worker.completed`・`task.aggregated` 等を Event Store に書き込む。

**3. イベントスキーマに従う**

`events/schema.yaml` で定義されたペイロード構造を守る（Section 6 参照）。

**4. 成果物をファイルとして残す**

`plan.md`・`results/*.md`・`report.md` 等をイベントで指定されたパスに書き出す。

これだけが契約。どんな技術で処理するか、何を内部で使うかは Executor の自由。

### 2.2 Event Store の構造

Event Store はファイルベースの不変イベントログ。各コマンドのイベントは独立したディレクトリに格納される。

```
work/cmd_NNN/events/
├── 001_task.created.yaml
├── 002_decompose.requested.yaml      # Core → Executor
├── 003_task.decomposed.yaml          # Executor → Core
├── 004_execute.requested.yaml        # Core → Executor
├── 005_worker.started.yaml
├── 006_worker.completed.yaml         # Executor → Core
├── 007_execute.requested.yaml        # Core → Executor（Wave 2）
├── 008_worker.completed.yaml
├── 009_wave.completed.yaml
├── 010_aggregate.requested.yaml      # Core → Executor
└── 011_task.aggregated.yaml          # Executor → Core
```

#### ファイル命名規則

```
NNN_event.type.yaml
^^^  ^^^^^^^^^^
 |   イベント名（ドット区切りをそのまま保持）
 3桁連番（001 始まり）
```

**重要な特性**:
- イベントは追記のみ。書き換え・削除しない
- 連番ファイル名（`001_`, `002_`, ...）が発行順序を保証する
- 複数の消費者（Core / Executor）が同じイベントを読める

### 2.3 イベント発火: emit_event.sh

Executor がイベントを発行する際は `scripts/emit_event.sh` を使う:

```bash
bash scripts/emit_event.sh <cmd_dir> <event_type> '<payload_yaml>'
```

**例: worker.completed を発行**

```bash
bash scripts/emit_event.sh "work/cmd_001" "worker.completed" "
cmd_id: cmd_001
subtask_id: subtask_001
status: success
quality: GREEN
domain: backend
"
```

**例: task.decomposed を発行**

```bash
bash scripts/emit_event.sh "work/cmd_001" "task.decomposed" "
cmd_id: cmd_001
plan:
  subtasks:
    - id: subtask_001
      description: APIエンドポイント実装
      persona: backend_specialist_v2
      wave: 1
    - id: subtask_002
      description: ユニットテスト作成
      persona: test_writer_v1
      wave: 2
  waves: 2
  persona_assignments:
    - subtask_id: subtask_001
      persona_id: backend_specialist_v2
    - subtask_id: subtask_002
      persona_id: test_writer_v1
"
```

`emit_event.sh` はイベントを Event Store に書き込む。Python API（`src/tanebi/core/event_store.py` の `emit_event()`）も同等機能を提供する（Section 4.7 参照）。

### 2.4 イベントファイル形式

各イベントファイルの構造:

```yaml
event_type: execute.requested
timestamp: "2026-03-01T12:05:00"
cmd_dir: work/cmd_001
payload:
  cmd_id: cmd_001
  subtask_id: subtask_001
  subtask_file: work/cmd_001/plan_subtasks/subtask_001.md
  persona_file: personas/active/backend_specialist_v2.yaml
  output_path: work/cmd_001/results/subtask_001.md
  wave: 1
```

Executor は `payload` セクションを読んで処理を行う。`cmd_dir` は Event Store のルートパス。

### 2.5 フロー全体像

```
Core                     Event Store              Executor
  │                           │                      │
  │── decompose.requested ───▶│                      │
  │                           │◀─── (読み取り) ──────│
  │                           │                      │  Decomposer実行
  │                           │                      │  plan.md 生成
  │                           │◀── task.decomposed ──│
  │◀─── (読み取り) ───────────│                      │
  │                           │                      │
  │── execute.requested ─────▶│  (Wave 1, 複数並列)  │
  │                           │◀─── (読み取り) ──────│
  │                           │                      │  Worker 実行
  │                           │                      │  results/*.md 生成
  │                           │◀── worker.completed ─│
  │◀─── (読み取り) ───────────│                      │
  │                           │                      │
  │── aggregate.requested ───▶│                      │
  │                           │◀─── (読み取り) ──────│
  │                           │                      │  Aggregator 実行
  │                           │                      │  report.md 生成
  │                           │◀── task.aggregated ──│
  │◀─── (読み取り) ───────────│                      │
```

---

## 3. config.yaml 設定

### 3.1 Executor に関連する設定セクション

Executor の環境を問わず、TANEBI の動作は `config.yaml` の次のセクションで制御する。

```yaml
tanebi:
  version: "1.0"

  # === Store設定 ===
  storage:
    event_store:
      type: file              # file (default)
    persona_store:
      type: file              # file (default)
    knowledge_store:
      type: file              # file (default)

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

### 3.2 設定項目の説明

#### tanebi.storage

Event Store・Persona Store・Knowledge Store のバックエンド設定。
現在は `file` のみサポート。Executor はこの設定を直接参照する必要はない。

| キー | 説明 | デフォルト |
|------|------|----------|
| `event_store.type` | Event Store バックエンド | `file` |
| `persona_store.type` | Persona Store バックエンド | `file` |
| `knowledge_store.type` | Knowledge Store バックエンド | `file` |

#### tanebi.execution

| キー | 説明 | デフォルト |
|------|------|----------|
| `max_parallel_workers` | Wave 内の最大並列 Worker 数 | 5 |
| `worker_max_turns` | Worker の最大ターン数（LLM 対話上限） | 30 |
| `default_model` | デフォルトモデル ID | `claude-sonnet-4-6` |

#### tanebi.paths

Executor が Event Store やファイルを読み書きする際のパス起点。
サブディレクトリ構成を変更した場合はここを更新する。

#### tanebi.evolution

進化エンジンの設定。Executor の実装環境によらず同じパラメータを使用する。

### 3.3 環境別の考慮点

| 環境 | 考慮点 |
|------|--------|
| subprocess | `TANEBI_ROOT` をプロジェクトルートに設定。全パスは相対パスでも動作 |
| Docker | `work/`・`personas/`・`knowledge/` をボリュームマウント。コンテナ終了後もデータが残ることを確認 |
| Lambda/Cloud | エフェメラル環境では `paths` を S3 等の永続ストレージに対応させた形で運用する（Section 5.3 参照） |

---

## 4. subprocess Executor 実装（リファレンス）

### 4.1 リファレンス実装の概要

TANEBI は subprocess 向けの Executor リファレンス実装を `scripts/` に同梱している。

| スクリプト | 役割 | 位置づけ |
|-----------|------|---------|
| `scripts/command_executor.sh` | config.yaml 設定を読み取り subprocess_worker.sh へディスパッチ | **Executor**（Core 外部） |
| `scripts/subprocess_worker.sh` | `claude -p` で Decomposer / Worker を起動 | **Executor**（Core 外部） |
| `scripts/emit_event.sh` | Event Store にイベントを書き込む | Event Store インターフェース（Core / Executor 共用） |

**重要**: `command_executor.sh` は TANEBI Core の一部ではない。**Executor 側のリファレンス実装**である。
Core は `emit_event.sh` を通じて `*.requested` イベントを Event Store に書き込むだけ。
`command_executor.sh` はその後段で動作する。

### 4.2 command_executor.sh の動作

```
Usage:
  bash scripts/command_executor.sh [--dry-run] <port_name> [key=value ...]
```

**ドライラン（確認）**:

```bash
bash scripts/command_executor.sh --dry-run worker_launch.execute \
  subtask_file=work/cmd_001/plan_subtasks/subtask_001.md \
  persona_file=personas/active/backend_specialist_v2.yaml \
  output_path=work/cmd_001/results/subtask_001.md
```

出力例:
```
[command_executor] Dry run:
  Port:    worker_launch.execute
  Command: bash scripts/subprocess_worker.sh execute work/cmd_001/...
  Timeout: 600s
```

内部動作:
1. `TANEBI_ROOT/config.yaml` からポートの `command` 文字列を読み取る
2. `{subtask_file}` 等のプレースホルダーを実引数で置換する
3. `timeout` ラップして `bash -c "$CMD"` で実行する（`CLAUDECODE` / `CLAUDE_CODE_ENTRYPOINT` を unset してから実行）

### 4.3 subprocess_worker.sh の動作

`subprocess_worker.sh` は `claude -p`（subprocess モード）で Decomposer または Worker を起動する。

```bash
# Decompose モード
bash scripts/subprocess_worker.sh decompose \
  <request_file> <plan_output> <persona_list> <cmd_id>

# Execute モード
bash scripts/subprocess_worker.sh execute \
  <subtask_file> <output_path> [<persona_file>]
```

**内部動作**:

```
subprocess_worker.sh
  └── claude -p
        --system-prompt <templates/decomposer.md or worker_base.md>
        --allowed-tools Read,Write,Glob,Grep,Bash
        --permission-mode acceptEdits
        (stdin: リクエスト内容 + Persona情報)
        (stdout: 結果ファイルに書き出し)
```

`claude -p` 実行前に `CLAUDECODE` と `CLAUDE_CODE_ENTRYPOINT` を unset することで
subprocess として正常動作する（TANEBI subprocess モードの既知の要件）。

### 4.4 decompose.requested フロー例

**前提**: Core が `decompose.requested` イベントを Event Store に書き込み済み。

```yaml
# work/cmd_001/events/002_decompose.requested.yaml
event_type: decompose.requested
timestamp: "2026-03-01T12:00:00"
cmd_dir: work/cmd_001
payload:
  cmd_id: cmd_001
  request_path: work/cmd_001/request.md
  persona_list: backend_specialist_v2,test_writer_v1
  plan_output_path: work/cmd_001/plan.md
```

**Executor の処理（subprocess）**:

```bash
# 1. *.requested イベントを検出・ペイロードを読み取る
# （実際には Core が直接 subprocess_worker.sh を呼ぶか、
#   または Executor がイベントファイルを監視して処理する）

# 2. subprocess_worker.sh を呼ぶ
bash scripts/subprocess_worker.sh decompose \
  "work/cmd_001/request.md" \
  "work/cmd_001/plan.md" \
  "backend_specialist_v2,test_writer_v1" \
  "cmd_001"

# 3. plan.md が生成されたことを確認
# 4. task.decomposed イベントを発行
bash scripts/emit_event.sh "work/cmd_001" "task.decomposed" "
cmd_id: cmd_001
plan:
  subtasks:
    - id: subtask_001
      description: APIエンドポイント実装
      persona: backend_specialist_v2
      wave: 1
    - id: subtask_002
      description: ユニットテスト作成
      persona: test_writer_v1
      wave: 2
  waves: 2
  persona_assignments:
    - subtask_id: subtask_001
      persona_id: backend_specialist_v2
    - subtask_id: subtask_002
      persona_id: test_writer_v1
"
```

### 4.5 execute.requested フロー例

**前提**: Core が `execute.requested` イベントを Event Store に書き込み済み。

```yaml
# work/cmd_001/events/004_execute.requested.yaml
event_type: execute.requested
timestamp: "2026-03-01T12:05:00"
cmd_dir: work/cmd_001
payload:
  cmd_id: cmd_001
  subtask_id: subtask_001
  subtask_file: work/cmd_001/plan_subtasks/subtask_001.md
  persona_file: personas/active/backend_specialist_v2.yaml
  output_path: work/cmd_001/results/subtask_001.md
  wave: 1
```

**Executor の処理（subprocess）**:

```bash
# 1. *.requested イベントを検出・ペイロードを読み取る

# 2. worker.started イベントを発行（オプション。progress プラグインが表示に使用）
bash scripts/emit_event.sh "work/cmd_001" "worker.started" "
cmd_id: cmd_001
subtask_id: subtask_001
persona_id: backend_specialist_v2
wave: 1
"

# 3. subprocess_worker.sh を呼ぶ
bash scripts/subprocess_worker.sh execute \
  "work/cmd_001/plan_subtasks/subtask_001.md" \
  "work/cmd_001/results/subtask_001.md" \
  "personas/active/backend_specialist_v2.yaml"

# 4. result ファイルが生成されたことを確認（YAML frontmatter を解析して status/quality/domain を取得）

# 5. worker.completed イベントを発行
bash scripts/emit_event.sh "work/cmd_001" "worker.completed" "
cmd_id: cmd_001
subtask_id: subtask_001
status: success
quality: GREEN
domain: backend
"
```

### 4.6 Worker 結果ファイル（ResultYAML）の形式

Worker は YAML frontmatter 付き Markdown を `output_path` に出力する:

```markdown
---
subtask_id: subtask_001
persona: backend_specialist_v2
status: success
quality: GREEN
domain: backend
duration_estimate: medium
---

# 実装結果

[タスクの成果物をここに記述]
```

`status`・`quality`・`domain` は `worker.completed` イベントのペイロードとして使用する。

### 4.7 Worker からのイベント発行パターン

Worker（subprocess_worker.sh が起動した `claude -p` プロセス）が完了イベントを発行する際、
`scripts/emit_event.sh` を直接呼ぶか、ラッパーの `scripts/tanebi-callback.sh` を呼ぶかを選べる。

**直接 emit_event.sh を呼ぶ**:

```bash
# Worker スクリプトの末尾
bash scripts/emit_event.sh "$CMD_DIR" "worker.completed" "
cmd_id: $CMD_ID
subtask_id: $SUBTASK_ID
status: success
quality: GREEN
domain: backend
"
```

**tanebi-callback.sh 経由で呼ぶ**（`emit_event.sh` のシェルラッパー）:

```bash
# Worker スクリプトの末尾（同等の動作）
bash scripts/tanebi-callback.sh "worker.completed" \
  cmd_id="$CMD_ID" subtask_id="$SUBTASK_ID" status="success"
```

**Python API 経由で呼ぶ**（`src/tanebi/core/callback.py`）:

```python
# Python Worker スクリプトでの使用例
from pathlib import Path
from tanebi.core.callback import handle_callback

handle_callback(
    cmd_id="cmd_001",
    work_dir=Path("work"),
    kwargs={
        "event_type": "worker.completed",
        "subtask_id": "subtask_001",
        "status": "success",
        "quality": "GREEN",
        "domain": "backend",
    },
)
```

`emit_event.sh`・`tanebi-callback.sh`・`handle_callback()` はすべて同じ Event Store（`work/cmd_NNN/events/`）に書き込む。
Python API はスキーマ検証（`events/schema.yaml`）を自動で行うため、カスタム Executor の実装に推奨する。

### 4.8 Wave 並列実行パターン（subprocess）

同一 Wave の複数サブタスクを並列実行する:

```bash
# Wave 1 のサブタスクリストを取得
SUBTASKS=("subtask_001" "subtask_002" "subtask_003")

# 並列実行（xargs -P）
printf '%s\n' "${SUBTASKS[@]}" | xargs -P 4 -I {} bash -c '
  subtask_id="{}"
  bash scripts/subprocess_worker.sh execute \
    "work/cmd_001/plan_subtasks/${subtask_id}.md" \
    "work/cmd_001/results/${subtask_id}.md" \
    "personas/active/..."
  # 完了後にイベント発行
  bash scripts/emit_event.sh "work/cmd_001" "worker.completed" "
    cmd_id: cmd_001
    subtask_id: ${subtask_id}
    status: success
    quality: GREEN
    domain: backend
  "
'
```

---

## 5. 環境別実装例

### 5.1 subprocess

#### 概要

TANEBI リポジトリをローカルにクローンし、`claude -p` で各 Worker を起動する最もシンプルな構成。
追加インフラ不要。Event Store はローカルファイルシステム。

#### 構成図

```
Host Machine
├── TANEBI_ROOT/
│   ├── CLAUDE.md（Core + フロー決定ロジック）
│   ├── config.yaml
│   ├── work/cmd_NNN/events/   ← Event Store（ローカルファイル）
│   ├── personas/
│   ├── knowledge/
│   ├── scripts/
│   │   ├── command_executor.sh  ← Executor リファレンス実装
│   │   └── subprocess_worker.sh ← claude -p ブリッジ
│   └── templates/
│
└── claude (CLI)               ← subprocess として起動される
```

#### config.yaml 例

```yaml
tanebi:
  version: "1.0"
  storage:
    event_store:
      type: file
    persona_store:
      type: file
    knowledge_store:
      type: file
  paths:
    work_dir: "work"
    persona_dir: "personas/active"
    knowledge_dir: "knowledge"
    few_shot_dir: "knowledge/few_shot_bank"
  execution:
    max_parallel_workers: 4    # ローカルマシンのCPU/メモリに合わせて調整
    worker_max_turns: 30
    default_model: "claude-sonnet-4-6"
  evolution:
    few_shot_max_per_domain: 100
    snapshot_interval: 5
```

#### 動作確認

```bash
# Executor ドライラン（実行前の確認）
bash scripts/command_executor.sh --dry-run worker_launch.execute \
  subtask_file=work/cmd_001/plan_subtasks/subtask_001.md \
  persona_file=personas/active/generalist_v1.yaml \
  output_path=work/cmd_001/results/subtask_001.md

# 実際に Executor を実行
bash scripts/subprocess_worker.sh execute \
  work/cmd_001/plan_subtasks/subtask_001.md \
  work/cmd_001/results/subtask_001.md \
  personas/active/generalist_v1.yaml

# 完了後にイベント発行
bash scripts/emit_event.sh "work/cmd_001" "worker.completed" "
cmd_id: cmd_001
subtask_id: subtask_001
status: success
quality: GREEN
domain: backend
"
```

#### 注意点

- `CLAUDECODE` / `CLAUDE_CODE_ENTRYPOINT` は `subprocess_worker.sh` が自動で unset する
- 並列 Worker 起動時は `xargs -P` 等を使用（Wave 内の並列実行）
- ローカルファイルが Event Store のため、永続化・バックアップは別途考慮

### 5.2 Docker

#### 概要

Worker を Docker コンテナとして起動する構成。ホスト環境に依存せず Worker を実行できる。
Event Store（`work/`）と Persona Store（`personas/`）はボリュームマウントで共有する。

#### 構成図

```
Host Machine
├── TANEBI_ROOT/
│   ├── CLAUDE.md（Core + フロー決定ロジック）
│   ├── config.yaml
│   └── work/cmd_NNN/events/   ← Event Store（ホスト上のファイル）
│
└── Docker
    ├── tanebi-worker:latest   ← Worker コンテナイメージ
    │   ├── scripts/subprocess_worker.sh
    │   ├── templates/
    │   └── claude (CLI)
    │
    └── Volumes
        ├── work/     → /app/work        （Event Store 共有）
        ├── personas/ → /app/personas    （Persona Store 共有）
        └── knowledge/→ /app/knowledge   （知識バンク共有）
```

#### Docker Executor の実装

`execute.requested` イベントを検出したら `docker run` で Worker コンテナを起動する:

```bash
# Executor（ホスト側）の処理
docker run --rm \
  --memory 512m --cpus 1.0 \
  -e TANEBI_ROOT=/app \
  -v "$(pwd)/work:/app/work" \
  -v "$(pwd)/personas:/app/personas:ro" \
  -v "$(pwd)/knowledge:/app/knowledge:ro" \
  -v "$(pwd)/templates:/app/templates:ro" \
  tanebi-worker:latest \
  execute \
  /app/work/cmd_001/plan_subtasks/subtask_001.md \
  /app/work/cmd_001/results/subtask_001.md \
  /app/personas/active/backend_specialist_v2.yaml
```

コンテナ内の `subprocess_worker.sh` が `claude -p` を実行し、結果をマウントされた `work/` に書き込む。
処理完了後、ホスト側の Executor が `emit_event.sh` で `worker.completed` を発行する。

#### Docker イメージの構成例

```dockerfile
FROM ubuntu:24.04

# Claude CLI のインストール
RUN apt-get update && apt-get install -y curl nodejs npm
RUN npm install -g @anthropic-ai/claude-code

# TANEBI scripts / templates をコピー
COPY scripts/ /app/scripts/
COPY templates/ /app/templates/

WORKDIR /app
ENTRYPOINT ["bash", "/app/scripts/subprocess_worker.sh"]
```

#### config.yaml 例

```yaml
tanebi:
  version: "1.0"
  storage:
    event_store:
      type: file
    persona_store:
      type: file
    knowledge_store:
      type: file
  paths:
    work_dir: "work"
    persona_dir: "personas/active"
    knowledge_dir: "knowledge"
  execution:
    max_parallel_workers: 8    # コンテナ並列数
    worker_max_turns: 30
    default_model: "claude-sonnet-4-6"
  evolution:
    few_shot_max_per_domain: 100
    snapshot_interval: 5
```

#### 並列 Worker 起動

同一 Wave の Worker を並列コンテナとして起動する例:

```bash
# Wave 1 の全 execute.requested を並列処理
for subtask_id in subtask_001 subtask_002 subtask_003; do
  docker run --rm -d \
    --name "tanebi-worker-${subtask_id}" \
    -v "$(pwd)/work:/app/work" \
    -v "$(pwd)/personas:/app/personas:ro" \
    tanebi-worker:latest \
    execute \
    "/app/work/cmd_001/plan_subtasks/${subtask_id}.md" \
    "/app/work/cmd_001/results/${subtask_id}.md" \
    "/app/personas/active/generalist_v1.yaml"
done

# 全コンテナの完了を待つ
for subtask_id in subtask_001 subtask_002 subtask_003; do
  docker wait "tanebi-worker-${subtask_id}"
  bash scripts/emit_event.sh "work/cmd_001" "worker.completed" "
    cmd_id: cmd_001
    subtask_id: ${subtask_id}
    status: success
    quality: GREEN
    domain: backend
  "
done
```

#### 注意点

- Event Store (`work/`) は必ずホストにマウントすること。コンテナ内に閉じると Core がイベントを読めない
- Persona の並列更新は `flock` で排他制御する（`evolve.sh` が自動で行う）
- コンテナ起動のオーバーヘッドがあるため、軽量タスクでは subprocess の方が速い場合がある

### 5.3 Lambda / Cloud Run

#### 概要

AWS Lambda・Google Cloud Run 等のサーバーレス環境で Worker を実行する構成。
各 Worker 呼び出しはステートレスなため、永続データは外部ストレージ（S3 等）に置く必要がある。

#### 構成図

```
TANEBI Core（常駐: EC2 / ローカル等）
  │
  ├── Event Store（ローカル or S3）
  │     └── *.requested イベントを書き込み
  │
  └── Executor Dispatcher（ホスト側）
        ├── *.requested イベントを検出
        ├── Lambda を invoke（非同期）
        └── *.completed イベントを SQS / S3 ポーリングで待機

Lambda / Cloud Run（ステートレス Worker）
  ├── execute.requested ペイロードを受信
  ├── S3 から subtask_file・persona_file をダウンロード
  ├── Worker 処理（LLM 呼び出し等）
  ├── 成果物を S3 に書き込み
  └── *.completed イベントを SQS に発行
```

#### イベント配信方式

**方式 1: S3 イベントトリガー**

```
Core が work/cmd_001/events/002_decompose.requested.yaml を S3 にアップロード
  → S3 Event Notification で Lambda 起動
  → Lambda がイベントファイルを読んで処理
  → Lambda が *.completed を SQS に書き込み
  → Core が SQS をポーリングで完了を検知
```

**方式 2: SQS トリガー**

```
Core が SQS に {event_type: "execute.requested", payload: ...} をエンキュー
  → SQS が Lambda をトリガー
  → Lambda が処理
  → Lambda が SQS completions キューに {event_type: "worker.completed", ...} をエンキュー
  → Core が completions キューをポーリング
```

#### Lambda Worker の実装例（Python）

```python
# lambda_handler.py
import json
import boto3
import subprocess
import os

def handler(event, context):
    """TANEBI execute.requested イベントを処理"""
    payload = event.get('payload', {})
    cmd_id = payload['cmd_id']
    subtask_id = payload['subtask_id']
    subtask_s3_key = payload['subtask_file']
    persona_s3_key = payload['persona_file']
    output_s3_key = payload['output_path']

    s3 = boto3.client('s3')
    bucket = os.environ['TANEBI_BUCKET']

    # 1. 入力ファイルを /tmp にダウンロード
    s3.download_file(bucket, subtask_s3_key, '/tmp/subtask.md')
    s3.download_file(bucket, persona_s3_key, '/tmp/persona.yaml')

    # 2. Worker テンプレートを読む（Lambda Layer に同梱）
    system_prompt = open('/opt/templates/worker_base.md').read()

    # 3. 入力を構築（subprocess_worker.sh と同等）
    worker_input = ""
    if os.path.exists('/tmp/persona.yaml'):
        worker_input += "## Persona情報\n\n"
        worker_input += open('/tmp/persona.yaml').read() + "\n\n"
    worker_input += "## サブタスク定義\n\n"
    worker_input += open('/tmp/subtask.md').read()
    worker_input += f"\n\n## 出力先\n\noutput_path: /tmp/result.md\n"

    # 4. claude -p で Worker 実行
    result = subprocess.run(
        ['claude', '-p',
         '--system-prompt', system_prompt,
         '--allowed-tools', 'Read,Write',
         '--output-format', 'text'],
        input=worker_input,
        capture_output=True, text=True, timeout=600,
        env={**os.environ, 'CLAUDECODE': '', 'CLAUDE_CODE_ENTRYPOINT': ''}
    )

    # 5. 結果を S3 にアップロード
    result_content = open('/tmp/result.md').read() if os.path.exists('/tmp/result.md') else result.stdout
    s3.put_object(Bucket=bucket, Key=output_s3_key, Body=result_content)

    # 6. ResultYAML から status/quality を解析
    status, quality, domain = parse_result_yaml(result_content)

    # 7. worker.completed イベントを SQS に発行
    sqs = boto3.client('sqs')
    sqs.send_message(
        QueueUrl=os.environ['TANEBI_COMPLETIONS_QUEUE'],
        MessageBody=json.dumps({
            'event_type': 'worker.completed',
            'payload': {
                'cmd_id': cmd_id,
                'subtask_id': subtask_id,
                'status': status,
                'quality': quality,
                'domain': domain
            }
        }),
        MessageGroupId=cmd_id,
        MessageDeduplicationId=f'{cmd_id}_{subtask_id}'
    )

    return {'statusCode': 200}


def parse_result_yaml(content: str) -> tuple:
    """ResultYAML の frontmatter を解析"""
    import re, yaml
    match = re.match(r'^---\n(.*?)\n---', content, re.DOTALL)
    if match:
        fm = yaml.safe_load(match.group(1))
        return (
            fm.get('status', 'success'),
            fm.get('quality', 'GREEN'),
            fm.get('domain', 'general')
        )
    return 'success', 'GREEN', 'general'
```

#### config.yaml 例

```yaml
tanebi:
  version: "1.0"
  storage:
    event_store:
      type: file
    persona_store:
      type: file
    knowledge_store:
      type: file
  paths:
    work_dir: "work"           # ホスト側のローカルパス（Event Store はホストに置く）
    persona_dir: "personas/active"
  execution:
    max_parallel_workers: 20   # Lambda は高並列が得意
    worker_max_turns: 20
    default_model: "claude-sonnet-4-6"
  evolution:
    few_shot_max_per_domain: 100
    snapshot_interval: 5
```

#### Persona の排他制御（Lambda 環境）

Lambda はステートレスなため、Persona 更新の競合対策が必要。

**推奨パターン: Persona Manager をオーケストレーター（常駐プロセス）に集約**

```
Orchestrator（常駐: EC2 / ローカル等）
  └── Persona Manager（single writer）
      ├── state_read: "aws s3 cp s3://tanebi-data/personas/{id}.yaml /tmp/ && cat /tmp/{id}.yaml"
      └── evolve.sh → Persona 更新 → S3 に書き戻し（排他制御）

Worker Lambda（ステートレス）
  └── Persona は read-only で参照（invoke payload 埋め込み or pre-signed URL）
```

#### 注意点

- コールドスタートに注意: Claude CLI の起動に数秒かかる場合がある
- タイムアウト設定: Worker の処理時間（最大 20〜30 ターン）を考慮して Lambda タイムアウトを設定する（推奨: 600 秒以上）
- S3 の `work/` パスとホストのローカル `work/` を同期させる仕組みが必要（Core はローカルファイルを前提とする場合）

---

## 6. イベントスキーマ参照

詳細スキーマは `events/schema.yaml` を参照すること。ここでは Executor が処理する主要イベントを示す。

### 6.1 Core → Executor（依頼イベント）

#### decompose.requested

```yaml
event_type: decompose.requested
payload:
  cmd_dir: string             # 作業ディレクトリのパス（例: work/cmd_001）
  request_file: string        # リクエストファイルのパス
  persona_file: string        # ペルソナファイルのパス
```

**Executor の責務**:
- `request_file` を読んでサブタスクに分解する
- 分解計画を `cmd_dir/plan.md` に書き出す
- `task.decomposed` イベントを発行する

#### execute.requested

```yaml
event_type: execute.requested
payload:
  cmd_dir: string             # 作業ディレクトリのパス
  subtask_id: string          # サブタスクID（例: subtask_001）
  request_file: string        # サブタスク定義ファイルのパス
  persona_file: string        # personas/active/{id}.yaml
  wave: integer               # Wave番号（並列グループ）
```

**Executor の責務**:
- `persona_file` を読んで Persona 情報を取得する
- `request_file` を読んでサブタスクを実行する
- 結果を `cmd_dir/results/{subtask_id}.md` に書き出す（YAML frontmatter 付き Markdown）
- `worker.completed` イベントを発行する

#### aggregate.requested

```yaml
event_type: aggregate.requested
payload:
  cmd_dir: string             # 作業ディレクトリのパス
  persona_file: string        # Aggregator 用 Persona ファイルのパス
```

**Executor の責務**:
- `cmd_dir/results/` 配下の全 ResultYAML を読んで集約する
- 集約レポートを `cmd_dir/report.md` に書き出す
- `task.aggregated` イベントを発行する

### 6.2 記録系・Core内部イベント

#### task.created

```yaml
event_type: task.created
payload:
  task_id: string             # タスクID（例: cmd_001）
  request: string             # ユーザーリクエスト本文
  timestamp: string           # ISO8601
```

タスク作成時に Core が発行する記録イベント。Executor は参照のみ（発行しない）。

#### wave.completed

```yaml
event_type: wave.completed
payload:
  cmd_id: string
  wave: integer               # 完了したWave番号
  results_summary: string     # Wave内サブタスクの結果概要
```

Wave 内の全 Worker 完了後に Core が発行する記録イベント。Executor は参照のみ（発行しない）。

### 6.3 Executor → Core（完了イベント）

#### task.decomposed

```yaml
event_type: task.decomposed
payload:
  cmd_id: string
  plan:
    subtasks:
      - id: string             # subtask_001 など
        description: string
        persona: string        # Persona ID
        wave: integer
    waves: integer
    persona_assignments:
      - subtask_id: string
        persona_id: string
```

#### worker.completed

```yaml
event_type: worker.completed
payload:
  cmd_id: string
  subtask_id: string
  status: enum[success, failure]
  quality: enum[GREEN, YELLOW, RED]
  domain: string               # backend / frontend / testing / docs 等
```

#### worker.started（任意）

```yaml
event_type: worker.started
payload:
  cmd_id: string
  subtask_id: string
  persona_id: string
  wave: integer
```

Worker 起動時に発行すると、Core がリアルタイム進捗を把握できる。

#### worker.progress（任意）

```yaml
event_type: worker.progress
payload:
  cmd_id: string
  subtask_id: string
  message: string
  percent: integer?            # 0-100（オプション）
```

#### task.aggregated

```yaml
event_type: task.aggregated
payload:
  cmd_id: string
  report_path: string
  quality_summary:
    GREEN: integer
    YELLOW: integer
    RED: integer
```

### 6.4 エラーイベント

Worker が失敗した場合は 2 つのイベントを発行する:

```bash
# error.worker_failed（失敗記録）
bash scripts/emit_event.sh "work/cmd_001" "error.worker_failed" "
cmd_id: cmd_001
subtask_id: subtask_001
error_detail: 'claude -p exited with code 1: timeout'
"

# worker.completed（フロー継続のため status: failure で発行）
bash scripts/emit_event.sh "work/cmd_001" "worker.completed" "
cmd_id: cmd_001
subtask_id: subtask_001
status: failure
quality: RED
domain: backend
"
```

### 6.5 events/schema.yaml への参照

```bash
# 全イベントスキーマを確認
cat events/schema.yaml

# 特定のイベントスキーマを確認（python3 + PyYAML）
python3 -c "
import yaml
with open('events/schema.yaml') as f:
    schema = yaml.safe_load(f)
print(yaml.dump(schema['events'].get('execute.requested', {})))
"
```

---

## 7. トラブルシューティング

### 7.1 よくあるエラーと対処法

#### Worker が Event Store に書き込まない

**症状**: `*.requested` イベントが発行されても、Core が `*.completed` を受け取れない。

**確認手順**:
```bash
# Event Store の内容を確認
ls -la work/cmd_001/events/

# 最新イベントを確認
cat work/cmd_001/events/$(ls work/cmd_001/events/ | tail -1)
```

**対処**: Executor 内で `bash scripts/emit_event.sh` を呼び出しているか確認する。

#### Worker が途中で止まる（タイムアウト）

**原因**: `claude -p` のターン数上限または時間制限に達した。

**対処**:
```yaml
# config.yaml
tanebi:
  execution:
    worker_max_turns: 50     # ターン上限を増やす
```

または `subprocess_worker.sh` の `claude -p` コマンドに `--max-turns` を追加する:

```bash
# subprocess_worker.sh の claude -p 呼び出し箇所を修正
claude -p \
  --max-turns 50 \
  --system-prompt "$SYSTEM_PROMPT" \
  ...
```

#### Docker 環境で Persona 更新が失われる

**症状**: Worker 完了後、Persona の trust_score 等が更新されない。

**原因**: `personas/` ディレクトリがコンテナ内に閉じており、ホストにマウントされていない。

**対処**:
```bash
# ホストの personas/ をマウントすること
docker run -v "$(pwd)/personas:/app/personas" tanebi-worker:latest ...
```

#### Lambda で Persona 更新が競合する

**症状**: 複数の Lambda が同時に同じ Persona を更新しようとして不整合が起きる。

**対処**: Persona 更新はオーケストレーター（常駐プロセス）に集約する。Lambda は Persona を read-only で参照し、更新は SQS 等でオーケストレーターに委譲する（Section 5.3 参照）。

#### emit_event.sh でイベントが重複する

**症状**: 同じイベントが複数回発行される。

**原因**: Executor が失敗後に再試行する際、前回のイベントが残っている。

**対処**: Event Store の連番管理により自然に重複は別イベントとして蓄積される。Core は
イベント ID で冪等性を保証する。Executor 側での重複防止は不要。

#### subprocess_worker.sh が "nested claude" エラーで失敗する

**症状**:
```
Error: Cannot run claude in subprocess mode when already running claude
```

**原因**: `CLAUDECODE` または `CLAUDE_CODE_ENTRYPOINT` が設定されたまま。

**対処**: `subprocess_worker.sh` が自動で unset するが、外部からの呼び出しで環境変数が
渡される場合は明示的に unset する:

```bash
unset CLAUDECODE CLAUDE_CODE_ENTRYPOINT
bash scripts/subprocess_worker.sh execute ...
```

### 7.2 デバッグ手法

#### Event Store の状態確認

```bash
# 特定コマンドの全イベントを一覧表示
ls -la work/cmd_001/events/

# イベント内容を全て確認
for f in work/cmd_001/events/*.yaml; do
  echo "=== $(basename $f) ==="
  cat "$f"
  echo
done
```

#### Executor の動作ログ確認

subprocess_worker.sh の標準出力/エラーを確認:

```bash
bash scripts/subprocess_worker.sh execute \
  work/cmd_001/plan_subtasks/subtask_001.md \
  work/cmd_001/results/subtask_001.md 2>&1 | tee /tmp/executor.log

cat /tmp/executor.log
```

#### イベントを手動で発行（テスト）

```bash
# テスト用に execute.requested を手動発行（シェル）
bash scripts/emit_event.sh "work/cmd_001" "execute.requested" "
cmd_dir: work/cmd_001
subtask_id: subtask_001
request_file: work/cmd_001/plan_subtasks/subtask_001.md
persona_file: personas/active/generalist_v1.yaml
wave: 1
"
```

```python
# テスト用に execute.requested を手動発行（Python）
from pathlib import Path
from tanebi.core.event_store import emit_event

emit_event(Path("work/cmd_001"), "execute.requested", {
    "cmd_dir": "work/cmd_001",
    "subtask_id": "subtask_001",
    "request_file": "work/cmd_001/plan_subtasks/subtask_001.md",
    "persona_file": "personas/active/generalist_v1.yaml",
    "wave": 1,
})
```

### 7.3 実装チェックリスト

独自 Executor を実装する際の確認リスト:

- [ ] `*.requested` イベントを Event Store から読み取れるか
- [ ] 処理完了後に `*.completed` イベントを `emit_event.sh` で発行しているか
- [ ] `worker.completed` ペイロードに `status`・`quality`・`domain` が含まれているか
- [ ] 成果物（plan.md / results/*.md / report.md）がイベントで指定されたパスに書き出されているか
- [ ] Worker 失敗時に `error.worker_failed` と `worker.completed (status: failure)` の両方を発行しているか
- [ ] Event Store（`work/`）がホスト・コンテナ・クラウド間で共有されているか
- [ ] Persona ファイルの並列更新が競合しないよう制御されているか
- [ ] Worker 起動時に `CLAUDECODE` / `CLAUDE_CODE_ENTRYPOINT` を unset しているか（subprocess の場合）

### 7.4 ログ確認コマンド集

```bash
# 特定コマンドのイベント数を確認
ls work/cmd_001/events/ | wc -l

# *.requested イベントのみ確認
ls work/cmd_001/events/ | grep "requested"

# *.completed イベントのみ確認
ls work/cmd_001/events/ | grep "completed"

# 最後のイベントを確認（フロー状態の把握）
cat work/cmd_001/events/$(ls work/cmd_001/events/ | sort | tail -1)

# 全コマンドの状況を一覧（work/ 配下に events/ がある場合）
for d in work/cmd_*/; do
  cmd_id=$(basename "$d")
  event_count=$(ls "$d/events/" 2>/dev/null | wc -l)
  last_event=$(ls "$d/events/" 2>/dev/null | sort | tail -1 | sed 's/\.yaml//')
  echo "$cmd_id: $event_count events, last: $last_event"
done
```

---

*End of Executor Implementation Guide*
