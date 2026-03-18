import logging
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_auth
from app.models.class_ import Class
from app.models.student import Student
from app.templates_config import templates

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("", response_class=HTMLResponse)
async def list_classes(
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(require_auth),
):
    """講座一覧（HTMX用）"""
    classes = db.query(Class).all()
    return templates.TemplateResponse(
        "partials/classes_table.html",
        {"request": request, "classes": classes},
    )


@router.post("", response_class=HTMLResponse)
async def create_class(
    request: Request,
    name: str = Form(...),
    day: str = Form(""),
    time: str = Form(""),
    capacity: int = Form(30),
    db: Session = Depends(get_db),
    _: None = Depends(require_auth),
):
    """講座追加（HTMX用）"""
    try:
        # ID 自動採番（最大の数値 + 1）
        max_id = 0
        for c in db.query(Class).all():
            try:
                num = int(c.id.lstrip("c"))
                if num > max_id:
                    max_id = num
            except ValueError:
                pass
        new_id = f"c{max_id + 1:03d}"

        new_class = Class(
            id=new_id,
            name=name,
            day=day or None,
            time=time or None,
            capacity=capacity,
        )
        db.add(new_class)
        db.commit()

        classes = db.query(Class).all()
        return templates.TemplateResponse(
            "partials/classes_table.html",
            {"request": request, "classes": classes},
        )
    except Exception as e:
        logger.error("Class create error: %s", e, exc_info=True)
        return "<p style='color:#c62828;'>保存中にエラーが発生しました</p>"


@router.get("/{class_id}/students", response_class=HTMLResponse)
async def get_class_students(
    class_id: str,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(require_auth),
):
    """講座別生徒セレクトボックス（HTMX用、連鎖セレクト）"""
    students = db.query(Student).filter(Student.class_id == class_id).all()
    return templates.TemplateResponse(
        "partials/class_students_select.html",
        {"request": request, "students": students},
    )
