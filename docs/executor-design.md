# Executor 実行モデル設計書

生成日: 2026-02-23
根拠: design.md Section 7 を具体化。設計議論に基づく。

---

## 1. 概要

本文書は design.md Section 7「Executor インターフェース」の実装設計を定める。
design.md が定めた原則（Core と Executor の疎結合、イベントスキーマが唯一の契約）を維持しつつ、
具体的な実行モデル・モード切替・公開 API を設計する。

### 1.1 設計判断サマリー

| 判断 | 結論 | 理由 |
|------|------|------|
| command_executor（汎用コマンドテンプレートエンジン） | **不要** | 旧シェル設計の残骸。Python で直接書けばよい |
| イベント駆動モデル | **EventStore は純粋なログ。リスナーは外部** | EventStore にディスパッチ機構を持たせると責務肥大・疎結合崩壊 |
| Core の動作 | **完全リアクティブ（ハンドラの集合）** | Core は待たない。イベントに反応して次のイベントを発行するだけ |
| モード切替 | **config.yaml `claude_native: true/false`** | claude-native だけが特殊。外部 Listener の種類（subprocess / Lambda 等）は Core の関知外 |
| 公開 API | **submit / status / result** | 入口は EventStore の詳細を知らない |
| tanebi run（一括実行コマンド） | **不要** | Claude session + background task で通知が成立するため迂回不要 |

---

## 2. アーキテクチャ

### 2.1 全体構造

```
┌─────────────────────────────────────────────────────────────┐
│ Entry Point（Claude session / Web API / CLI / 任意）        │
│                                                             │
│  submit("FizzBuzzを実装して") → task_id                     │
│  status(task_id) → { state, progress }                      │
│  result(task_id) → report                                   │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────┐
│ TANEBI Public API（薄いラッパー）                            │
│                                                              │
│  submit(): task_id 採番 → EventStore.create_task()           │
│  status(): EventStore からイベントログを集計                   │
│  result(): report.md を返す                                   │
└──────────────────────┬───────────────────────────────────────┘
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
    ┌──────────┐ ┌──────────┐ ┌──────────┐
    │EventStore│ │   Core   │ │ Executor │
    │(純粋ログ)│ │(ハンドラ)│ │(リスナー)│
    └──────────┘ └──────────┘ └──────────┘
```

### 2.2 各コンポーネントの責務

| コンポーネント | 責務 | 知っていること | 知らないこと |
|--------------|------|-------------|------------|
| **Public API** | タスク投入・状態照会 | EventStore の create_task / list_tasks | Core, Executor の存在 |
| **EventStore** | イベントの書き出し・読み出し | ファイルパス、スキーマ | リスナーの存在、実行モード |
| **Core** | フロー決定（*.completed → 次の *.requested） | イベントスキーマ、フロー規則 | Executor の実装、入口の種類 |
| **Executor** | タスク実行（*.requested → 処理 → *.completed） | イベントスキーマ、worker の起動方法 | Core の存在、フロー規則 |

**原則: 各コンポーネントは EventStore 上のイベントファイルだけを接点とする。互いを直接呼ばない。**

---

## 3. 公開 API

入口（Entry Point）が TANEBI に対して使う唯一のインタフェース。
EventStore、Core、Executor の内部を一切公開しない。

### 3.1 API 定義

```python
# src/tanebi/api.py

def submit(request: str, *, project_dir: Path | None = None) -> str:
    """タスクを投入する。

    Args:
        request: ユーザーの依頼テキスト
        project_dir: 対象プロジェクトのパス（省略時は cwd）

    Returns:
        task_id: 採番されたタスクID
    """

def status(task_id: str) -> dict:
    """タスクの現在状態を返す。

    Returns:
        {
            "task_id": "cmd_001",
            "state": "executing",  # created | decomposing | executing | aggregating | completed | failed
            "progress": {
                "total_subtasks": 3,
                "completed": 1,
                "current_wave": 1,
            },
            "last_event": "worker.completed",
        }
    """

def result(task_id: str) -> str | None:
    """完了していれば report.md の内容を返す。未完了なら None。"""
```

### 3.2 設計意図

- **入口は submit() だけ知っていればいい。** task_id の採番規則、work dir の構造、イベントスキーマは全部内部
- **status() は EventStore のイベントログから集計する。** 別途ステータスDBを持たない
- **result() は work/{task_id}/report.md を読むだけ。** Aggregator が書いたファイルをそのまま返す

---

## 4. EventStore

design.md Section 3.2 / 4 の実装。**純粋なログ。ディスパッチ機構を持たない。**

### 4.1 責務

1. イベントファイルの書き出し（emit）
2. イベントファイルの読み出し（list / get）
3. タスク管理（create_task / list_tasks / get_task_summary）

### 4.2 持たないもの

- リスナー登録・ディスパッチ
- イベント監視・通知
- Executor の起動・管理

**理由**: EventStore にディスパッチを持たせると、Core がリスナーに指示を出しているのと同じ。
イベント駆動の意味が薄れる。EventStore はファイルを書くだけ。
誰がそれを読むかは EventStore の関知するところではない。

---

## 5. Core（フロー決定ロジック）

### 5.1 設計: リアクティブハンドラ

Core は「待つ」という概念を持たない。イベントに対するリアクションの集合として定義される。

```
on task.created:
  → emit decompose.requested

on task.decomposed:
  → plan を読む
  → wave 1 の各サブタスクに emit execute.requested

on worker.completed:
  → wave 内の全 worker 完了か確認
  → 全完了なら emit wave.completed

on wave.completed:
  → 次の wave あり → 次 wave の execute.requested を emit
  → 最終 wave    → emit aggregate.requested

on task.aggregated:
  → タスク完了
```

### 5.2 Core の状態判定

Core は「状態」を保持しない。EventStore のイベントログから現在の状態を導出する。

```python
def determine_state(task_id: str) -> str:
    """イベントログから現在の状態を判定"""
    events = event_store.list_events(task_id)
    last = events[-1].event_type

    if last == "task.created":
        return "needs_decompose"
    elif last == "task.decomposed":
        return "needs_execute"
    elif last == "worker.completed":
        if all_workers_in_wave_complete(events):
            return "wave_complete"
        else:
            return "executing"  # まだ待ち
    elif last == "wave.completed":
        if has_next_wave(events):
            return "needs_execute"  # 次の wave
        else:
            return "needs_aggregate"
    elif last == "task.aggregated":
        return "completed"
```

**これにより Core はステートレス。** 任意の時点で再起動しても、イベントログから状態を復元できる。

### 5.3 claude-native での Core

Claude セッションが Core を兼ねる場合、CLAUDE.md にハンドラテーブルとして記述する。

```markdown
## イベントハンドラ

work/{task_id}/events/ を読み、最後のイベントに応じて行動せよ。

| 最後のイベント | アクション |
|--------------|-----------|
| task.created | decompose.requested を emit → 自分で分解 → task.decomposed を emit |
| task.decomposed | plan.md を読む → wave 1 の execute.requested を emit → 自分で実行 → worker.completed を emit |
| worker.completed | wave 完了か確認 → 完了なら次 wave or aggregate.requested |
| wave.completed | 次 wave の execute.requested を emit、または aggregate.requested を emit |
| aggregate.requested | 自分で統合 → task.aggregated を emit |
| task.aggregated | ユーザーに報告 |
```

claude-native では Claude セッションが Core と Executor を兼ねる。
イベントは全て記録される（ログの完全性）。フロー制御は逐次実行。

---

## 6. Executor

### 6.1 実行モード

config.yaml の `tanebi.execution.claude_native` で指定。

```yaml
tanebi:
  execution:
    claude_native: true       # true = Core が自分で処理 / false = 外部 Listener に任せる（本設計書で追加）
    default_model: "claude-sonnet-4-6"
    max_parallel_workers: 5
    worker_max_turns: 30
    timeout: 300              # 本設計書で追加
```

**注**: `claude_native` と `timeout` は本設計書で新たに追加するフィールド。design.md Section 8.1 への反映が必要。

Core が知るのはこの1フラグだけ。`false` のとき誰がどう処理するか（subprocess / Lambda / Docker）は
Listener 側の実装詳細であり、Core の関知するところではない。

| claude_native | Core | Executor |
|--------------|------|----------|
| **true** | Claude セッション自身 | Claude セッション自身（Task tool） |
| **false** | Core Listener（Python）、または Claude session + background task | 外部 Listener（種類は問わない） |

### 6.2 claude-native モード

Claude セッションが Core と Executor を兼ねる。ゼロインフラ原則に合致。

```
Claude session
  ├─ Core:     ハンドラテーブルに従いフロー制御
  ├─ Executor: Task tool でサブタスク実行
  └─ イベント:  全て EventStore に記録（ログ完全性）
```

Claude セッションは Section 5.3 のハンドラテーブルに従い逐次処理する。
真のイベント駆動ではないが、同じイベントログが生成される。

### 6.3 外部 Listener モード（claude_native: false）

Core と Executor が独立したイベントリスナーとして動作する。
以下は subprocess（claude -p）による Listener 実装例だが、
Lambda / Docker 等でも同じイベント契約に従えば差し替え可能。

```
Core Listener                EventStore              Executor Listener
     │                           │                         │
     │◀─ task.created ──────────│                         │
     │── decompose.requested ──▶│                         │
     │                           │── (検知) ──────────────▶│
     │                           │                         │ claude -p
     │                           │◀── task.decomposed ────│
     │◀── (検知) ───────────────│                         │
     │── execute.requested ────▶│                         │
     │                           │── (検知) ──────────────▶│
     │                           │                         │ claude -p
     │                           │◀── worker.completed ───│
     │◀── (検知) ───────────────│                         │
     ...
```

Core Listener と Executor Listener は互いを知らない。
EventStore 上のファイル変更を各自が監視し、自分の担当イベントに反応する。

#### Executor Listener

```python
# src/tanebi/executor/listener.py

class ExecutorListener:
    """EventStore を監視し *.requested を処理する"""

    def __init__(self, tanebi_root: Path, config: dict):
        self.tanebi_root = tanebi_root
        self.config = config
        self.event_store = EventStore(tanebi_root)

    def start(self):
        """監視を開始する"""
        # work/ 以下の events/ ディレクトリを監視
        # 新しい *.requested.yaml を検知 → handle()

    def handle(self, task_id: str, event_type: str, payload: dict):
        if event_type == "decompose.requested":
            self._run_decompose(task_id, payload)
        elif event_type == "execute.requested":
            self._run_execute(task_id, payload)
        elif event_type == "aggregate.requested":
            self._run_aggregate(task_id, payload)

    def _run_decompose(self, task_id, payload):
        result = run_claude_p(
            system_prompt=read_template("decomposer.md"),
            user_prompt=build_decompose_prompt(payload),
        )
        self.event_store.emit(task_id, "task.decomposed", parse_plan(result))

    def _run_execute(self, task_id, payload):
        self.event_store.emit(task_id, "worker.started", {
            "task_id": task_id,
            "subtask_id": payload["subtask_id"],
            "persona_id": extract_persona_id(payload["persona_file"]),
            "wave": payload["wave"],
        })
        result = run_claude_p(
            system_prompt=read_template("worker_base.md"),
            user_prompt=build_execute_prompt(payload),
        )
        self.event_store.emit(task_id, "worker.completed", parse_result(result))

    def _run_aggregate(self, task_id, payload):
        result = run_claude_p(
            system_prompt=read_template("aggregator.md"),
            user_prompt=build_aggregate_prompt(payload),
        )
        self.event_store.emit(task_id, "task.aggregated", parse_report(result))
```

#### Core Listener

```python
# src/tanebi/core/listener.py

class CoreListener:
    """EventStore を監視し *.completed に反応してフロー制御する"""

    def __init__(self, tanebi_root: Path):
        self.tanebi_root = tanebi_root
        self.event_store = EventStore(tanebi_root)

    def start(self):
        """監視を開始する"""
        # work/ 以下の events/ ディレクトリを監視
        # 新しいイベントを検知 → handle()

    def handle(self, task_id: str, event_type: str, payload: dict):
        if event_type == "task.created":
            self._on_task_created(task_id, payload)
        elif event_type == "task.decomposed":
            self._on_task_decomposed(task_id, payload)
        elif event_type == "worker.completed":
            self._on_worker_completed(task_id, payload)
        elif event_type == "wave.completed":
            self._on_wave_completed(task_id, payload)

    def _on_task_created(self, task_id, payload):
        self.event_store.emit(task_id, "decompose.requested", {
            "task_id": task_id,
            "request_path": f"work/{task_id}/request.md",
            "persona_list": self._list_personas(),
            "plan_output_path": f"work/{task_id}/plan.md",
        })

    def _on_task_decomposed(self, task_id, payload):
        plan = payload["plan"]
        for subtask in plan["subtasks"]:
            if subtask["wave"] == 1:
                self.event_store.emit(task_id, "execute.requested", {
                    "task_id": task_id,
                    "subtask_id": subtask["id"],
                    "subtask_file": subtask["description"],
                    "persona_file": f"personas/active/{subtask['persona']}.yaml",
                    "output_path": subtask["output_path"],
                    "wave": 1,
                })

    def _on_worker_completed(self, task_id, payload):
        events = self.event_store.list_events(task_id)
        wave = self._current_wave(events)
        if self._wave_all_complete(events, wave):
            self.event_store.emit(task_id, "wave.completed", {
                "task_id": task_id,
                "wave": wave,
                "results_summary": self._summarize_wave(events, wave),
            })

    def _on_wave_completed(self, task_id, payload):
        plan = self._read_plan(task_id)
        current_wave = payload["wave"]
        next_wave_tasks = [s for s in plan["subtasks"] if s["wave"] == current_wave + 1]

        if next_wave_tasks:
            for subtask in next_wave_tasks:
                self.event_store.emit(task_id, "execute.requested", {
                    "task_id": task_id,
                    "subtask_id": subtask["id"],
                    "subtask_file": subtask["description"],
                    "persona_file": f"personas/active/{subtask['persona']}.yaml",
                    "output_path": subtask["output_path"],
                    "wave": current_wave + 1,
                })
        else:
            self.event_store.emit(task_id, "aggregate.requested", {
                "task_id": task_id,
                "results_dir": f"work/{task_id}/results/",
                "report_path": f"work/{task_id}/report.md",
            })
```

### 6.4 Claude セッション + 外部 Listener（ハイブリッド）

Claude セッションがインタフェースとして外部 Listener モードを使う場合。
Claude Code の background task 機能を活用する。

```
Claude session (UI)
  │
  ├─ tanebi.submit(request) → task_id
  │
  ├─ Background Task: "task.aggregated が現れるまで監視"
  │     └─ events/ を polling → 完了検知
  │
  │   ... Claude はブロックされない ...
  │   ... Core Listener + Executor Listener が処理 ...
  │
  ├─ ◀── task-notification（自動通知）
  │
  └─ tanebi.result(task_id) → ユーザーに報告
```

Claude session は Public API（submit / status / result）だけを使う。
EventStore、Core、Executor の内部を知らない。

---

## 7. subprocess worker

### 7.1 claude -p の呼び出し

```python
# src/tanebi/executor/worker.py

def run_claude_p(
    system_prompt: str,
    user_prompt: str,
    *,
    model: str | None = None,
    timeout: int | None = None,
    allowed_tools: str = "Read,Write,Glob,Grep,Bash",
) -> str:
    """claude -p を subprocess で実行し、結果テキストを返す。

    - shell=False でシェルインジェクションを防止（旧 C-001 解消）
    - CLAUDECODE / CLAUDE_CODE_ENTRYPOINT を除去（既知バグ対策）
    - タイムアウト対応（旧 M-013 解消）
    - 失敗時は WorkerError を送出（旧 M-001 解消）
    """
    config = load_config()
    model = model or config.get("default_model", "claude-sonnet-4-6")
    timeout = timeout or config.get("timeout", 300)

    env = {k: v for k, v in os.environ.items()
           if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")}

    result = subprocess.run(
        ["claude", "-p",
         "--model", model,
         "--output-format", "text",
         "--system-prompt", system_prompt,
         "--allowed-tools", allowed_tools],
        input=user_prompt,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )

    if result.returncode != 0:
        raise WorkerError(
            f"claude -p failed (exit {result.returncode}): {result.stderr}"
        )

    return result.stdout
```

### 7.2 テンプレートの扱い

既存の `templates/` をそのまま使用する。

| テンプレート | 用途 | system prompt として渡す |
|------------|------|------------------------|
| `templates/decomposer.md` | サブタスク分解 | decompose.requested ハンドラ |
| `templates/worker_base.md` | サブタスク実行 | execute.requested ハンドラ |
| `templates/aggregator.md` | 結果統合 | aggregate.requested ハンドラ |

テンプレート内の `{PLACEHOLDER}` は使わない。
具体的な値（request 内容、persona 情報等）は user prompt として stdin で渡す。
テンプレートはロール定義（system prompt）、具体値はプロンプト本文（user prompt）。

---

## 8. イベント claiming（重複処理防止）

外部 Listener モードでは Executor Listener が複数起動される可能性がある（将来）。
同じ `*.requested` を複数の Executor が処理しないよう claiming メカニズムを設ける。

### 8.1 companion ファイル方式

イベントファイルの不変性を維持するため、companion ファイルで claim を表現する。

```
work/{task_id}/events/
  002_decompose.requested.yaml          ← イベント（不変）
  002_decompose.requested.claimed       ← Executor が作成
```

`.claimed` ファイルの作成は `O_CREAT | O_EXCL` でアトミックに行う。
先に作成できた Executor だけが処理を実行する。

```python
def try_claim(event_path: Path) -> bool:
    """イベントの claim を試みる。成功なら True。"""
    claim_path = event_path.with_suffix(".claimed")
    try:
        fd = os.open(str(claim_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w") as f:
            yaml.dump({"claimed_at": datetime.now(timezone.utc).isoformat()}, f)
        return True
    except OSError:
        return False  # 既に claim 済み
```

### 8.2 claude-native での claiming

不要。Claude セッションが自分で処理するため競合しない。

---

## 9. イベント監視方式

Core Listener / Executor Listener が EventStore のファイル変更を検知する方式。

### 9.1 方式

**watchdog をデフォルトとする。**

| 方式 | 採用 | 理由 |
|------|------|------|
| **watchdog** | **デフォルト** | FSEvents（macOS）/ inotify（Linux）対応。venv setup で入る |
| polling | フォールバック | watchdog 未インストール環境向け |

```toml
[project]
dependencies = [
    "pyyaml>=6.0",
    "watchdog>=4.0",
]
```

watchdog は macOS で問題なし（FSEvents ネイティブ対応）。

---

## 10. 起動方法

### 10.1 claude-native（デフォルト）

```bash
cd ~/projects/tanebi
claude
# CLAUDE.md が自動ロード → ハンドラテーブルに従い動作
```

設定不要。ゼロインフラ原則に合致。

### 10.2 外部 Listener（claude_native: false）

```yaml
# config.yaml
tanebi:
  execution:
    claude_native: false
```

```bash
# ターミナル 1: Listener 起動（Core + Executor）
tanebi listener start

# ターミナル 2: タスク投入（何でもよい）
tanebi new "FizzBuzzを実装して"
# または Claude session から submit()
# または Web API / スクリプト等
```

### 10.3 Claude session + 外部 Listener

```bash
# ターミナル 1: Listener 起動
tanebi listener start

# ターミナル 2: Claude session
claude
# Claude が submit() → background task で完了監視 → 自動通知
```

---

## 11. 実装対象ファイル

### Phase 2 で作成するもの

| ファイル | 内容 |
|---------|------|
| `src/tanebi/api.py` | 公開 API（submit / status / result） |
| `src/tanebi/executor/worker.py` | claude -p 呼び出し（run_claude_p） |
| `src/tanebi/executor/listener.py` | Executor Listener（*.requested 監視・処理） |
| `src/tanebi/core/listener.py` | Core Listener（*.completed 監視・フロー制御） |
| `src/tanebi/core/flow.py` | ハンドラ定義（on_task_created 等） |
| `src/tanebi/cli/listener_cmd.py` | `tanebi listener start` CLI サブコマンド |
| `tests/unit/test_api.py` | 公開 API テスト |
| `tests/unit/test_worker.py` | worker テスト（claude CLI はモック） |
| `tests/unit/test_flow.py` | Core フローテスト |
| `tests/unit/test_listener.py` | Listener テスト |

### Phase 2 で変更するもの

| ファイル | 変更内容 |
|---------|---------|
| `src/tanebi/event_store/__init__.py` | list_events / get_task_summary 追加 |
| `src/tanebi/cli/main.py` | `tanebi listener` / `tanebi new` サブコマンド追加 |
| `config.yaml` | `execution.claude_native` フィールド追加 |

### 既存ファイルで不要になるもの（Phase 4 で削除）

| ファイル | 理由 |
|---------|------|
| `scripts/command_executor.sh` | Python Executor Listener に置換 |
| `scripts/subprocess_worker.sh` | Python worker.py に置換 |

---

## 12. 解消される既知の問題

| ID | 問題 | 解消方法 |
|----|------|---------|
| C-001 | シェルインジェクション | `subprocess.run(shell=False)` |
| M-001 | Worker 全失敗サイレント | WorkerError 例外送出 |
| M-013 | タイムアウトなし | `subprocess.run(timeout=)` |

---

## 13. モード対応表

| 側面 | claude_native: true | claude_native: false |
|------|--------------------|---------------------|
| Core | Claude session（ハンドラテーブル） | Core Listener（Python）or Claude session + background task |
| Executor | Claude session（Task tool） | 外部 Listener（種類は問わない） |
| UI | Claude session | 任意（Claude / CLI / Web / なし） |
| 常駐プロセス | なし | Listener 1 プロセス |
| 並列 worker | なし（逐次処理） | max_parallel_workers まで |
| イベントログ | 完全（同じスキーマ） | 完全（同じスキーマ） |
| 設定 | `claude_native: true` | `claude_native: false` |
| インフラ要件 | Claude Code のみ | Claude Code + Listener プロセス |
