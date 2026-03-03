# TANEBIアイデア集

外部分析から得られた知見を元に整理した将来アイデア集。
このドキュメントは生きたドキュメント。新しいアイデアが出たら追記する。

---

## 採用済み（実装中・実装予定）

### Learnerエージェント新設

**概要**: 知識抽出をフローの一等市民にする専用エージェントを新設。
**ステータス**: 実装中
**接続**: シグナル抽出品質問題（ギャップ2）の根本解決を担う。

---

## 検討中（次に手をつける候補）

### 1. エピソード記憶（episodes/）

**概要**: `knowledge/learned/`（Workerへの実行知恵）とは別に、`knowledge/episodes/` にタスク体験を蓄積。Decomposer起動時に類似事例として参照。
**使い分け**: learned = Worker向け暗黙知（何をどうやるか）、episodes = Decomposer向け計画参考事例（こういうタスクはこう分解した）
**優先度**: 中
**難易度**: 中

### 2. 役割別モデルルーティング

**課題**: ワーカーが一律で同じモデルを使用。コスト非効率。
**対策**: `config.yaml` に `model_routing` セクションを追加し、ドメイン/タスクタイプ別にモデルを切り替え。

```yaml
model_routing:
  default: claude-sonnet-4-6
  overrides:
    - domain: testing
      model: claude-haiku-4-5
    - domain: checkpoint
      model: claude-opus-4-6
```

**優先度**: 中（コスト効率改善）
**難易度**: 低〜中

### 3. tanebi status / 一覧コマンドの改善

**課題**: 現在の `tanebi status` は最後のイベント名を表示するだけ。`determine_state()` の判定結果（フロー上の論理状態）を使っていない。タスク一覧コマンドもない。
**検討ポイント**:
- status が表す意味: 完了状態？フロー全体での立ち位置？
- `determine_state()` の結果を表示に使うべきか
- タスク一覧コマンド（`tanebi list`）の新設
**優先度**: 中
**難易度**: 低

