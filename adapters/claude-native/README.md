# claude-native Adapter

TANEBIのclaude-nativeアダプター。
Claude CodeのネイティブTASK機能（CLAUDE.md + Task tool）を使ってワーカーを起動する。

## 特徴
- 低レイテンシ（サブプロセス起動なし）
- コンテキスト共有が容易
- シングルプロセスで動作

## 有効化
tanebi_config.yaml:
```yaml
adapter_set: claude-native
```

## ファイル
- CLAUDE.md: このアダプターの参照実装仕様
