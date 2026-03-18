import os
from pathlib import Path
from dotenv import load_dotenv

# 中央 .env（Dev/.env）を優先で読み込み
_central_env = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(_central_env)
load_dotenv()  # ローカル .env も補完

class Settings:
    SECRET_KEY: str = os.getenv("SECRET_KEY", "")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./data/student_manager.db")
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    BEHIND_PORTAL: bool = os.getenv("BEHIND_PORTAL", "false").lower() == "true"

    def __init__(self):
        if not self.BEHIND_PORTAL:
            # スタンドアロン時のみ必須
            if not self.SECRET_KEY:
                raise RuntimeError("SECRET_KEY environment variable is required")
            if not self.ADMIN_PASSWORD:
                raise RuntimeError("ADMIN_PASSWORD environment variable is required")
        else:
            # ポータル経由: SessionMiddleware用にデフォルト値を設定
            if not self.SECRET_KEY:
                self.SECRET_KEY = "portal-session-key"

settings = Settings()

# チェックテスト用: PDF一時保存ディレクトリ
TEMP_PDF_DIR = Path(__file__).resolve().parent.parent / "data" / "temp_pdf"
TEMP_PDF_DIR.mkdir(parents=True, exist_ok=True)

# チェックテスト用: デバッグ画像ディレクトリ
DEBUG_IMG_DIR = Path(__file__).resolve().parent.parent / "data" / "debug_img"
DEBUG_IMG_DIR.mkdir(parents=True, exist_ok=True)
