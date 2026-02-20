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

`templates/decomposer.md` を Read tool で読み取り、以下のプレースホルダーを展開して
Task tool の prompt として使用する:

- `{REQUEST_PATH}` → `work/cmd_NNN/request.md` の絶対パス
- `{PERSONA_LIST}` → `personas/active/` のYAMLファイル名一覧（拡張子なし）
- `{PLAN_PATH}` → `work/cmd_NNN/plan.md` の絶対パス
- `{CMD_ID}` → cmd_NNN
- `{TIMESTAMP}` → ISO8601形式の現在時刻

Task tool でDecomposerを起動し、出力 `work/cmd_NNN/plan.md` を待つ。

### Trust Module チェック

各サブタスクのPersona割り当て前に信頼スコアを検証する:

```bash
bash modules/trust/trust_module.sh on_task_assign {PERSONA_ID} {TASK_RISK_LEVEL}
# 戻り値が1の場合は別のPersonaを選択すること
```

- `{TASK_RISK_LEVEL}` は Decomposer が plan.md で指定（low / medium / high）
- 拒否された場合、次に適応度の高い別のPersonaで再試行する

### Step 3: EXECUTE（Worker群を並列起動）

`plan.md` を Read tool で読み、各サブタスクに対して以下を実行:

**Persona YAMLの読み取りとプレースホルダー展開:**

割り当てPersona YAML（`personas/active/{persona_id}.yaml`）を Read tool で読み取り、
`templates/worker_base.md` の以下のプレースホルダーを展開して Task tool の prompt として使用する:

- `{PERSONA_PATH}` → `personas/active/{persona_id}.yaml` の絶対パス
- `{PERSONA_NAME}` → `persona.identity.name`
- `{PERSONA_ARCHETYPE}` → `persona.identity.archetype`
- `{PERSONA_SPEECH_STYLE}` → `persona.identity.speech_style`
- `{PERSONA_DOMAINS}` → `persona.knowledge.domains` の一覧（name + proficiency）
- `{BEHAVIOR_RISK_TOLERANCE}` → `persona.behavior.risk_tolerance`
- `{BEHAVIOR_DETAIL_ORIENTATION}` → `persona.behavior.detail_orientation`
- `{BEHAVIOR_SPEED_VS_QUALITY}` → `persona.behavior.speed_vs_quality`
- `{FEW_SHOT_PATHS}` → `knowledge/few_shot_bank/{domain}/` 以下の関連ファイルパス一覧（なければ "なし"）
- `{SUBTASK_ID}` → サブタスクID
- `{TASK_DESCRIPTION}` → サブタスクの説明
- `{OUTPUT_PATH}` → `work/cmd_NNN/results/{SUBTASK_ID}.md` の絶対パス

**Waveベースの並列実行:**

- 同一wave内のサブタスク → **同一メッセージで複数 Task tool 呼び出し**（並列起動）
- Wave N が全て完了してから Wave N+1 を開始
- 出力先: `work/cmd_NNN/results/{subtask_id}.md`

### Step 4: AGGREGATE（Aggregatorに委譲）

全Worker完了後、`templates/aggregator.md` を Read tool で読み取り、以下のプレースホルダーを展開して
Task tool の prompt として使用する:

- `{RESULTS_DIR}` → `work/cmd_NNN/results/` の絶対パス
- `{REPORT_PATH}` → `work/cmd_NNN/report.md` の絶対パス
- `{CMD_ID}` → cmd_NNN
- `{TIMESTAMP}` → ISO8601形式の現在時刻

**パス受け渡し係原則（再確認）**: オーケストレーター自身は `results/` ファイルの内容を読まない。
Aggregator にディレクトリパスを渡すだけ。Aggregator が内容を読んで統合レポートを生成する。

### Step 5: EVOLVE（進化ループ）

Aggregator完了後、以下のコマンドで進化ステップを実行:

```bash
bash scripts/evolve.sh work/{CMD_ID}
```

**進化完了後の確認:**

```bash
cat personas/active/{persona_id}.yaml
# → performance.total_tasks, success_rate, last_task_date が更新されているはず
# → evolution.last_evolution_event に今回のコマンドが追記されているはず
```

`evolve.sh` はWorker結果の YAML frontmatter を解析し、対応するPersonaのパフォーマンス統計を
自動更新する。GREEN品質のタスクはFew-Shot Bankへ自動登録される。

**evolve.sh が実行する進化ステップ:**

1. **パフォーマンス更新**: `total_tasks`, `success_rate`, `last_task_date` を更新
2. **失敗補正**: 失敗したドメインの `proficiency` を -0.02 調整
3. **行動パラメータ調整**: GREEN/RED品質に基づき `risk_tolerance` を微調整
4. **適応度スコア計算**: `scripts/_fitness.py` の `update_fitness_score()` を呼び出し、`evolution.fitness_score` を更新。適応度 = w1*品質 + w2*完了率 + w3*効率 + w4*成長率（直近20タスクのスライディングウィンドウ）
5. **自動スナップショット**: `total_tasks` が5の倍数に達したら `personas/history/` にスナップショットを保存
6. **Few-Shot自動登録**: GREEN+success の結果を `knowledge/few_shot_bank/{domain}/` に登録（ドメインあたり最大20件）

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

### Persona自動選択（適応度ベース）

各サブタスクのドメインに対して、最も適応度の高いPersonaを自動選択する:

1. サブタスクのドメインを特定（例: backend, frontend, testing等）
2. `personas/active/` の全Personaを確認
3. 各Personaの `evolution.fitness_score` を読む
4. 同ドメイン対応のPersonaのうち、fitness_score が最高のものを選択
5. fitness_scoreが未設定（新規Persona）の場合は0.5として扱う
6. 適合するPersonaがない場合はgeneralist_v1をフォールバックとして使用

Decomposerが `personas/active/*.yaml` を読む際、`knowledge.domains` の照合に加えて
`evolution.fitness_score` を参照し、同ドメインで複数候補がある場合はスコア最高のPersonaを優先する。

## 進化フェーズ（Week 2以降）

| Week | テーマ | 状態 |
|------|--------|------|
| 1 | コア骨格: CLAUDE.md + Persona YAMLスキーマ + Seed 2-3種 | ✅ 完了 |
| 2 | 進化ループ基礎: Workerテンプレート + Few-Shot Bank + evolve.sh | ✅ 完了 |
| 3 | 進化エンジン本体: 適応度関数 + Persona自動更新 | ✅ 完了 |
| 4 | 統合・検証: E2Eテスト + Trust Module + 進化可視化 | 予定 |

Week 1-2完了。Step 5（EVOLVE）は `bash scripts/evolve.sh` として実装済み。
