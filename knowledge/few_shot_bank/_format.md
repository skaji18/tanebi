# Few-Shot Bank フォーマット定義

## 概要

Few-Shot Bankは、Workerエージェントへ注入する成功事例ライブラリです。
各事例は以下のYAML frontmatter + Markdown形式で記述します。

## ファイル配置ルール

- ドメイン別ディレクトリに配置: `{domain}/{task_type_description}.md`
- ドメイン名は config/persona_schema.yaml の domains.name に合わせる
- ファイル名はスネークケース: `sample_api_design.md`

## フォーマット

```yaml
---
domain: backend          # ドメイン分類（config/persona_schema.yaml の domains.name）
task_type: api_design    # タスク種別（スネークケース）
quality: GREEN           # 品質評価: GREEN / YELLOW
persona: backend_specialist_v1  # 作成したPersona（personas/active/ のID）
created_at: "YYYY-MM-DD"
source_cmd: "cmd_001"    # 元のコマンドID（手動登録の場合は "manual"）
tags: [rest, design]     # 検索用タグ（オプション）
---

## タスク
[元のタスク内容を簡潔に記載]

## 成果物
[成功した出力の要約または主要部分]

## 学び
[この事例から得られた教訓・ポイント（1-3行）]
```

## 自動登録について

scripts/evolve.sh が quality: GREEN の結果を自動登録候補として提案します（Week 3で有効化）。
現在は手動で事例を追加してください。
