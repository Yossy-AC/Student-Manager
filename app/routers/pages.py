from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session
import os

from yossy_portal_lib import base_href as _base_href
from app.database import get_db
from app.dependencies import is_authenticated
from app.models.student import Student
from app.models.class_ import Class
from app.models.attendance import Attendance
from app.models.checktest import ChecktestConfig, ChecktestSession

router = APIRouter()

templates_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
templates = Jinja2Templates(directory=templates_dir)


def _redirect(request: Request, path: str) -> RedirectResponse:
    """base_href を考慮したリダイレクト"""
    return RedirectResponse(url=f"{_base_href(request)}{path}", status_code=302)


@router.get("/", response_class=HTMLResponse)
async def root(request: Request):
    if is_authenticated(request):
        return _redirect(request, "admin")
    return _redirect(request, "login")


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if is_authenticated(request):
        return _redirect(request, "admin")
    return templates.TemplateResponse("login.html", {"request": request, "base_href": _base_href(request)})


@router.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    if not is_authenticated(request):
        return _redirect(request, "login")
    return templates.TemplateResponse("admin/index.html", {"request": request, "base_href": _base_href(request)})


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_select(request: Request, db: Session = Depends(get_db)):
    if not is_authenticated(request):
        return _redirect(request, "login")
    students = db.query(Student).order_by(Student.name).all()
    return templates.TemplateResponse(
        "dashboard/select.html",
        {"request": request, "base_href": _base_href(request), "students": students}
    )


@router.get("/dashboard/{student_id}", response_class=HTMLResponse)
async def dashboard_page(request: Request, student_id: str):
    if not is_authenticated(request):
        return _redirect(request, "login")
    return templates.TemplateResponse(
        "dashboard/index.html",
        {"request": request, "student_id": student_id, "base_href": _base_href(request)}
    )


@router.get("/checktest/", response_class=HTMLResponse)
async def checktest_dashboard(request: Request, db: Session = Depends(get_db)):
    """チェックテスト ダッシュボード"""
    if not is_authenticated(request):
        return _redirect(request, "login")
    classes = db.query(Class).order_by(Class.name).all()
    recent_sessions = (
        db.query(ChecktestSession)
        .join(ChecktestConfig)
        .order_by(ChecktestSession.created_at.desc())
        .limit(10)
        .all()
    )
    # eager load config info
    for s in recent_sessions:
        _ = s.config.class_id
        _ = s.config.test_no

    return templates.TemplateResponse("checktest/index.html", {
        "request": request,
        "base_href": _base_href(request),
        "classes": classes,
        "recent_sessions": recent_sessions,
    })


@router.get("/admin/tabs/{tab_name}", response_class=HTMLResponse)
async def admin_tab(request: Request, tab_name: str, db: Session = Depends(get_db)):
    """管理画面タブコンテンツ切り替え（HTMX用）"""
    if not is_authenticated(request):
        return _redirect(request, "login")

    tab_templates = {
        "dashboard": "admin/_dashboard_tab.html",
        "students": "admin/_students_tab.html",
        "classes": "admin/_classes_tab.html",
        "reports": "admin/_reports_tab.html",
    }

    template_path = tab_templates.get(tab_name)
    if not template_path:
        return _redirect(request, "admin")

    context = {"request": request, "base_href": _base_href(request)}

    if tab_name == "dashboard":
        context["student_count"] = db.query(func.count(Student.id)).scalar() or 0
        context["class_count"] = db.query(func.count(Class.id)).scalar() or 0
        context["session_count"] = db.query(func.count(ChecktestSession.id)).scalar() or 0
        context["attendance_count"] = db.query(func.count(Attendance.id)).scalar() or 0

    return templates.TemplateResponse(template_path, context)
