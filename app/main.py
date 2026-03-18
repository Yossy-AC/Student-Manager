from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
import os

from yossy_portal_lib import portal_auth_middleware, csp_middleware, add_health_endpoint

from app.database import create_db_and_tables
from app.config import settings
from app.routers import (
    pages, students, classes, attendance, auth as auth_router,
    checktest_configs, checktest_scan, checktest_results, checktest_export,
)

# FastAPI アプリ作成
app = FastAPI(
    title="塾成績管理システム",
    version="0.2.0"
)

# セッションミドルウェア設定
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# ポータル認証・CSP ミドルウェア
app.middleware("http")(portal_auth_middleware)
app.middleware("http")(csp_middleware)

# 静的ファイル配信
static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

# ルーター登録（認証関連は最初に）
app.include_router(auth_router.router, prefix="/auth", tags=["auth"])
app.include_router(pages.router, tags=["pages"])
app.include_router(students.router, prefix="/api/students", tags=["students"])
app.include_router(classes.router, prefix="/api/classes", tags=["classes"])
app.include_router(attendance.router, prefix="/api/attendance", tags=["attendance"])

# チェックテスト ルーター
app.include_router(checktest_configs.router, prefix="/checktest", tags=["checktest"])
app.include_router(checktest_scan.router, prefix="/checktest", tags=["checktest"])
app.include_router(checktest_results.router, prefix="/checktest", tags=["checktest"])
app.include_router(checktest_export.router, prefix="/checktest", tags=["checktest"])

# ヘルスチェック
add_health_endpoint(app)

# アプリ起動時にDBテーブルを作成
create_db_and_tables()
