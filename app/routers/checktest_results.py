"""過去結果・履歴・集計"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from yossy_portal_lib import base_href as _base_href

from app.database import get_db
from app.dependencies import require_auth
from app.models.checktest import (
    ChecktestConfig,
    ChecktestSession,
)
from app.models.class_ import Class
from app.templates_config import templates

router = APIRouter(tags=["checktest"])


def _redirect(request: Request, path: str) -> RedirectResponse:
    return RedirectResponse(url=f"{_base_href(request)}{path}", status_code=303)


# --- セッション一覧 ---
@router.get("/results", response_class=HTMLResponse)
async def results_page(request: Request, db: Session = Depends(get_db), _=Depends(require_auth)):
    classes = db.query(Class).order_by(Class.name).all()
    class_map = {c.id: c.name for c in classes}

    sessions = (
        db.query(ChecktestSession)
        .join(ChecktestConfig)
        .order_by(ChecktestSession.created_at.desc())
        .limit(50)
        .all()
    )
    session_data = []
    for s in sessions:
        session_data.append({
            "id": s.id,
            "class_name": class_map.get(s.config.class_id, s.config.class_id),
            "test_no": s.config.test_no,
            "scan_date": s.scan_date,
            "total_pages": s.total_pages,
            "ok_pages": s.ok_pages,
            "ng_pages": s.ng_pages,
            "status": s.status,
        })

    return templates.TemplateResponse("checktest/results/sessions.html", {
        "request": request,
        "base_href": _base_href(request),
        "sessions": session_data,
    })


# --- セッション詳細 ---
@router.get("/results/sessions/{session_id}", response_class=HTMLResponse)
async def session_detail(request: Request, session_id: int, db: Session = Depends(get_db), _=Depends(require_auth)):
    session = db.query(ChecktestSession).filter(ChecktestSession.id == session_id).first()
    if not session:
        return _redirect(request, "checktest/results")

    config = session.config
    questions = sorted(config.questions, key=lambda q: q.question_index)

    pages = sorted(session.pages, key=lambda p: p.page_number)
    page_data = []
    all_totals = []
    for p in pages:
        scores = sorted(p.scores, key=lambda s: s.question_index)
        page_data.append({
            "page_number": p.page_number,
            "name_ocr": p.student_name_ocr,
            "student_id": p.student_id,
            "total_mark": p.total_mark,
            "page_flag": p.page_flag,
            "scores": [s.score for s in scores],
        })
        if p.total_mark is not None:
            all_totals.append(p.total_mark)

    stats = {}
    if all_totals:
        stats = {
            "avg": round(sum(all_totals) / len(all_totals), 1),
            "max": max(all_totals),
            "min": min(all_totals),
            "count": len(all_totals),
        }

    class_map = {c.id: c.name for c in db.query(Class).all()}

    return templates.TemplateResponse("checktest/results/detail.html", {
        "request": request,
        "base_href": _base_href(request),
        "session": session,
        "config": config,
        "class_name": class_map.get(config.class_id, config.class_id),
        "questions": questions,
        "pages": page_data,
        "stats": stats,
    })
