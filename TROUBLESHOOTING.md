# トラブルシューティング

Memory Assistant v4 の使用中に発生する可能性のある問題と解決策を説明します。

## 目次

1. [抽出結果が「なし」になる](#抽出結果がなしになる)
2. [処理の途中経過が表示されない](#処理の途中経過が表示されない)
3. [チャット履歴が重複する](#チャット履歴が重複する)
4. [Raw Responseに数値の羅列が表示される](#raw-responseに数値の羅列が表示される)

---

## 抽出結果が「なし」になる

### 症状

ログを確認すると、LLMの応答が「なし」となっており、属性が抽出されていない。

例：
```
<ユーザーの入力>
私の名前は？
</ユーザーの入力>

抽出された内容: なし
```

### 原因

これは**正常な動作**です。属性抽出は、ユーザーが**情報を提供した場合**にのみ実行されます。

#### 情報抽出の仕組み

Memory Assistant v4 は、ユーザーの発言から情報を抽出してデータベースに保存する仕組みを持っています。抽出処理は以下のロジックで動作します（`src/llm_client.py:65-89`）：

```python
def extract(self, extraction_prompt: str, user_input: str, attribute_name: Optional[str] = None) -> Optional[str]:
    """
    抽出タスク: ユーザー入力から情報を抽出

    抽出できなかった場合はNoneを返す
    """
    prompt = f"""あなたは情報抽出を行うアシスタントです。

<抽出指示>
{extraction_prompt}
</抽出指示>

<ユーザーの入力>
{user_input}
</ユーザーの入力>

抽出する情報がない場合は「なし」と回答してください。
抽出された内容:"""

    response = self.generate(prompt, task_type="extraction", attribute_name=attribute_name)
    content = response.content.strip()

    if content == "なし" or content == "" or "なし" in content[:10]:
        return None
    return content
```

#### 正しい動作例

**質問形式（抽出されない）**
- ユーザー入力：「私の名前は？」
- 抽出結果：「なし」 ✓ 正常
- 理由：質問であり、新しい情報が提供されていない

**情報提供形式（抽出される）**
- ユーザー入力：「私の名前は田中太郎です」
- 抽出結果：「田中太郎」 ✓ 正常
- 理由：プロフィール情報（名前）が提供されている

### 解決策

これは設計通りの動作であり、修正の必要はありません。

- **質問**をする場合 → 属性は抽出されません（既存の属性データを使って応答を生成します）
- **情報を提供**する場合 → 属性が抽出され、データベースに保存されます

---

## 処理の途中経過が表示されない

### 症状

チャットメッセージを送信しても、処理の途中経過が画面に表示されず、最終結果だけが表示される。

### 原因（修正済み）

以前のバージョンでは、全ての処理が完了してから一度に結果を返していたため、リアルタイムで途中経過を表示できませんでした。

### 解決策

**v4.1以降で修正済み**：Server-Sent Events (SSE) を実装し、リアルタイムで処理状況を表示できるようになりました。

- 各タスク（判定、抽出、応答生成など）の進行状況がリアルタイムで表示されます
- ステータス表示エリアに、現在実行中のタスクが表示されます

実装詳細：
- バックエンド：`app.py:183-242` - `/api/chat/stream` エンドポイント
- フロントエンド：`templates/chat.html:116-204` - SSE受信処理

---

## チャット履歴が重複する

### 症状

1回の送信で、同じメッセージが2回チャット履歴に追加される。

### 原因（修正済み）

以前のバージョンでは、`process_user_input_streaming()` と `process_user_input()` を両方呼び出していたため、処理が2回実行されていました。

### 解決策

**v4.1で修正済み**：ジェネレーターの戻り値を正しく取得するように修正しました。

修正内容（`app.py:121-157`）：
```python
# 修正前（重複実行）
for status in chat_service.process_user_input_streaming(user_input):
    statuses.append(...)
response = chat_service.process_user_input(user_input)  # ← 2回目の実行

# 修正後（1回のみ実行）
gen = chat_service.process_user_input_streaming(user_input)
try:
    while True:
        status = next(gen)
        statuses.append(...)
except StopIteration as e:
    response = e.value  # ジェネレーターのreturn値を取得
```

---

## Raw Responseに数値の羅列が表示される

### 症状

ログ画面の「Raw Response (詳細)」に、`context` フィールドが数値の配列として表示される。

例：
```json
{
  "context": [1, 15043, 3054, 1552, 319, 264, 10695, ...]
}
```

### 原因

Ollama API は、レスポンスに `context` フィールドを含めることがあります。これは**トークンIDの配列**であり、内部的な処理に使用されるデータです。

### 解決策

**v4.1で修正済み**：`context` フィールドが配列の場合、要約表示するように変更しました。

修正内容（`templates/logs.html:55-82`）：
```javascript
// contextフィールドが数値配列の場合は処理
let displayData = {...rawData};
if (displayData.context && Array.isArray(displayData.context)) {
    // contextが数値配列の場合は要約表示
    const contextLength = displayData.context.length;
    displayData.context = `[トークンID配列: ${contextLength}個のトークン (表示省略)]`;
}
```

表示例（修正後）：
```json
{
  "response": "こんにちは！",
  "context": "[トークンID配列: 128個のトークン (表示省略)]"
}
```

---

## LLMリクエストは並列処理されていますか？

### 回答

**いいえ、逐次処理（シーケンシャル）です。**

設計上、各属性マスタに対するLLMリクエストは順番に実行されます（`src/chat_service.py:64-96`, `181-211`）：

```python
for master in masters:
    # 判定処理（逐次）
    is_required = self.llm.judge(master.judgment_prompt, user_input, master.attribute_name)

    if is_required:
        # 抽出処理（逐次）
        content = self.db.get_latest_attribute_content(master.attribute_id)
```

### なぜ逐次処理なのか？

1. **処理の透明性**：各タスクの進行状況をリアルタイムで表示するため
2. **リソース管理**：Ollama サーバーへの負荷を制御するため
3. **デバッグのしやすさ**：処理順序が明確で、問題の特定が容易

### 性能への影響

- 属性マスタの数が多い場合、処理時間が長くなる可能性があります
- ただし、Server-Sent Events により、ユーザーは途中経過を確認できるため、体感的な待ち時間は短縮されます

---

## その他の問題

上記以外の問題が発生した場合：

1. **ログを確認**：`/logs` ページでLLMとのやり取りを確認
2. **サーバーログを確認**：コンソールにエラーメッセージが出力されていないか確認
3. **Ollamaの接続を確認**：`OLLAMA_URL` と `OLLAMA_MODEL` の設定が正しいか確認
4. **Issue報告**：GitHubリポジトリにIssueを作成して報告

---

**更新日**: 2025-12-28
**バージョン**: v4.1
