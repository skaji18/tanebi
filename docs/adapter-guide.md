# TANEBI アダプター抽象ポリシー v2 — コマンド設定モデル

> 日付: 2026-02-20

---

## 1. ポリシー概要（Executive Summary）

### 設計原則（最高優先）

> 「config.yamlに `worker.start: docker run ...` のように具体的な起動コマンドを書く。tanebiコアはそのコマンドをただ呼ぶだけ。if分岐もアダプター名も不要。**設定ファイル自体がアダプターである。**」

### 設計原則（5箇条）

| # | 原則 | 説明 |
|---|------|------|
| **AP-1** | **コアはフロー制御のみ** | TANEBIコアの責務はDECOMPOSE→EXECUTE→AGGREGATE→EVOLVEのフロー制御に限定する。実行方式・通信手段・ストレージ実装を一切知らない |
| **AP-2** | **設定ファイルがアダプターである** | config.yamlの各Portに具体的なコマンドを記述する。TANEBIコアはそのコマンドをプレースホルダー置換してshell execするだけ。アダプター名・if分岐・ポート選択コードは**一切存在しない** |
| **AP-3** | **Portが契約、コマンドが実装** | TANEBIは「Portの入出力スキーマ」のみを定義する。どう実現するか（シェル・Docker・Lambda・API等）はconfig.yamlのコマンドに委ねる |
| **AP-4** | **Port単位でコマンドを混合可能** | Worker起動はDocker、State保存はS3、Event発火はRedis — 旧設計の「1 adapter = 全Port実装」と異なり、Port単位で自由に構成できる |
| **AP-5** | **データ交換はYAML契約** | Port間のデータ交換は全てYAMLスキーマで定義される。transport層（ファイル/Redis/S3等）はPortの外側 |

### 旧設計との根本的な違い

| 観点 | 旧設計（名前選択式） | 新設計（コマンド設定モデル） |
|------|---------------------|---------------------------|
| **Adapter表現** | `adapter_set: docker` → case文分岐 | `ports.worker_launch.command: "docker run ..."` |
| **TANEBIのAdapter知識** | 「docker」「lambda」「subprocess」を知っている | **何も知らない。** コマンド文字列を実行するだけ |
| **構成単位** | adapter単位（1 adapter = 全Port） | **Port単位**（Port毎にコマンドを自由に混合） |
| **新Adapter追加** | TANEBIコアにcase分岐追加 | config.yamlにコマンド記述のみ。**コア変更ゼロ** |
| **コア内部のif文** | `case "$adapter_set" in docker) ... subprocess) ... esac` | **なし** |
| **ディレクトリ構成** | `adapters/{adapter_name}/orchestrator.sh` + `port_mapping.yaml` | config.yamlのみ。adapter専用ディレクトリは任意（外部スクリプト置き場として） |

### 適用範囲

本ポリシーは以下に適用される:

- TANEBIコア（DECOMPOSE→EXECUTE→AGGREGATE→EVOLVEフロー制御）
- config.yamlのPort command定義
- 統一プラグインシステム（Plugin APIを介したPort利用に限定）
- CLAUDE.md / オーケストレーター定義

本ポリシーは以下には適用されない:

- Persona YAMLスキーマ（環境非依存のデータ定義。変更不要）
- 進化エンジン内部ロジック（evolve.shの進化ステップ。Portを通じてのみ外界と接触）

---

## 2. TANEBIコアの責務定義

### 責務とする（Core Responsibilities）

| 責務 | 説明 | 該当コンポーネント |
|------|------|------------------|
| フロー制御 | DECOMPOSE→EXECUTE→AGGREGATE→EVOLVEの順序制御 | オーケストレーター |
| Wave管理 | 依存関係に基づくWave順序決定と同期ポイント | オーケストレーター |
| Persona選択 | fitness_scoreに基づくPersona-サブタスク最適割当 | Decomposer（テンプレート） |
| 進化制御 | タスク完了後の進化ステップ発動 | evolve.sh（コア呼び出し） |
| **コマンド実行エンジン** | config.yamlからPortコマンドを読み取り、プレースホルダーを置換し、shell execする | **command_executor（新規）** |
| イベントスキーマ定義 | イベント名・ペイロード構造の定義 | events/schema.yaml |
| プラグインライフサイクル管理 | init/event/destroyの呼び出し順序 | component_loader.sh |

### 責務としない（config.yamlに移動 = 利用者の責務）

| 責務 | 説明 | 判断根拠 |
|------|------|---------|
| Worker起動方式 | Task tool / bash / docker run / API call | **config.yamlのcommandで決定** |
| 並列実行方式 | 複数Task tool / xargs -P / docker-compose / 並列invoke | **config.yamlのcommandで決定** |
| 通信transport | ファイル書き出し / Redis PUBLISH / SQS / WebSocket | **config.yamlのcommandで決定** |
| 状態永続化方式 | ローカルYAML / S3 / DynamoDB / PostgreSQL | **config.yamlのcommandで決定** |
| 知識アクセス方式 | ローカルファイル / S3 pre-signed URL / Lambda Layer内蔵 | **config.yamlのcommandで決定** |
| セキュリティ実装 | Claude Code permissions / IAM / カスタム認証 | **config.yamlのcommandで決定** |

### 境界判断基準

```
Q1: この機能は「フローのどのステップで何を呼ぶか」を決めるか、「そのステップの中身」を実装するか？
    → 「どのステップで」 = コア、「中身」 = config.yamlのコマンド

Q2: この機能を変更した時、config.yamlの書き換えだけで済むか？
    → 済む = 正しい設計、コア変更が必要 = 設計違反

Q3: 新しい実行環境（例: Kubernetes）を追加する時、TANEBIのコードに触れるか？
    → 触れる = 設計違反。config.yamlにコマンドを書くだけで済むべき
```

---

## 3. コマンド設定モデル — 詳細設計

### 3.1 config.yaml Port構造

```yaml
tanebi:
  ports:
    # === Worker起動 ===
    worker_launch:
      decompose:
        command: "<コマンド文字列>"     # プレースホルダー付き
        timeout: 120                    # 秒（省略時デフォルト）
      execute:
        command: "<コマンド文字列>"
        timeout: 600
      execute_wave:
        command: "<コマンド文字列>"     # 省略時: execute.commandをN回呼ぶ
        timeout: 900

    # === イベント発火 ===
    event_emit:
      command: "<コマンド文字列>"

    # === 状態読み書き ===
    state_read:
      command: "<コマンド文字列>"       # stdout に YAML/内容を出力
    state_write:
      command: "<コマンド文字列>"       # stdin から YAML/内容を受け取り

    # === 知識アクセス ===
    knowledge_read:
      command: "<コマンド文字列>"       # stdout にパス一覧 or 内容

    # === セキュリティ ===
    security_check:
      command: "<コマンド文字列>"       # exit 0 = allow, exit 1 = deny
    security_update:
      command: "<コマンド文字列>"
```

### 3.2 プレースホルダー規約

TANEBIコアはコマンド文字列中のプレースホルダーを実引数で置換する。

#### 共通プレースホルダー

| プレースホルダー | 型 | 説明 |
|----------------|-----|------|
| `{cmd_id}` | string | コマンドID（例: cmd_001） |
| `{work_dir}` | path | コマンド作業ディレクトリ |

#### worker_launch.decompose

| プレースホルダー | 型 | 説明 |
|----------------|-----|------|
| `{request_file}` | path | ユーザー依頼ファイルパス |
| `{persona_list}` | string | カンマ区切りPersona ID一覧 |
| `{plan_output}` | path | 分解計画の出力先パス |

#### worker_launch.execute

| プレースホルダー | 型 | 説明 |
|----------------|-----|------|
| `{subtask_id}` | string | サブタスクID |
| `{subtask_file}` | path | サブタスク定義YAMLパス |
| `{persona_file}` | path | Persona YAMLパス |
| `{few_shot_files}` | string | カンマ区切りFew-Shotファイルパス |
| `{output_path}` | path | 結果の出力先パス |

#### event_emit

| プレースホルダー | 型 | 説明 |
|----------------|-----|------|
| `{event_type}` | string | イベント種別（events/schema.yaml準拠） |
| `{payload}` | json | イベントペイロード（JSONエスケープ済） |
| `{idempotency_key}` | string | 冪等性キー |

#### state_read / state_write

| プレースホルダー | 型 | 説明 |
|----------------|-----|------|
| `{resource_type}` | string | `persona` / `result` / `plan` / `cost` / `history` / `event` |
| `{resource_id}` | string | リソース識別子（persona_id, cmd_id, subtask_id等） |
| `{resource_path}` | path | リソースのローカルパス（fileベース時） |

#### knowledge_read

| プレースホルダー | 型 | 説明 |
|----------------|-----|------|
| `{domain}` | string | ドメイン名 |
| `{limit}` | integer | 取得上限数 |
| `{query}` | string | 検索クエリ（search時） |

#### security_check

| プレースホルダー | 型 | 説明 |
|----------------|-----|------|
| `{persona_id}` | string | チェック対象Persona |
| `{risk_level}` | string | `low` / `medium` / `high` |

### 3.3 コマンド実行フロー

TANEBIコアのコマンド実行エンジン（`command_executor`）の処理フロー:

```
1. config.yaml から該当Port のコマンド文字列を読み取る
2. プレースホルダーを実引数で置換
   - 全プレースホルダーが解決されたことを検証（未解決 → エラー）
   - シェルインジェクション対策: 引数値をシングルクォートでエスケープ
3. コマンドを shell exec する
   - timeout コマンドでラップ（config.yaml の timeout 値）
   - exit code を確認（0 = 成功, 非0 = 失敗）
4. stdout / stderr をキャプチャし、Port の出力スキーマに従いパース
```

**疑似コード:**

```bash
# scripts/command_executor.sh — TANEBIコアの心臓部
execute_port() {
  local port_name="$1"  # 例: "worker_launch.execute"
  shift
  # 残りの引数はkey=value形式のプレースホルダー

  # 1. コマンド読み取り
  local cmd_template
  cmd_template=$(read_config "tanebi.ports.${port_name}.command")

  if [ -z "$cmd_template" ]; then
    echo "[TANEBI] ERROR: No command configured for port ${port_name}" >&2
    return 1
  fi

  # 2. プレースホルダー置換
  local cmd="$cmd_template"
  for arg in "$@"; do
    local key="${arg%%=*}"
    local value="${arg#*=}"
    local escaped_value
    escaped_value=$(printf '%s' "$value" | sed "s/'/'\\\\''/g")
    cmd="${cmd//\{${key}\}/'${escaped_value}'}"
  done

  # 未解決プレースホルダー検出
  if echo "$cmd" | grep -qE '\{[a-z_]+\}'; then
    echo "[TANEBI] ERROR: Unresolved placeholders in command: $cmd" >&2
    return 1
  fi

  # 3. タイムアウト付きで実行
  local timeout_sec
  timeout_sec=$(read_config "tanebi.ports.${port_name}.timeout" "120")
  timeout "$timeout_sec" bash -c "$cmd"
}
```

### 3.4 Port契約定義（入出力スキーマ）

Port契約はYAMLスキーマベースの言語非依存形式で記述する。**コマンド文字列は契約に含まれない** — 契約は「何を入力し、何を出力するか」のみ。

#### PORT: worker_launch.decompose

```yaml
contract:
  input:
    request: FilePath          # ユーザー依頼
    personas: string[]         # 利用可能Persona ID一覧
    plan_path: FilePath        # 分解計画の出力先
    cmd_id: string             # コマンドID
  output:
    plan: PlanYAML             # 分解計画（plan_pathに書き出し）
  precondition:
    - request ファイルが存在し読み取り可能
    - personas リストが1つ以上のIDを含む
    - plan_path の親ディレクトリが書き込み可能
  postcondition:
    - plan_path にYAML構造の計画ファイルが生成される
```

#### PORT: worker_launch.execute

```yaml
contract:
  input:
    subtask: SubtaskYAML       # サブタスク定義
    persona: FilePath          # Persona YAMLパス
    few_shots: FilePath[]      # Few-Shot事例パス一覧
    output_path: FilePath      # 結果の出力先
  output:
    result: ResultYAML         # YAML frontmatter付きMarkdown
  precondition:
    - subtask がSubtaskスキーマに適合
    - persona ファイルが存在
  postcondition:
    - output_path にYAML frontmatter付きMarkdownが生成
    - frontmatter に status, quality, domain が含まれる
```

#### PORT: worker_launch.execute_wave

```yaml
contract:
  input:
    subtasks: SubtaskYAML[]
    personas: FilePath[]
    few_shots: FilePath[][]
    output_paths: FilePath[]
  output:
    results: ResultYAML[]
  postcondition:
    - 全subtaskのoutput_pathにResultが生成
  note: |
    execute_wave.commandが設定されていない場合、
    TANEBIコアはexecute.commandを並列呼び出し（xargs -P相当）で代替する。
    execute_wave.commandが設定されている場合はそのコマンドに一括委任する。
```

#### PORT: event_emit

```yaml
contract:
  input:
    event_type: string         # events/schema.yaml準拠
    payload: YAML              # イベントペイロード
    idempotency_key: string    # 冪等性キー
  output:
    event_id: string           # 発行されたイベントID（stdout出力）
  postcondition:
    - イベントが永続化されること
    - 同一idempotency_keyのイベントは重複処理されないこと
```

> **注記**: event_emit Portの責務は「イベントを外部システムへ転送・永続化すること」に限定される。
> プラグインへの内部配信は component_loader の責務であり、Port外の内部機構である。
> event_emit 完了後、component_loader が購読プラグインにイベントを dispatch する。

#### PORT: state_read / state_write

```yaml
contract:
  state_read:
    input:
      resource_type: enum[persona, result, plan, cost, history, event]
      resource_id: string
    output:
      content: YAML | Markdown  # stdoutに出力
    postcondition:
      - 対象データが存在しない場合は空出力 + exit 0

  state_write:
    input:
      resource_type: enum[persona, result, plan, cost, history, event]
      resource_id: string
      content: YAML | Markdown  # stdinから入力
    postcondition:
      - データが永続化されること
```

#### PORT: knowledge_read

```yaml
contract:
  input:
    domain: string
    limit: integer?
  output:
    paths: string[]            # stdout に1行1パスで出力
```

#### PORT: security_check / security_update

```yaml
contract:
  security_check:
    input:
      persona_id: string
      risk_level: enum[low, medium, high]
    output:
      decision: exit_code      # 0 = allow, 1 = deny
      detail: string           # stdoutにJSON（trust_score, reason等）
  security_update:
    input:
      persona_id: string
      task_result: ResultYAML  # stdinから入力
    postcondition:
      - trust_scoreが更新規則に従い更新
```

### 3.5 戻り値スキーマ

```yaml
# Plan（decompose戻り値）
plan:
  cmd: string
  total_subtasks: integer
  waves: integer
  subtasks:
    - id: string
      description: string
      persona: string
      output_path: string
      depends_on: string[]
      wave: integer

# Result（execute戻り値）— YAML frontmatter
subtask_id: string
persona: string
status: enum[success, failure]
quality: enum[GREEN, YELLOW, RED]
domain: string
duration_estimate: enum[short, medium, long]
```

### 3.6 イベント冪等性・順序保証ポリシー

**方針: 冪等設計を基本とし、順序保証は利用者のコマンド選択に委ねる**

1. **全イベントにidempotency_keyをプレースホルダーとして渡す**: `{cmd_id}_{subtask_id}_{event_type}_{timestamp}`
2. **冪等性の実装責務はコマンド側にある**: TANEBIコアはidempotency_keyを渡すだけ
3. **順序保証**: コマンド側の選択
   - ファイルベース: ファイル名タイムスタンプ順（自然順序）
   - SQS FIFO: MessageGroupId = `cmd_id`
   - Redis: XADD で自然順序

### 3.7 全Port共通: タイムアウト仕様

各Portに `timeout` フィールドを設定可能。

| Port | デフォルト | 超過時の挙動 |
|------|----------|------------|
| worker_launch.decompose | 120秒 | プロセス強制終了。エラー報告 |
| worker_launch.execute | 600秒 | プロセス強制終了。`status: failure` |
| worker_launch.execute_wave | 900秒 | 全プロセス強制終了 |
| event_emit | 30秒 | タイムアウト。非致命的（ログ記録） |
| state_read / state_write | 60秒 | エラー終了 |
| security_check | 30秒 | デフォルトdeny（安全側） |

---

## 4. claude-nativeの扱い — The Builtin Exception

### 4.1 問題の本質

Task toolはClaude Codeセッション内部のプログラマティックAPI。外部シェルコマンドではない。

```
subprocess:   command: "bash run_worker.sh {subtask_file}"     ← shell execできる
Docker:       command: "docker run --rm tanebi-worker ..."      ← shell execできる
Lambda:       command: "aws lambda invoke --payload '...' ..."  ← shell execできる
claude-native: ???  Task tool呼び出し                            ← shell execできない
```

claude-nativeはTANEBIの**現在のデフォルト動作環境**であり、最も使われる構成である。これを「特殊ケース」として扱うのか、コマンドモデルに統合するのかが設計上の最大の難題。

### 4.2 4案の比較分析

#### 案1: ブリッジスクリプト方式

```yaml
worker_launch:
  execute:
    command: "bash tanebi-claude-bridge.sh {subtask_file} {persona_file}"
```

- ブリッジスクリプトがCLAUDE.md内で動作し、Task tool呼び出しロジックを含む
- TANEBIコアからは通常のコマンド実行に見える

**利点**: コマンドモデルに完全統合。TANEBIコアに特殊コードなし。
**欠点**: ブリッジスクリプトは実際にはシェルから実行できない（Task toolはClaude Code内部API）。「コマンドとして書かれているが、実際にはshell execされない」という欺瞞が生まれる。コマンドモデルの「コマンドをshell execする」という前提を破壊する。
**判定**: **却下** — 形式的にはコマンドだが実質は嘘。設計の誠実さを損なう。

#### 案2: レガシーfallback方式

```yaml
# config.yaml にworker_launch.execute.commandが未設定
# → TANEBIコアがTask tool（claude-native）にfallback
```

- コマンドが設定されていないPortはclaude-native動作
- TANEBIコア内に「commandが空ならTask toolを使う」ロジック

**利点**: 既存動作を維持。新規アダプターはコマンドモデルの恩恵を受ける。
**欠点**: TANEBIコアにclaude-native固有の知識（「Task toolを使う」）が残る。AP-2違反。「設定がない = デフォルト動作」は暗黙知であり、config.yamlを読んだだけでは何が起きるかわからない。
**判定**: **却下** — 暗黙のfallbackは設計原則「設定ファイルで全て決まる」に反する。

#### 案3: Builtin Command方式（推奨）

```yaml
worker_launch:
  execute:
    command: "builtin:task_tool"
    args:
      instructions: |
        Read {persona_file}. Complete the subtask defined in {subtask_file}.
        Write result to {output_path}.
```

- `builtin:` プレフィックス付きコマンドは、shell execではなくTANEBI内蔵の呼び出しメカニズムを使う
- 現在の唯一のbuiltin: `task_tool`（Claude Code内部API呼び出し）
- TANEBIコアの分岐は**1つだけ**: `builtin:` で始まるか否か

**利点**:
1. **config.yamlに明示的に記述される** — 何が起きるか一目瞭然
2. **TANEBIコアの分岐は最小限** — `builtin:` プレフィックス検出の1行のみ
3. **アダプター名が存在しない** — `builtin:task_tool` はアダプター名ではなく「呼び出し方式」の指定
4. **Shell builtinの類推**: bashにも `cd`, `echo` 等のbuiltinがある。外部コマンドとbuiltinの共存はUNIXの伝統
5. **将来消滅可能** — Claude Code CLIが`claude --invoke-task`等のシェル呼び出し可能なAPIを提供した時点で、`builtin:task_tool` → `claude --invoke-task '...'` に書き換えるだけでbuiltinが消える

**欠点**:
1. `builtin:` プレフィックスの特殊処理がTANEBIコアに存在する（AP-2の微小な違反）
2. 現時点で `builtin:task_tool` が唯一のbuiltinであり、「将来追加されるかもしれない」builtinのために抽象化している感がある

**判定**: **推奨** — 設計原則の精神（設定ファイルで全て決まる・TANEBIコアに環境固有知識を入れない）を最大限尊重しつつ、Task toolの技術的制約に対する誠実な解決策。

#### 案4: ネイティブモード/コマンドモード二重構造

```yaml
tanebi:
  mode: native    # or "command"
```

- `native`: CLAUDE.mdベースの現行動作
- `command`: config.yamlのコマンドベース

**利点**: 既存動作を完全に保持。
**欠点**: TANEBIに**2つの動作モード**が生まれる。全てのフロー制御コードに `if mode == native` 分岐が入る。これは旧設計の`case "$adapter_set"`よりさらに悪い — コアの全ステップに分岐が入るため。
**判定**: **却下** — 設計原則に最も反する。コアに二重構造を持ち込む最悪の選択。

### 4.3 推奨案の詳細設計: Builtin Command方式

#### TANEBIコアの実装

```bash
# scripts/command_executor.sh — 変更箇所

execute_port() {
  local port_name="$1"
  shift

  local cmd_template
  cmd_template=$(read_config "tanebi.ports.${port_name}.command")

  # プレースホルダー置換（前述の通り）
  local cmd
  cmd=$(resolve_placeholders "$cmd_template" "$@")

  # === ここが唯一の分岐 ===
  if [[ "$cmd" == builtin:* ]]; then
    local builtin_name="${cmd#builtin:}"
    execute_builtin "$builtin_name" "$port_name" "$@"
  else
    # 通常のshell exec
    local timeout_sec
    timeout_sec=$(read_config "tanebi.ports.${port_name}.timeout" "120")
    timeout "$timeout_sec" bash -c "$cmd"
  fi
}

execute_builtin() {
  local builtin_name="$1"
  local port_name="$2"
  shift 2

  case "$builtin_name" in
    task_tool)
      # Task tool呼び出し（CLAUDE.mdから使用時のみ動作）
      local args_yaml
      args_yaml=$(read_config "tanebi.ports.${port_name}.args")
      # Task tool invocation logic here
      # （CLAUDE.mdのオーケストレーターが実際にTask toolを呼ぶ）
      ;;
    *)
      echo "[TANEBI] ERROR: Unknown builtin: $builtin_name" >&2
      return 1
      ;;
  esac
}
```

**コア内部のcase文について**: `execute_builtin` 内に `case "$builtin_name"` が存在する。しかしこれは旧設計の `case "$adapter_set"` とは根本的に異なる:

| 旧設計のcase | 新設計のcase |
|-------------|-------------|
| **全Port**に影響（adapter_setで全Port実装が切り替わる） | **呼び出し方式のみ**に影響（特定Portの特定コマンドだけ） |
| 新adapter追加のたびにcase分岐が増える | builtin追加は「外部コマンドで代替できない技術的理由」がある時のみ |
| アダプター固有ロジックがコアに入る | builtinの中身は「Task toolを呼ぶ」という1行だけ |

#### claude-native config.yaml プロファイル

```yaml
tanebi:
  ports:
    worker_launch:
      decompose:
        command: "builtin:task_tool"
        timeout: 120
        args:
          instructions: |
            You are TANEBI Decomposer.
            Read the request at {request_file}.
            Available personas: {persona_list}.
            Create a decomposition plan and write to {plan_output}.
          max_turns: 10
      execute:
        command: "builtin:task_tool"
        timeout: 600
        args:
          instructions: |
            You are TANEBI Worker with persona {persona_file}.
            Complete the subtask defined in {subtask_file}.
            Reference few-shot examples: {few_shot_files}.
            Write your result to {output_path}.
          max_turns: 20
      execute_wave:
        # 省略時: execute.commandを並列Task tool呼び出し
        timeout: 900

    event_emit:
      command: "bash scripts/emit_event.sh {work_dir}/{cmd_id} {event_type} {payload}"

    state_read:
      command: "cat {resource_path}"
    state_write:
      command: "tee {resource_path} > /dev/null"

    knowledge_read:
      command: "ls knowledge/few_shot_bank/{domain}/ | head -n {limit}"

    security_check:
      command: "bash modules/trust/trust_module.sh on_task_assign {persona_id} {risk_level}"
    security_update:
      command: "bash modules/trust/trust_module.sh on_task_complete {persona_id}"
```

### 4.4 トレードオフ表

| 観点 | 案1 Bridge | 案2 Fallback | **案3 Builtin** | 案4 Dual Mode |
|------|-----------|-------------|-----------------|---------------|
| AP-2適合度 | ◎（表面上） | ✕ | ○（微小違反） | ✕✕ |
| 設計の誠実さ | ✕（偽コマンド） | △（暗黙知） | **◎（明示的）** | ○ |
| コア内分岐数 | 0 | 全Port分 | **1** | 全Step分 |
| config.yaml明示性 | ◎ | ✕ | **◎** | ○ |
| 新adapter追加コスト | ゼロ | ゼロ | **ゼロ** | ゼロ |
| 将来のbuiltin消滅 | — | — | **可能** | — |
| 実装複雑度 | 低 | 低 | **低** | 高 |

### 4.5 将来展望: builtinが消える日

Claude Code（またはAnthropic API）が以下のいずれかを提供した時点で、`builtin:task_tool` は不要になる:

1. **`claude --invoke-task '...'` CLI**: シェルからTask toolを呼べるCLIサブコマンド
2. **MCP経由のTask tool呼び出し**: 外部プロセスからMCPプロトコルでTask toolを利用
3. **`claude -p '...'` の成熟**: 現時点でも`claude --print`はあるが、これは独立プロセス起動であり、セッション内コンテキスト共有がない。将来的にセッション共有が可能になれば代替可能

その時の移行:
```yaml
# Before (builtin)
worker_launch:
  execute:
    command: "builtin:task_tool"
    args:
      instructions: "..."

# After (external command)
worker_launch:
  execute:
    command: "claude --invoke-task --session={session_id} --instructions '{instructions}'"
```

config.yamlの変更のみ。**TANEBIコアの変更はゼロ。** そしてbuiltinのcase文は安全に削除できる。

---

## 5. 環境別 config.yaml プロファイル

### 5.1 subprocess（最も単純）

```yaml
tanebi:
  ports:
    worker_launch:
      decompose:
        command: "bash scripts/run_worker.sh decomposer {request_file} {persona_list} {plan_output}"
        timeout: 120
      execute:
        command: "bash scripts/run_worker.sh worker {subtask_file} {persona_file} {few_shot_files} {output_path}"
        timeout: 600
      execute_wave:
        command: "echo {subtask_file} | xargs -P 4 -I {} bash scripts/run_worker.sh worker {} {persona_file} '' {output_path}"
        timeout: 900

    event_emit:
      command: "bash scripts/emit_event.sh {work_dir}/{cmd_id} {event_type} {payload}"

    state_read:
      command: "cat {resource_path}"
    state_write:
      command: "tee {resource_path} > /dev/null"

    knowledge_read:
      command: "ls knowledge/few_shot_bank/{domain}/ | head -n {limit}"

    security_check:
      command: "bash modules/trust/trust_module.sh on_task_assign {persona_id} {risk_level}"
    security_update:
      command: "bash modules/trust/trust_module.sh on_task_complete {persona_id}"
```

### 5.2 Docker

```yaml
tanebi:
  ports:
    worker_launch:
      decompose:
        command: >-
          docker run --rm
          --network tanebi-net
          --memory 512m --cpus 1.0
          -e TANEBI_ROOT=/app
          -v work:/app/work
          -v personas:/app/personas:ro
          -v templates:/app/templates:ro
          tanebi-worker:latest
          --role=decomposer
          --request=/app/work/{cmd_id}/request.md
          --plan-output=/app/work/{cmd_id}/plan.md
        timeout: 120
      execute:
        command: >-
          docker run --rm
          --network tanebi-net
          --memory 512m --cpus 1.0
          -e TANEBI_ROOT=/app
          -v work:/app/work
          -v personas:/app/personas:ro
          -v knowledge:/app/knowledge:ro
          -v templates:/app/templates:ro
          tanebi-worker:latest
          --role=worker
          --subtask-id={subtask_id}
          --persona=/app/personas/active/{persona_id}.yaml
          --output=/app/work/{cmd_id}/results/{subtask_id}.md
        timeout: 600
      execute_wave:
        # 省略: TANEBIコアがexecute.commandを並列呼び出し
        timeout: 900

    event_emit:
      command: "bash scripts/emit_event.sh {work_dir}/{cmd_id} {event_type} {payload}"

    state_read:
      command: "cat {resource_path}"
    state_write:
      command: "tee {resource_path} > /dev/null"

    knowledge_read:
      command: "ls knowledge/few_shot_bank/{domain}/ | head -n {limit}"

    security_check:
      command: "bash modules/trust/trust_module.sh on_task_assign {persona_id} {risk_level}"
    security_update:
      command: "bash modules/trust/trust_module.sh on_task_complete {persona_id}"

    # Polling fallback（コールバック未着時の安全策）
    worker_status_check:
      command: "docker inspect {container_id} --format '{{.State.Status}}'"
      polling_interval: 5
```

### 5.3 Lambda / Step Functions

```yaml
tanebi:
  ports:
    worker_launch:
      decompose:
        command: >-
          aws lambda invoke
          --function-name tanebi-worker
          --invocation-type RequestResponse
          --payload '{"role":"decomposer","cmd_id":"{cmd_id}","payload":{"request_s3_key":"work/{cmd_id}/request.md","persona_list":[{persona_list}],"plan_s3_key":"work/{cmd_id}/plan.md"}}'
          /tmp/tanebi_decompose_result.json
          && cat /tmp/tanebi_decompose_result.json
        timeout: 120
      execute:
        command: >-
          aws lambda invoke
          --function-name tanebi-worker
          --invocation-type Event
          --payload '{"role":"worker","cmd_id":"{cmd_id}","payload":{"subtask":{"id":"{subtask_id}"},"persona_s3_key":"personas/active/{persona_id}.yaml","output_s3_key":"work/{cmd_id}/results/{subtask_id}.md"}}'
          /tmp/tanebi_execute_result.json
        timeout: 600
      execute_wave:
        # Step Functions Map Stateを使う場合
        command: >-
          aws stepfunctions start-sync-execution
          --state-machine-arn arn:aws:states:us-east-1:123456789:stateMachine:tanebi-execute-wave
          --input '{"cmd_id":"{cmd_id}","subtasks":{subtask_list_json}}'
          --query 'output'
          --output text
        timeout: 900

    event_emit:
      command: >-
        aws sqs send-message
        --queue-url https://sqs.us-east-1.amazonaws.com/123456789/tanebi-events.fifo
        --message-body '{payload}'
        --message-group-id '{cmd_id}'
        --message-deduplication-id '{idempotency_key}'

    state_read:
      command: "aws s3 cp s3://tanebi-data/{resource_type}/{resource_id} -"
    state_write:
      command: "aws s3 cp - s3://tanebi-data/{resource_type}/{resource_id}"

    knowledge_read:
      command: "aws s3 ls s3://tanebi-data/few_shot_bank/{domain}/ --recursive | head -n {limit} | awk '{print $4}'"

    security_check:
      command: >-
        aws lambda invoke
        --function-name tanebi-trust-check
        --invocation-type RequestResponse
        --payload '{"persona_id":"{persona_id}","risk_level":"{risk_level}"}'
        /tmp/tanebi_trust_result.json
        && jq -r '.decision' /tmp/tanebi_trust_result.json | grep -q allow
    security_update:
      command: >-
        aws lambda invoke
        --function-name tanebi-trust-update
        --invocation-type Event
        --payload '{"persona_id":"{persona_id}"}'
        /dev/null

    # Polling: SQS long polling で Worker 完了検知
    worker_status_check:
      command: >-
        aws sqs receive-message
        --queue-url https://sqs.us-east-1.amazonaws.com/123456789/tanebi-completions.fifo
        --wait-time-seconds 20
      polling_interval: 0   # SQS側で待機
```

### 5.4 混成構成の例（Port単位で混合）

コマンド設定モデルの最大の利点: **Port単位で自由に混合できる**。

```yaml
tanebi:
  ports:
    # Worker起動はDocker（重い処理をコンテナ分離）
    worker_launch:
      execute:
        command: "docker run --rm -v work:/app/work tanebi-worker:latest --subtask-id={subtask_id}"

    # イベントはRedis（低レイテンシが必要）
    event_emit:
      command: "redis-cli PUBLISH tanebi.events.{event_type} '{payload}'"

    # 状態保存はS3（永続化が必要）
    state_read:
      command: "aws s3 cp s3://tanebi-data/{resource_type}/{resource_id} -"
    state_write:
      command: "aws s3 cp - s3://tanebi-data/{resource_type}/{resource_id}"

    # セキュリティはローカル（低レイテンシ）
    security_check:
      command: "bash modules/trust/trust_module.sh on_task_assign {persona_id} {risk_level}"
```

旧設計（`adapter_set: docker`）ではこの混成構成は不可能だった。

---

## 6. Inbound Port設計 — コールバックスクリプトモデル

### 6.1 設計思想: 対称的コマンドモデル

補足設計方針:
> 「呼ぶ側だけでなく、受ける側もコマンド設定モデルで考えよ。Worker完了時にtanebiに結果を返す手段として、tanebiが用意しているスクリプトを実行するだけ、というシンプルな形もありうる。」

これにより、TANEBIのPort設計は**完全に対称的**になる:

```
┌──────────────────────────────────────────────────────────┐
│ Outbound Port（TANEBIが外部を呼ぶ）                        │
│                                                          │
│   TANEBI core                                            │
│     → command_executor.sh                                │
│       → config.yaml の tanebi.ports.X.command を読む      │
│         → プレースホルダー置換                              │
│           → shell exec                                   │
│                                                          │
│   TANEBIが「やりたいこと」をコマンドとして実行する            │
├──────────────────────────────────────────────────────────┤
│ Inbound Port（外部がTANEBIに通知する）                      │
│                                                          │
│   Worker                                                 │
│     → tanebi-callback.sh <event_type> key=value ...      │
│       → emit_event.sh を直接呼び出し                       │
│         → イベント発行（環境別の転送はevent_emitが吸収）     │
│                                                          │
│   Workerが「伝えたいこと」をTANEBI提供の固定APIで通知する    │
└──────────────────────────────────────────────────────────┘
```

**核心**: Outbound Portは「config.yamlからコマンドを読んで実行する」設定可能なメカニズム。一方、Inbound（callbacks）はTANEBIが提供する**固定API仕様**であり、Workerは `tanebi-callback.sh` を叩くだけ。内部的には `emit_event.sh` を通じてイベントを発行し、環境別の転送方式の違いは `event_emit` コマンド設定が吸収する。Workerはその先の実装を一切知る必要がない。

### 6.2 tanebi-callback.sh — TANEBIが提供する固定APIスクリプト

```bash
#!/usr/bin/env bash
# tanebi-callback.sh — TANEBIへの完了通知スクリプト（固定API）
# Usage: bash scripts/tanebi-callback.sh <event_type> [key=value ...]
#
# 例:
#   bash scripts/tanebi-callback.sh worker_completed cmd_id=cmd_042 status=success
#   bash scripts/tanebi-callback.sh worker_progress cmd_id=cmd_042 progress=50

CALLBACK_TYPE="${1:?event_type required}"
shift

TANEBI_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# callbacksはconfigで差し替えるものではない。
# event_emit Portを通じてTANEBIにイベントを送る（環境別の転送設定はevent_emitが担う）。
bash "${TANEBI_ROOT}/scripts/emit_event.sh" "${CALLBACK_TYPE}" "$@"
```

### 6.3 callbacksは設定項目ではなく固定API仕様

`tanebi.callbacks` はconfig.yamlで設定するPortではない。

**設計上の区別:**

| 種別 | 仕組み | 設定 |
|------|--------|------|
| tanebi.ports（Outbound） | TANEBIが外部を呼ぶ | config.yamlで差し替え可能 |
| tanebi-callback.sh（Inbound） | Workerがtanebiを呼ぶ | 固定API仕様（設定不要） |

callbacksはTANEBIが提供する固定インターフェースであり、
Workerは単純に `bash scripts/tanebi-callback.sh <event_type> [key=value ...]` を実行するだけ。
環境（subprocess/Docker/Lambda）にかかわらず、呼び出し方は変わらない。

内部的には tanebi-callback.sh が event_emit Port を通じて完了イベントを送信する。
環境別のイベント転送方式の違いは event_emit コマンド設定が吸収する。

### 6.4 Workerの責務

**Workerは `tanebi-callback.sh` を叩くだけ。** それ以上の知識は不要。

```bash
# Worker実行スクリプトの末尾（全環境共通パターン）

# タスク実行...
do_work "$SUBTASK_FILE" "$PERSONA_FILE" > "$OUTPUT_PATH"

# 完了通知 — これだけ
bash scripts/tanebi-callback.sh worker_completed \
  cmd_id="$CMD_ID" \
  subtask_id="$SUBTASK_ID" \
  status="success" \
  result_path="$OUTPUT_PATH"
```

Docker環境では `tanebi-callback.sh` がvolume mountされている。Lambda環境ではLambda Layerに含まれている。subprocess環境ではプロジェクトディレクトリ内にある。**Workerは環境を問わず同じ呼び出し方をする。**

### 6.5 Polling Fallback（Orchestrator側の補助）

コールバックが何らかの理由で届かない場合の安全策。Outbound Portとして設定。

```yaml
tanebi:
  ports:
    # ... 既存のOutbound Ports ...

    # Polling用のOutbound Port（コールバックのfallback）
    worker_status_check:
      command: "test -f {work_dir}/{cmd_id}/results/{subtask_id}.md && echo done || echo running"
      polling_interval: 5   # 秒
```

Orchestratorは `worker_status_check` Portを定期的にpollingし、コールバック未着のWorker完了を検知する。**これもOutbound Portの1つ** — Orchestratorが「Workerの状態を確認する」コマンドを実行するだけ。

Docker版:
```yaml
worker_status_check:
  command: "docker inspect {container_id} --format '{{.State.Status}}'"
  polling_interval: 5
```

Lambda版:
```yaml
worker_status_check:
  command: >-
    aws sqs receive-message
    --queue-url https://sqs.us-east-1.amazonaws.com/123456789/tanebi-completions.fifo
    --wait-time-seconds 20
  polling_interval: 0   # SQS long polling
```

### 6.6 Outbound / Inbound の対称性と違い

| 方向 | 仕組み | 実行主体 | エントリポイント | 設定 |
|------|--------|---------|---------------|------|
| **Outbound** (TANEBI → 外部) | `tanebi.ports` | TANEBIコア | `command_executor.sh` | config.yamlで差し替え可能 |
| **Inbound** (外部 → TANEBI) | `tanebi-callback.sh`（固定API） | Worker | `tanebi-callback.sh` → `emit_event.sh` | 設定不要（固定API仕様） |
| **Polling** (TANEBI → 外部、状態確認) | `tanebi.ports.worker_status_check` | TANEBIコア | `command_executor.sh` | config.yamlで差し替え可能 |

**Outbound Portはconfig.yamlで差し替え可能なコマンド設定モデル。** 一方、**Inbound（callbacks）はTANEBIが提供する固定API仕様**であり、Workerは環境を問わず `tanebi-callback.sh` を叩くだけ。環境別の転送方式の違いは `event_emit` コマンド設定（Outbound Port）が吸収する。TANEBIコアにもWorkerにも、環境固有の知識は入らない。

### 6.7 Worker配布物

Workerに配布する最小ファイルセット:

| ファイル | 目的 | 配布方法 |
|---------|------|---------|
| `scripts/tanebi-callback.sh` | コールバックスクリプト（固定API） | Docker: volume mount / Lambda: Layer / subprocess: プロジェクト内 |
| `scripts/emit_event.sh` | イベント発行スクリプト | 同上 |
| `config.yaml` | tanebi.portsの参照のみ（callbacksセクション不要） | 同上 |

Workerは `tanebi-callback.sh` さえ叩ければ、自分がDocker内にいるのかLambda内にいるのかsubprocessなのかを知る必要がない。**callbacksは固定APIのため環境別の設定は不要。環境差の吸収はevent_emit Port（Outbound側）が担う。**

---

## 7. StateStore のエフェメラル環境設計

### 7.1 問題の本質

TANEBIの現実装は全てのI/Oがローカルファイルシステム前提。Lambda / Cloud Run / Fargate等のエフェメラル実行環境では、ファイルシステムはコンテナ終了時に消滅する。

| データ種別 | 現在の保存先 | 揮発時の影響 |
|-----------|------------|------------|
| Persona YAML | `personas/active/*.yaml` | **致命的** — 全進化履歴喪失 |
| タスク結果 | `work/cmd_NNN/results/*.md` | **致命的** — タスク成果喪失 |
| イベントログ | `work/cmd_NNN/events/*.yaml` | **中程度** — 監査証跡喪失 |
| コスト記録 | `work/cmd_NNN/cost.yaml` | **軽微** — 再計算可能 |
| 計画 | `work/cmd_NNN/plan.md` | **致命的** — フロー中断 |
| Few-Shot Bank | `knowledge/few_shot_bank/` | **中程度** — 知識蓄積リセット |

### 7.2 コマンド設定モデルでの解決

**エフェメラル環境はconfig.yamlのstate_read/state_writeコマンドで完全に解決される。**

```yaml
# ローカル環境（ファイルベース — デフォルト）
state_read:
  command: "cat {resource_path}"
state_write:
  command: "tee {resource_path} > /dev/null"

# エフェメラル環境（S3バックエンド）
state_read:
  command: "aws s3 cp s3://tanebi-data/{resource_type}/{resource_id} -"
state_write:
  command: "aws s3 cp - s3://tanebi-data/{resource_type}/{resource_id}"

# DynamoDB（低レイテンシ・高頻度アクセス）
state_read:
  command: "aws dynamodb get-item --table-name tanebi --key '{\"pk\":{\"S\":\"{resource_type}#{resource_id}\"}}' --query 'Item.data.S' --output text"
state_write:
  command: "aws dynamodb put-item --table-name tanebi --item '{\"pk\":{\"S\":\"{resource_type}#{resource_id}\"},\"data\":{\"S\":\"'$(cat)'\"}}}'"
```

旧設計ではStateStoreのバックエンド切り替えに「StateStore Adapter」「3層ストレージ戦略」「Write-Through/Write-Behind」等の複雑な設計が必要だった。コマンド設定モデルではconfig.yamlのコマンドを変えるだけ。**TANEBIコアには何の変更も不要。**

### 7.3 高度なパターン

#### Write-Through（コマンドチェーン）

ローカルキャッシュ + S3永続化を同時に行う場合:

```yaml
state_write:
  command: "tee {resource_path} | aws s3 cp - s3://tanebi-data/{resource_type}/{resource_id}"
```

1つのコマンドで「ローカル書き込み」と「S3アップロード」を同時実行。`tee`のパイプ。

#### Persona排他制御

```yaml
state_write:
  command: "flock /tmp/tanebi_{resource_type}_{resource_id}.lock tee {resource_path} > /dev/null"
```

`flock`による排他制御もコマンドレベルで解決。

### 7.4 Persona Manager パターン（Lambda環境）

エフェメラル環境でのPersona排他更新は、オーケストレーター側に集約する設計を推奨。

```
Orchestrator (常駐 — ECS / EC2 / ローカル)
  └── Persona Manager (single writer)
      ├── state_read: "aws s3 cp s3://tanebi-data/persona/{persona_id} -"
      ├── state_write: "aws s3 cp - s3://tanebi-data/persona/{persona_id}"
      └── evolve.sh → state_read → update → state_write の排他実行

Worker (Lambda — stateless)
  └── Persona は read-only で参照（invoke payload埋め込み or pre-signed URL）
```

---

## 8. 現実装ギャップ分析（コマンド設定モデル観点）

旧ポリシーのV-001〜V-005を、コマンド設定モデルの観点で再評価する。

### 解消される問題

| 旧問題 | 旧深刻度 | コマンドモデルでの状況 |
|--------|---------|---------------------|
| **V-001: CLAUDE.mdのclaude-native固定** | Critical | **解消** — claude-nativeは `builtin:task_tool` としてconfig.yamlに明示。CLAUDE.mdの分離は不要（CLAUDE.md自体がclaude-native構成時のオーケストレーター） |
| **V-003: Wave並列のTask tool固定** | High | **解消** — execute_wave.commandで並列方式を構成側が決定 |
| **V-004: emit_event.sh密結合** | High | **解消** — event_emit.commandで任意のtransportを指定可能 |
| 旧adapter_setのcase文分岐 | — | **消滅** — case文自体が不要に |
| port_mapping.yamlの管理コスト | — | **消滅** — config.yamlに全て集約 |

### 残存する問題

| 問題 | 深刻度 | 内容 | 対策 |
|------|--------|------|------|
| **V-002: TANEBI_ROOTオーバーライド不可** | High | `scripts/tanebi_config.sh`の8行目。Docker等でパス注入できない | FIX-001: `TANEBI_ROOT="${TANEBI_ROOT:-$(computed)}"` パターン採用。1行変更 |
| **V-005: handler.sh内ファイル直接I/O** | Medium | 3プラグインがstate Portを経由せずファイル直接読み書き | 段階的修正: state_read/state_writeコマンドを利用するヘルパー関数に置換 |
| **command_executor未実装** | New | §3.3で設計したコマンド実行エンジンがまだ存在しない | Phase 3.5で新規実装 |
| **config.yaml Port構造未実装** | New | 現config.yamlにportsセクションが存在しない | Phase 3.5で追加 |
| **builtin:task_tool未実装** | New | claude-native用のbuiltin呼び出しメカニズムが未実装 | Phase 3.5で実装 |

### ポリシー適合済み（変更不要）

| コンポーネント | 適合状況 | 備考 |
|--------------|---------|------|
| **Persona YAMLスキーマ** | 完全適合 | データ定義。環境非依存 |
| **events/schema.yaml** | 完全適合 | イベントスキーマ。コア定義 |
| **evolve.sh** | 高適合 | state_read/state_writeコマンド経由に改修すれば完全適合 |
| **Trust Module** | 高適合 | security_check/updateコマンドとして自然に表現 |
| **subprocess adapter** | 高適合 | config.yamlにコマンドとして記述するだけ |

---

## 9. 改修ロードマップ

### Phase 3.5（コマンド設定モデル基盤構築）

| 改修ID | 内容 | 工数見積 |
|--------|------|---------|
| **CMD-001** | `scripts/command_executor.sh` 新規作成 — §3.3のコマンド実行エンジン | 2日 |
| **CMD-002** | config.yaml に `tanebi.ports` セクション追加。claude-native構成をデフォルトで記述 | 1日 |
| **CMD-003** | `builtin:task_tool` メカニズム実装 — CLAUDE.mdオーケストレーターとの統合 | 2日 |
| **CMD-004** | 既存オーケストレーター（CLAUDE.md）をcommand_executor経由の呼び出しに段階的移行 | 3日 |
| **FIX-001** | V-002修正 — `TANEBI_ROOT` オーバーライド対応（1行変更） | 0.5日 |
| **FIX-003** | V-005部分修正 — plugin_helpers.shにstate_read/state_write wrapper追加 | 1日 |

**Phase 3.5 合計工数: 9.5日**

### Phase 4（Docker構成のconfig.yaml作成 + 検証）

| 項目 | 内容 | 工数見積 |
|------|------|---------|
| Docker config.yaml | §5.2のプロファイルを作成・検証 | 1日 |
| Dockerイメージ作成 | `tanebi-worker:latest` ビルド | 1日 |
| orchestrator.sh（command_executor利用版） | command_executorを呼ぶだけのシンプルなシェル | 1日 |
| E2Eテスト | Docker構成でのfull flow | 2日 |

**Phase 4 合計工数: 5日**（旧設計の8-9日から大幅短縮 — adapter固有コードが減るため）

### Phase 5（Lambda構成のconfig.yaml作成 + 検証）

| 項目 | 内容 | 工数見積 |
|------|------|---------|
| Lambda config.yaml | §5.3のプロファイルを作成 | 1日 |
| Lambda handler.py | Worker/Decomposer/Aggregator | 3日 |
| Step Functions定義 | execute_wave用 | 2日 |
| E2Eテスト | Lambda構成でのfull flow | 3日 |

**Phase 5 合計工数: 9日**（旧設計の15-20日から大幅短縮）

---

## 10. Hello World Adapter（コマンドモデル版）

### Step 1: config.yamlにコマンドを書く

```yaml
# config.yaml — Hello World構成
tanebi:
  ports:
    worker_launch:
      decompose:
        command: "echo 'plan:\\n  cmd: {cmd_id}\\n  total_subtasks: 1\\n  waves: 1\\n  subtasks:\\n    - id: subtask_001\\n      description: Process request\\n      persona: generalist_v1\\n      wave: 1' > {plan_output}"
        timeout: 10
      execute:
        command: "echo '---\\nsubtask_id: {subtask_id}\\npersona: generalist_v1\\nstatus: success\\nquality: GREEN\\n---\\nHello from TANEBI!' > {output_path}"
        timeout: 10

    event_emit:
      command: "echo '[EVENT] {event_type}: {payload}'"

    state_read:
      command: "cat {resource_path} 2>/dev/null || echo ''"
    state_write:
      command: "tee {resource_path} > /dev/null"

    security_check:
      command: "exit 0"   # 常にallow
```

**これだけ。** adapter専用ディレクトリも、orchestrator.shも、port_mapping.yamlも不要。config.yamlにコマンドを書くだけで新しい「アダプター」が完成する。

### Step 2: 実行

```bash
bash scripts/command_executor.sh worker_launch.execute \
  cmd_id=cmd_test subtask_id=subtask_001 \
  output_path=work/cmd_test/results/subtask_001.md
```

### Step 3: 結果確認

```bash
cat work/cmd_test/results/subtask_001.md
# ---
# subtask_id: subtask_001
# persona: generalist_v1
# status: success
# quality: GREEN
# ---
# Hello from TANEBI!
```

### 旧設計との比較

| 項目 | 旧設計 | 新設計（コマンドモデル） |
|------|---------------------|----------------------|
| 必要なファイル | `adapters/hello-world/orchestrator.sh` + `port_mapping.yaml` + config.yaml変更 | **config.yamlのみ** |
| コード行数 | orchestrator.sh 60行 + port_mapping.yaml 15行 | **config.yaml 20行** |
| TANEBIコア変更 | case文に`hello-world)`を追加 | **なし** |

---

## 11. エラーハンドリング

### 11.1 コマンド実行エラー

command_executorが処理するエラーパターン:

| 状況 | 検知方法 | 対応 |
|------|---------|------|
| コマンド未設定 | `command` フィールド空 | エラー終了。「Port {name} にcommandが設定されていません」 |
| プレースホルダー未解決 | `{xxx}` パターン残存 | エラー終了。「未解決プレースホルダー: {xxx}」 |
| コマンド実行失敗 | exit code 非0 | Port種別に応じた処理（§3.7参照） |
| タイムアウト | timeout超過 | プロセス強制終了。結果を `status: failure` に設定 |
| builtin未知 | `builtin:unknown_name` | エラー終了。「Unknown builtin: unknown_name」 |

### 11.2 設定バリデーション

TANEBIコア起動時に以下を検証:

```yaml
validation:
  required_ports:
    - worker_launch.decompose.command   # フロー実行に必須
    - worker_launch.execute.command     # フロー実行に必須
    - state_write.command               # 結果保存に必須
  optional_ports:
    - worker_launch.execute_wave.command  # 省略時: execute.commandの並列呼び出し
    - event_emit.command                  # 省略時: イベント発火なし（プラグイン無効）
    - state_read.command                  # 省略時: ファイル直接読み取り
    - knowledge_read.command              # 省略時: ローカルファイル参照
    - security_check.command              # 省略時: 常にallow
    - security_update.command             # 省略時: no-op
  validation_steps:
    - 全required_portのcommandが非空であること
    - 全commandのプレースホルダーが既知のものであること（タイポ検出）
    - timeout値が正の整数であること
    - builtin:XXX のXXX が既知のbuiltinであること
```

### 11.3 デバッグ支援

```bash
# コマンドのドライラン（実行せず置換結果を表示）
bash scripts/command_executor.sh --dry-run worker_launch.execute \
  cmd_id=cmd_001 subtask_id=subtask_001 persona_file=personas/active/gen_v1.yaml \
  output_path=work/cmd_001/results/subtask_001.md

# 出力例:
# [TANEBI] Dry run for port: worker_launch.execute
# [TANEBI] Command: docker run --rm --network tanebi-net -v work:/app/work ...
# [TANEBI] Timeout: 600s
```

---

## 12. docs/design.md 反映計画

本ポリシーの内容をdocs/design.mdに反映するための計画。

### 追加が必要なセクション

| 追加位置 | 内容 |
|---------|------|
| **Section 1.3（設計原則）** | AP-1〜AP-5（コマンド設定モデル版）を記載 |
| **Section 8（アダプターインターフェース）全面改訂** | IF-001〜005を廃止。コマンド設定モデルのPort定義に置換 |
| **Section 8 新設 "config.yaml Port構造"** | §3.1の構造定義 |
| **Section 8 新設 "プレースホルダー規約"** | §3.2の全プレースホルダー表 |
| **Section 8 新設 "builtin:task_tool"** | §4の設計と根拠 |

### 削除が必要な概念

| 概念 | 理由 |
|------|------|
| `adapter_set` | コマンド設定モデルでは不要 |
| `case "$adapter_set"` 分岐 | 消滅 |
| `adapters/{adapter_name}/port_mapping.yaml` | config.yamlに統合 |
| IF-001〜IF-005（名前付きインターフェース） | Port command定義に置換 |

---

*End of Policy Document (Command Configuration Model)*
