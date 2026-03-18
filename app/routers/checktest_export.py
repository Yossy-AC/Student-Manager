"""Excel ダウンロード"""

import io
import os

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.config import TEMP_PDF_DIR
from app.database import get_db
from app.dependencies import require_auth
from app.models.checktest import ChecktestSession
from app.core.checktest.excel_writer import write_excel

router = APIRouter(tags=["checktest"])


@router.get("/api/export/{session_id}/excel")
async def download_excel(session_id: int, db: Session = Depends(get_db), _=Depends(require_auth)):
    session = db.query(ChecktestSession).filter(ChecktestSession.id == session_id).first()
    if not session:
        return Response("セッションが見つかりません", status_code=404)

    config = session.config
    questions = sorted(config.questions, key=lambda q: q.question_index)

    config_dict = {
        "class_name": config.class_id,
        "test_no": config.test_no,
        "questions": [{"label": q.label, "max_score": q.max_score} for q in questions],
        "total_max": sum(q.max_score for q in questions),
    }

    pages = sorted(session.pages, key=lambda p: p.page_number)
    results = []
    for p in pages:
        scores_list = sorted(p.scores, key=lambda s: s.question_index)
        results.append({
            "page": p.page_number,
            "name": p.student_name_ocr or "不明",
            "scores": [s.score for s in scores_list],
            "total_mark": p.total_mark,
            "total_written": p.total_written,
            "flags": [s.flag for s in scores_list],
            "page_flag": p.page_flag,
        })

    tmp_path = str(TEMP_PDF_DIR / f"session_{session_id}.xlsx")
    write_excel(results, config_dict, tmp_path)

    with open(tmp_path, "rb") as f:
        content = f.read()
    try:
        os.remove(tmp_path)
    except OSError:
        pass

    filename = f"checktest_{config.class_id}_{config.test_no}_{session.scan_date}.xlsx"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
