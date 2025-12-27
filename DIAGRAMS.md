# Memory Assistant v4 フロー図

このドキュメントでは、Memory Assistant v4の実装を視覚的に理解できるように、各種フロー図をmermaid記法で提供します。

## 目次

1. [システムアーキテクチャ図](#システムアーキテクチャ図)
2. [チャットワークフローシーケンス図](#チャットワークフローシーケンス図)
3. [データベースER図](#データベースer図)
4. [クラス図](#クラス図)
5. [LLMタスク状態遷移図](#llmタスク状態遷移図)
6. [属性判定・抽出フロー](#属性判定抽出フロー)

---

## システムアーキテクチャ図

システム全体の構成とコンポーネント間の関係を示します。

```mermaid
graph TB
    subgraph "ユーザーインターフェース層"
        UI[チャットUI]
        LogUI[ログ確認画面]
        MasterUI[属性マスタ保守画面]
        RecordUI[属性テーブル保守画面]
    end

    subgraph "アプリケーション層"
        ChatService[ChatService<br/>チャットワークフロー管理]
        StatusCallback[ステータスコールバック<br/>リアルタイム表示]
    end

    subgraph "LLM層"
        LLMClient[LLMClient<br/>抽象インターフェース]
        MockLLM[MockLLMClient<br/>テスト用]
        OllamaLLM[OllamaClient<br/>Ollama API]
        AnthropicLLM[AnthropicClient<br/>Claude API]
        CloudflareLLM[CloudflareClient<br/>Workers AI]
    end

    subgraph "データ層"
        Database[Database<br/>SQLite操作]
        Models[Models<br/>データモデル定義]
    end

    subgraph "外部サービス"
        Ollama[Ollama<br/>llama3.1:8b]
        Claude[Anthropic Claude]
        Workers[Cloudflare Workers]
    end

    UI --> ChatService
    LogUI --> Database
    MasterUI --> Database
    RecordUI --> Database

    ChatService --> LLMClient
    ChatService --> Database
    ChatService --> StatusCallback

    LLMClient <|-- MockLLM
    LLMClient <|-- OllamaLLM
    LLMClient <|-- AnthropicLLM
    LLMClient <|-- CloudflareLLM

    OllamaLLM --> Ollama
    AnthropicLLM --> Claude
    CloudflareLLM --> Workers

    Database --> Models
    StatusCallback --> UI

    style ChatService fill:#e1f5ff
    style LLMClient fill:#fff4e1
    style Database fill:#f0f0f0
```

---

## チャットワークフローシーケンス図

ユーザー入力から応答生成までの処理フローを時系列で示します。

```mermaid
sequenceDiagram
    actor User as ユーザー
    participant UI as チャットUI
    participant CS as ChatService
    participant DB as Database
    participant LLM as LLMClient

    User->>UI: メッセージ入力
    UI->>CS: process_user_input(user_input)

    Note over CS: Step 1-2: 属性判定と抽出

    CS->>DB: get_all_attribute_masters()
    DB-->>CS: 属性マスタ一覧

    loop 各属性マスタ
        CS->>UI: ステータス表示<br/>"属性「XX」が応答に必要か判定中"
        CS->>LLM: judge(judgment_prompt, user_input)
        LLM-->>CS: True/False

        alt 属性が必要
            CS->>UI: ステータス表示<br/>"属性「XX」のデータを抽出中"
            CS->>DB: get_latest_attribute_content(attribute_id)
            DB-->>CS: 属性データ
        end
    end

    Note over CS: Step 3: 応答文の生成

    CS->>UI: ステータス表示<br/>"応答文を生成中"
    CS->>LLM: generate_response(history, input, attributes)
    LLM-->>CS: 応答テキスト

    Note over CS: Step 4: 応答を表示

    CS-->>UI: 応答テキスト
    UI-->>User: 応答表示

    Note over CS: Step 5: 属性抽出と登録

    loop 各属性マスタ
        CS->>UI: ステータス表示<br/>"ユーザー入力から「XX」を抽出中"
        CS->>LLM: extract(extraction_prompt, user_input)
        LLM-->>CS: 抽出された内容 or None

        alt 抽出成功
            CS->>DB: insert_attribute_record(record)
            DB-->>CS: 登録完了
        end
    end

    CS-->>UI: 処理完了
```

---

## データベースER図

属性マスタと属性テーブルの関係を示します。

```mermaid
erDiagram
    ATTRIBUTE_MASTER ||--o{ ATTRIBUTE_RECORDS : "1:N"

    ATTRIBUTE_MASTER {
        int attribute_id PK "属性ID（自動採番）"
        string attribute_name "属性名称"
        text extraction_prompt "抽出プロンプト"
        text judgment_prompt "判定プロンプト"
    }

    ATTRIBUTE_RECORDS {
        int sequence_no PK "シーケンスNO（自動採番）"
        int attribute_id FK "属性ID"
        text content "内容"
        datetime created_at "登録日時"
        datetime updated_at "更新日時"
    }
```

---

## クラス図

主要なクラスとその関係を示します。

```mermaid
classDiagram
    class ChatService {
        -LLMClient llm
        -Database db
        -list~ChatMessage~ chat_history
        -Callable status_callback
        +process_user_input(user_input) ChatResponse
        +process_user_input_streaming(user_input) Generator
        +clear_history()
        +get_chat_history() list
    }

    class LLMClient {
        <<abstract>>
        +generate(prompt) LLMResponse
        +judge(judgment_prompt, user_input) bool
        +extract(extraction_prompt, user_input) Optional~str~
        +generate_response(history, input, attributes) str
    }

    class MockLLMClient {
        -dict judgment_responses
        -dict extraction_responses
        -list generate_responses
        +set_judgment_response(attr_name, response)
        +set_extraction_response(attr_name, response)
        +add_generate_response(response)
    }

    class OllamaClient {
        -str base_url
        -str model
        +generate(prompt) LLMResponse
    }

    class Database {
        -str db_path
        -Connection _connection
        +connect() Connection
        +initialize()
        +insert_attribute_master(master) int
        +get_all_attribute_masters() list
        +insert_attribute_record(record) int
        +get_latest_attribute_content(attr_id) Optional~str~
    }

    class AttributeMaster {
        +int attribute_id
        +str attribute_name
        +str extraction_prompt
        +str judgment_prompt
    }

    class AttributeRecord {
        +Optional~int~ sequence_no
        +int attribute_id
        +str content
        +datetime created_at
        +datetime updated_at
    }

    class ChatMessage {
        +str role
        +str content
        +datetime timestamp
    }

    class LLMTaskStatus {
        +str task_type
        +Optional~str~ attribute_name
        +str status
        +display_text() str
    }

    class ChatResponse {
        +str response_text
        +dict used_attributes
        +list extracted_attributes
        +list task_statuses
    }

    ChatService --> LLMClient : uses
    ChatService --> Database : uses
    ChatService ..> ChatMessage : creates
    ChatService ..> LLMTaskStatus : creates
    ChatService ..> ChatResponse : returns

    LLMClient <|-- MockLLMClient : implements
    LLMClient <|-- OllamaClient : implements

    Database ..> AttributeMaster : manages
    Database ..> AttributeRecord : manages
```

---

## LLMタスク状態遷移図

LLMタスクの処理状態の遷移を示します。

```mermaid
stateDiagram-v2
    [*] --> pending : タスク生成

    pending --> processing : タスク開始

    state processing {
        [*] --> judgment : 属性判定タスク
        [*] --> extraction : データ抽出タスク
        [*] --> response : 応答生成タスク
        [*] --> attribute_extraction : 属性抽出タスク
    }

    processing --> completed : 処理成功
    processing --> failed : 処理失敗

    completed --> [*]
    failed --> [*]

    note right of judgment
        判定プロンプトを使用して
        属性が必要かどうかを判定
    end note

    note right of extraction
        データベースから
        属性データを取得
    end note

    note right of response
        チャット履歴と属性データから
        応答文を生成
    end note

    note right of attribute_extraction
        ユーザー入力から
        属性を抽出して登録
    end note
```

---

## 属性判定・抽出フロー

属性マスタを使った判定・抽出の詳細フローを示します。

```mermaid
flowchart TD
    Start([ユーザー入力受信]) --> GetMasters[属性マスタを全件取得]

    GetMasters --> Loop1{各属性マスタ<br/>をループ}

    Loop1 -->|次の属性| Judge[判定プロンプトでLLMに判定]
    Judge --> IsRequired{応答に<br/>必要？}

    IsRequired -->|はい| FetchDB[DBから最新の<br/>属性データを取得]
    IsRequired -->|いいえ| Loop1

    FetchDB --> HasData{データが<br/>存在？}
    HasData -->|あり| AddToContext[コンテキストに追加]
    HasData -->|なし| Loop1

    AddToContext --> Loop1

    Loop1 -->|全属性処理完了| GenerateResponse[応答文を生成]

    GenerateResponse --> DisplayResponse[応答を表示]

    DisplayResponse --> Loop2{各属性マスタ<br/>をループ}

    Loop2 -->|次の属性| Extract[抽出プロンプトで<br/>LLMに抽出依頼]

    Extract --> Extracted{抽出<br/>成功？}

    Extracted -->|あり| SaveDB[(属性レコードを<br/>DBに保存)]
    Extracted -->|なし| Loop2

    SaveDB --> Loop2

    Loop2 -->|全属性処理完了| End([処理完了])

    style Start fill:#e1f5ff
    style End fill:#e1ffe1
    style GenerateResponse fill:#ffe1e1
    style Judge fill:#fff4e1
    style Extract fill:#fff4e1
```

---

## 2段階プロンプト設計の概念図

推論タスクと構造化タスクを分離する設計思想を示します。

```mermaid
graph LR
    subgraph "従来の方法（非推奨）"
        Input1[ユーザー入力] --> Task1[推論 + 構造化<br/>を同時に実行]
        Task1 --> Output1[JSON出力<br/>品質が不安定]

        style Task1 fill:#ffcccc
        style Output1 fill:#ffcccc
    end

    subgraph "2段階プロンプト設計（推奨）"
        Input2[ユーザー入力]

        Input2 --> Reasoning[Step 1: 推論タスク<br/>自然言語で思考]
        Reasoning --> ReasoningOut[自然言語の結果]

        ReasoningOut --> Structure[Step 2: 構造化タスク<br/>JSON変換]
        Structure --> StructureOut[JSON出力<br/>高品質・安定]

        style Reasoning fill:#ccffcc
        style Structure fill:#ccffcc
        style StructureOut fill:#ccffcc
    end

    Note1[SLMでも高精度な<br/>処理が可能]

    StructureOut -.-> Note1
```

---

## LLMプロバイダー切り替えフロー

複数のLLMプロバイダーに対応する仕組みを示します。

```mermaid
flowchart TD
    Start([アプリケーション起動]) --> ReadEnv[環境変数を読み込み]

    ReadEnv --> CheckProvider{LLM_PROVIDER<br/>の値は？}

    CheckProvider -->|ollama| CreateOllama[OllamaClientを生成]
    CheckProvider -->|anthropic| CreateAnthropic[AnthropicClientを生成]
    CheckProvider -->|cloudflare| CreateCloudflare[CloudflareClientを生成]
    CheckProvider -->|未設定| CreateDefault[デフォルト: OllamaClient]

    CreateOllama --> SetClient[LLMClientとして設定]
    CreateAnthropic --> SetClient
    CreateCloudflare --> SetClient
    CreateDefault --> SetClient

    SetClient --> InitService[ChatServiceを初期化]

    InitService --> Ready([準備完了])

    style CreateOllama fill:#e1f5ff
    style CreateAnthropic fill:#ffe1f5
    style CreateCloudflare fill:#f5ffe1
```

---

## 使用方法

これらの図は、以下のmermaid対応ツールで表示できます：

- **GitHub**: `.md`ファイルに記述すれば自動的にレンダリングされます
- **VS Code**: Mermaid拡張機能をインストール
- **オンラインエディタ**: [Mermaid Live Editor](https://mermaid.live/)
- **ドキュメントサイト**: GitBook、MkDocs、Docusaurusなど

## 参考ドキュメント

- [design.md](design.md) - システム設計の詳細
- [README.md](README.md) - プロジェクト概要
- [JSON-Schema-compliant.md](JSON-Schema-compliant.md) - 2段階プロンプト設計の理論
