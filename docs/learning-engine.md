# Learning Engine 設計書

---

## 1. 設計方針

### 基本思想

LLM の出力品質を左右する本質的要因は、**どのような知識（パターン・事例・教訓）をコンテキストに注入するか** である。

TANEBI はこの知見に基づき、**知識蓄積型マルチエージェント実行フレームワーク** として設計されている:

- **タスク経験が知識パターンに蒸留され、静かに反映される**
- 学習単位は個体ではなく**システム全体（Learned Patterns）**
- メタファー: **種火（小さな火種が知識の炎に育つ）**

---

## 2. 設計原則

### 知識蓄積型マルチエージェント実行フレームワーク

> 種火 — 小さな火種から、消えない炎へ。
> The spark that never dies — wisdom that grows with every task.

TANEBI は**タスク経験を種火として蓄え、蒸留された知識パターンをシステム全体に静かに反映するマルチエージェント実行フレームワーク**である。

#### 設計の三原則

| 原則 | 説明 |
|------|------|
| **蓄積** | すべてのタスク結果からシグナルを検出し、ドメイン別に蓄積する |
| **蒸留** | 十分なシグナルが溜まったら、具体的タスク情報を落として汎化パターンに蒸留する |
| **沈黙** | 蒸留された知識は Worker 起動時に自動注入される。ユーザーもエージェントも意識しない |

---

## 4. Learning Engine ライフサイクル

### 4.1 概要図

```
                    Learning Engine Lifecycle
                    ========================

  ┌─────────────────────────────────────────────────────────────┐
  │                                                             │
  │  1. Signal Detection          2. Accumulation               │
  │  ┌────────────────────┐       ┌────────────────────┐       │
  │  │ worker.completed   │──────▶│ knowledge/signals/ │       │
  │  │ checkpoint.completed│       │   {domain}/        │       │
  │  │ user feedback      │       │     signal_*.yaml  │       │
  │  └────────────────────┘       └────────┬───────────┘       │
  │                                         │                   │
  │                                         │ N ≥ K ?           │
  │                                         │                   │
  │  4. Application (Silent)       3. Distillation              │
  │  ┌────────────────────┐       ┌────────┴───────────┐       │
  │  │ Worker/Decomposer  │◀──────│ 汎化パターン抽出    │       │
  │  │ 起動時に自動注入    │       │ 具体情報を除去      │       │
  │  │                    │       │ → knowledge/learned/│       │
  │  └────────────────────┘       └────────────────────┘       │
  │                                                             │
  └─────────────────────────────────────────────────────────────┘
```

### 4.2 Phase 1: Signal Detection

タスク完了時に結果シグナルを検出する。シグナルはタスクの成否と品質を抽象化した軽量データ。

#### シグナルの発生源

| 発生源 | イベント | 説明 |
|--------|---------|------|
| Worker 完了 | `worker.completed` | `status` + `quality` からシグナル生成 |
| Checkpoint 完了 | `checkpoint.completed` | `verdict` + `attribution` からシグナル生成 |
| ユーザーフィードバック | （将来） | 構造化フィードバックを受信 |

#### シグナルの分類

| quality | status | シグナル種別 | weight |
|---------|--------|-------------|--------|
| GREEN | success | positive | 1.0 |
| YELLOW | success | weak_positive | 0.5 |
| RED | failure | negative | 1.0 |
| — | — | checkpoint_feedback | 1.0 |

#### シグナルの抽出ルール

`worker.completed` イベントから以下を自動抽出する:

1. **domain**: タスクのドメイン（`worker.completed.domain`）
2. **quality**: 品質評価（`GREEN` / `YELLOW` / `RED`）
3. **status**: 成否（`success` / `failure`）
4. **abstracted_context**: タスク内容の抽象化（具体的なファイル名・変数名等を除去）

`checkpoint.completed` イベントからは追加で以下を抽出:

5. **attribution**: 失敗帰属（`execution` / `input` / `partial`）
6. **round**: チェックポイントラウンド数

### 4.3 Phase 2: Accumulation

検出されたシグナルをドメイン別に蓄積する。

```
knowledge/signals/
├── coding/
│   ├── signal_20260115_001.yaml
│   ├── signal_20260116_002.yaml
│   └── signal_20260120_003.yaml
├── api_design/
│   └── signal_20260118_001.yaml
└── testing/
    ├── signal_20260115_001.yaml
    └── signal_20260119_002.yaml
```

蓄積はシンプルな追記操作。シグナルファイルは不変（immutable）であり、書き換えない。

#### 蓄積時の処理

1. シグナル YAML をドメインディレクトリに書き出す
2. ドメイン内のシグナル件数をカウント
3. **N ≥ K** の条件を確認し、蒸留フェーズへの移行を判断

### 4.4 Phase 3: Distillation（N≥K ルール）

同一ドメインで **K 件以上**のシグナルが蓄積され、パターンの収束が検出された場合、
具体的なタスク情報を落として汎化パターンに蒸留する。

#### 蒸留の条件

```
蒸留トリガー:
  同一ドメインのシグナル数 N ≥ K (デフォルト K=5)
  かつ
  同一パターン方向（positive or negative）が一定割合以上
```

#### 蒸留のプロセス

```
入力: N 件のシグナル（同一ドメイン）
  ↓
1. パターン収束分析
   - positive シグナルから共通する成功アプローチを抽出
   - negative シグナルから共通する失敗パターンを抽出
  ↓
2. 抽象化
   - 具体的なタスク ID、ファイルパス、変数名を除去
   - ドメイン固有の汎用パターンに昇格
  ↓
3. 信頼度算出
   - confidence = 一致シグナル数 / 総シグナル数
   - confidence < 0.6 の場合は蒸留を保留（データ不足）
  ↓
4. Learned Pattern 生成
   - knowledge/learned/{domain}/ に YAML ファイルとして書き出し
  ↓
5. シグナルアーカイブ（任意）
   - 蒸留済みシグナルを knowledge/signals/{domain}/archived/ に移動
```

#### 蒸留の主体

蒸留処理は **LLM ベース**で行う。シグナルの抽象化・パターン抽出は人間の介入なしに LLM が実行する。
具体的には `distill.requested` イベントを Event Store に発行し、Executor が LLM を使って蒸留処理を行い、`distill.completed` イベントを返す。

#### 蒸留時の注意事項

- **過学習の防止**: 少数のシグナルからパターンを抽出しない（K≥5 ルール）
- **矛盾の検出**: 同一ドメインで positive と negative が拮抗する場合は蒸留を保留
- **鮮度管理**: 古いシグナル（config で設定可能、デフォルト 90 日）は重みを減衰

### 4.5 Phase 4: Application（Silent）

Worker / Decomposer 起動時に、該当ドメインの Learned Patterns を**自動的に**プロンプトに注入する。

#### 注入のフロー

```
1. execute.requested イベント受信
2. subtask の domain を特定
3. knowledge/learned/{domain}/ から全 Learned Patterns を読み込み
4. Worker プロンプトに以下を追加:
   - approach パターン → 「推奨アプローチ」セクション
   - avoid パターン → 「回避すべきパターン」セクション
   - tooling パターン → 「推奨ツール構成」セクション
5. Worker 実行（Learned Patterns がコンテキストに含まれた状態で）
```

#### 注入の設計原則

| 原則 | 説明 |
|------|------|
| **サイレント** | Worker は自分が Learned Patterns を受け取っていることを意識しない |
| **非侵襲的** | 注入は追加情報の提供のみ。Worker の判断を強制しない |
| **ドメイン限定** | 関連ドメインのパターンのみ注入。無関係な知識は注入しない |
| **量の制御** | 注入パターン数に上限を設ける（デフォルト: approach 5 件、avoid 3 件） |

---

## 5. パターン分類と YAML フォーマット定義

### 5.1 パターン分類

Learned Patterns は以下の 4 種に分類される:

| 種別 | 説明 | 例 |
|------|------|-----|
| **approach** | 効くアプローチ | 「テストファーストで実装するとGREEN率が高い」 |
| **avoid** | 失敗するパターン | 「N+1クエリを放置するとRED評価になる」 |
| **decompose** | 効く分解パターン | 「API実装は schema→handler→test の順で分解すると効率的」 |
| **tooling** | 効くツール構成 | 「Python CLIにはclickよりargparseが軽量で適する」 |

### 5.2 Learned Pattern YAML フォーマット

```yaml
# knowledge/learned/{domain}/approach_001.yaml
id: approach_001
type: approach
domain: coding
pattern: "テストファーストで実装する"
detail: |
  実装前にテストケースを書き、RED→GREEN→Refactorのサイクルで進める。
  特にエッジケースを先にテストに含めておくと、実装漏れが減る。
signal_count: 12
confidence: 0.83
distilled_at: "2026-01-15"
source_signals:
  - signal_20260110_001
  - signal_20260111_003
  - signal_20260112_001
  # ... (蒸留元シグナルへの参照)
tags: [testing, workflow, quality]
```

```yaml
# knowledge/learned/{domain}/avoid_001.yaml
id: avoid_001
type: avoid
domain: database
pattern: "マイグレーション無しでスキーマ変更する"
detail: |
  既存テーブルのカラム変更をマイグレーションファイル無しで直接実行すると、
  ロールバック不能になりRED評価につながる。
signal_count: 7
confidence: 0.86
distilled_at: "2026-01-20"
source_signals:
  - signal_20260115_002
  - signal_20260116_001
tags: [database, migration, safety]
```

```yaml
# knowledge/learned/{domain}/decompose_001.yaml
id: decompose_001
type: decompose
domain: api_design
pattern: "API実装はschema→handler→test→docsの順で分解する"
detail: |
  API エンドポイントの実装タスクを分解する際、
  1. スキーマ/型定義  2. ハンドラ実装  3. テスト  4. ドキュメント
  の順序で Wave を切ると、依存関係が最小化され並列実行効率が上がる。
signal_count: 9
confidence: 0.78
distilled_at: "2026-02-01"
source_signals:
  - signal_20260125_001
  - signal_20260128_002
tags: [api, decomposition, workflow]
```

```yaml
# knowledge/learned/{domain}/tooling_001.yaml
id: tooling_001
type: tooling
domain: coding
pattern: "Python CLIにはargparseを使う"
detail: |
  軽量なCLIツールではclick等の外部依存よりargparseを使うことで
  依存関係を最小化し、CI/CD環境での実行が安定する。
signal_count: 6
confidence: 0.75
distilled_at: "2026-02-05"
source_signals:
  - signal_20260201_001
  - signal_20260203_001
tags: [python, cli, dependencies]
```

### 5.3 Signal YAML フォーマット

```yaml
# knowledge/signals/{domain}/signal_20260115_001.yaml
id: signal_20260115_001
type: signal
domain: coding
task_id: cmd_042
subtask_id: subtask_042_a
quality: GREEN
status: success
weight: 1.0
signal_type: positive
abstracted_context: "Python CLI ツールの実装。argparse使用。テストファースト。"
observation: |
  テストを先に書いてから実装したことで、エッジケースのカバレッジが高く、
  一発でGREEN評価を獲得した。
timestamp: "2026-01-15T10:00:00"
```

```yaml
# knowledge/signals/{domain}/signal_20260116_001.yaml
id: signal_20260116_001
type: signal
domain: database
task_id: cmd_045
subtask_id: subtask_045_b
quality: RED
status: failure
weight: 1.0
signal_type: negative
abstracted_context: "DBスキーマ変更。マイグレーション無しで直接ALTER TABLE実行。"
observation: |
  マイグレーションファイルを作成せずにスキーマを変更したため、
  ロールバックが不可能になり、修正に余分な工数が発生。
attribution: execution
timestamp: "2026-01-16T14:30:00"
```

---

## 6. ディレクトリ構造

### 6.1 新 knowledge/ 構造

旧構造と新構造の対比:

```
# 旧構造
knowledge/
├── few_shot_bank/          # 成功事例のみ
│   ├── backend/
│   └── testing/
└── episodes/               # 未使用

# 新構造
knowledge/
├── signals/                # Phase 2: シグナル蓄積（生データ）
│   ├── coding/
│   │   ├── signal_20260115_001.yaml
│   │   └── signal_20260116_002.yaml
│   ├── api_design/
│   │   └── signal_20260118_001.yaml
│   ├── database/
│   │   └── signal_20260120_001.yaml
│   └── testing/
│       └── signal_20260115_001.yaml
│
├── learned/                # Phase 3: 蒸留済みパターン（蒸留知識）
│   ├── coding/
│   │   ├── approach_001.yaml
│   │   ├── avoid_001.yaml
│   │   └── tooling_001.yaml
│   ├── api_design/
│   │   ├── approach_001.yaml
│   │   └── decompose_001.yaml
│   ├── database/
│   │   └── avoid_001.yaml
│   └── testing/
│       └── approach_001.yaml
│
└── _meta/                  # メタデータ
    ├── domains.yaml        # 既知ドメイン一覧
    └── distill_log.yaml    # 蒸留実行ログ
```

### 6.2 旧ディレクトリとの対応

| 旧パス | 新パス | 備考 |
|--------|--------|------|
| `knowledge/few_shot_bank/` | `knowledge/learned/` | Few-Shot は approach パターンの一形態として吸収 |
| `knowledge/episodes/` | `knowledge/signals/` | エピソード記録はシグナルとして再定義 |

### 6.3 config.yaml のパス設定変更

```yaml
# 旧設定
paths:
  knowledge_dir: "knowledge"
  few_shot_dir: "knowledge/few_shot_bank"
  episode_dir: "knowledge/episodes"

# 新設定
paths:
  knowledge_dir: "knowledge"
  signals_dir: "knowledge/signals"
  learned_dir: "knowledge/learned"
```

---

## 7. 主要コンポーネント

| コンポーネント | 説明 |
|--------------|------|
| `few_shot_bank` → **Learned Patterns** | 成功事例だけでなく失敗パターン等も含む上位概念（`knowledge/learned/`） |
| `anti_patterns` → **Avoid Patterns** | Learned Patterns の一種（`type: avoid`） |
| `src/tanebi/core/signal.py` | Signal Detection ロジック |
| `src/tanebi/core/distill.py` | 蒸留エンジン（LLM ベースのパターン抽出） |
| `src/tanebi/core/inject.py` | Worker 起動時の Learned Patterns 自動注入 |
| `events/schema.yaml` | `distill.requested` / `distill.completed` イベント定義 |

---

## 8. 実装済みコンポーネント

| コンポーネント | 説明 |
|--------------|------|
| Signal Detection | `worker.completed` からシグナルを自動抽出（`src/tanebi/core/signal.py`） |
| Signal Accumulation | ドメイン別シグナル蓄積（`knowledge/signals/`） |
| Pattern Distillation | N≥K ルールに基づくパターン蒸留（`src/tanebi/core/distill.py`） |
| Silent Application | Worker 起動時の自動パターン注入（`src/tanebi/core/inject.py`） |
| `distill.requested/completed` | 蒸留処理用イベント（`events/schema.yaml`） |
| Learned Patterns | 蒸留済み知識パターン（`knowledge/learned/`） |

---

## 9. 実装ロードマップ

### 9.1 コード実装フェーズ

#### Wave 1: 知識基盤の構築（完了）

1. `knowledge/signals/` ディレクトリ構造を作成
2. `knowledge/learned/` ディレクトリ構造を作成
3. Signal Detection ロジックの実装（`src/tanebi/core/signal.py`）
4. Signal YAML の書き出し処理の実装

#### Wave 2: 蒸留エンジン（完了）

5. `src/tanebi/core/distill.py` の新規作成
6. `distill.requested` / `distill.completed` イベントの追加
7. 蒸留処理の実装（LLM ベースのパターン抽出）
8. `knowledge/_meta/distill_log.yaml` の管理

#### Wave 3: サイレント注入（完了）

9. Worker テンプレート (`templates/worker_base.md`) に Learned Patterns 注入セクションを追加
10. Executor の Worker 起動時に `knowledge/learned/{domain}/` を読み込み、プロンプトに注入するロジック（`src/tanebi/core/inject.py`）
11. 注入量の制御（config.yaml の `learning.max_inject_*` パラメータ）

---

## 10. 設計の制約と今後の課題

### 10.1 現時点の制約

| 制約 | 説明 | 対処方針 |
|------|------|---------|
| **蒸留品質は LLM 依存** | パターン抽出の品質は蒸留を行う LLM の能力に依存する | 蒸留結果の confidence を測定し、閾値未満は破棄 |
| **ドメイン分類の曖昧さ** | タスクのドメイン特定が自動化困難な場合がある | 初期は worker.completed の domain フィールドに依存。将来的にドメイン推定 LLM を導入 |
| **シグナル量の Cold Start** | 初期段階ではシグナルが少なく、蒸留が発動しない | K の初期値を低め（5）に設定。旧 Few-Shot Bank のデータをシグナルに変換して初期投入も検討 |
| **パターンの陳腐化** | 技術や要件の変化により過去のパターンが無効になる場合がある | パターンに `distilled_at` を記録し、一定期間経過後に再検証する仕組みを将来導入 |
| **注入量の最適化** | 注入パターンが多すぎるとコンテキスト圧迫、少なすぎると効果薄 | config.yaml で上限を設定し、confidence 順で上位のみ注入 |

### 10.2 今後の課題

#### 短期（Wave 1-3 完了後）

- **蒸留品質の測定フレームワーク**: 蒸留されたパターンが実際に品質向上に寄与しているか測定する仕組み
- **シグナル→パターンの自動パイプライン**: 蒸留トリガーの自動化（現時点では手動 or タスク完了時のフック）
- **旧 Few-Shot Bank データの移行スクリプト**: 既存の `knowledge/few_shot_bank/` データを `knowledge/learned/` + `knowledge/signals/` 形式に変換

#### 中期

- **Cross-Domain Patterns**: 複数ドメインに跨がるパターンの蒸留（例: 「API + テスト」の複合パターン）
- **Pattern Versioning**: 同一パターンの更新・進化の追跡
- **Confidence Decay**: 時間経過による confidence の減衰とパターンの自動再検証
- **ユーザーフィードバックの統合**: 構造化フィードバックをシグナルソースとして追加

#### 長期

- **Knowledge GC**: 利用されないパターンの自動削除
- **Pattern Conflicts Resolution**: 矛盾するパターン（approach vs avoid が同一行動を指す）の自動検出と解決
- **Learning Effectiveness Dashboard**: 学習の効果をシステム全体で可視化するダッシュボード
- **Federated Learning**: 複数の TANEBI インスタンス間でのパターン共有（組織レベルの知識蓄積）

### 10.3 設計上の意図的な制約

以下は意図的に設計に含めていない機能である:

| 除外した機能 | 除外理由 |
|------------|---------|
| **パターンの自動適用強制** | LLM の判断を尊重。パターンは参考情報であり、指示ではない |
| **リアルタイム学習** | タスク実行中にパターンを更新すると一貫性が崩れる。蒸留はタスク完了後 |
| **Worker 個別の知識** | 知識はシステム共有。個別 Worker の知識サイロ化を防ぐ |
| **ペルソナの完全廃止（Phase 1 で）** | 後方互換性のため段階的に移行。急激な変更は避ける |

---

## 付録 A: config.yaml learning セクション（新設計）

```yaml
tanebi:
  # === Learning Engine 設定 ===
  learning:
    # シグナル蓄積
    signal:
      auto_detect: true              # worker.completed からシグナル自動検出
      retention_days: 90             # シグナル保持日数（超過分は重み減衰）

    # 蒸留
    distillation:
      min_signals: 5                 # 蒸留に必要な最小シグナル数（K）
      min_confidence: 0.6            # 蒸留に必要な最小信頼度
      auto_trigger: true             # N≥K 到達時に自動蒸留
      model: "claude-sonnet-4-6"     # 蒸留に使用するモデル

    # パターン注入
    injection:
      max_approach: 5                # 注入する approach パターンの上限
      max_avoid: 3                   # 注入する avoid パターンの上限
      max_decompose: 2               # 注入する decompose パターンの上限
      max_tooling: 2                 # 注入する tooling パターンの上限
      sort_by: confidence            # 注入優先度（confidence / distilled_at）

```

## 付録 B: 新イベント定義

```yaml
# events/schema.yaml に追加

  # Learning Engine Events
  distill.requested:
    task_id: string
    domain: string
    signal_count: integer
    signal_ids: array               # 蒸留対象のシグナル ID リスト
    timestamp: string

  distill.completed:
    task_id: string
    domain: string
    patterns_created: array          # 生成された Learned Pattern ID リスト
    confidence: number
    timestamp: string
```

## 付録 C: フロー制御の変更

旧フロー:
```
DECOMPOSE → EXECUTE → AGGREGATE → (EVOLVE)
```

新フロー:
```
DECOMPOSE → EXECUTE → AGGREGATE → SIGNAL_DETECT → (DISTILL if N≥K)
```

SIGNAL_DETECT は毎タスク実行。DISTILL は N≥K 条件成立時のみ実行。
