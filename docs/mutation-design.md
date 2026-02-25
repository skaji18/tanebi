# Mutation機構 設計検討

> **Status**: Design Document (実装なし)
> **Date**: 2026-02-25

## 1. 背景と目的

### 1.1 問題: 局所最適への収束

LLMベースのマルチエージェントシステムは、以下の理由で局所最適に陥りやすい:

- **Sycophancy（追従性）**: LLMは批判よりも肯定を生成しがち
- **パターン固着**: Learning Engineが成功パターンを蓄積→同じアプローチを繰り返す
- **チェックポイントの甘さ**: Checkpoint workerも同じLLMであり、厳しい判定を避ける傾向

Mutation機構は「本当にそれでいいのか？」という対抗圧力を体系的に注入し、局所最適からの脱出を促す。

### 1.2 4層ハイブリッドアーキテクチャ

| Layer | 機構 | トリガー | コスト | カバレッジ |
|-------|------|----------|--------|-----------|
| **L0** | Self-Challenge Prompt | 常時ON | 最小 | 70-80% |
| **L1** | Mutation Keywords | ユーザー指定 | 低 | 75-85% |
| **L2A** | Enhanced Reviewer (Red Pen Protocol) | 自動(複雑タスク) | 中 | 70-85% |
| **L2B** | 専用Mutation Worker | 手動呼び出し | 高 | 85-90% |

設計原則: **Progressive Validation** — L0で70-80%カバーできるならそこで停止。実測に基づき次層に進む。

### 1.3 TANEBIにおける意義

TANEBIのLearning Engineは「何がうまくいったか」を蓄積・注入する**正のフィードバックループ**。
Mutationは「それは本当に正しいか」を問う**負のフィードバックループ**。

```
Learning Engine:  成功 → signal → distill → inject (強化)
Mutation:         出力 → challenge → contradict → improve (挑戦)
```

両者は補完関係にある。Learningだけでは「過去の成功パターンへの過剰適合」リスクがある。Mutationがそれを防ぐ。

---

## 2. 各層のTANEBI適用分析

### 2.1 Layer 0: Self-Challenge Prompt

#### 概要

全ワーカー出力に`## Self-Challenge`セクションを義務化するプロンプト注入。

Anti-sycophancy措置:
- 最低1つのベースライン矛盾を義務化
- Bad/Good例示で品質基準を明示
- RE-CHALLENGE指令（全発見がベースラインと一致なら再考を強制）

#### TANEBIでの対応先

**`templates/worker_base.md`** — Worker系テンプレートへの直接注入。

TANEBIにはすでに`<!-- LEARNED_PATTERNS_SECTION -->`という動的注入ポイントが存在する。Self-Challenge Promptはこれとは別に、テンプレート本文に**静的に**埋め込む。

```
templates/worker_base.md
├── 既存: LEARNED_PATTERNS_SECTION (動的・inject.pyが置換)
└── 追加: Self-Challenge Section (静的・テンプレート本文)
```

#### 親和性: ★★★★★

TANEBIのテンプレートシステムとの親和性は最高。理由:
- テンプレート編集のみ、コード変更不要
- 既存のWorker出力フォーマット（YAMLフロントマター）にセクション追加するだけ
- Learning Engineのsignal detectionが`quality`フィールドを読む→Self-Challenge結果の追跡も同じパスで可能

#### 期待効果とコスト

| 項目 | 値 |
|------|-----|
| 実装コスト | テンプレート数行追加（~1時間） |
| トークンコスト増 | Worker出力あたり+200-400トークン |
| 期待効果 | trivialタスクの品質向上、明白な見落とし防止 |
| 限界 | 同一LLMの自己批判→sycophancy上限あり（70-80%） |

#### 設計判断

1. **出力フォーマット統合**: Worker出力のYAMLフロントマターに`self_challenge_findings`フィールドを追加するか、本文Markdownセクションとするか
   - **推奨: Markdownセクション**。フロントマターは機械処理用、Self-Challengeは人間+Checkpoint向け
2. **Signal Detection連携**: Self-Challengeで重大な問題を自己発見した場合、`quality: RED`にすべきか
   - **推奨: Workerの自己判定に委ねる**。Self-Challengeは「気づき」の提示であり、品質判定はCheckpointの役割

---

### 2.2 Layer 1: Mutation Keywords

#### 概要

`request.md`内のキーワードをDecomposerが検出し、戦略固有の指示をサブタスクに注入する。

キーワード→戦略マッピング:
- "challenge assumptions" → assumption_reversal
- "find flaws" / "red team" → adversarial_review
- "explore alternatives" → alternative_exploration
- "critical challenges" → comprehensive_mutation（全戦略適用）

#### TANEBIでの対応先

**`templates/decomposer.md`** — Decomposer テンプレートでの検出・注入。

TANEBIのDecomposerはすでに`request.md`を読み、`plan.md`を生成する。キーワード検出ロジックをDecomposerテンプレートに追加し、plan.md内のサブタスク記述に戦略指示を埋め込む。

```
request.md ("explore alternatives"を含む)
  ↓
Decomposer (キーワード検出)
  ↓
plan.md (subtask descriptionに戦略指示を追加)
  ↓
Worker (戦略指示に従い代替案を探索)
```

#### 親和性: ★★★★☆

高い親和性。ただし1点注意:
- TANEBIのDecomposerはテンプレート（プロンプト）のみで動作する。キーワード→戦略マッピングをテンプレート内にハードコードするか、config.yamlに外出しするか

#### 期待効果とコスト

| 項目 | 値 |
|------|-----|
| 実装コスト | Decomposerテンプレート改修 + config.yamlにキーワード定義（~3-4時間） |
| トークンコスト増 | 戦略指示分 +100-200トークン/サブタスク |
| 期待効果 | ユーザーが意図的にMutationを要求→深い代替案探索 |
| 限界 | ユーザーがキーワードを書かない限り発火しない |

#### 設計判断

1. **キーワード定義の配置**:
   - **案A**: `config.yaml`に`mutation.keywords`セクション追加
   - **案B**: Decomposerテンプレート内にハードコード
   - **推奨: 案A**。config.yamlに置くことでプロジェクトごとにカスタマイズ可能

2. **自動キーワード注入**:
   - TANEBIのCheckpoint fail → re-decompose時に自動でキーワードを追加できる
   - `checkpoint.completed(verdict=fail)`のfeedbackにmutationキーワードを含める
   - **推奨: Phase 2以降で検討**。まずは手動キーワードで効果測定

3. **config.yaml追加案**:

```yaml
tanebi:
  mutation:
    keywords:
      challenge_assumptions: assumption_reversal
      find_flaws: adversarial_review
      red_team: adversarial_review
      explore_alternatives: alternative_exploration
      critical_challenges: comprehensive
```

---

### 2.3 Layer 2A: Enhanced Reviewer / Red Pen Protocol

#### 概要

レビュワーに敵対的レビュープロトコルを適用する:
1. Assumption Audit — 前提の精査（3-5個）
2. Failure Mode Catalog — 5種の障害モード列挙
3. Pre-Mortem — 「6ヶ月後に大失敗した。原因は？」
4. Evidence Audit — 根拠なき主張のフラグ
5. Alternative Check — ベースラインと矛盾する代替パラダイム

verdict（approve/revise/reject）をAggregatorに流す。

#### TANEBIでの対応先

**`templates/checkpoint.md`** — Checkpoint テンプレートの強化。

これはTANEBIにとって**最も自然な統合点**。理由:

1. **Checkpointはすでにレビュワー**: Worker出力を評価し、verdict（pass/fail）を出す
2. **Round機構が既存**: fail時のre-decompose + feedbackフローが実装済み
3. **attribution分析が既存**: execution/input/partialの帰属分析がCheckpointの役割

Red Pen ProtocolはCheckpointの「評価基準を厳格化する」だけであり、新しいイベントやフローは不要。

```
既存:
  checkpoint.requested → Checkpoint Worker → checkpoint.completed(verdict, attribution)

強化後:
  checkpoint.requested → Checkpoint Worker [Red Pen Protocol] → checkpoint.completed(verdict, attribution, mutation_findings)
```

#### 親和性: ★★★★★

最高の親和性。Checkpoint機構とRed Pen Protocolは同じ目的を持つ。差分はテンプレート内容の強化のみ。

#### 期待効果とコスト

| 項目 | 値 |
|------|-----|
| 実装コスト | checkpoint.mdテンプレート強化（~2-3時間） |
| トークンコスト増 | Checkpoint出力あたり+300-500トークン |
| 期待効果 | 甘いpass判定の防止、深い障害モード分析 |
| 限界 | 同一LLMがビルドとレビュー→認知的不協和（sycophancy 15-20%） |

#### 設計判断

1. **checkpoint.completedペイロード拡張**:
   - 既存: `{ verdict, failed_subtasks, summary, attribution }`
   - 追加: `{ mutation_findings: [...], assumption_challenges: [...] }`
   - **推奨: summary内にMarkdownとして含める**。ペイロードスキーマ変更は影響範囲が大きい

2. **verdict_policyとの関係**:
   - 現在`any_fail`がデフォルト。Red Pen ProtocolでFail率が上がる可能性
   - `max_rounds: 3`で過剰な再実行ループを防止（既存のまま十分）

3. **Learning Engine連携**:
   - Red Pen Protocolで見つかった問題パターン→signal detectionに流す
   - checkpoint.completedのmutation_findings → `avoid`タイプのLearnedPatternとして蓄積可能
   - **推奨: Phase 3以降で検討**。まずはCheckpoint単体の強化から

---

### 2.4 Layer 2B: 専用Mutation Worker

#### 概要

タスク完了後にオンデマンドで呼び出す専用のMutationワーカー。

5戦略: assumption_reversal, adversarial_review, alternative_exploration, failure_mode_analysis, paradigm_challenge

専用ワーカーのため認知的不協和なし（sycophancy ~10%）。出力は`mutation_report.md`に分離。

#### TANEBIでの対応先

代替案を3つ検討する。

**案A: 新イベントタイプ `mutate.requested` / `mutate.completed`**

```
aggregate.completed (or ユーザーリクエスト)
  ↓
Core → emit mutate.requested { task_id, target_path, strategy }
  ↓
Executor → Mutation Worker (templates/mutator.md)
  ↓
emit mutate.completed { task_id, findings, report_path }
```

- 利点: TANEBIのイベント駆動アーキテクチャに完全準拠
- 欠点: Event Catalogに2イベント追加、flow.pyにハンドラ追加
- 結果ファイル: `work/{task_id}/mutation_report.md`

**案B: Checkpointの特殊モード（mutation_checkpoint）**

```
config.yaml:
  checkpoint:
    mode: always
    mutation_mode: dedicated  # none / dedicated / enhanced

# mutation_mode: dedicated の場合、通常Checkpoint + 別途Mutation Checkpointを実行
```

- 利点: 既存Checkpoint機構の拡張、新イベント不要
- 欠点: Checkpointの責務が肥大化、設計の単純さを損なう

**案C: Post-Aggregation Hook**

```
task.aggregated → (条件判定) → mutate.requested → mutate.completed → 最終レポート更新
```

- 利点: 明確なタイミング（Aggregation後）
- 欠点: タスクフローが長くなる、コスト増

#### 推奨: 案A（新イベントタイプ）

理由:
1. TANEBIの設計原則「Core/Executorはイベントのみで通信」に最も忠実
2. 既存コンポーネントの責務を肥大化させない
3. 将来的にMutation結果をLearning Engineに流すパスが明確
4. On-demand実行（APIから`mutate.requested`を直接emit）も自然にサポート

#### 親和性: ★★★☆☆

中程度。新イベント追加は設計変更を伴うが、TANEBIのイベント駆動アーキテクチャに沿った拡張。

#### 期待効果とコスト

| 項目 | 値 |
|------|-----|
| 実装コスト | 新テンプレート + Event Catalog拡張 + flow.pyハンドラ + Executor対応（~15-20時間） |
| トークンコスト増 | Mutation Worker実行分（タスクあたり+1000-3000トークン） |
| 期待効果 | 専用ワーカーによる最高品質のMutation（sycophancy ~10%） |
| 限界 | コスト高、全タスクに適用は非現実的 |

#### 設計判断

1. **トリガー条件**: いつMutation Workerを起動するか
   - 手動: API経由でユーザーが要求
   - 自動: 特定条件（複雑タスク、round>=2、キーワード検出）
   - **推奨: まず手動のみ。自動トリガーはPhase 4以降**

2. **パス渡し原則との整合**:
   - Mutation WorkerもCoreの出力内容を読まない（パスのみ）
   - Mutation Worker自身が`report.md`を読み、`mutation_report.md`を出力
   - Coreは`mutation_report.md`のパスのみ保持

3. **templates/mutator.md**: 新テンプレート
   - 5戦略をすべて含むか、戦略別テンプレートにするか
   - **推奨: 単一テンプレート + 戦略パラメータ**。テンプレート増殖を防ぐ

---

## 3. 既存機構との関係

### 3.1 Learning Engine（signal→distill→inject）との補完性

```
                ┌──────────────────────────┐
                │     Learning Engine      │
                │  「何がうまくいったか」    │
                │  正のフィードバック        │
                └────────────┬─────────────┘
                             │ inject (approach, tooling)
                             ▼
                    ┌──────────────┐
                    │    Worker    │
                    └──────────────┘
                             ▲
                             │ inject (avoid, challenge)
                ┌────────────┴─────────────┐
                │     Mutation Engine      │
                │  「本当にそれでいいか」    │
                │  負のフィードバック        │
                └──────────────────────────┘
```

**重複はない。補完関係。**

- Learning: `approach`（成功戦略）と`tooling`（ツール推奨）を注入
- Mutation: `avoid`（失敗パターン）と`challenge`（前提への挑戦）を注入
- 同じ`inject.py`を通じて両方をWorkerに注入可能

**リスク: Learning Engineの強化ループがMutationを打ち消す可能性**

Learning Engineが「パターンXは常に成功」と学習した場合、Self-Challenge Promptで「パターンXは本当に正しいか」と問うても、inject済みのLearned Patternが支配する可能性がある。

**対策**: Learned Patternの`confidence`スコアにdecay（減衰）を導入。長期間Mutationで挑戦されていないパターンはconfidenceを下げる。ただしこれはPhase 4以降の最適化。

### 3.2 Checkpoint機構との関係

```
現在のCheckpoint:
  verdict: pass/fail
  attribution: execution/input/partial
  → fail時: re-decompose(round++)

Red Pen強化後:
  verdict: pass/fail
  attribution: execution/input/partial
  mutation_findings: [前提の問題, 障害モード, ...]
  → fail時: re-decompose(round++) + mutation_findingsをfeedbackに含める
```

Checkpoint機構はRed Pen Protocolの**自然なホスト**。新しいフローを作るのではなく、既存フローの品質を上げる。

### 3.3 Templates注入ポイントまとめ

| テンプレート | 現在の注入 | Mutation追加 |
|------------|-----------|-------------|
| `worker_base.md` | `LEARNED_PATTERNS_SECTION`（動的） | Self-Challenge Section（静的） |
| `decomposer.md` | Learned Patterns参照 | Mutation Keywords検出ロジック |
| `checkpoint.md` | verdict + attribution | Red Pen Protocol 5ステップ |
| `aggregator.md` | 品質サマリー | 変更なし（Mutation結果は別パス） |
| **`mutator.md`** | *(新規)* | 5戦略のMutation指示 |

### 3.4 EventStore拡張

L2Bを採用する場合のEvent Catalog変更:

| Event | Category | Payload |
|-------|----------|---------|
| `mutate.requested` | Core→Executor | `{ task_id, target_path, strategy, round }` |
| `mutate.completed` | Executor→Core | `{ task_id, report_path, findings_count, critical_count }` |

flow.pyへのハンドラ追加:
```
task.aggregated → (mutation_mode check) → emit mutate.requested
mutate.completed → task.completed (or manual review待ち)
```

---

## 4. 設計上の考慮事項

### 4.1 Skill呼び出し vs イベント駆動

L2B（専用Mutation Worker）の呼び出し方式について:

| 方式 | 特徴 |
|------|------|
| Skill呼び出し（即座・同期的） | 単一セッション内で完結。呼び出し側のコンテキストを消費する |
| イベント駆動（非同期） | 独立ワーカーとして実行。物理的にプロセスが分離される |

**TANEBIの利点**: Mutation Workerが完全に独立したプロセスで動くため、原著作ワーカーとの認知的不協和が物理的に排除される。Skill方式では同一セッション内で動くため10%程度のsycophancyが残るが、プロセス分離によりさらに低減が期待できる。

### 4.2 Path-Passing原則との整合

TANEBIのCore設計原則: **Coreはワーカー出力の内容を読まない。パスのみ保持する。**

Mutation機構でもこれを厳守:

```
# OK: パスのみ渡す
mutate.requested: { target_path: "work/cmd_001/report.md", strategy: "adversarial_review" }
mutate.completed: { report_path: "work/cmd_001/mutation_report.md" }

# NG: 内容をイベントペイロードに含める
mutate.completed: { findings: "問題1: XXX, 問題2: YYY" }  ← 違反
```

### 4.3 実行モード互換性

Mutation機構は**両モードで動作する**必要がある:

| モード | L0 | L1 | L2A | L2B |
|--------|----|----|-----|-----|
| claude-native | テンプレート | テンプレート | テンプレート | CLAUDE.mdにハンドラ追加 |
| 外部Listener | テンプレート | テンプレート | テンプレート | listener.pyにハンドラ追加 |

L0-L2Aはテンプレートのみの変更なので両モード自動対応。L2Bのみ両モードのハンドラ追加が必要。

---

## 5. 推奨アプローチ

### 5.1 採用判断サマリー

| Layer | 採用推奨 | 理由 |
|-------|---------|------|
| **L0: Self-Challenge** | **強く推奨** | 最小コストで最大効果。テンプレート編集のみ。Progressive Validationの起点。 |
| **L1: Mutation Keywords** | **推奨** | L0の効果測定後、条件付き導入。config.yaml拡張で自然に統合。 |
| **L2A: Red Pen Protocol** | **推奨** | Checkpoint強化として最も自然。既存フローを活用し新規コンポーネント不要。 |
| **L2B: Mutation Worker** | **条件付き** | コスト高。L0-L2Aで不十分な場合のみ。新イベントタイプ追加が必要。 |

### 5.2 段階的導入計画

Progressive Validationの原則に従い、効果測定をゲートとして段階的に導入する。

```
Phase 1: L0 Deploy + Measure
  ↓ (効果 >=60% → STOP)
Phase 2: L1 Deploy + Measure
  ↓ (L0+L1効果 >=70% → STOP)
Phase 3: L2A Deploy + Measure
  ↓ (L0+L1+L2A効果 >=85% → L2B不要)
Phase 4: L2B Deploy (条件付き)
```

#### Phase 1: Self-Challenge導入（推定1-2時間）

**作業内容**:
1. `templates/worker_base.md`にSelf-Challenge Sectionを追加
2. Self-ChallengeプロンプトをTANEBI向けに調整:
   - TANEBIのWorker出力フォーマット（YAMLフロントマター + Markdown本文）に合わせる
   - `## Self-Challenge`セクションを本文末尾に追加する形式
3. trivialタスク（<10分）は簡易版（障害シナリオ2つ）、complexタスクは完全版

**効果測定**（10タスク実行後）:
- Compliance Rate（Self-Challengeセクション出力率）>=65%
- Genuine Critique Rate（実質的な批判を含む率）>=60%
- User Value Rate（ユーザーにとって有用な指摘率）>=50%

**Go/No-Go**:
- >=60%効果 → **STOP**（L0で十分）
- 30-60% → Phase 2へ
- <30% → L0設計見直し or KILL

#### Phase 2: Mutation Keywords導入（推定3-4時間）

**作業内容**:
1. `config.yaml`に`mutation.keywords`セクション追加
2. `templates/decomposer.md`にキーワード検出ロジック追加
3. 検出時、plan.md内のサブタスク記述に戦略指示を埋め込む

**効果測定**:
- Keyword Adoption Rate（ユーザーがキーワードを使う率）>=30%
- Combined Mutation Value（L0+L1）>=60%

#### Phase 3: Red Pen Protocol導入（推定2-3時間）

**作業内容**:
1. `templates/checkpoint.md`にRed Pen Protocol 5ステップを追加
2. checkpoint.completedのsummaryにmutation findings含める
3. re-decompose時のfeedbackにmutation findingsを自動注入

**効果測定**:
- False Positive Rate（不当なfail判定率）<30%
- Combined Mutation Value（L0+L1+L2A）>=85%

#### Phase 4: Mutation Worker導入（推定15-20時間、条件付き）

**作業内容**:
1. Event Catalogに`mutate.requested` / `mutate.completed`追加
2. `templates/mutator.md`新規作成
3. `src/tanebi/core/flow.py`にmutationハンドラ追加
4. `src/tanebi/executor/listener.py`にMutation Worker起動ロジック追加
5. claude-nativeモードのCLAUDE.mdにハンドラテーブル追記

**Go/No-Go**: L0+L1+L2Aで85%以上達成していればPhase 4は**不要**。

### 5.3 設計判断まとめ

| 判断ポイント | 推奨 | 理由 |
|-------------|------|------|
| Self-Challenge出力形式 | Markdownセクション（フロントマター外） | 人間+Checkpoint向け、機械処理不要 |
| Keywords定義の配置 | config.yaml | プロジェクトごとにカスタマイズ可能 |
| L2A実装先 | checkpoint.md強化 | 既存フロー活用、新コンポーネント不要 |
| L2B実装方式 | 新イベントタイプ | TANEBIのイベント駆動原則に忠実 |
| Mutation結果のLearning連携 | Phase 3以降で検討 | まず各層の単体効果を測定 |
| Learned Pattern decay | Phase 4以降で検討 | 過剰最適化防止の高度な最適化 |
| 自動Mutation Keyword注入 | Phase 2以降で検討 | Checkpoint fail時のre-decomposeに組込み |

---

## 6. リスク分析

| リスク | 確率 | 影響 | 軽減策 |
|--------|------|------|--------|
| L0 compliance <50% | 中 | Mutation機構全体の基盤が弱い | プロンプト調整、6行簡易版にフォールバック |
| L2A False Positive過多 | 中 | ユーザー体験悪化（過剰なfail） | verdict_policyを`majority`に変更、Red Pen閾値調整 |
| トークンコスト増大 | 中 | 運用コスト上昇 | trivialタスクではL0のみ（L2A/L2B適用外） |
| Learning Engine + Mutation の干渉 | 低 | パターン矛盾による品質低下 | inject.pyでMutation findingsとLearned Patternsの競合を検出 |
| L2B実装コスト>見込み | 中 | 開発遅延 | Progressive Validationにより不要と判断される可能性が高い |

---

## 7. 結論

4層Mutation機構はTANEBIに**高い親和性**を持つ。特にL0（Self-Challenge）とL2A（Red Pen Protocol）はTANEBIの既存テンプレート・Checkpoint機構と自然に統合できる。

**最重要ポイント**: Progressive Validationの原則を厳守する。L0だけで70-80%カバーできる可能性がある。実測なしにL2Bまで実装するのは過剰投資。

TANEBIの強みであるEvent-Driven Architecture、Learning Engine、Checkpoint機構を活かし、Mutationを「もう一つのフィードバックループ」として統合することで、局所最適への耐性を獲得しつつ、フレームワークの設計一貫性を維持できる。
