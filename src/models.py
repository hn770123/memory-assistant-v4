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
    """チャットメッセージ"""
    role: str  # "user" or "assistant"
    content: str
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
