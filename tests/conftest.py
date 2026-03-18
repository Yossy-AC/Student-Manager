"""テスト共通設定: インメモリSQLite + 認証バイパス"""

import os

# app.config が読まれる前に環境変数を設定
os.environ["SECRET_KEY"] = "test-secret"
os.environ["ADMIN_PASSWORD"] = "test-password"
os.environ["DATABASE_URL"] = "sqlite:///./data/test.db"
os.environ["BEHIND_PORTAL"] = "true"

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.main import app

# インメモリDB — StaticPool で全接続が同一DBを共有
TEST_ENGINE = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = sessionmaker(autocommit=False, autoflush=False, bind=TEST_ENGINE)


def _override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db


@pytest.fixture(autouse=True)
def setup_db():
    """各テスト前にテーブルを作成し、テスト後に削除"""
    Base.metadata.create_all(bind=TEST_ENGINE)
    yield
    Base.metadata.drop_all(bind=TEST_ENGINE)


@pytest.fixture
def client():
    """認証済みテストクライアント"""
    with TestClient(app) as c:
        c.headers["X-Portal-Role"] = "staff"
        yield c


@pytest.fixture
def db():
    """テスト用DBセッション"""
    session = TestSession()
    try:
        yield session
    finally:
        session.close()
