"""checktest 用 ORM モデル（student_manager.db に追加）"""

from sqlalchemy import Column, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class ChecktestConfig(Base):
    """テスト設定（クラス × 回次）"""
    __tablename__ = "checktest_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    class_id = Column(String(20), nullable=False)   # classes.id 参照
    test_no = Column(String(50), nullable=False)     # "第1回", "第2回"
    created_at = Column(Text, server_default="(datetime('now','localtime'))")
    updated_at = Column(Text, server_default="(datetime('now','localtime'))")

    questions = relationship(
        "ChecktestQuestion", back_populates="config",
        cascade="all, delete-orphan", order_by="ChecktestQuestion.question_index",
    )
    sessions = relationship("ChecktestSession", back_populates="config")

    __table_args__ = (
        Index("uq_checktest_config", "class_id", "test_no", unique=True),
    )


class ChecktestQuestion(Base):
    """テスト設定の各大問"""
    __tablename__ = "checktest_questions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    config_id = Column(Integer, ForeignKey("checktest_configs.id", ondelete="CASCADE"), nullable=False)
    question_index = Column(Integer, nullable=False)  # 0-based
    label = Column(String(100), nullable=False)        # "大問1", "リスニング"
    max_score = Column(Integer, nullable=False)

    config = relationship("ChecktestConfig", back_populates="questions")

    __table_args__ = (
        Index("uq_checktest_question", "config_id", "question_index", unique=True),
    )


class ChecktestSession(Base):
    """処理セッション（1PDF = 1セッション）"""
    __tablename__ = "checktest_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    config_id = Column(Integer, ForeignKey("checktest_configs.id"), nullable=False)
    scan_date = Column(Text, nullable=False)           # YYYY-MM-DD
    pdf_filename = Column(Text)
    total_pages = Column(Integer, default=0)
    ok_pages = Column(Integer, default=0)
    ng_pages = Column(Integer, default=0)
    status = Column(String(20), default="review")      # review / confirmed
    created_at = Column(Text, server_default="(datetime('now','localtime'))")

    config = relationship("ChecktestConfig", back_populates="sessions")
    pages = relationship(
        "ChecktestPage", back_populates="session",
        cascade="all, delete-orphan", order_by="ChecktestPage.page_number",
    )

    __table_args__ = (
        Index("idx_checktest_sessions_config", "config_id"),
    )


class ChecktestPage(Base):
    """ページ（1生徒 = 1ページ）"""
    __tablename__ = "checktest_pages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("checktest_sessions.id", ondelete="CASCADE"), nullable=False)
    page_number = Column(Integer, nullable=False)
    student_name_ocr = Column(Text)                    # OCR読み取り氏名
    student_id = Column(String(20))                    # students.id (手動マッチ後, NULL可)
    total_mark = Column(Integer)                       # マーク合計
    total_written = Column(Integer)                    # 手書き合計(OCR)
    page_flag = Column(String(50), default="正常")

    session = relationship("ChecktestSession", back_populates="pages")
    scores = relationship(
        "ChecktestScore", back_populates="page",
        cascade="all, delete-orphan", order_by="ChecktestScore.question_index",
    )

    __table_args__ = (
        Index("idx_checktest_pages_session", "session_id"),
        Index("idx_checktest_pages_student", "student_id"),
    )


class ChecktestScore(Base):
    """個別スコア（1ページ × N大問）"""
    __tablename__ = "checktest_scores"

    id = Column(Integer, primary_key=True, autoincrement=True)
    page_id = Column(Integer, ForeignKey("checktest_pages.id", ondelete="CASCADE"), nullable=False)
    question_index = Column(Integer, nullable=False)   # 0-based
    score = Column(Integer)                            # NULL = 複数塗り/読み取り失敗
    flag = Column(String(20), default="")              # '', '複数塗り'
    edited = Column(Integer, default=0)                # 手動修正済み

    page = relationship("ChecktestPage", back_populates="scores")

    __table_args__ = (
        Index("idx_checktest_scores_page", "page_id"),
    )
