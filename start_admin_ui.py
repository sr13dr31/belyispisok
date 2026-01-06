from __future__ import annotations

from pathlib import Path

from flask import Flask, send_file, send_from_directory

BASE_DIR = Path(__file__).resolve().parent
DIST_DIR = BASE_DIR / "admin-ui" / "dist"
INDEX_FILE = DIST_DIR / "index.html"

app = Flask(__name__, static_folder=str(DIST_DIR), static_url_path="")


@app.route("/")
def index() -> "flask.Response":
    return send_file(INDEX_FILE)


@app.route("/<path:asset_path>")
def static_proxy(asset_path: str) -> "flask.Response":
    file_path = DIST_DIR / asset_path
    if file_path.exists():
        return send_from_directory(DIST_DIR, asset_path)
    return send_file(INDEX_FILE)


if __name__ == "__main__":
    if not INDEX_FILE.exists():
        raise RuntimeError(
            "Admin UI build not found. Run `npm install` and `npm run build` in ./admin-ui to generate dist/."
        )

    host = "0.0.0.0"
    port = 5001
    app.run(host=host, port=port)
