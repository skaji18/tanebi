# Getting Started with TANEBI

## Prerequisites

- **Python 3.10+** — `python3 --version` で確認
- **Claude Code** — `claude --version` で確認
- **Git**

## Installation

### 1. Clone

```bash
git clone https://github.com/skaji18/tanebi
cd tanebi
```

### 2. Setup

```bash
bash scripts/setup.sh
```

このスクリプトが行うこと:

- Python venv を `.venv/` に作成してパッケージをインストール
- `personas/active/` にスターター Persona を初期配置
- `work/`, `knowledge/` などのランタイムディレクトリを作成

冪等（2回以上実行しても安全）。

### 3. 動作確認

```bash
source .venv/bin/activate
tanebi --version   # tanebi 0.1.0
```

## Your First Task

TANEBI は Claude Code の `CLAUDE.md` を自動ロードすることで起動する。

```bash
cd tanebi
claude
```

起動後、オーケストレーターが以下を表示する:

- 利用可能な Persona 数（`personas/active/`）
- 過去のコマンド数（`work/`）
- タスク入力の案内

タスクを入力するとフローが始まる:

1. **REQUEST** — `work/cmd_NNN/request.md` に依頼を保存
2. **DECOMPOSE** — Decomposer がサブタスクに分解、Persona を選択
3. **EXECUTE** — Worker がサブタスクを実行、Event Store に結果を記録
4. **AGGREGATE** — 結果を統合してレポートを生成
5. **EVOLVE** — Persona と共有知識を更新

実行結果は `work/cmd_NNN/` に蓄積される。

## Architecture Overview

```
Core (CLAUDE.md orchestrator)
  ↓ *.requested
Event Store (work/{cmd}/events/)   ←→   Executor (subprocess_worker)
  ↑ *.completed
```

- **Core** — Evolution Engine + Persona 管理 + フロー制御。Executor を知らない
- **Event Store** — 不変イベントログ。Core と Executor の唯一の通信経路
- **Executor** — `*.requested` を処理して `*.completed` を返す。実装技術は自由

詳細は [design.md](design.md) を参照。

## Next Steps

- **[design.md](design.md)** — アーキテクチャ全仕様、Persona スキーマ、Evolution Engine
- **[executor-design.md](executor-design.md)** — 独自 Executor の実装方法
