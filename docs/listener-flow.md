# TANEBI Listener Flow（claude_native: false）

このドキュメントは config.yaml の `claude_native: false` 時に読む。
CLI コマンドを使ってタスクを投入し、Listener が全フローを自動処理する。

## 基本操作

### タスク投入
```bash
tanebi new "<request>"
```

### 状態確認
```bash
tanebi status [<task_id>]
```

### ペルソナ確認
```bash
tanebi persona list
```

### 進化実行
```bash
tanebi evolve <task_id> <persona_id>
```

## フロー
Listener が decompose → execute → aggregate を自動処理する。
Claude Code の介入は不要。タスク完了後に status で結果を確認せよ。
