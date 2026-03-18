"""テスト設定 CRUD"""

from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from yossy_portal_lib import base_href as _base_href

from app.database import get_db
from app.dependencies import require_auth
from app.models.checktest import ChecktestConfig, ChecktestQuestion
from app.models.class_ import Class
from app.templates_config import templates

router = APIRouter(tags=["checktest"])


def _redirect(request: Request, path: str) -> RedirectResponse:
    return RedirectResponse(url=f"{_base_href(request)}{path}", status_code=303)


# --- 一覧 ---
@router.get("/configs", response_class=HTMLResponse)
async def configs_page(request: Request, db: Session = Depends(get_db), _=Depends(require_auth)):
    classes = db.query(Class).order_by(Class.name).all()
    configs = (
        db.query(ChecktestConfig)
        .order_by(ChecktestConfig.class_id, ChecktestConfig.test_no)
        .all()
    )
    class_map = {c.id: c.name for c in classes}
    config_data = []
    for c in configs:
        config_data.append({
            "id": c.id,
            "class_id": c.class_id,
            "class_name": class_map.get(c.class_id, c.class_id),
            "test_no": c.test_no,
            "n_questions": len(c.questions),
            "total_max": sum(q.max_score for q in c.questions),
        })

    return templates.TemplateResponse("checktest/configs/list.html", {
        "request": request,
        "base_href": _base_href(request),
        "classes": classes,
        "configs": config_data,
    })


# --- 新規作成フォーム ---
@router.get("/configs/new", response_class=HTMLResponse)
async def new_config_form(request: Request, db: Session = Depends(get_db), _=Depends(require_auth)):
    classes = db.query(Class).order_by(Class.name).all()
    return templates.TemplateResponse("checktest/configs/form.html", {
        "request": request,
        "base_href": _base_href(request),
        "classes": classes,
        "config": None,
        "questions": [{"label": "大問1", "max_score": 20}],
    })


# --- 編集フォーム ---
@router.get("/configs/{config_id}/edit", response_class=HTMLResponse)
async def edit_config_form(request: Request, config_id: int, db: Session = Depends(get_db), _=Depends(require_auth)):
    classes = db.query(Class).order_by(Class.name).all()
    config = db.query(ChecktestConfig).filter(ChecktestConfig.id == config_id).first()
    if not config:
        return _redirect(request, "checktest/configs")
    questions = [{"label": q.label, "max_score": q.max_score} for q in config.questions]

    return templates.TemplateResponse("checktest/configs/form.html", {
        "request": request,
        "base_href": _base_href(request),
        "classes": classes,
        "config": config,
        "questions": questions,
    })


# --- 作成 API ---
@router.post("/api/configs")
async def create_config(request: Request, db: Session = Depends(get_db), _=Depends(require_auth)):
    form = await request.form()
    class_id = form.get("class_id")
    test_no = form.get("test_no")
    labels = form.getlist("q_label")
    max_scores = form.getlist("q_max_score")

    existing = (
        db.query(ChecktestConfig)
        .filter(ChecktestConfig.class_id == class_id, ChecktestConfig.test_no == test_no)
        .first()
    )
    if existing:
        return _redirect(request, f"checktest/configs/{existing.id}/edit")

    config = ChecktestConfig(class_id=class_id, test_no=test_no)
    db.add(config)
    db.flush()

    for i, (label, ms) in enumerate(zip(labels, max_scores)):
        if label.strip() and ms.strip():
            q = ChecktestQuestion(
                config_id=config.id, question_index=i,
                label=label.strip(), max_score=int(ms),
            )
            db.add(q)

    db.commit()
    return _redirect(request, "checktest/configs")


# --- 更新 API ---
@router.post("/api/configs/{config_id}")
async def update_config(request: Request, config_id: int, db: Session = Depends(get_db), _=Depends(require_auth)):
    form = await request.form()
    test_no = form.get("test_no")
    labels = form.getlist("q_label")
    max_scores = form.getlist("q_max_score")

    config = db.query(ChecktestConfig).filter(ChecktestConfig.id == config_id).first()
    if not config:
        return _redirect(request, "checktest/configs")

    config.test_no = test_no
    config.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    db.query(ChecktestQuestion).filter(ChecktestQuestion.config_id == config_id).delete()
    for i, (label, ms) in enumerate(zip(labels, max_scores)):
        if label.strip() and ms.strip():
            q = ChecktestQuestion(
                config_id=config_id, question_index=i,
                label=label.strip(), max_score=int(ms),
            )
            db.add(q)

    db.commit()
    return _redirect(request, "checktest/configs")


# --- 削除 API ---
@router.post("/api/configs/{config_id}/delete")
async def delete_config(request: Request, config_id: int, db: Session = Depends(get_db), _=Depends(require_auth)):
    config = db.query(ChecktestConfig).filter(ChecktestConfig.id == config_id).first()
    if config:
        db.delete(config)
        db.commit()
    return _redirect(request, "checktest/configs")


# --- HTMX: クラスごとの設定リスト ---
@router.get("/api/configs", response_class=HTMLResponse)
async def get_configs_for_class(request: Request, class_id: str = "", db: Session = Depends(get_db), _=Depends(require_auth)):
    """HTMX 用: 指定クラスのテスト設定を <option> リストで返す"""
    query = db.query(ChecktestConfig)
    if class_id:
        query = query.filter(ChecktestConfig.class_id == class_id)
    configs = query.order_by(ChecktestConfig.test_no).all()

    html = '<option value="">-- テスト設定を選択 --</option>'
    for c in configs:
        total = sum(q.max_score for q in c.questions)
        html += f'<option value="{c.id}">{c.test_no} ({len(c.questions)}問, {total}点)</option>'

    return HTMLResponse(html)
