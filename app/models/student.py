from sqlalchemy import Column, String, Date, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

class Student(Base):
    __tablename__ = "students"

    id = Column(String(20), primary_key=True)   # "s001"
    classroom = Column(String(100))              # "難関大クラス"（CSV由来の表示名）
    name = Column(String(100), nullable=False)
    name_kana = Column(String(100))
    gender = Column(String(10))                  # "男" / "女"
    high_school = Column(String(100))
    course_subject = Column(String(50))          # "理系" / "文系"
    school_class = Column(String(20))            # "3-A"
    club = Column(String(100))
    target_university = Column(String(100))
    target_dept = Column(String(100))
    class_id = Column(String(20), ForeignKey("classes.id"))
    join_date = Column(Date)

    class_ = relationship("Class", backref="students")
    attendance = relationship("Attendance", back_populates="student")
