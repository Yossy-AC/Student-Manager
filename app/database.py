from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker
from app.config import settings

# データベース接続
engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {},
    echo=settings.DEBUG
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 全モデルが継承するベースクラス
Base = declarative_base()

def get_db():
    """依存関数: DB セッションを取得"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    """WALモード有効化（concurrent read対応）"""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


def create_db_and_tables():
    """アプリ起動時にテーブルを作成"""
    # checktest モデルも含めてテーブル生成
    import app.models  # noqa: F401
    Base.metadata.create_all(bind=engine)
