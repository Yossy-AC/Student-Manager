from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_auth
from app.models.student import Student
from app.models.attendance import Attendance
from app.templates_config import templates

router = APIRouter()


def _get_attendance_summary(db: Session, student_id: str) -> dict:
    """出席状況サマリーを集計"""
    records = db.query(Attendance).filter(Attendance.student_id == student_id).all()
    total = len(records)
    present = sum(1 for r in records if r.status == "出席")
    absent = sum(1 for r in records if r.status == "欠席")
    late = sum(1 for r in records if r.status == "遅刻")
    rate = round(present / total * 100) if total > 0 else 0
    return {"present": present, "absent": absent, "late": late, "rate": rate, "total": total}


@router.get("/student/{student_id}", response_class=HTMLResponse)
async def get_attendance(
    student_id: str,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(require_auth),
):
    """出席状況（HTMX用）"""
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        return "<p>生徒が見つかりません</p>"
    summary = _get_attendance_summary(db, student_id)
    return templates.TemplateResponse(
        "partials/attendance.html",
        {"request": request, "summary": summary},
    )
