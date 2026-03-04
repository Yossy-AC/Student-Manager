from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import os

from app.dependencies import is_authenticated

router = APIRouter()

templates_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
templates = Jinja2Templates(directory=templates_dir)


def _base_href(request: Request) -> str:
    """ポータル経由の場合は X-Portal-Prefix からベースパスを返す。スタンドアロンは /"""
    prefix = request.headers.get("X-Portal-Prefix", "")
    return f"{prefix}/" if prefix else "/"


@router.get("/", response_class=HTMLResponse)
async def root(request: Request):
    if is_authenticated(request):
        return RedirectResponse(url="/admin", status_code=302)
    return RedirectResponse(url="/login", status_code=302)


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if is_authenticated(request):
        return RedirectResponse(url="/admin", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request})


@router.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse("admin/index.html", {"request": request, "base_href": _base_href(request)})


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_select(request: Request):
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse(
        "dashboard/select.html",
        {"request": request, "base_href": _base_href(request)}
    )


@router.get("/dashboard/{student_id}", response_class=HTMLResponse)
async def dashboard_page(request: Request, student_id: str):
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse(
        "dashboard/index.html",
        {"request": request, "student_id": student_id, "base_href": _base_href(request)}
    )


@router.get("/upload", response_class=HTMLResponse)
async def upload_page(request: Request):
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse("upload/index.html", {"request": request, "base_href": _base_href(request)})


@router.get("/admin/tabs/{tab_name}", response_class=HTMLResponse)
async def admin_tab(request: Request, tab_name: str):
    """管理画面タブコンテンツ切り替え（HTMX用）"""
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=302)

    tab_templates = {
        "dashboard": "admin/_dashboard_tab.html",
        "grades": "admin/_grades_tab.html",
        "students": "admin/_students_tab.html",
        "classes": "admin/_classes_tab.html",
        "upload": "upload/index.html",
        "reports": "admin/_reports_tab.html",
    }

    template_path = tab_templates.get(tab_name)
    if not template_path:
        return RedirectResponse(url="/admin", status_code=302)
    return templates.TemplateResponse(template_path, {"request": request, "base_href": _base_href(request)})
