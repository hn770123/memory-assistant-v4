"""
SQLiteデータベース操作
属性マスタと属性テーブルのCRUD操作
"""
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import AttributeMaster, AttributeRecord


class Database:
    """SQLiteデータベース管理クラス"""

    def __init__(self, db_path: str = "memory_assistant.db"):
        self.db_path = db_path
        self._local = threading.local()

    def connect(self) -> sqlite3.Connection:
        """データベース接続を取得（スレッドローカル）"""
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            self._local.connection = sqlite3.connect(
                self.db_path,
                check_same_thread=False  # マルチスレッド環境での警告を抑制
            )
            self._local.connection.row_factory = sqlite3.Row
        return self._local.connection

    def close(self):
        """接続をクローズ"""
        if hasattr(self._local, 'connection') and self._local.connection:
            self._local.connection.close()
            self._local.connection = None

    def initialize(self):
        """テーブルを作成"""
        conn = self.connect()
        cursor = conn.cursor()

        # 属性マスタテーブル
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS attribute_master (
                attribute_id INTEGER PRIMARY KEY AUTOINCREMENT,
                attribute_name TEXT NOT NULL,
                extraction_prompt TEXT NOT NULL,
                judgment_prompt TEXT NOT NULL
            )
        """)

        # 属性テーブル
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS attribute_records (
                sequence_no INTEGER PRIMARY KEY AUTOINCREMENT,
                attribute_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (attribute_id) REFERENCES attribute_master(attribute_id)
            )
        """)

        conn.commit()

    # === 属性マスタ操作 ===

    def insert_attribute_master(self, master: AttributeMaster) -> int:
        """属性マスタを登録"""
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO attribute_master (attribute_name, extraction_prompt, judgment_prompt)
            VALUES (?, ?, ?)
            """,
            (master.attribute_name, master.extraction_prompt, master.judgment_prompt)
        )
        conn.commit()
        return cursor.lastrowid

    def get_attribute_master(self, attribute_id: int) -> Optional[AttributeMaster]:
        """属性マスタを取得"""
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM attribute_master WHERE attribute_id = ?",
            (attribute_id,)
        )
        row = cursor.fetchone()
        if row:
            return AttributeMaster(
                attribute_id=row["attribute_id"],
                attribute_name=row["attribute_name"],
                extraction_prompt=row["extraction_prompt"],
                judgment_prompt=row["judgment_prompt"]
            )
        return None

    def get_all_attribute_masters(self) -> list[AttributeMaster]:
        """全属性マスタを取得"""
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM attribute_master ORDER BY attribute_id")
        rows = cursor.fetchall()
        return [
            AttributeMaster(
                attribute_id=row["attribute_id"],
                attribute_name=row["attribute_name"],
                extraction_prompt=row["extraction_prompt"],
                judgment_prompt=row["judgment_prompt"]
            )
            for row in rows
        ]

    def update_attribute_master(self, master: AttributeMaster) -> bool:
        """属性マスタを更新"""
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE attribute_master
            SET attribute_name = ?, extraction_prompt = ?, judgment_prompt = ?
            WHERE attribute_id = ?
            """,
            (
                master.attribute_name,
                master.extraction_prompt,
                master.judgment_prompt,
                master.attribute_id
            )
        )
        conn.commit()
        return cursor.rowcount > 0

    def delete_attribute_master(self, attribute_id: int) -> bool:
        """属性マスタを削除"""
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM attribute_master WHERE attribute_id = ?",
            (attribute_id,)
        )
        conn.commit()
        return cursor.rowcount > 0

    # === 属性レコード操作 ===

    def insert_attribute_record(self, record: AttributeRecord) -> int:
        """属性レコードを登録"""
        conn = self.connect()
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        cursor.execute(
            """
            INSERT INTO attribute_records (attribute_id, content, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (record.attribute_id, record.content, now, now)
        )
        conn.commit()
        return cursor.lastrowid

    def get_attribute_records_by_attribute_id(
        self, attribute_id: int
    ) -> list[AttributeRecord]:
        """属性IDで属性レコードを取得"""
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM attribute_records
            WHERE attribute_id = ?
            ORDER BY sequence_no DESC
            """,
            (attribute_id,)
        )
        rows = cursor.fetchall()
        return [
            AttributeRecord(
                sequence_no=row["sequence_no"],
                attribute_id=row["attribute_id"],
                content=row["content"],
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"])
            )
            for row in rows
        ]

    def get_all_attribute_records(self) -> list[AttributeRecord]:
        """全属性レコードを取得"""
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM attribute_records ORDER BY sequence_no DESC"
        )
        rows = cursor.fetchall()
        return [
            AttributeRecord(
                sequence_no=row["sequence_no"],
                attribute_id=row["attribute_id"],
                content=row["content"],
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"])
            )
            for row in rows
        ]

    def update_attribute_record(self, record: AttributeRecord) -> bool:
        """属性レコードを更新"""
        conn = self.connect()
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        cursor.execute(
            """
            UPDATE attribute_records
            SET content = ?, updated_at = ?
            WHERE sequence_no = ?
            """,
            (record.content, now, record.sequence_no)
        )
        conn.commit()
        return cursor.rowcount > 0

    def delete_attribute_record(self, sequence_no: int) -> bool:
        """属性レコードを削除"""
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM attribute_records WHERE sequence_no = ?",
            (sequence_no,)
        )
        conn.commit()
        return cursor.rowcount > 0

    def get_latest_attribute_content(self, attribute_id: int) -> Optional[str]:
        """最新の属性内容を取得"""
        records = self.get_attribute_records_by_attribute_id(attribute_id)
        if records:
            return records[0].content
        return None
