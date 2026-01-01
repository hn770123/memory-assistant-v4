# チャット翻訳レイテンシー調査レポート

**調査日**: 2026-01-01
**対象ブランチ**: claude/debug-translation-latency-EaqOq

## 概要

チャットの入力から英語への翻訳が完了するまで想定より時間がかかる問題について調査を実施しました。

## 処理フロー分析

### 現在の処理フロー

ユーザーが日本語でメッセージを入力してから応答が表示されるまで、以下の処理が逐次実行されます:

```
[ユーザー入力(日本語)]
    ↓
1. 翻訳(入力): 日本語 → 英語 ...................... 1-2秒
    ↓
2. 属性判定 x 4件 (逐次処理) ..................... 1.2-2秒
    ├─ User Profile判定
    ├─ Current Tasks & Projects判定
    ├─ Expertise & Skills判定
    └─ Past Decisions & Policies判定
    ↓
3. 応答生成(英語) ................................ 2-5秒
    ↓
4. 翻訳(応答): 英語 → 日本語 ..................... 2-5秒
    ↓
[応答表示(日本語)]
    ↓
5. 属性抽出 x 4件 (応答表示後、バックグラウンド)
```

**合計予想時間: 6-14秒**

### コード上の実装箇所

#### 翻訳処理
- **ファイル**: `src/translation_service.py`
- **関数**: `translate_ja_to_en()` (19-50行), `translate_en_to_ja()` (52-83行)
- **処理**: 直近2件のメッセージをコンテキストとして含むプロンプトでLLMに翻訳を依頼

#### 属性判定の逐次処理
- **ファイル**: `src/chat_service.py`
- **行番号**: 259-272
- **問題**: `for master in masters:` で4つの属性マスタに対して順番に判定処理を実行
```python
for master in masters:
    # Step 1: 判定（英語の入力を使用）
    status = LLMTaskStatus(...)
    yield status

    is_required = self.llm.judge(master.judgment_prompt, user_input_en, master.attribute_name)
    # ↑ここで前の判定の完了を待つ

    status.status = "completed"
    yield status
```

## パフォーマンスボトルネック

### 1. 逐次的な属性判定処理（最大の問題）

**現状**: 4つの属性判定が順番に実行される
**影響**: 各判定に0.3-0.5秒かかり、合計1.2-2秒の遅延

**該当コード**: `src/chat_service.py:259-272`, `src/chat_service.py:350-372`

**改善案**: ThreadPoolExecutorやasyncioを使った並列処理
- 並列化により1.2-2秒 → 0.3-0.5秒に短縮可能（約1.5秒の改善）

### 2. 翻訳オーバーヘッド

**現状**: 入力と応答の2回の翻訳で合計3-7秒の追加処理時間

**改善案**:
- 翻訳キャッシュの実装（同じ入力の再翻訳を回避）
- より高速なモデルの使用（llama3.2:1bなど軽量モデル）
- 翻訳の選択的スキップ（英語入力を自動検出）

### 3. LLM処理時間

**現状**: 各LLMリクエストで以下の時間が発生

| タスク | プロンプトトークン | 生成トークン | 推定時間 |
|--------|-------------------|-------------|----------|
| 翻訳(入力) | 100-250 | 20-50 | 1-2秒 |
| 属性判定(1件) | 80-150 | 1-5 ("yes"/"no") | 0.3-0.5秒 |
| 応答生成 | 150-400 | 50-200 | 2-5秒 |
| 翻訳(応答) | 150-300 | 50-200 | 2-5秒 |

**モデル性能** (llama3.1:8b):
- プロンプト処理速度: 約500-1000トークン/秒
- テキスト生成速度: 約30-50トークン/秒

## Ollamaへのリクエスト/レスポンス時間計算

### プロンプト内容の詳細

#### 1. 翻訳プロンプト（入力）
```
Translate the Japanese text to English. Output only the translation.

<Recent Conversation Context>
User: [前のメッセージ英語版]
Assistant: [前のメッセージ英語版]
</Recent Conversation Context>

<Japanese Text>
[ユーザー入力]
</Japanese Text>
```
- **トークン数**: 100-250トークン（コンテキスト含む）
- **生成トークン**: 20-50トークン
- **予想時間**: 1-2秒

#### 2. 属性判定プロンプト
```
You are an assistant that makes judgments.
Please answer the following question with only 'yes' or 'no'.

<Judgment Question>
Does answering the following text require information about the user's profile?
</Judgment Question>

<User Input>
[ユーザー入力英語版]
</User Input>

Answer (only 'yes' or 'no'):
```
- **トークン数**: 80-150トークン
- **生成トークン**: 1-5トークン（"yes" または "no"）
- **予想時間**: 0.3-0.5秒/件、合計1.2-2秒（4件）

#### 3. 応答生成プロンプト
```
You are a helpful assistant.
Please generate an appropriate response considering the user's attribute information.

<User Attribute Information>
- User Profile: [値]
- Current Tasks & Projects: [値]
...
</User Attribute Information>

<Conversation History>
User: [履歴]
Assistant: [履歴]
...
</Conversation History>

<User Input>
[ユーザー入力英語版]
</User Input>

Response:
```
- **トークン数**: 150-400トークン（属性情報と履歴含む）
- **生成トークン**: 50-200トークン（応答の長さによる）
- **予想時間**: 2-5秒

#### 4. 翻訳プロンプト（応答）
```
Translate the English text to Japanese. Output only the translation.

<Recent Conversation Context>
User: [前のメッセージ英語版]
Assistant: [前のメッセージ英語版]
</Recent Conversation Context>

<English Text>
[応答英語版]
</English Text>
```
- **トークン数**: 150-300トークン
- **生成トークン**: 50-200トークン
- **予想時間**: 2-5秒

### タイムライン例（標準的なケース）

```
時刻    処理内容                     累積時間
0.0s    ユーザー入力受信             0.0s
0.0s    翻訳(入力)開始               0.0s
1.5s    翻訳(入力)完了               1.5s
1.5s    属性判定#1開始               1.5s
1.9s    属性判定#1完了               1.9s
1.9s    属性判定#2開始               1.9s
2.3s    属性判定#2完了               2.3s
2.3s    属性判定#3開始               2.3s
2.7s    属性判定#3完了               2.7s
2.7s    属性判定#4開始               2.7s
3.1s    属性判定#4完了               3.1s
3.1s    応答生成開始                 3.1s
6.1s    応答生成完了                 6.1s
6.1s    翻訳(応答)開始               6.1s
9.1s    翻訳(応答)完了               9.1s
9.1s    ユーザーに応答表示           9.1s ← ユーザー体感レイテンシー
```

**合計: 約9秒**（標準的なケース）

## 改善提案

### 優先度: 高

**1. 属性判定の並列化**
- **効果**: 1.5秒の短縮
- **実装**: ThreadPoolExecutorまたはasyncioを使用
- **対象**: `src/chat_service.py:259-272`, `350-372`

**2. より高速なモデルの使用**
- **効果**: 全体で30-50%の高速化
- **実装**: `OLLAMA_MODEL=llama3.2:1b` に変更
- **トレードオフ**: 精度の若干の低下

### 優先度: 中

**3. 翻訳キャッシュの実装**
- **効果**: 同じ入力の再翻訳回避
- **実装**: LRUキャッシュの追加

**4. 英語入力の自動検出**
- **効果**: 英語入力時の翻訳スキップ
- **実装**: 言語検出ライブラリの使用

### 優先度: 低

**5. ストリーミング応答の最適化**
- **効果**: UX改善（処理時間は変わらず）
- **実装**: 既に実装されているが、さらなる細分化

**6. 属性判定の賢いスキップ**
- **効果**: 不要な判定の削減
- **実装**: コンテキストベースの事前フィルタリング

## 結論

チャット入力から応答表示までに**6-14秒（標準9秒）**かかる主な原因は:

1. **属性判定の逐次処理** (1.2-2秒)
2. **2回の翻訳処理** (3-7秒)
3. **応答生成の時間** (2-5秒)

最も効果的な改善策は**属性判定の並列化**（約1.5秒短縮）と**より高速なモデルの使用**（全体で30-50%高速化）です。

両方を実装することで、**9秒 → 4-5秒**程度に短縮できる見込みです。
