# student-manager

塾の統合管理システム — 生徒・講座管理 + チェックテスト自動読み取り（OCR採点）。

## 機能

- **管理画面** (`/admin`): 生徒管理、講座管理、ダッシュボード統計
- **チェックテスト** (`/checktest/`): テスト設定、PDFスキャン・OCR採点、結果レビュー、Excel出力
- **生徒ダッシュボード** (`/dashboard/{student_id}`): 出席状況
- **CLI** (`tools/checktest_reader.py`): PDF→Excel直接変換

## Tech Stack

- Backend: FastAPI + Uvicorn
- Frontend: HTMX + Jinja2
- Data: SQLite + SQLAlchemy ORM（WALモード）
- Image Processing: PyMuPDF + OpenCV
- Package Manager: uv
- Portal統合: yossy-portal-lib

## セットアップ

```bash
# 依存インストール
uv sync

# サーバー起動（スタンドアロン）
SECRET_KEY=xxx ADMIN_PASSWORD=xxx uv run uvicorn app.main:app --port 8010

# テスト実行
uv run pytest tests/ -v
```

ポータル経由の場合は `yossy-portal/start-portal.sh` で一括起動されます。

## ライセンス

MIT License
