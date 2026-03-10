import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    SECRET_KEY: str = os.getenv("SECRET_KEY", "")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./data/student_manager.db")
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    def __init__(self):
        if not self.SECRET_KEY:
            raise RuntimeError("SECRET_KEY environment variable is required")
        if not self.ADMIN_PASSWORD:
            raise RuntimeError("ADMIN_PASSWORD environment variable is required")

settings = Settings()
