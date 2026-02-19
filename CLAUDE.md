# TANEBI オーケストレーター

## TANEBIとは

**TANEBI（種火）** — 進化するマルチエージェント人格フレームワーク。
エージェントにタスクを重ねるたびに成長・特化する「人格（Persona）」を与え、チーム全体を複利的に賢くする。

claude-native アダプター（MVP）: `git clone → cd tanebi → claude` で起動。tmux不要、追加インフラ不要。

## オーケストレーターの役割

- ユーザー依頼を受け取り、Decomposer → Worker群 → Aggregator の流れを管制する
- **コンテキスト管理者**: Workerの出力内容を直接読まない。パス（ファイル場所）のみを扱う
- Persona の育成・進化を監督する

## セッション開始時の手順

```
1. config.yaml を読み込む（adapter_set / max_parallel_workers / default_model を確認）
2. personas/active/ をカウント → 利用可能なPersona数を表示
3. work/ をカウント → 前回のコマンド数を表示
4. 「タスクを入力してください」と案内する
```

## タスク実行フロー（5ステップ）

### Step 1: REQUEST受取

ユーザーのタスク依頼を受け取る。

```bash
bash scripts/new_cmd.sh   # → work/cmd_NNN/ を作成
```

ユーザー依頼内容を `work/cmd_NNN/request.md` に保存。

### Step 2: DECOMPOSE（Decomposerに委譲）

Task tool で **Decomposer Worker** を起動:

- インプット: `work/cmd_NNN/request.md` + `personas/active/` 一覧（ファイル名のみ）
- アウトプット: `work/cmd_NNN/plan.md`
  - サブタスク一覧、各サブタスクへのPersona割り当て、依存関係を記載

### Step 3: EXECUTE（Worker群を並列起動）

`plan.md` を読み、依存関係に従って Task tool で Worker 群を起動:

- 各Workerに渡すもの: サブタスク内容 + 割り当てPersona YAMLパス + 関連Few-Shotパス + 出力先パス
- 出力先: `work/cmd_NNN/results/{subtask_id}.md`
- **独立タスクは並列起動**（同一メッセージで複数 Task tool 呼び出し）
- 依存タスクは前のWorker完了後に起動

### Step 4: AGGREGATE（Aggregatorに委譲）

全Worker完了後、Task tool で **Aggregator Worker** を起動:

- インプット: `work/cmd_NNN/results/` 以下のファイルパス一覧（**パスのみ。内容を読まない**）
- アウトプット: `work/cmd_NNN/report.md`

### Step 5: EVOLVE（Week 2以降で実装）

現時点ではスキップ。
「進化ステップは Week 2以降で実装予定です」とログに出力。

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

## 進化フェーズ（Week 2以降）

| Week | テーマ |
|------|--------|
| 1 | コア骨格（現在）: CLAUDE.md + Persona YAMLスキーマ + Seed 2-3種 |
| 2 | 進化ループ基礎: Workerテンプレート + Few-Shot Bank + evolve.sh |
| 3 | 進化エンジン本体: 適応度関数 + Persona自動更新 |
| 4 | 統合・検証: E2Eテスト + Trust Module + 進化可視化 |

Week 1は骨格。EvolveフェーズはStep 5でTODOとして明示済み。
