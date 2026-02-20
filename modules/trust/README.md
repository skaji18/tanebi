# Trust Module

信頼スコア（trust_score）に基づく段階的権限委譲モジュール。

## 概要

各Personaの `performance.trust_score`（0〜100）を管理し、タスクのリスクレベルに応じてPersonaの割り当て可否を判定する。タスク完了時に結果に応じてスコアを自動更新する。

## フック一覧

### 1. `on_init` — 初期化

```bash
bash modules/trust/trust_module.sh on_init <persona_yaml_path>
```

- `performance.trust_score` が存在しなければ初期値 **50** を設定
- 既に存在する場合は何もしない

### 2. `on_task_assign` — タスク割り当て判定

```bash
bash modules/trust/trust_module.sh on_task_assign <persona_id> <task_risk_level>
# task_risk_level: low / medium / high
# 戻り値: 0=許可, 1=拒否
```

- `personas/active/{persona_id}.yaml` から trust_score を読み取る
- **high** リスク かつ trust_score < 30 → exit 1（拒否、stderr に理由出力）
- それ以外 → exit 0（許可）

### 3. `on_task_complete` — スコア更新

```bash
bash modules/trust/trust_module.sh on_task_complete <persona_id> <status> <quality>
# status: success / failure
# quality: GREEN / YELLOW / RED
```

#### スコア変動表

| status | quality | 変動 |
|--------|---------|------|
| success | GREEN | +5 |
| success | YELLOW | +2 |
| success | RED | +0 |
| failure | (any) | -10 |

- 上限: 100
- 下限: 0

## 使用例

```bash
# Persona初期化
bash modules/trust/trust_module.sh on_init personas/active/generalist_v1.yaml

# タスク割り当て判定
bash modules/trust/trust_module.sh on_task_assign generalist_v1 high
echo $?  # 0=許可, 1=拒否

# タスク完了後のスコア更新
bash modules/trust/trust_module.sh on_task_complete generalist_v1 success GREEN
```
