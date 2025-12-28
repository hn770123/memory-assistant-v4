"""
Memory Assistant v4 - Webアプリケーション

FlaskベースのWebインターフェースを提供
"""
import os
import json
from flask import Flask, render_template, request, jsonify, session
from flask_cors import CORS
from dotenv import load_dotenv

from src.database import Database
from src.chat_service import ChatService, create_default_attribute_masters
from src.llm_client import MockLLMClient, OllamaClient, LLMResponse
from src.models import AttributeMaster, AttributeRecord, LLMLog
from datetime import datetime
import json

# 環境変数を読み込み
load_dotenv()

# Flaskアプリケーション初期化
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
CORS(app)

# データベース初期化
db = Database("memory_assistant.db")
db.initialize()

# LLMクライアント初期化
llm_provider = os.environ.get("LLM_PROVIDER", "mock")

if llm_provider == "ollama":
    try:
        ollama_url = os.environ.get("OLLAMA_URL", "http://localhost:11434")
        ollama_model = os.environ.get("OLLAMA_MODEL", "llama3.1:8b")
        llm_client = OllamaClient(base_url=ollama_url, model=ollama_model)
        print(f"Using Ollama LLM client: {ollama_url} with model {ollama_model}")
    except Exception as e:
        print(f"Warning: Ollama client initialization failed: {e}")
        print("Using mock LLM client instead")
        llm_client = MockLLMClient()
else:
    print("Using mock LLM client")
    llm_client = MockLLMClient()
    llm_client.add_generate_response("こんにちは！どのようにお手伝いできますか？")

# LLMログコールバック関数
def llm_log_callback(prompt: str, response: LLMResponse, task_type: str, attribute_name: str = None):
    """LLMとのやり取りをデータベースに記録"""
    # モデル名を取得
    model = getattr(llm_client, 'model', 'mock')

    # raw_responseをJSON文字列に変換
    raw_response_str = None
    if response.raw_response:
        raw_response_str = json.dumps(response.raw_response, ensure_ascii=False)

    log = LLMLog(
        log_id=None,
        timestamp=datetime.now(),
        model=model,
        task_type=task_type,
        prompt=prompt,
        response=response.content,
        raw_response=raw_response_str,
        attribute_name=attribute_name,
        metadata=None
    )
    db.insert_llm_log(log)


# LLMクライアントにログコールバックを設定
llm_client.set_log_callback(llm_log_callback)

# チャットサービス初期化
chat_service = ChatService(llm_client, db)


# ================
# ルーティング
# ================

@app.route("/")
def index():
    """トップページ - チャット画面にリダイレクト"""
    return render_template("index.html")


@app.route("/chat")
def chat():
    """チャット画面"""
    return render_template("chat.html")


@app.route("/logs")
def logs():
    """ログ確認画面"""
    return render_template("logs.html")


@app.route("/attribute-masters")
def attribute_masters():
    """属性マスタ保守画面"""
    return render_template("attribute_masters.html")


@app.route("/attribute-records")
def attribute_records():
    """属性テーブル保守画面"""
    return render_template("attribute_records.html")


# ================
# API エンドポイント
# ================

# === チャット API ===

@app.route("/api/chat", methods=["POST"])
def api_chat():
    """チャットメッセージを処理"""
    data = request.get_json()
    user_input = data.get("message", "")

    if not user_input:
        return jsonify({"error": "メッセージが空です"}), 400

    try:
        # ストリーミング形式でステータスを取得
        statuses = []
        response = None

        for status in chat_service.process_user_input_streaming(user_input):
            statuses.append({
                "task_type": status.task_type,
                "attribute_name": status.attribute_name,
                "status": status.status,
                "display_text": status.display_text
            })

        # 最終的な応答を取得（generatorの戻り値）
        response = chat_service.process_user_input(user_input)

        return jsonify({
            "response": response.response_text,
            "used_attributes": response.used_attributes,
            "extracted_attributes": response.extracted_attributes,
            "statuses": statuses
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/chat/history", methods=["GET"])
def api_chat_history():
    """チャット履歴を取得"""
    history = chat_service.get_chat_history()
    return jsonify({
        "history": [
            {
                "role": msg.role,
                "content": msg.content,
                "timestamp": msg.timestamp.isoformat()
            }
            for msg in history
        ]
    })


@app.route("/api/chat/clear", methods=["POST"])
def api_chat_clear():
    """チャット履歴をクリア"""
    chat_service.clear_history()
    return jsonify({"success": True})


# === ログ API ===

@app.route("/api/logs", methods=["GET"])
def api_logs():
    """LLMログを取得"""
    limit = request.args.get("limit", type=int)
    logs = db.get_all_llm_logs(limit=limit)

    return jsonify({
        "logs": [
            {
                "log_id": log.log_id,
                "timestamp": log.timestamp.isoformat(),
                "model": log.model,
                "task_type": log.task_type,
                "prompt": log.prompt,
                "response": log.response,
                "raw_response": log.raw_response,
                "attribute_name": log.attribute_name,
                "metadata": log.metadata
            }
            for log in logs
        ]
    })


@app.route("/api/logs/clear", methods=["POST"])
def api_logs_clear():
    """ログをクリア"""
    db.delete_all_llm_logs()
    return jsonify({"success": True})


# === 属性マスタ API ===

@app.route("/api/attribute-masters", methods=["GET"])
def api_get_attribute_masters():
    """全属性マスタを取得"""
    masters = db.get_all_attribute_masters()
    return jsonify({
        "masters": [
            {
                "attribute_id": m.attribute_id,
                "attribute_name": m.attribute_name,
                "extraction_prompt": m.extraction_prompt,
                "judgment_prompt": m.judgment_prompt
            }
            for m in masters
        ]
    })


@app.route("/api/attribute-masters/<int:attribute_id>", methods=["GET"])
def api_get_attribute_master(attribute_id):
    """特定の属性マスタを取得"""
    master = db.get_attribute_master(attribute_id)
    if master:
        return jsonify({
            "attribute_id": master.attribute_id,
            "attribute_name": master.attribute_name,
            "extraction_prompt": master.extraction_prompt,
            "judgment_prompt": master.judgment_prompt
        })
    return jsonify({"error": "属性マスタが見つかりません"}), 404


@app.route("/api/attribute-masters", methods=["POST"])
def api_create_attribute_master():
    """属性マスタを作成"""
    data = request.get_json()

    try:
        master = AttributeMaster(
            attribute_id=0,  # 自動採番
            attribute_name=data["attribute_name"],
            extraction_prompt=data["extraction_prompt"],
            judgment_prompt=data["judgment_prompt"]
        )
        attribute_id = db.insert_attribute_master(master)
        return jsonify({"attribute_id": attribute_id, "success": True}), 201
    except (KeyError, ValueError) as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/attribute-masters/<int:attribute_id>", methods=["PUT"])
def api_update_attribute_master(attribute_id):
    """属性マスタを更新"""
    data = request.get_json()

    try:
        master = AttributeMaster(
            attribute_id=attribute_id,
            attribute_name=data["attribute_name"],
            extraction_prompt=data["extraction_prompt"],
            judgment_prompt=data["judgment_prompt"]
        )
        success = db.update_attribute_master(master)
        if success:
            return jsonify({"success": True})
        return jsonify({"error": "属性マスタが見つかりません"}), 404
    except (KeyError, ValueError) as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/attribute-masters/<int:attribute_id>", methods=["DELETE"])
def api_delete_attribute_master(attribute_id):
    """属性マスタを削除"""
    success = db.delete_attribute_master(attribute_id)
    if success:
        return jsonify({"success": True})
    return jsonify({"error": "属性マスタが見つかりません"}), 404


@app.route("/api/attribute-masters/init-defaults", methods=["POST"])
def api_init_default_masters():
    """デフォルトの属性マスタを初期化"""
    count = create_default_attribute_masters(db)
    return jsonify({"success": True, "count": count})


# === 属性レコード API ===

@app.route("/api/attribute-records", methods=["GET"])
def api_get_attribute_records():
    """全属性レコードを取得"""
    attribute_id = request.args.get("attribute_id", type=int)

    if attribute_id:
        records = db.get_attribute_records_by_attribute_id(attribute_id)
    else:
        records = db.get_all_attribute_records()

    return jsonify({
        "records": [
            {
                "sequence_no": r.sequence_no,
                "attribute_id": r.attribute_id,
                "content": r.content,
                "created_at": r.created_at.isoformat(),
                "updated_at": r.updated_at.isoformat()
            }
            for r in records
        ]
    })


@app.route("/api/attribute-records", methods=["POST"])
def api_create_attribute_record():
    """属性レコードを作成"""
    data = request.get_json()

    try:
        record = AttributeRecord(
            sequence_no=None,  # 自動採番
            attribute_id=data["attribute_id"],
            content=data["content"]
        )
        sequence_no = db.insert_attribute_record(record)
        return jsonify({"sequence_no": sequence_no, "success": True}), 201
    except (KeyError, ValueError) as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/attribute-records/<int:sequence_no>", methods=["PUT"])
def api_update_attribute_record(sequence_no):
    """属性レコードを更新"""
    data = request.get_json()

    try:
        record = AttributeRecord(
            sequence_no=sequence_no,
            attribute_id=data["attribute_id"],
            content=data["content"]
        )
        success = db.update_attribute_record(record)
        if success:
            return jsonify({"success": True})
        return jsonify({"error": "属性レコードが見つかりません"}), 404
    except (KeyError, ValueError) as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/attribute-records/<int:sequence_no>", methods=["DELETE"])
def api_delete_attribute_record(sequence_no):
    """属性レコードを削除"""
    success = db.delete_attribute_record(sequence_no)
    if success:
        return jsonify({"success": True})
    return jsonify({"error": "属性レコードが見つかりません"}), 404


if __name__ == "__main__":
    # 開発サーバーを起動
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "True").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
