"""
チャットワークフローサービス

design.md で定義されたフローを実装:
1. ユーザーの入力内容から、属性マスタに登録された１つ１つが応答に必要かLLMに判定
2. 応答に必要と判定された属性を抽出
3. チャット履歴 ＋ ユーザーの入力 + 抽出された属性データ を元に応答文を生成
4. 画面にチャットの応答を表示
5. 応答の表示が完了したら、ユーザーの入力から属性を抽出・登録
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Callable, Generator

from .models import AttributeMaster, AttributeRecord, ChatMessage, LLMTaskStatus
from .database import Database
from .llm_client import LLMClient


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
        status_callback: Optional[Callable[[LLMTaskStatus], None]] = None
    ):
        self.llm = llm_client
        self.db = database
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

        # チャット履歴にユーザー入力を追加
        self.chat_history.append(ChatMessage(role="user", content=user_input))

        # === Step 1 & 2: 属性の判定と抽出 ===
        masters = self.db.get_all_attribute_masters()
        required_attributes: dict[str, str] = {}

        for master in masters:
            # Step 1: 判定
            status = LLMTaskStatus(
                task_type="judgment",
                attribute_name=master.attribute_name,
                status="processing"
            )
            task_statuses.append(status)
            self._emit_status(status)

            is_required = self.llm.judge(master.judgment_prompt, user_input, master.attribute_name)

            status.status = "completed"
            self._emit_status(status)

            if is_required:
                # Step 2: 属性データの取得
                status = LLMTaskStatus(
                    task_type="extraction",
                    attribute_name=master.attribute_name,
                    status="processing"
                )
                task_statuses.append(status)
                self._emit_status(status)

                # データベースから既存の属性を取得
                content = self.db.get_latest_attribute_content(master.attribute_id)
                if content:
                    required_attributes[master.attribute_name] = content

                status.status = "completed"
                self._emit_status(status)

        # === Step 3: 応答文の生成 ===
        status = LLMTaskStatus(
            task_type="response",
            status="processing"
        )
        task_statuses.append(status)
        self._emit_status(status)

        history_for_llm = [
            {"role": msg.role, "content": msg.content}
            for msg in self.chat_history[:-1]  # 現在の入力を除く
        ]

        response_text = self.llm.generate_response(
            chat_history=history_for_llm,
            user_input=user_input,
            attributes=required_attributes
        )

        status.status = "completed"
        self._emit_status(status)

        # チャット履歴にアシスタント応答を追加
        self.chat_history.append(ChatMessage(role="assistant", content=response_text))

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

            extracted = self.llm.extract(master.extraction_prompt, user_input, master.attribute_name)

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

        # チャット履歴にユーザー入力を追加
        self.chat_history.append(ChatMessage(role="user", content=user_input))

        # === Step 1 & 2: 属性の判定と抽出 ===
        masters = self.db.get_all_attribute_masters()
        required_attributes: dict[str, str] = {}

        for master in masters:
            # Step 1: 判定
            status = LLMTaskStatus(
                task_type="judgment",
                attribute_name=master.attribute_name,
                status="processing"
            )
            task_statuses.append(status)
            yield status

            is_required = self.llm.judge(master.judgment_prompt, user_input, master.attribute_name)

            status.status = "completed"
            yield status

            if is_required:
                # Step 2: 属性データの取得
                status = LLMTaskStatus(
                    task_type="extraction",
                    attribute_name=master.attribute_name,
                    status="processing"
                )
                task_statuses.append(status)
                yield status

                content = self.db.get_latest_attribute_content(master.attribute_id)
                if content:
                    required_attributes[master.attribute_name] = content

                status.status = "completed"
                yield status

        # === Step 3: 応答文の生成 ===
        status = LLMTaskStatus(
            task_type="response",
            status="processing"
        )
        task_statuses.append(status)
        yield status

        history_for_llm = [
            {"role": msg.role, "content": msg.content}
            for msg in self.chat_history[:-1]
        ]

        response_text = self.llm.generate_response(
            chat_history=history_for_llm,
            user_input=user_input,
            attributes=required_attributes
        )

        status.status = "completed"
        yield status

        self.chat_history.append(ChatMessage(role="assistant", content=response_text))

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

            extracted = self.llm.extract(master.extraction_prompt, user_input, master.attribute_name)

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
            attribute_name="プロフィール",
            extraction_prompt="文章の中にユーザーのプロフィール（名前、職業、役職、専門分野など）が含まれている場合、抽出してください。例: 私はエンジニアです → エンジニア",
            judgment_prompt="この質問に適切に答えるために、ユーザーのプロフィール情報が必要ですか"
        ),
        AttributeMaster(
            attribute_id=0,
            attribute_name="趣味・興味",
            extraction_prompt="文章の中にユーザーの趣味や興味関心が含まれている場合、抽出してください。例: 週末はよく登山をしています → 登山",
            judgment_prompt="この質問に適切に答えるために、ユーザーの趣味や興味に関する情報が必要ですか"
        ),
        AttributeMaster(
            attribute_id=0,
            attribute_name="スケジュール",
            extraction_prompt="文章の中に予定やスケジュールに関する情報が含まれている場合、抽出してください。例: 来週の月曜日に会議があります → 来週月曜日: 会議",
            judgment_prompt="この質問に適切に答えるために、ユーザーのスケジュール情報が必要ですか"
        ),
        AttributeMaster(
            attribute_id=0,
            attribute_name="連絡先",
            extraction_prompt="文章の中に連絡先情報（メールアドレス、電話番号など）が含まれている場合、抽出してください。",
            judgment_prompt="この質問に適切に答えるために、ユーザーの連絡先情報が必要ですか"
        ),
        AttributeMaster(
            attribute_id=0,
            attribute_name="好み・嗜好",
            extraction_prompt="文章の中にユーザーの好みや嗜好（食べ物、色、スタイルなど）が含まれている場合、抽出してください。例: コーヒーより紅茶派です → 紅茶派",
            judgment_prompt="この質問に適切に答えるために、ユーザーの好みや嗜好に関する情報が必要ですか"
        ),
        AttributeMaster(
            attribute_id=0,
            attribute_name="目標・課題",
            extraction_prompt="文章の中にユーザーの目標や抱えている課題が含まれている場合、抽出してください。例: 来月までにプロジェクトを完成させたい → プロジェクト完成（来月まで）",
            judgment_prompt="この質問に適切に答えるために、ユーザーの目標や課題に関する情報が必要ですか"
        ),
    ]

    for master in default_masters:
        db.insert_attribute_master(master)

    return len(default_masters)
