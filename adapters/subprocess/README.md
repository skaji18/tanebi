# subprocess Adapter

## ステータス: 未実装（cmd_020で実装予定）

TANEBIのsubprocessアダプター。
`claude -p` をサブプロセスとして起動してワーカーを実行する。

## 特徴（予定）
- プロセス分離による安全性
- 並列実行が可能
- コスト管理がしやすい

## 実装予定の機能
- orchestrator.sh: サブプロセス起動・管理
- worker_runner.sh: ワーカー実行ラッパー
- result_collector.sh: 結果収集
