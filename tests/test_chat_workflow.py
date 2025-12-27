"""
チャットワークフローの一連のタスクを確認するテスト

design.md に記載された以下のフローをテスト:
1. ユーザーの入力内容から、属性マスタに登録された１つ１つが応答に必要かLLMに判定
2. 応答に必要と判定された属性を抽出
3. チャット履歴 ＋ ユーザーの入力 + 抽出された属性データ を元に応答文を生成
4. 画面にチャットの応答を表示
5. 応答の表示が完了したら、ユーザーの入力から属性を抽出・登録
"""
import os
import sys
import tempfile
import unittest
from datetime import datetime

# srcディレクトリをパスに追加
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.models import AttributeMaster, AttributeRecord, LLMTaskStatus
from src.database import Database
from src.llm_client import MockLLMClient
from src.chat_service import ChatService, create_default_attribute_masters


class TestDatabaseOperations(unittest.TestCase):
    """データベース操作のテスト"""

    def setUp(self):
        """テスト用の一時データベースを作成"""
        self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.temp_file.close()
        self.db = Database(self.temp_file.name)
        self.db.initialize()

    def tearDown(self):
        """一時データベースを削除"""
        self.db.close()
        os.unlink(self.temp_file.name)

    def test_attribute_master_crud(self):
        """属性マスタのCRUD操作"""
        # Create
        master = AttributeMaster(
            attribute_id=0,
            attribute_name="テスト属性",
            extraction_prompt="テスト用抽出プロンプト",
            judgment_prompt="テスト用判定プロンプト"
        )
        master_id = self.db.insert_attribute_master(master)
        self.assertIsNotNone(master_id)

        # Read
        retrieved = self.db.get_attribute_master(master_id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.attribute_name, "テスト属性")

        # Update
        retrieved.attribute_name = "更新された属性"
        self.db.update_attribute_master(retrieved)
        updated = self.db.get_attribute_master(master_id)
        self.assertEqual(updated.attribute_name, "更新された属性")

        # Delete
        self.db.delete_attribute_master(master_id)
        deleted = self.db.get_attribute_master(master_id)
        self.assertIsNone(deleted)

    def test_attribute_record_crud(self):
        """属性レコードのCRUD操作"""
        # 先に属性マスタを作成
        master = AttributeMaster(
            attribute_id=0,
            attribute_name="プロフィール",
            extraction_prompt="プロフィールを抽出",
            judgment_prompt="プロフィールが必要か"
        )
        master_id = self.db.insert_attribute_master(master)

        # Create
        record = AttributeRecord(
            sequence_no=None,
            attribute_id=master_id,
            content="エンジニア"
        )
        seq_no = self.db.insert_attribute_record(record)
        self.assertIsNotNone(seq_no)

        # Read
        records = self.db.get_attribute_records_by_attribute_id(master_id)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].content, "エンジニア")

        # Update
        records[0].content = "シニアエンジニア"
        self.db.update_attribute_record(records[0])
        updated = self.db.get_attribute_records_by_attribute_id(master_id)
        self.assertEqual(updated[0].content, "シニアエンジニア")

        # Delete
        self.db.delete_attribute_record(seq_no)
        deleted = self.db.get_attribute_records_by_attribute_id(master_id)
        self.assertEqual(len(deleted), 0)


class TestMockLLMClient(unittest.TestCase):
    """MockLLMClientのテスト"""

    def setUp(self):
        self.mock = MockLLMClient()

    def test_judgment_responses(self):
        """判定応答のテスト"""
        self.mock.set_judgment_response("プロフィール", True)
        self.mock.set_judgment_response("スケジュール", False)

        # 判定結果を確認
        result1 = self.mock.judge("プロフィールが必要ですか？", "私はエンジニアです")
        result2 = self.mock.judge("スケジュールが必要ですか？", "今日の天気は？")

        self.assertTrue(result1)
        self.assertFalse(result2)

    def test_extraction_responses(self):
        """抽出応答のテスト"""
        self.mock.set_extraction_response("プロフィール", "ソフトウェアエンジニア")
        self.mock.set_extraction_response("趣味", None)

        result1 = self.mock.extract("プロフィールを抽出", "私はソフトウェアエンジニアです")
        result2 = self.mock.extract("趣味を抽出", "今日は暑いですね")

        self.assertEqual(result1, "ソフトウェアエンジニア")
        self.assertIsNone(result2)

    def test_call_history(self):
        """呼び出し履歴のテスト"""
        self.mock.judge("テスト判定", "入力テスト")
        self.mock.extract("テスト抽出", "入力テスト")

        # judge と extract はそれぞれ内部で generate も呼ぶため、4件になる
        # (judge -> generate, extract -> generate)
        self.assertEqual(len(self.mock.call_history), 4)
        self.assertEqual(self.mock.call_history[0]["type"], "judge")
        self.assertEqual(self.mock.call_history[1]["type"], "generate")
        self.assertEqual(self.mock.call_history[2]["type"], "extract")
        self.assertEqual(self.mock.call_history[3]["type"], "generate")


class TestChatWorkflow(unittest.TestCase):
    """チャットワークフローのテスト"""

    def setUp(self):
        """テスト環境をセットアップ"""
        self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.temp_file.close()
        self.db = Database(self.temp_file.name)
        self.db.initialize()

        # 属性マスタを作成
        self.profile_master = AttributeMaster(
            attribute_id=0,
            attribute_name="プロフィール",
            extraction_prompt="文章の中にユーザーのプロフィールが含まれている場合、抽出してください",
            judgment_prompt="次の文章に答えるにはユーザーのプロフィールが必要か答えてください"
        )
        self.profile_id = self.db.insert_attribute_master(self.profile_master)

        self.hobby_master = AttributeMaster(
            attribute_id=0,
            attribute_name="趣味",
            extraction_prompt="文章の中にユーザーの趣味が含まれている場合、抽出してください",
            judgment_prompt="次の文章に答えるにはユーザーの趣味情報が必要か答えてください"
        )
        self.hobby_id = self.db.insert_attribute_master(self.hobby_master)

        # モックLLMクライアントを作成
        self.mock_llm = MockLLMClient()

        # ステータス記録用
        self.status_history: list[LLMTaskStatus] = []

        def on_status(status: LLMTaskStatus):
            self.status_history.append(status)

        # チャットサービスを作成
        self.chat_service = ChatService(
            llm_client=self.mock_llm,
            database=self.db,
            status_callback=on_status
        )

    def tearDown(self):
        self.db.close()
        os.unlink(self.temp_file.name)

    def test_workflow_step1_judgment(self):
        """Step 1: 属性の判定テスト"""
        # プロフィールが必要と判定されるように設定
        self.mock_llm.set_judgment_response("プロフィール", True)
        self.mock_llm.set_judgment_response("趣味", False)
        self.mock_llm.add_generate_response("こんにちは！お手伝いします。")

        result = self.chat_service.process_user_input("私の仕事に関するアドバイスをください")

        # 判定タスクが実行されたことを確認
        judgment_statuses = [
            s for s in self.status_history
            if s.task_type == "judgment"
        ]
        self.assertEqual(len(judgment_statuses), 4)  # 2属性 × 2回（processing, completed）

    def test_workflow_step2_attribute_extraction(self):
        """Step 2: 必要な属性データの取得テスト"""
        # プロフィール属性を先に登録しておく
        record = AttributeRecord(
            sequence_no=None,
            attribute_id=self.profile_id,
            content="ソフトウェアエンジニア"
        )
        self.db.insert_attribute_record(record)

        # プロフィールが必要と判定されるように設定
        self.mock_llm.set_judgment_response("プロフィール", True)
        self.mock_llm.set_judgment_response("趣味", False)
        self.mock_llm.add_generate_response("エンジニアとして働いているのですね。")

        result = self.chat_service.process_user_input("私の仕事に適したスキルは？")

        # 使用された属性を確認
        self.assertIn("プロフィール", result.used_attributes)
        self.assertEqual(result.used_attributes["プロフィール"], "ソフトウェアエンジニア")

    def test_workflow_step3_response_generation(self):
        """Step 3: 応答文の生成テスト"""
        expected_response = "これはテスト応答です。"
        self.mock_llm.add_generate_response(expected_response)
        self.mock_llm.set_judgment_response("プロフィール", False)
        self.mock_llm.set_judgment_response("趣味", False)

        result = self.chat_service.process_user_input("こんにちは")

        # 応答が正しく生成されたことを確認
        self.assertEqual(result.response_text, expected_response)

        # 応答生成タスクが実行されたことを確認
        response_statuses = [
            s for s in self.status_history
            if s.task_type == "response"
        ]
        self.assertEqual(len(response_statuses), 2)  # processing, completed

    def test_workflow_step4_chat_history(self):
        """Step 4: チャット履歴の管理テスト"""
        self.mock_llm.add_generate_response("最初の応答です。")
        self.mock_llm.add_generate_response("二番目の応答です。")
        self.mock_llm.set_judgment_response("プロフィール", False)
        self.mock_llm.set_judgment_response("趣味", False)

        self.chat_service.process_user_input("最初の質問")
        self.chat_service.process_user_input("二番目の質問")

        history = self.chat_service.get_chat_history()

        # 4つのメッセージ（2ユーザー + 2アシスタント）
        self.assertEqual(len(history), 4)
        self.assertEqual(history[0].role, "user")
        self.assertEqual(history[0].content, "最初の質問")
        self.assertEqual(history[1].role, "assistant")
        self.assertEqual(history[2].role, "user")
        self.assertEqual(history[3].role, "assistant")

    def test_workflow_step5_attribute_extraction_and_registration(self):
        """Step 5: ユーザー入力からの属性抽出と登録テスト"""
        self.mock_llm.set_judgment_response("プロフィール", False)
        self.mock_llm.set_judgment_response("趣味", False)
        self.mock_llm.set_extraction_response("プロフィール", "データサイエンティスト")
        self.mock_llm.set_extraction_response("趣味", "プログラミング")
        self.mock_llm.add_generate_response("素晴らしい職業ですね！")

        result = self.chat_service.process_user_input(
            "私はデータサイエンティストで、趣味はプログラミングです"
        )

        # 抽出された属性を確認
        self.assertEqual(len(result.extracted_attributes), 2)

        # データベースに登録されたことを確認
        profile_records = self.db.get_attribute_records_by_attribute_id(self.profile_id)
        hobby_records = self.db.get_attribute_records_by_attribute_id(self.hobby_id)

        self.assertEqual(len(profile_records), 1)
        self.assertEqual(profile_records[0].content, "データサイエンティスト")
        self.assertEqual(len(hobby_records), 1)
        self.assertEqual(hobby_records[0].content, "プログラミング")

    def test_full_workflow_integration(self):
        """完全なワークフローの統合テスト"""
        # 初回: ユーザー情報を登録
        self.mock_llm.set_judgment_response("プロフィール", False)
        self.mock_llm.set_judgment_response("趣味", False)
        self.mock_llm.set_extraction_response("プロフィール", "フロントエンドエンジニア")
        self.mock_llm.set_extraction_response("趣味", None)
        self.mock_llm.add_generate_response("はじめまして！")

        result1 = self.chat_service.process_user_input(
            "こんにちは、私はフロントエンドエンジニアです"
        )

        # プロフィールが登録されたことを確認
        self.assertEqual(len(result1.extracted_attributes), 1)
        self.assertEqual(result1.extracted_attributes[0][0], "プロフィール")

        # 2回目: プロフィールを使って応答
        self.mock_llm.reset()
        self.mock_llm.set_judgment_response("プロフィール", True)
        self.mock_llm.set_judgment_response("趣味", False)
        self.mock_llm.set_extraction_response("プロフィール", None)
        self.mock_llm.set_extraction_response("趣味", None)
        self.mock_llm.add_generate_response("フロントエンドエンジニアとして、React や Vue.js がおすすめです。")

        self.status_history.clear()
        result2 = self.chat_service.process_user_input(
            "おすすめのJavaScriptフレームワークを教えてください"
        )

        # プロフィール情報が使用されたことを確認
        self.assertIn("プロフィール", result2.used_attributes)
        self.assertEqual(result2.used_attributes["プロフィール"], "フロントエンドエンジニア")

        # チャット履歴が正しく維持されていることを確認
        history = self.chat_service.get_chat_history()
        self.assertEqual(len(history), 4)

    def test_status_display_text(self):
        """ステータス表示テキストのテスト"""
        status1 = LLMTaskStatus(
            task_type="judgment",
            attribute_name="プロフィール",
            status="processing"
        )
        self.assertIn("プロフィール", status1.display_text)
        self.assertIn("判定中", status1.display_text)

        status2 = LLMTaskStatus(
            task_type="response",
            status="processing"
        )
        self.assertEqual(status2.display_text, "応答文を生成中")


class TestDefaultAttributeMasters(unittest.TestCase):
    """デフォルト属性マスタのテスト"""

    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.temp_file.close()
        self.db = Database(self.temp_file.name)
        self.db.initialize()

    def tearDown(self):
        self.db.close()
        os.unlink(self.temp_file.name)

    def test_create_default_masters(self):
        """デフォルト属性マスタの作成テスト"""
        count = create_default_attribute_masters(self.db)

        # 6つの属性が作成されることを確認
        self.assertEqual(count, 6)

        masters = self.db.get_all_attribute_masters()
        self.assertEqual(len(masters), 6)

        # 期待される属性名を確認
        attribute_names = [m.attribute_name for m in masters]
        expected_names = ["プロフィール", "趣味・興味", "スケジュール", "連絡先", "好み・嗜好", "目標・課題"]
        for name in expected_names:
            self.assertIn(name, attribute_names)


class TestStreamingWorkflow(unittest.TestCase):
    """ストリーミングワークフローのテスト"""

    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.temp_file.close()
        self.db = Database(self.temp_file.name)
        self.db.initialize()

        master = AttributeMaster(
            attribute_id=0,
            attribute_name="テスト属性",
            extraction_prompt="テスト抽出",
            judgment_prompt="テスト判定"
        )
        self.db.insert_attribute_master(master)

        self.mock_llm = MockLLMClient()
        self.chat_service = ChatService(
            llm_client=self.mock_llm,
            database=self.db
        )

    def tearDown(self):
        self.db.close()
        os.unlink(self.temp_file.name)

    def test_streaming_statuses(self):
        """ストリーミングでステータスが順次返されるテスト"""
        self.mock_llm.set_judgment_response("テスト属性", False)
        self.mock_llm.set_extraction_response("テスト属性", None)
        self.mock_llm.add_generate_response("テスト応答")

        statuses = []
        generator = self.chat_service.process_user_input_streaming("テスト入力")

        try:
            while True:
                status = next(generator)
                statuses.append(status)
        except StopIteration as e:
            result = e.value

        # 複数のステータスが返されることを確認
        self.assertGreater(len(statuses), 0)

        # 最終結果が正しいことを確認
        self.assertEqual(result.response_text, "テスト応答")


if __name__ == "__main__":
    unittest.main()
