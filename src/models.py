"""
データベースモデル定義
属性マスタと属性テーブルを管理
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class AttributeMaster:
    """属性マスタ

    属性の定義とLLMプロンプトを管理する
    """
    attribute_id: int
    attribute_name: str
    extraction_prompt: str  # 抽出プロンプト
    judgment_prompt: str    # 判定プロンプト

    def __post_init__(self):
        if not self.attribute_name:
            raise ValueError("属性名は必須です")
        if not self.extraction_prompt:
            raise ValueError("抽出プロンプトは必須です")
        if not self.judgment_prompt:
            raise ValueError("判定プロンプトは必須です")


@dataclass
class AttributeRecord:
    """属性テーブル

    ユーザーから抽出した属性データを格納
    """
    sequence_no: Optional[int]
    attribute_id: int
    content: str
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        if not self.content:
            raise ValueError("内容は必須です")


@dataclass
class ChatMessage:
    """チャットメッセージ

    日本語と英語の両方のコンテンツを保持
    """
    role: str  # "user" or "assistant"
    content: str  # 日本語コンテンツ
    content_en: Optional[str] = None  # 英語コンテンツ
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class LLMTaskStatus:
    """LLMタスクのステータス"""
    task_type: str  # "judgment", "extraction", "response", "attribute_extraction"
    attribute_name: Optional[str] = None
    status: str = "processing"  # "processing", "completed", "failed"

    @property
    def display_text(self) -> str:
        """ステータス表示用テキスト"""
        task_descriptions = {
            "judgment": f"属性「{self.attribute_name}」が応答に必要か判定中",
            "extraction": f"属性「{self.attribute_name}」のデータを抽出中",
            "response": "応答文を生成中",
            "attribute_extraction": f"ユーザー入力から「{self.attribute_name}」を抽出中",
        }
        return task_descriptions.get(self.task_type, "処理中")


@dataclass
class LLMLog:
    """LLMリクエスト/レスポンスログ"""
    log_id: Optional[int]
    timestamp: datetime
    model: str
    task_type: str  # "judgment", "extraction", "response", "attribute_extraction"
    prompt: str  # LLMに送信した完全なプロンプト
    response: str  # LLMからの応答テキスト
    raw_response: Optional[str] = None  # JSON形式のraw response
    attribute_name: Optional[str] = None  # タスクに関連する属性名
    metadata: Optional[str] = None  # 追加のメタデータ（JSON形式）

    def __post_init__(self):
        if not self.prompt:
            raise ValueError("プロンプトは必須です")
        if not self.response:
            raise ValueError("レスポンスは必須です")
