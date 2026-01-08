from __future__ import annotations

import json
from pathlib import Path

from flask import Flask, jsonify, request, send_file, send_from_directory
from flask_cors import CORS

try:
    from db import (
        get_conn,
        get_company_by_id,
        get_master_by_id,
        get_review_appeal_by_id,
        get_review_by_id,
        log_admin_action,
        set_company_blocked,
        set_company_subscription,
        set_master_blocked,
        update_company_verification_status,
        update_review_appeal_company_response,
    )
except ImportError:
    # Для случаев, когда db.py не доступен
    pass

BASE_DIR = Path(__file__).resolve().parent
DIST_DIR = BASE_DIR / "admin-ui" / "dist"
INDEX_FILE = DIST_DIR / "index.html"

app = Flask(__name__, static_folder=str(DIST_DIR), static_url_path="")
CORS(app)  # Разрешаем CORS для API


@app.route("/")
def index() -> "flask.Response":
    return send_file(INDEX_FILE)


@app.route("/<path:asset_path>")
def static_proxy(asset_path: str) -> "flask.Response":
    file_path = DIST_DIR / asset_path
    if file_path.exists():
        return send_from_directory(DIST_DIR, asset_path)
    return send_file(INDEX_FILE)


# API Endpoints
@app.route("/api/review-appeals", methods=["GET"])
def get_review_appeals():
    """Получить список жалоб на отзывы"""
    try:
        from db import get_conn
        
        with get_conn() as conn:
            c = conn.cursor()
            c.execute("""
                SELECT ra.*, 
                       r.text as review_text, 
                       r.created_at as review_created_at,
                       m.full_name as master_full_name, 
                       m.public_id as master_public_id,
                       c2.name as company_name, 
                       c2.public_id as company_public_id
                FROM review_appeals ra
                JOIN reviews r ON ra.review_id = r.id
                JOIN masters m ON ra.master_id = m.id
                LEFT JOIN companies c2 ON ra.company_id = c2.id
                ORDER BY ra.created_at DESC
                LIMIT 100
            """)
            rows = c.fetchall()
            appeals = [dict(row) for row in rows]
            return jsonify(appeals)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/review-appeals/<int:appeal_id>", methods=["GET"])
def get_review_appeal(appeal_id: int):
    """Получить детали жалобы"""
    try:
        appeal = get_review_appeal_by_id(appeal_id)
        if not appeal:
            return jsonify({"error": "Appeal not found"}), 404
        return jsonify(appeal)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/review-appeals/<int:appeal_id>/photos", methods=["GET"])
def get_appeal_photos(appeal_id: int):
    """Получить фото из жалобы"""
    try:
        from db import get_conn
        
        appeal = get_review_appeal_by_id(appeal_id)
        if not appeal:
            return jsonify({"error": "Appeal not found"}), 404
        
        photos = []
        
        # Фото от исполнителя
        if appeal.get("master_files_message_id"):
            # Сохраняем как JSON массив message_id
            master_files = appeal.get("master_files_message_id")
            if isinstance(master_files, str):
                try:
                    photos.extend(json.loads(master_files))
                except:
                    photos.append(master_files)
            elif master_files:
                photos.append(master_files)
        
        # Фото от компании
        if appeal.get("company_files_message_id"):
            photos.append(appeal["company_files_message_id"])
        
        return jsonify({"photos": photos, "type": "message_ids"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    if not INDEX_FILE.exists():
        raise RuntimeError(
            "Admin UI build not found. Run `npm install` and `npm run build` in ./admin-ui to generate dist/."
        )

    host = "0.0.0.0"
    port = 5001
    app.run(host=host, port=port)
