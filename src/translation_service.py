"""
翻訳サービス
LLMを使用して日本語と英語の翻訳を行う
"""
from typing import Optional
from datetime import datetime
from .llm_client import LLMClient


class TranslationService:
    """LLMを使用した翻訳サービス"""

    def __init__(self, llm_client: LLMClient):
        """
        Args:
            llm_client: 翻訳に使用するLLMクライアント
        """
        self.llm_client = llm_client

    def translate_ja_to_en(
        self,
        text: str,
        context_messages: Optional[list[dict]] = None
    ) -> str:
        """
        日本語から英語に翻訳

        Args:
            text: 翻訳する日本語テキスト
            context_messages: 直近のメッセージ履歴（翻訳精度向上のため）
                             [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]

        Returns:
            翻訳された英語テキスト
        """
        start_time = datetime.now()
        print(f"[翻訳] 日本語→英語 開始: {start_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")

        context_text = ""
        if context_messages:
            context_text = "\n<Recent Conversation Context>\n"
            for msg in context_messages[-2:]:  # 直近2つのメッセージ
                role = "User" if msg["role"] == "user" else "Assistant"
                context_text += f"{role}: {msg['content']}\n"
            context_text += "</Recent Conversation Context>\n\n"

        prompt = f"""Translate the Japanese text to English. Output only the translation.
{context_text}
<Japanese Text>
{text}
</Japanese Text>"""

        response = self.llm_client.generate(prompt, task_type="translation_ja_to_en")

        end_time = datetime.now()
        duration_ms = (end_time - start_time).total_seconds() * 1000
        print(f"[翻訳] 日本語→英語 完了: {end_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]} (処理時間: {duration_ms:.0f}ms)")

        return response.content.strip()

    def translate_en_to_ja(
        self,
        text: str,
        context_messages: Optional[list[dict]] = None
    ) -> str:
        """
        英語から日本語に翻訳

        Args:
            text: 翻訳する英語テキスト
            context_messages: 直近のメッセージ履歴（翻訳精度向上のため）
                             [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]

        Returns:
            翻訳された日本語テキスト
        """
        start_time = datetime.now()
        print(f"[翻訳] 英語→日本語 開始: {start_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")

        context_text = ""
        if context_messages:
            context_text = "\n<Recent Conversation Context>\n"
            for msg in context_messages[-2:]:  # 直近2つのメッセージ
                role = "User" if msg["role"] == "user" else "Assistant"
                context_text += f"{role}: {msg['content']}\n"
            context_text += "</Recent Conversation Context>\n\n"

        prompt = f"""Translate the English text to Japanese. Output only the translation.
{context_text}
<English Text>
{text}
</English Text>"""

        response = self.llm_client.generate(prompt, task_type="translation_en_to_ja")

        end_time = datetime.now()
        duration_ms = (end_time - start_time).total_seconds() * 1000
        print(f"[翻訳] 英語→日本語 完了: {end_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]} (処理時間: {duration_ms:.0f}ms)")

        return response.content.strip()
