"""
LLMクライアントインターフェースと実装
モック実装とOllama実装を提供
"""
import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Callable
import urllib.request
import urllib.error


@dataclass
class LLMResponse:
    """LLM応答"""
    content: str
    raw_response: Optional[dict] = None


class LLMClient(ABC):
    """LLMクライアントの抽象基底クラス"""

    def __init__(self):
        # ログ記録用コールバック関数 (prompt, response, task_type, attribute_name) -> None
        self.log_callback: Optional[Callable[[str, LLMResponse, str, Optional[str]], None]] = None

    @abstractmethod
    def generate(self, prompt: str, task_type: str = "general", attribute_name: Optional[str] = None) -> LLMResponse:
        """プロンプトからテキストを生成"""
        pass

    def set_log_callback(self, callback: Callable[[str, LLMResponse, str, Optional[str]], None]):
        """ログ記録用コールバック関数を設定"""
        self.log_callback = callback

    def _log_interaction(self, prompt: str, response: LLMResponse, task_type: str, attribute_name: Optional[str] = None):
        """ログを記録（コールバックが設定されている場合）"""
        if self.log_callback:
            self.log_callback(prompt, response, task_type, attribute_name)

    def judge(self, judgment_prompt: str, user_input: str, attribute_name: Optional[str] = None) -> bool:
        """
        判定タスク: ユーザー入力に対して判定プロンプトで評価

        返り値: True = 必要、False = 不要
        """
        prompt = f"""あなたは判定を行うアシスタントです。
以下の質問に「はい」または「いいえ」のみで答えてください。

<判定の質問>
{judgment_prompt}
</判定の質問>

<ユーザーの入力>
{user_input}
</ユーザーの入力>

回答（「はい」または「いいえ」のみ）:"""

        response = self.generate(prompt, task_type="judgment", attribute_name=attribute_name)
        answer = response.content.strip().lower()
        return "はい" in answer or "yes" in answer

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

    def generate_response(
        self,
        chat_history: list[dict],
        user_input: str,
        attributes: dict[str, str]
    ) -> str:
        """
        応答生成タスク: チャット履歴と属性情報を使って応答を生成
        """
        history_text = ""
        for msg in chat_history[-5:]:  # 直近5件
            role = "ユーザー" if msg["role"] == "user" else "アシスタント"
            history_text += f"{role}: {msg['content']}\n"

        attributes_text = ""
        if attributes:
            attributes_text = "\n<ユーザーの属性情報>\n"
            for name, value in attributes.items():
                attributes_text += f"- {name}: {value}\n"
            attributes_text += "</ユーザーの属性情報>\n"

        prompt = f"""あなたは親切なアシスタントです。
ユーザーの属性情報を考慮して、適切な応答を生成してください。
{attributes_text}
<会話履歴>
{history_text}
</会話履歴>

<ユーザーの入力>
{user_input}
</ユーザーの入力>

応答:"""

        response = self.generate(prompt, task_type="response")
        return response.content.strip()


class MockLLMClient(LLMClient):
    """
    テスト用モックLLMクライアント

    事前定義された応答パターンを返す
    """

    def __init__(self):
        super().__init__()
        # 判定応答のパターン
        self.judgment_responses: dict[str, bool] = {}
        # 抽出応答のパターン
        self.extraction_responses: dict[str, Optional[str]] = {}
        # 生成応答
        self.generate_responses: list[str] = []
        self._generate_index = 0
        # コールバック（テスト用）
        self.on_generate: Optional[Callable[[str], None]] = None
        # 呼び出し履歴
        self.call_history: list[dict] = []

    def set_judgment_response(self, attribute_name: str, response: bool):
        """判定結果を設定"""
        self.judgment_responses[attribute_name] = response

    def set_extraction_response(self, attribute_name: str, response: Optional[str]):
        """抽出結果を設定"""
        self.extraction_responses[attribute_name] = response

    def add_generate_response(self, response: str):
        """生成応答を追加"""
        self.generate_responses.append(response)

    def generate(self, prompt: str, task_type: str = "general", attribute_name: Optional[str] = None) -> LLMResponse:
        """モック生成"""
        self.call_history.append({"type": "generate", "prompt": prompt})

        if self.on_generate:
            self.on_generate(prompt)

        # 判定プロンプトのパターンをチェック
        if "「はい」または「いいえ」" in prompt:
            for attr_name, response in self.judgment_responses.items():
                if attr_name in prompt or self._check_attribute_context(prompt, attr_name):
                    llm_response = LLMResponse(content="はい" if response else "いいえ")
                    self._log_interaction(prompt, llm_response, task_type, attribute_name)
                    return llm_response
            llm_response = LLMResponse(content="いいえ")
            self._log_interaction(prompt, llm_response, task_type, attribute_name)
            return llm_response

        # 抽出プロンプトのパターンをチェック
        if "抽出された内容:" in prompt:
            for attr_name, response in self.extraction_responses.items():
                if attr_name in prompt or self._check_attribute_context(prompt, attr_name):
                    llm_response = LLMResponse(content=response if response else "なし")
                    self._log_interaction(prompt, llm_response, task_type, attribute_name)
                    return llm_response
            llm_response = LLMResponse(content="なし")
            self._log_interaction(prompt, llm_response, task_type, attribute_name)
            return llm_response

        # 応答生成
        if self.generate_responses and self._generate_index < len(self.generate_responses):
            response = self.generate_responses[self._generate_index]
            self._generate_index += 1
            llm_response = LLMResponse(content=response)
            self._log_interaction(prompt, llm_response, task_type, attribute_name)
            return llm_response

        llm_response = LLMResponse(content="モックの応答です。")
        self._log_interaction(prompt, llm_response, task_type, attribute_name)
        return llm_response

    def _check_attribute_context(self, prompt: str, attr_name: str) -> bool:
        """プロンプトに属性のコンテキストが含まれているか確認"""
        # プロフィール判定パターン
        if "プロフィール" in attr_name.lower():
            patterns = ["プロフィール", "職業", "仕事", "年齢", "名前", "住んでいる"]
            return any(p in prompt for p in patterns)
        return False

    def judge(self, judgment_prompt: str, user_input: str, attribute_name: Optional[str] = None) -> bool:
        """モック判定"""
        self.call_history.append({
            "type": "judge",
            "judgment_prompt": judgment_prompt,
            "user_input": user_input
        })

        # 判定プロンプトに含まれるキーワードで応答を決定
        for attr_name, response in self.judgment_responses.items():
            if attr_name in judgment_prompt:
                return response

        # デフォルトの判定ロジック
        return super().judge(judgment_prompt, user_input, attribute_name)

    def extract(self, extraction_prompt: str, user_input: str, attribute_name: Optional[str] = None) -> Optional[str]:
        """モック抽出"""
        self.call_history.append({
            "type": "extract",
            "extraction_prompt": extraction_prompt,
            "user_input": user_input
        })

        # 抽出プロンプトに含まれるキーワードで応答を決定
        for attr_name, response in self.extraction_responses.items():
            if attr_name in extraction_prompt:
                return response

        # デフォルトの抽出ロジック
        return super().extract(extraction_prompt, user_input, attribute_name)

    def reset(self):
        """状態をリセット"""
        self.judgment_responses.clear()
        self.extraction_responses.clear()
        self.generate_responses.clear()
        self._generate_index = 0
        self.call_history.clear()


class OllamaClient(LLMClient):
    """Ollama API クライアント"""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3.1:8b"
    ):
        super().__init__()
        self.base_url = base_url.rstrip("/")
        self.model = model

    def generate(self, prompt: str, task_type: str = "general", attribute_name: Optional[str] = None) -> LLMResponse:
        """Ollama APIを呼び出してテキストを生成"""
        url = f"{self.base_url}/api/generate"

        data = json.dumps({
            "model": self.model,
            "prompt": prompt,
            "stream": False
        }).encode("utf-8")

        request = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                result = json.loads(response.read().decode("utf-8"))
                llm_response = LLMResponse(
                    content=result.get("response", ""),
                    raw_response=result
                )
                # ログを記録
                self._log_interaction(prompt, llm_response, task_type, attribute_name)
                return llm_response
        except urllib.error.URLError as e:
            raise ConnectionError(f"Ollama API接続エラー: {e}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Ollama API応答パースエラー: {e}")
