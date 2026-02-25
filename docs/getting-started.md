# Getting Started with TANEBI

## Prerequisites

- **Python 3.10+** — `python3 --version` で確認
- **Claude Code** — `claude --version` で確認 ([Install](https://claude.ai/code))
- **Anthropic API Key** — `export ANTHROPIC_API_KEY=your_api_key_here` で設定 ([取得はこちら](https://console.anthropic.com/))
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
- `work/`, `knowledge/` などのランタイムディレクトリを作成

冪等（2回以上実行しても安全）。

### 3. 動作確認

```bash
.venv/bin/tanebi --version   # tanebi 0.1.0
export ANTHROPIC_API_KEY=your_api_key_here  # まだ設定していない場合
```

## Your First Task

TANEBI は Claude Code の `CLAUDE.md` を自動ロードすることで起動する。Claude Code は起動ディレクトリの CLAUDE.md を自動読込し、その指示に従う。

```bash
cd tanebi
claude
```

起動後、オーケストレーターが以下を表示する:

- 蓄積済み Learned Patterns 数（`knowledge/learned/`）
- 過去のコマンド数（`work/`）
- タスク入力の案内

タスクを入力するとフローが始まる（統一フロー: DECOMPOSE → EXECUTE → [CHECKPOINT] → AGGREGATE → LEARN）:

1. **REQUEST** — `work/cmd_NNN/request.md` に依頼を保存
2. **DECOMPOSE** — Decomposer がサブタスクに分解
3. **EXECUTE** — Worker がサブタスクを実行、Event Store に結果を記録
4. **CHECKPOINT**（オプション）— 中間品質チェックと進捗評価
5. **AGGREGATE** — 結果を統合してレポートを生成
6. **LEARN** — シグナル蓄積・蒸留・パターン注入で知識を更新

実行結果は `work/cmd_NNN/` に蓄積される。

タスク入力例（claude 起動後に何を入力するか）:

- `FizzBuzzを実装してください（1から100まで）`
- `src/ 以下のユニットテストをすべて書いてください`
- `README.md の誤字を修正してください`

## Architecture Overview

```
Core (CLAUDE.md orchestrator)
  ↓ *.requested
Event Store (work/{cmd}/events/)   ←→   Executor (subprocess_worker)
  ↑ *.completed
```

- **Core** — Learning Engine + Knowledge Store + フロー制御。Executor を知らない
- **Event Store** — 不変イベントログ。Core と Executor の唯一の通信経路
- **Executor** — `*.requested` を処理して `*.completed` を返す。実装技術は自由

詳細は [design.md](design.md) を参照。

## Next Steps

- **[design.md](design.md)** — アーキテクチャ全仕様、Learning Engine
- **[executor-design.md](executor-design.md)** — 独自 Executor の実装方法
