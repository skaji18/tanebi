# TANEBI E2Eテスト計画書

> 作成日: 2026-02-20
> 対象: TANEBI MVP（claude-native アダプター）
> 前提: `~/projects/tanebi` にTANEBIがセットアップ済み、`personas/active/` にPersona YAML が存在すること

---

## 1. テスト手順（ステップバイステップ）

全5ステップ（Request → Decompose → Execute → Aggregate → Evolve）を順に実行する。

### 前提準備

```bash
cd ~/projects/tanebi

# 利用可能なPersona確認
ls personas/active/
# → backend_specialist_v1.yaml  generalist_v1.yaml  test_writer_v1.yaml

# 現在のPersona状態を記録（進化前スナップショット）
bash scripts/persona_ops.sh list
# → 各Personaのfitness_score, total_tasksを控えておく

# 既存のwork/cmd_* 数を確認
ls work/ | grep cmd_ | wc -l
```

### Step 1: REQUEST — new_cmd.sh でタスクディレクトリ生成

```bash
bash scripts/new_cmd.sh
# → 出力例: /Users/kajishinnosuke/projects/tanebi/work/cmd_006
```

**確認項目:**
- `work/cmd_006/` ディレクトリが作成されている
- `work/cmd_006/request.md` が存在し、テンプレート内容（`# Request: cmd_006`）を含む
- `work/cmd_006/plan.md` が存在する
- `work/cmd_006/report.md` が存在する
- `work/cmd_006/results/` ディレクトリが存在する

```bash
# 確認コマンド
ls -la work/cmd_006/
ls -la work/cmd_006/results/
head -1 work/cmd_006/request.md
# → "# Request: cmd_006" であること
```

**request.md にタスク内容を記入:**

```bash
cat > work/cmd_006/request.md <<'EOF'
# Request: cmd_006

## Task Description
バックエンドAPIの設計レビューを行い、改善提案をまとめる。
対象: RESTful API のエンドポイント設計。

## Context
新規プロジェクトの初期設計フェーズ。
エンドポイント数は5〜10程度を想定。

## Acceptance Criteria
- エンドポイント一覧表の作成
- 命名規則の統一性チェック
- 改善提案を3点以上
EOF
```

### Step 2: DECOMPOSE — Decomposerでサブタスク分解

オーケストレーター（親セッション）が以下を実行する:

1. `templates/decomposer.md` を読み込む
2. プレースホルダーを展開する:
   - `{REQUEST_PATH}` → `~/projects/tanebi/work/cmd_006/request.md`
   - `{PERSONA_LIST}` → `backend_specialist_v1, generalist_v1, test_writer_v1`
   - `{PLAN_PATH}` → `~/projects/tanebi/work/cmd_006/plan.md`
   - `{CMD_ID}` → `cmd_006`
   - `{TIMESTAMP}` → 現在時刻（ISO8601）
3. Task tool でDecomposerサブエージェントを起動

**確認項目:**
- `work/cmd_006/plan.md` が更新されている（テンプレートではなくYAML形式のplan）
- plan.md に `subtasks:` セクションが含まれる
- 各サブタスクに `persona:` が割り当てられている（`personas/active/` のファイル名と一致）
- `wave:` が設定されている
- API設計関連のタスクには `backend_specialist_v1` が割り当てられていること（fitness_score・domain照合）

```bash
# 確認コマンド
cat work/cmd_006/plan.md
# → subtasks: の下に各サブタスクが列挙されていること
# → persona: が personas/active/ のファイル名（拡張子なし）と一致すること
```

### Step 3: EXECUTE — Worker群を並列起動

オーケストレーターが plan.md を読み、各サブタスクに対して:

1. 割り当てPersona YAML（`personas/active/{persona_id}.yaml`）を読む
2. `templates/worker_base.md` のプレースホルダーを展開
3. Few-Shot Bank（`knowledge/few_shot_bank/{domain}/`）の関連ファイルパスを注入
4. Task tool でWorkerサブエージェントを起動（同一wave内は並列）

**確認項目:**
- `work/cmd_006/results/` に各サブタスクの結果ファイルが生成されている
- 各結果ファイルにYAML frontmatterが含まれている
- frontmatter に `subtask_id`, `persona`, `status`, `quality`, `domain` が含まれる
- Personaの口調・スタイルが結果に反映されている

```bash
# 確認コマンド
ls work/cmd_006/results/
# → subtask_001.md, subtask_002.md, ... が存在すること

# frontmatterの確認（各ファイル）
head -10 work/cmd_006/results/subtask_001.md
# → ---
# → subtask_id: subtask_001
# → persona: backend_specialist_v1
# → status: success
# → quality: GREEN
# → domain: api_design
# → ---
```

### Step 4: AGGREGATE — 結果統合レポート生成

オーケストレーターが以下を実行:

1. `templates/aggregator.md` のプレースホルダーを展開
2. Task tool でAggregatorサブエージェントを起動
3. Aggregator が `work/cmd_006/results/` 内の全 .md を読み、統合レポートを生成

**確認項目:**
- `work/cmd_006/report.md` が更新されている（テンプレートではなくYAML frontmatter付きレポート）
- frontmatter に `total_subtasks`, `succeeded`, `failed`, `quality_summary` が含まれる
- 本文にサブタスク結果の一覧表と統合サマリーが含まれる

```bash
# 確認コマンド
cat work/cmd_006/report.md
# → YAML frontmatter に succeeded/failed/quality_summary が含まれること
# → サブタスク結果の一覧テーブルが含まれること
```

### Step 5: EVOLVE — 進化エンジン実行

```bash
bash scripts/evolve.sh work/cmd_006
```

**確認項目:**
- 出力に `[evolve] Starting evolution for cmd_006` が表示される
- 各Personaについて `[evolve] Updated Persona:` が表示される
- `[fitness]` ログに各Personaのfitness_scoreが表示される
- GREEN+success の結果がある場合、`[evolve] Registered few-shot:` が表示される

```bash
# 確認コマンド: Persona YAMLの変化を確認
cat personas/active/backend_specialist_v1.yaml
# → performance.total_tasks が増加していること
# → performance.last_task_date が更新されていること
# → evolution.last_evolution_event に cmd_006 のエントリが追加されていること
# → evolution.fitness_score が再計算されていること

# Few-Shot Bank の確認
ls knowledge/few_shot_bank/
# → 該当ドメインのディレクトリにファイルが増えていること
```

---

## 2. 確認項目チェックリスト

全5ステップの正常動作確認:

- [ ] `new_cmd.sh` が `work/cmd_NNN/` を正しく生成する（request.md, plan.md, report.md, results/ を含む）
- [ ] `new_cmd.sh` がゼロパディング3桁の連番を正しくインクリメントする
- [ ] Decomposer が `plan.md` を生成する（YAML形式、subtasks配列を含む）
- [ ] Decomposer がPersona自動選択を行う（domain照合 + fitness_score優先）
- [ ] Decomposer がwave（実行順序）を正しく設定する
- [ ] Worker が `work/cmd_NNN/results/{subtask_id}.md` を生成する
- [ ] Worker の出力にYAML frontmatter（subtask_id, persona, status, quality, domain, duration_estimate）が含まれる
- [ ] Worker がPersonaの口調・行動特性を反映した出力を行う
- [ ] 同一wave内のWorkerが並列起動される（Task tool複数呼び出し）
- [ ] Aggregator が `report.md` を生成する（YAML frontmatter + 統合サマリー）
- [ ] Aggregator の `quality_summary` 集計が実際の結果と一致する
- [ ] `evolve.sh` がPersona YAMLの `performance.total_tasks` を正しく加算する
- [ ] `evolve.sh` が `performance.success_rate` を更新する
- [ ] `evolve.sh` が `performance.last_task_date` を今日の日付に更新する
- [ ] `evolve.sh` が `evolution.fitness_score` を再計算する（`_fitness.py` 経由）
- [ ] `evolve.sh` がGREEN+successの結果をFew-Shot Bankに自動登録する

---

## 3. 進化の確認方法（2タスク連続実行）

2つのタスクを連続実行し、Personaの進化を定量的に観測する。

### 準備: 実行前の状態記録

```bash
cd ~/projects/tanebi

# 進化前のPersona状態を記録
bash scripts/persona_ops.sh list
# 出力例:
# ID                              Fitness       Tasks
# backend_specialist_v1           0.857         1
# generalist_v1                   0.885         3
# test_writer_v1                  0.25          0

# 各Personaの詳細値を控える
grep -A2 'fitness_score' personas/active/generalist_v1.yaml
grep 'total_tasks' personas/active/generalist_v1.yaml
```

### 1タスク目: API設計レビュー

```bash
# Step 1
bash scripts/new_cmd.sh
# → work/cmd_NNN

# request.mdにタスク内容を記入（上記Step 1参照）
# Step 2-4: オーケストレーターが実行

# Step 5: 進化
bash scripts/evolve.sh work/cmd_NNN
```

**1タスク目完了後の確認:**

```bash
bash scripts/persona_ops.sh list
# → total_tasks が増加しているはず
# → fitness_score が変化しているはず（GREEN結果なら上昇方向）

# 具体的な変化を確認
grep 'total_tasks' personas/active/generalist_v1.yaml
grep 'fitness_score' personas/active/generalist_v1.yaml
# 期待: total_tasks 3→4, fitness_score 0.885→変化
```

### 2タスク目: テスト設計タスク

```bash
bash scripts/new_cmd.sh
# → work/cmd_NNN+1

cat > work/cmd_NNN+1/request.md <<'EOF'
# Request: cmd_NNN+1

## Task Description
ユーザー認証APIのユニットテスト設計書を作成する。

## Context
JWT認証を使用するREST API。ログイン・ログアウト・トークンリフレッシュの3エンドポイント。

## Acceptance Criteria
- テストケース一覧（正常系・異常系）
- 各テストの入力・期待出力
- モック/スタブの設計
EOF
```

**2タスク目完了後の確認:**

```bash
bash scripts/persona_ops.sh list
# → 2タスク分の累積変化を確認

# 差分の定量確認
grep 'total_tasks' personas/active/backend_specialist_v1.yaml
# 期待: 1 → 2〜3（担当サブタスク数に依存）

grep 'fitness_score' personas/active/backend_specialist_v1.yaml
# 期待: 0.857 → 変化（タスク履歴が増えることで再計算される）

grep 'total_tasks' personas/active/test_writer_v1.yaml
# 期待: 0 → 1〜2（テスト設計タスクで初めて使われるはず）

grep 'fitness_score' personas/active/test_writer_v1.yaml
# 期待: 0.25 → 上昇（タスク履歴が追加されることで再計算）
```

### show_evolution.sh での差分確認

> 注: `show_evolution.sh` はTask 18で作成予定。存在しない場合は手動で以下を実行。

```bash
# show_evolution.sh が存在する場合
bash scripts/show_evolution.sh

# 存在しない場合の手動確認
echo "=== 進化サマリー ==="
for p in personas/active/*.yaml; do
    name=$(basename "$p" .yaml)
    fitness=$(grep 'fitness_score' "$p" | head -1 | awk '{print $2}')
    tasks=$(grep 'total_tasks' "$p" | head -1 | awk '{print $2}')
    echo "$name: fitness=$fitness, total_tasks=$tasks"
done
```

**期待される進化パターン:**

| Persona | 実行前 fitness | 1タスク後 | 2タスク後 | 理由 |
|---------|--------------|----------|----------|------|
| generalist_v1 | 0.885 | 変化あり | 変化あり | 汎用タスクで使用される可能性大 |
| backend_specialist_v1 | 0.857 | 上昇方向 | 上昇方向 | API設計タスクで高品質成果が期待 |
| test_writer_v1 | 0.25 | 0.25（未使用なら） | 上昇 | テスト設計タスクで初起用 |

---

## 4. Few-Shot注入の確認方法

### 4.1 Few-Shot Bank への登録確認

1タスク目がGREEN+successの場合:

```bash
# Few-Shot Bankの確認
ls knowledge/few_shot_bank/
# → 該当ドメインのディレクトリ（例: api_design/, backend/）が存在

# 新規登録ファイルの確認
ls -lt knowledge/few_shot_bank/api_design/
# → cmd_006_subtask_001.md のようなファイルが追加されているはず

# 登録内容の確認
head -15 knowledge/few_shot_bank/api_design/cmd_006_subtask_001.md
# → YAML frontmatterに domain, quality: GREEN, persona, source_cmd が含まれる
```

### 4.2 2タスク目へのFew-Shot注入確認

2タスク目のDecomposer/Worker起動時に、1タスク目のFew-Shotが注入されていることを確認する方法:

**方法1: Worker テンプレートのプレースホルダー確認**

オーケストレーターがWorkerを起動する際、`templates/worker_base.md` の `{FEW_SHOT_PATHS}` に
該当ドメインのFew-Shotファイルパスが設定される。

```bash
# 該当ドメインのFew-Shotファイル一覧を確認
ls knowledge/few_shot_bank/api_design/
# → cmd_006_subtask_001.md が存在していれば、
#    2タスク目のWorkerプロンプトに注入される

# 注入されるパスの確認
echo "Worker起動時に {FEW_SHOT_PATHS} に設定されるパス:"
for f in knowledge/few_shot_bank/api_design/*.md; do
    [ "$(basename "$f")" = "_format.md" ] && continue
    echo "  - $f"
done
```

**方法2: Worker出力での確認**

Worker出力の「実行ノート」セクションにFew-Shot参照に言及があるか確認:

```bash
grep -i "few.shot\|参考事例\|past.*example" work/cmd_*/results/*.md
```

**方法3: 直接的な注入確認（デバッグ用）**

Worker起動時のプロンプト内容を一時的にファイルに保存するには、
CLAUDE.md のStep 3で Worker 起動前に展開済みプロンプトをログ出力する手順を追加する:

```bash
# デバッグ: 展開済みプロンプトを保存（オーケストレーター内で実行）
# work/cmd_NNN/debug/worker_{subtask_id}_prompt.md に保存
mkdir -p work/cmd_NNN/debug
# → プロンプト展開後にWriteで保存
```

---

## 5. 異常系テスト

### 5.1 存在しないPersona IDを指定した場合

**手順:**

```bash
# plan.mdを手動で編集し、存在しないPersonaを指定
cd ~/projects/tanebi
bash scripts/new_cmd.sh
# → work/cmd_NNN

cat > work/cmd_NNN/request.md <<'EOF'
# Request: cmd_NNN

## Task Description
テスト用のダミータスク。

## Acceptance Criteria
- 何かが出力される
EOF
```

plan.md を手動で作成し、存在しないPersonaを指定:

```bash
cat > work/cmd_NNN/plan.md <<'EOF'
plan:
  cmd: cmd_NNN
  created_at: "2026-02-20T12:00:00"
  total_subtasks: 1
  waves: 1

  subtasks:
    - id: subtask_001
      description: "テスト用ダミータスク"
      persona: nonexistent_persona_v99
      output_path: "work/cmd_NNN/results/subtask_001.md"
      depends_on: []
      wave: 1
EOF
```

**期待される動作:**
- オーケストレーターが `personas/active/nonexistent_persona_v99.yaml` を読もうとして失敗
- フォールバック: `generalist_v1` が使用される、またはエラーが報告される
- Worker起動自体は行われる（Persona YAMLが読めない場合もデフォルト行動で実行可能）

**evolve.sh の動作確認:**

```bash
# 結果ファイルに存在しないPersona名が含まれる場合
bash scripts/evolve.sh work/cmd_NNN
# → "[evolve] WARNING: Persona not found: .../nonexistent_persona_v99.yaml" が表示されること
# → 他のPersonaへの影響がないこと
```

### 5.2 空のリクエスト（空ファイル）での動作

```bash
bash scripts/new_cmd.sh
# → work/cmd_NNN

# request.md を空にする
> work/cmd_NNN/request.md

# Decomposerを起動（オーケストレーター経由）
# 期待: Decomposerがリクエスト内容が空であることを検知し、
#        エラーメッセージを含むplan.mdを出力する、
#        または「タスク内容が不明」として最小限のサブタスクを生成する
```

**確認項目:**
- [ ] Decomposerがクラッシュせずにplan.mdを出力する
- [ ] plan.md にエラー内容または最小限のサブタスク定義が含まれる
- [ ] システム全体がハングしない

### 5.3 evolve.sh に結果が存在しない場合

```bash
bash scripts/new_cmd.sh
# → work/cmd_NNN

# results/ ディレクトリは空のまま evolve.sh を実行
bash scripts/evolve.sh work/cmd_NNN
# → "[evolve] No results found to process." が表示されること
# → 終了コード0で正常終了すること
echo $?
# → 0
```

### 5.4 不正なfrontmatterを持つ結果ファイル

```bash
bash scripts/new_cmd.sh
# → work/cmd_NNN

# 不正なfrontmatterを持つ結果ファイルを配置
cat > work/cmd_NNN/results/subtask_001.md <<'EOF'
これはfrontmatterのないファイルです。
テスト用の不正データ。
EOF

bash scripts/evolve.sh work/cmd_NNN
# → frontmatterがパースできないため、スキップされるはず
# → "[evolve] No results found to process." が表示されること
# → クラッシュしないこと
```

---

## 6. Trust Module連携テスト

> 注: Trust Module は config.yaml で `modules.trust.enabled: false` の状態。
> テスト実行前に有効化するか、有効化せずに「無効時の動作確認」のみ行うかを決定する。

### 6.1 on_init: Persona YAMLにtrust_scoreが設定される

**前提:** Trust Moduleが有効化されていること（`config.yaml` の `modules.trust.enabled: true`）

```bash
# Trust Module 有効化
# config.yaml を編集: modules.trust.enabled: true

# 新規Personaを作成（trust_scoreの初期設定を確認）
bash scripts/persona_ops.sh copy generalist_v1 trust_test_v1

# trust_test_v1 に trust_score が設定されているか確認
grep -i 'trust' personas/active/trust_test_v1.yaml
# 期待: trust_score フィールドが存在する（初期値: 設計書に準拠）
```

**Trust Moduleが無効の場合の確認:**

```bash
grep -i 'trust' personas/active/generalist_v1.yaml
# → trust_score フィールドが存在しないことを確認
# → Trust Module無効時は trust_score の管理が行われないことが正常
```

### 6.2 on_task_assign: trust_score < 30 のPersonaへのhigh-riskタスク割り当て拒否

**手順:**

```bash
# テスト用Personaを作成し、trust_scoreを低く設定
bash scripts/persona_ops.sh copy generalist_v1 low_trust_v1

# low_trust_v1.yaml を手動編集: trust_score を 25 に設定
# （performance セクションに trust_score: 25 を追加）
```

```bash
# high-riskタスクのリクエストを作成
bash scripts/new_cmd.sh
cat > work/cmd_NNN/request.md <<'EOF'
# Request: cmd_NNN

## Task Description
本番データベースのマイグレーション設計（high-risk）

## Context
本番環境に影響するため、high-riskタスク。

## Acceptance Criteria
- マイグレーション計画書
- ロールバック手順
EOF
```

**期待される動作（Trust Module有効時）:**
- Decomposerが `low_trust_v1`（trust_score=25 < 30）にhigh-riskタスクを割り当てようとした場合、拒否される
- より高いtrust_scoreを持つPersonaに再割り当て、またはエラーが報告される

**確認項目:**
- [ ] trust_score < 30 のPersonaがhigh-riskタスクに割り当てられない
- [ ] 代替Personaが選択される、またはエラーが明示的に報告される

### 6.3 on_task_complete: GREEN+successでtrust_score +5

```bash
# タスク完了後のtrust_score変化を確認

# 実行前のtrust_scoreを記録
grep 'trust_score' personas/active/backend_specialist_v1.yaml
# → 例: trust_score: 72

# タスク実行（上記Step 1-5の通常フロー）
# → GREEN+success の結果が出た場合

# 実行後のtrust_scoreを確認
grep 'trust_score' personas/active/backend_specialist_v1.yaml
# 期待: trust_score: 77 (+5)
```

**注意:** Trust Moduleの `on_task_complete` フックが `evolve.sh` / `_evolve_helper.py` に
統合されている必要がある。現在のMVPでは未実装の可能性があるため、
テスト前に `_evolve_helper.py` にtrust_score更新ロジックが含まれているか確認すること。

```bash
grep -i 'trust' scripts/_evolve_helper.py
# → 該当行がなければ、Trust Module連携は未実装
# → 未実装の場合: このセクションのテストはTrust Module実装後に再実行
```

### Trust Module テストの前提条件まとめ

| テスト | 前提条件 | 現在の状態 |
|--------|---------|-----------|
| on_init | Trust Module有効、on_initフック実装済み | 未実装（config: false） |
| on_task_assign | Trust Module有効、Decomposerにtrust_scoreチェック実装済み | 未実装 |
| on_task_complete | evolve.shにtrust_score更新ロジック実装済み | 要確認 |

**Trust Module未実装の場合:**
- 6.1〜6.3のテストは「Trust Module実装完了後に実施」とマークする
- 代わりに「Trust Module無効時にシステムが正常動作すること」を確認する

```bash
# Trust Module無効時の正常動作確認
grep 'trust:' config.yaml
# → enabled: false

# 通常のタスク実行フロー（Step 1-5）が問題なく完了すること
# → Trust Moduleのフックが呼ばれない＝影響なしであること
```

---

## 補足: テスト実行時の注意事項

1. **テスト順序**: セクション1（正常系フロー）→ セクション3（2タスク連続）→ セクション4（Few-Shot注入）→ セクション5（異常系）→ セクション6（Trust Module）の順に実行を推奨
2. **状態リセット**: 異常系テスト後は、テスト用に作成したPersona（`trust_test_v1`, `low_trust_v1` 等）を削除すること
3. **テスト用cmdディレクトリ**: テスト用に作成した `work/cmd_*` は `cmd_test_*` の命名規則を使うと、本番データと区別しやすい（ただし `new_cmd.sh` は連番のため、手動リネームが必要）
4. **並列テスト**: Step 3のWorker並列起動テストは、`config.yaml` の `max_parallel_workers: 5` の範囲内で実行すること
