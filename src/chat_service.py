"""
チャットワークフローサービス

design.md で定義されたフローを実装:
1. ユーザーの入力内容から、属性マスタに登録された１つ１つが応答に必要かLLMに判定
2. 応答に必要と判定された属性を抽出
3. チャット履歴 ＋ ユーザーの入力 + 抽出された属性データ を元に応答文を生成
4. 画面にチャットの応答を表示
5. 応答の表示が完了したら、ユーザーの入力から属性を抽出・登録

翻訳パイプライン:
- ユーザー入力（日本語）→ 英語に翻訳 → LLM処理 → 応答を日本語に翻訳 → 出力
- 翻訳時には直近2つのメッセージをコンテキストとして使用
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Callable, Generator

from .models import AttributeMaster, AttributeRecord, ChatMessage, LLMTaskStatus
from .database import Database
from .llm_client import LLMClient
from .translation_service import TranslationService


@dataclass
class ChatResponse:
    """チャット応答の結果"""
    response_text: str
    used_attributes: dict[str, str]
    extracted_attributes: list[tuple[str, str]]  # (属性名, 抽出内容)
    task_statuses: list[LLMTaskStatus]


class ChatService:
    """チャットワークフローを管理するサービス"""

    def __init__(
        self,
        llm_client: LLMClient,
        database: Database,
        translation_service: Optional[TranslationService] = None,
        status_callback: Optional[Callable[[LLMTaskStatus], None]] = None
    ):
        self.llm = llm_client
        self.db = database
        self.translation_service = translation_service
        self.status_callback = status_callback
        self.chat_history: list[ChatMessage] = []

    def _emit_status(self, status: LLMTaskStatus):
        """ステータスを通知"""
        if self.status_callback:
            self.status_callback(status)

    def process_user_input(self, user_input: str) -> ChatResponse:
        """
        ユーザー入力を処理して応答を生成

        Returns:
            ChatResponse: 応答テキストと処理情報
        """
        task_statuses: list[LLMTaskStatus] = []

        # 翻訳パイプライン: ユーザー入力を英語に翻訳
        user_input_en = user_input
        if self.translation_service:
            status = LLMTaskStatus(
                task_type="translation_input",
                status="processing"
            )
            task_statuses.append(status)
            self._emit_status(status)

            # 日本語→英語翻訳時：直近2件の英語メッセージをコンテキストとして使用
            context_messages_en = [
                {"role": msg.role, "content": msg.content_en}
                for msg in self.chat_history[-2:]
                if msg.content_en is not None
            ] if len(self.chat_history) > 0 else None

            user_input_en = self.translation_service.translate_ja_to_en(
                user_input,
                context_messages_en if context_messages_en else None
            )

            status.status = "completed"
            self._emit_status(status)

        # チャット履歴にユーザー入力を追加（日本語と英語の両方を保存）
        self.chat_history.append(ChatMessage(role="user", content=user_input, content_en=user_input_en))

        # === Step 1 & 2: 属性の判定と抽出 ===
        masters = self.db.get_all_attribute_masters()
        required_attributes: dict[str, str] = {}

        for master in masters:
            # Step 1: 判定（英語の入力を使用）
            status = LLMTaskStatus(
                task_type="judgment",
                attribute_name=master.attribute_name,
                status="processing"
            )
            task_statuses.append(status)
            self._emit_status(status)

            is_required = self.llm.judge(master.judgment_prompt, user_input_en, master.attribute_name)

            status.status = "completed"
            self._emit_status(status)

            if is_required:
                # Step 2: 属性データの取得（瞬時に完了するのでステータス表示なし）
                content = self.db.get_latest_attribute_content(master.attribute_id)
                if content:
                    required_attributes[master.attribute_name] = content

        # === Step 3: 応答文の生成 ===
        status = LLMTaskStatus(
            task_type="response",
            status="processing"
        )
        task_statuses.append(status)
        self._emit_status(status)

        # チャット履歴を構築（現在のユーザー入力は除外し、それ以前の直近5件を使用）
        if self.translation_service:
            history_for_llm = [
                {"role": msg.role, "content": msg.content_en if msg.content_en else msg.content}
                for msg in self.chat_history[:-1][-5:]  # 現在の入力を除く直近5件
            ]
        else:
            history_for_llm = [
                {"role": msg.role, "content": msg.content}
                for msg in self.chat_history[:-1][-5:]  # 現在の入力を除く直近5件
            ]

        response_text_en = self.llm.generate_response(
            chat_history=history_for_llm,
            user_input=user_input_en,
            attributes=required_attributes
        )

        status.status = "completed"
        self._emit_status(status)

        # 応答を日本語に翻訳
        if self.translation_service:
            status = LLMTaskStatus(
                task_type="translation_response",
                status="processing"
            )
            task_statuses.append(status)
            self._emit_status(status)

            # 英語→日本語翻訳時：直近2件の日本語メッセージをコンテキストとして使用
            context_messages_ja = [
                {"role": msg.role, "content": msg.content}
                for msg in self.chat_history[-2:]
            ] if len(self.chat_history) > 0 else None

            response_text = self.translation_service.translate_en_to_ja(
                response_text_en,
                context_messages_ja if context_messages_ja else None
            )

            status.status = "completed"
            self._emit_status(status)
        else:
            response_text = response_text_en

        # チャット履歴にアシスタント応答を追加（日本語と英語の両方を保存）
        self.chat_history.append(ChatMessage(role="assistant", content=response_text, content_en=response_text_en))

        # === Step 4: 応答を返す（表示は呼び出し側で行う） ===

        # === Step 5: ユーザー入力から属性を抽出・登録 ===
        extracted_attributes: list[tuple[str, str]] = []

        for master in masters:
            status = LLMTaskStatus(
                task_type="attribute_extraction",
                attribute_name=master.attribute_name,
                status="processing"
            )
            task_statuses.append(status)
            self._emit_status(status)

            # 英語の入力を使用して属性を抽出
            extracted = self.llm.extract(master.extraction_prompt, user_input_en, master.attribute_name)

            if extracted:
                # 属性レコードを登録
                record = AttributeRecord(
                    sequence_no=None,
                    attribute_id=master.attribute_id,
                    content=extracted
                )
                self.db.insert_attribute_record(record)
                extracted_attributes.append((master.attribute_name, extracted))

            status.status = "completed"
            self._emit_status(status)

        return ChatResponse(
            response_text=response_text,
            used_attributes=required_attributes,
            extracted_attributes=extracted_attributes,
            task_statuses=task_statuses
        )

    def process_user_input_streaming(
        self, user_input: str
    ) -> Generator[LLMTaskStatus, None, ChatResponse]:
        """
        ストリーミング形式でユーザー入力を処理

        ステータスをyieldしながら処理を進める

        Yields:
            LLMTaskStatus: 各タスクのステータス

        Returns:
            ChatResponse: 最終的な応答
        """
        task_statuses: list[LLMTaskStatus] = []

        # 翻訳パイプライン: ユーザー入力を英語に翻訳
        user_input_en = user_input
        if self.translation_service:
            status = LLMTaskStatus(
                task_type="translation_input",
                status="processing"
            )
            task_statuses.append(status)
            yield status

            # 日本語→英語翻訳時：直近2件の英語メッセージをコンテキストとして使用
            context_messages_en = [
                {"role": msg.role, "content": msg.content_en}
                for msg in self.chat_history[-2:]
                if msg.content_en is not None
            ] if len(self.chat_history) > 0 else None

            user_input_en = self.translation_service.translate_ja_to_en(
                user_input,
                context_messages_en if context_messages_en else None
            )

            status.status = "completed"
            yield status

        # チャット履歴にユーザー入力を追加（日本語と英語の両方を保存）
        self.chat_history.append(ChatMessage(role="user", content=user_input, content_en=user_input_en))

        # === Step 1 & 2: 属性の判定と抽出 ===
        masters = self.db.get_all_attribute_masters()
        required_attributes: dict[str, str] = {}

        for master in masters:
            # Step 1: 判定（英語の入力を使用）
            status = LLMTaskStatus(
                task_type="judgment",
                attribute_name=master.attribute_name,
                status="processing"
            )
            task_statuses.append(status)
            yield status

            is_required = self.llm.judge(master.judgment_prompt, user_input_en, master.attribute_name)

            status.status = "completed"
            yield status

            if is_required:
                # Step 2: 属性データの取得（瞬時に完了するのでステータス表示なし）
                content = self.db.get_latest_attribute_content(master.attribute_id)
                if content:
                    required_attributes[master.attribute_name] = content

        # === Step 3: 応答文の生成 ===
        status = LLMTaskStatus(
            task_type="response",
            status="processing"
        )
        task_statuses.append(status)
        yield status

        # チャット履歴を構築（現在のユーザー入力は除外し、それ以前の直近5件を使用）
        if self.translation_service:
            history_for_llm = [
                {"role": msg.role, "content": msg.content_en if msg.content_en else msg.content}
                for msg in self.chat_history[:-1][-5:]  # 現在の入力を除く直近5件
            ]
        else:
            history_for_llm = [
                {"role": msg.role, "content": msg.content}
                for msg in self.chat_history[:-1][-5:]  # 現在の入力を除く直近5件
            ]

        response_text_en = self.llm.generate_response(
            chat_history=history_for_llm,
            user_input=user_input_en,
            attributes=required_attributes
        )

        status.status = "completed"
        yield status

        # 応答を日本語に翻訳
        if self.translation_service:
            status = LLMTaskStatus(
                task_type="translation_response",
                status="processing"
            )
            task_statuses.append(status)
            yield status

            # 英語→日本語翻訳時：直近2件の日本語メッセージをコンテキストとして使用
            context_messages_ja = [
                {"role": msg.role, "content": msg.content}
                for msg in self.chat_history[-2:]
            ] if len(self.chat_history) > 0 else None

            response_text = self.translation_service.translate_en_to_ja(
                response_text_en,
                context_messages_ja if context_messages_ja else None
            )

            status.status = "completed"
            yield status
        else:
            response_text = response_text_en

        # チャット履歴にアシスタント応答を追加（日本語と英語の両方を保存）
        self.chat_history.append(ChatMessage(role="assistant", content=response_text, content_en=response_text_en))

        # 応答準備完了を通知（即座に応答を表示するため）
        response_ready_status = LLMTaskStatus(
            task_type="response_ready",
            status="completed",
            response_text=response_text,
            used_attributes=required_attributes
        )
        task_statuses.append(response_ready_status)
        yield response_ready_status

        # === Step 5: 属性抽出・登録 ===
        extracted_attributes: list[tuple[str, str]] = []

        for master in masters:
            status = LLMTaskStatus(
                task_type="attribute_extraction",
                attribute_name=master.attribute_name,
                status="processing"
            )
            task_statuses.append(status)
            yield status

            # 英語の入力を使用して属性を抽出
            extracted = self.llm.extract(master.extraction_prompt, user_input_en, master.attribute_name)

            if extracted:
                record = AttributeRecord(
                    sequence_no=None,
                    attribute_id=master.attribute_id,
                    content=extracted
                )
                self.db.insert_attribute_record(record)
                extracted_attributes.append((master.attribute_name, extracted))

            status.status = "completed"
            yield status

        return ChatResponse(
            response_text=response_text,
            used_attributes=required_attributes,
            extracted_attributes=extracted_attributes,
            task_statuses=task_statuses
        )

    def clear_history(self):
        """チャット履歴をクリア"""
        self.chat_history.clear()

    def get_chat_history(self) -> list[ChatMessage]:
        """チャット履歴を取得"""
        return self.chat_history.copy()


def create_default_attribute_masters(db: Database):
    """
    デフォルトの属性マスタを作成

    design.md の要望:
    「優秀なアシスタントや秘書が、サポート対象者の情報を分類して記録する仕事を参考に、必要な属性を作成」
    """
    default_masters = [
        AttributeMaster(
            attribute_id=0,
            attribute_name="User Profile",
            extraction_prompt="Extract user profile information from the text, including occupation, position, and personal details. Example: I am an engineer → engineer",
            judgment_prompt="Does answering the following text require information about the user's profile, occupation, or personal details? Answer with 'yes' or 'no'."
        ),
        AttributeMaster(
            attribute_id=0,
            attribute_name="Current Tasks & Projects",
            extraction_prompt="Extract information about current tasks, projects, schedules, or goals from the text. Example: Meeting next Monday → Next Monday: Meeting",
            judgment_prompt="Does answering the following text require information about the user's current tasks, projects, or schedules? Answer with 'yes' or 'no'."
        ),
        AttributeMaster(
            attribute_id=0,
            attribute_name="Expertise & Skills",
            extraction_prompt="Extract information about user's expertise, skills, or areas of interest from the text. Example: I often go hiking on weekends → hiking",
            judgment_prompt="Does answering the following text require information about the user's expertise, skills, or interests? Answer with 'yes' or 'no'."
        ),
        AttributeMaster(
            attribute_id=0,
            attribute_name="Past Decisions & Policies",
            extraction_prompt="Extract information about user's past decisions, preferences, or policies from the text. Example: I prefer tea over coffee → prefers tea",
            judgment_prompt="Does answering the following text require information about the user's past decisions, preferences, or policies? Answer with 'yes' or 'no'."
        ),
    ]

    for master in default_masters:
        db.insert_attribute_master(master)

    return len(default_masters)
