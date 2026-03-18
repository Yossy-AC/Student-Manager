"""PDF アップロード + 処理 + レビュー"""

import logging
import os
from datetime import date

from fastapi import APIRouter, Depends, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from yossy_portal_lib import base_href as _base_href

from app.config import DEBUG_IMG_DIR, TEMP_PDF_DIR
from app.database import get_db
from app.dependencies import require_auth
from app.models.checktest import (
    ChecktestConfig,
    ChecktestPage,
    ChecktestQuestion,
    ChecktestScore,
    ChecktestSession,
)
from app.models.class_ import Class
from app.models.student import Student
from app.templates_config import templates

log = logging.getLogger(__name__)

router = APIRouter(tags=["checktest"])


def _redirect(request: Request, path: str) -> RedirectResponse:
    return RedirectResponse(url=f"{_base_href(request)}{path}", status_code=303)


@router.get("/scan", response_class=HTMLResponse)
async def scan_page(request: Request, db: Session = Depends(get_db), _=Depends(require_auth)):
    classes = db.query(Class).order_by(Class.name).all()
    return templates.TemplateResponse("checktest/scan/upload.html", {
        "request": request,
        "base_href": _base_href(request),
        "classes": classes,
        "today": date.today().isoformat(),
    })


@router.post("/api/scan/upload")
async def upload_and_process(
    request: Request,
    pdf: UploadFile = None,
    config_id: int = Form(...),
    scan_date: str = Form(None),
    thresh: float = Form(0.35),
    no_crop: bool = Form(False),
    debug: bool = Form(False),
    db: Session = Depends(get_db),
    _=Depends(require_auth),
):
    if not pdf or not pdf.filename:
        return JSONResponse({"error": "PDFファイルを選択してください"}, status_code=400)
    if not scan_date:
        scan_date = date.today().isoformat()

    config = db.query(ChecktestConfig).filter(ChecktestConfig.id == config_id).first()
    if not config:
        return JSONResponse({"error": "テスト設定が見つかりません"}, status_code=404)

    questions = db.query(ChecktestQuestion).filter(
        ChecktestQuestion.config_id == config_id
    ).order_by(ChecktestQuestion.question_index).all()

    config_dict = {
        "class_name": config.class_id,
        "test_no": config.test_no,
        "questions": [{"label": q.label, "max_score": q.max_score} for q in questions],
        "total_max": sum(q.max_score for q in questions),
    }

    pdf_bytes = await pdf.read()
    pdf_path = str(TEMP_PDF_DIR / (pdf.filename or "scan.pdf"))
    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)

    from app.core.checktest.processor import fail_result, process_page
    from app.core.checktest.scanner import pdf_page_count, pdf_to_images
    total_pages = pdf_page_count(pdf_path)

    session = ChecktestSession(
        config_id=config_id, scan_date=scan_date,
        pdf_filename=pdf.filename, total_pages=total_pages,
    )
    db.add(session)
    db.flush()

    debug_dir = str(DEBUG_IMG_DIR / str(session.id)) if debug else None

    ok_count = 0
    ng_count = 0
    for page_num, img in pdf_to_images(pdf_path):
        try:
            result = process_page(img, config_dict, page_num, thresh=thresh, no_crop=no_crop, debug_dir=debug_dir)
        except Exception as e:
            log.error(f"ページ {page_num} 処理エラー: {e}", exc_info=True)
            result = fail_result(page_num, len(questions))

        page = ChecktestPage(
            session_id=session.id, page_number=result["page"],
            student_name_ocr=result["name"], total_mark=result["total_mark"],
            total_written=result["total_written"], page_flag=result["page_flag"],
        )
        db.add(page)
        db.flush()

        for qi, (score, flag) in enumerate(zip(result["scores"], result["flags"])):
            db.add(ChecktestScore(page_id=page.id, question_index=qi, score=score, flag=flag))

        if result["page_flag"] == "正常":
            ok_count += 1
        else:
            ng_count += 1

    session.ok_pages = ok_count
    session.ng_pages = ng_count
    db.commit()
    try:
        os.remove(pdf_path)
    except OSError:
        pass
    return _redirect(request, f"checktest/scan/{session.id}/review")


@router.get("/scan/{session_id}/review", response_class=HTMLResponse)
async def review_page(request: Request, session_id: int, db: Session = Depends(get_db), _=Depends(require_auth)):
    session = db.query(ChecktestSession).filter(ChecktestSession.id == session_id).first()
    if not session:
        return _redirect(request, "checktest/scan")
    config = session.config
    questions = sorted(config.questions, key=lambda q: q.question_index)
    pages = sorted(session.pages, key=lambda p: p.page_number)
    page_data = []
    for p in pages:
        scores = sorted(p.scores, key=lambda s: s.question_index)
        page_data.append({
            "id": p.id, "page_number": p.page_number,
            "name_ocr": p.student_name_ocr, "student_id": p.student_id,
            "total_mark": p.total_mark, "total_written": p.total_written,
            "page_flag": p.page_flag,
            "scores": [{"id": s.id, "score": s.score, "flag": s.flag, "edited": s.edited} for s in scores],
        })
    students = db.query(Student).filter(Student.class_id == config.class_id).order_by(Student.name).all()

    return templates.TemplateResponse("checktest/scan/review.html", {
        "request": request, "base_href": _base_href(request),
        "session": session, "config": config,
        "questions": questions, "pages": page_data, "students": students,
    })


@router.put("/api/scan/scores/{score_id}")
async def update_score(score_id: int, request: Request, db: Session = Depends(get_db), _=Depends(require_auth)):
    body = await request.json()
    new_score = body.get("score")
    score = db.query(ChecktestScore).filter(ChecktestScore.id == score_id).first()
    if not score:
        return JSONResponse({"error": "not found"}, status_code=404)
    score.score = int(new_score) if new_score is not None and str(new_score).strip() != "" else None
    score.edited = 1
    score.flag = ""
    page = score.page
    all_scores = db.query(ChecktestScore).filter(ChecktestScore.page_id == page.id).all()
    if all(s.score is not None for s in all_scores):
        page.total_mark = sum(s.score for s in all_scores)
    else:
        page.total_mark = None
    db.commit()
    return JSONResponse({"ok": True, "total_mark": page.total_mark})


@router.put("/api/scan/pages/{page_id}/student")
async def match_student(page_id: int, request: Request, db: Session = Depends(get_db), _=Depends(require_auth)):
    body = await request.json()
    student_id = body.get("student_id") or None
    page = db.query(ChecktestPage).filter(ChecktestPage.id == page_id).first()
    if not page:
        return JSONResponse({"error": "not found"}, status_code=404)
    page.student_id = student_id
    db.commit()
    return JSONResponse({"ok": True})


@router.post("/api/scan/{session_id}/confirm")
async def confirm_session(request: Request, session_id: int, db: Session = Depends(get_db), _=Depends(require_auth)):
    session = db.query(ChecktestSession).filter(ChecktestSession.id == session_id).first()
    if not session:
        return JSONResponse({"error": "not found"}, status_code=404)
    session.status = "confirmed"
    db.commit()
    return _redirect(request, f"checktest/results/sessions/{session_id}")


@router.get("/api/scan/debug/{session_id}/{page_num}/{img_type}")
async def debug_image(session_id: int, page_num: int, img_type: str, _=Depends(require_auth)):
    """デバッグ画像を返す (img_type: sheet or detected)"""
    if img_type not in ("sheet", "detected"):
        return JSONResponse({"error": "invalid type"}, status_code=400)
    path = DEBUG_IMG_DIR / str(session_id) / f"page_{page_num:03d}_{img_type}.jpg"
    if not path.exists():
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(str(path), media_type="image/jpeg")
