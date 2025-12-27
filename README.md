# Memory Assistant v4

SLM（Small Language Model）を活用した、属性ベースのメモリ管理機能を持つチャットアシスタントです。モデルの性能に頼らず、工程を最適化することで役立つアシスタントとして機能します。

## 概要

Memory Assistant v4は、ユーザーとの会話から重要な属性情報を自動的に抽出・管理し、それを活用して精度の高い応答を生成するチャットアシスタントです。優秀な秘書やアシスタントが行うように、サポート対象者の情報を分類して記録し、適切なタイミングで活用します。

## 特徴

- **属性ベースのメモリ管理**: ユーザーのプロフィール、興味、予定などの属性を自動抽出・保存
- **2段階プロンプト設計**: 推論タスクと構造化タスクを分離することで、小規模モデルでも高精度な処理を実現
- **リアルタイムステータス表示**: LLMが何のタスクを処理しているかをリアルタイムで表示
- **複数LLMプロバイダー対応**: Ollama、Anthropic Claude、Cloudflare Workersに対応

## 技術スタック

- **言語**: Python
- **LLM**: Ollama + llama3.1:8b (デフォルト)
- **データベース**: SQLite
- **設計思想**: JSON-Schema準拠の構造化出力（詳細は `JSON-Schema-compliant.md` を参照）

## データ構造

### 属性マスタ
- 属性ID
- 属性名称
- 抽出プロンプト: ユーザー入力から属性を抽出するためのプロンプト
- 判定プロンプト: 応答に属性が必要かを判定するためのプロンプト

### 属性テーブル
- シーケンスNO
- 属性ID
- 内容
- 登録日
- 更新日

## セットアップ

### 必要要件

- Python 3.8以上
- Ollama（ローカルLLMを使用する場合）

### インストール

1. リポジトリをクローン
```bash
git clone <repository-url>
cd memory-assistant-v4
```

2. 仮想環境を作成（推奨）
```bash
python -m venv venv
source venv/bin/activate  # Windowsの場合: venv\Scripts\activate
```

3. 依存パッケージをインストール
```bash
pip install -r requirements.txt
```

4. 環境変数を設定
```bash
# .envファイルを作成
LLM_PROVIDER=ollama
OLLAMA_URL=http://localhost:11434

# Anthropic Claudeを使用する場合
# LLM_PROVIDER=anthropic
# ANTHROPIC_API_KEY=your_api_key

# Cloudflare Workersを使用する場合
# LLM_PROVIDER=cloudflare
# CF_ACCOUNT_ID=your_account_id
# CF_API_TOKEN=your_api_token
```

5. Ollamaのセットアップ（ローカルLLMを使用する場合）
```bash
# Ollamaをインストール後
ollama pull llama3.1:8b
```

## 使い方

### 基本的な使い方

```python
from src.chat_service import ChatService
from llm_config import LLMConfig

# LLMクライアントを初期化
extractor = LLMConfig.from_env()

# チャットサービスを開始
chat_service = ChatService(extractor)

# チャット開始
response = chat_service.process_user_input("こんにちは、私はエンジニアです")
print(response)
```

### チャットワークフロー

1. **ユーザー入力**
2. **属性判定**: 各属性マスタの判定プロンプトを使用して、応答に必要な属性を判定
3. **属性抽出**: 必要と判定された属性データをデータベースから抽出
4. **応答生成**: チャット履歴 + ユーザー入力 + 抽出された属性データを元に応答を生成
5. **応答表示**: 生成された応答をユーザーに表示
6. **属性登録**: ユーザー入力から新しい属性を抽出し、データベースに登録

## 機能

### チャット画面
- 応答の編集ステータスをリアルタイムで表示
- LLMに何のタスクを投げているかを可視化

### ログ確認画面
- LLMとのすべての応答（送信/受信）を一覧表示

### 属性マスタ保守画面
- 属性の追加・変更・削除

### 属性テーブル保守画面
- 属性データの追加・変更・削除
- 属性集計機能（重複する属性をLLMで統合）

## 設計思想

詳細は以下のドキュメントを参照してください：

- `design.md`: システム全体の設計思想とワークフロー
- `JSON-Schema-compliant.md`: 2段階プロンプト設計の理論的背景
- `porting-cloudflare.md`: Cloudflare Workers対応について

## テスト

```bash
pytest tests/
```

## プロジェクト構造

```
memory-assistant-v4/
├── src/
│   ├── __init__.py
│   ├── models.py           # データモデル定義
│   ├── database.py         # データベース操作
│   ├── llm_client.py       # LLMクライアント
│   └── chat_service.py     # チャットサービスロジック
├── tests/
│   ├── __init__.py
│   └── test_chat_workflow.py
├── llm_config.py           # LLM設定管理
├── design.md               # 設計ドキュメント
├── JSON-Schema-compliant.md
└── README.md
```

## 貢献

プルリクエストは歓迎します。大きな変更の場合は、まずissueを開いて変更内容を議論してください。

プルリクエストのタイトルは日本語で以下の形式で作成してください：
`[種別] 説明文`

例：
- `[修正] ログイン機能の改善`
- `[追加] ユーザー認証機能`
- `[削除] 不要なコード`

## ライセンス

[ライセンス情報をここに記載]
