"""ページ処理パイプライン"""

import json
import logging
import os
from typing import Optional

import cv2
import numpy as np

from .constants import DEFAULT_MARK_THRESH
from .detector import detect_scores
from .ocr import ocr_name_and_total
from .scanner import find_answer_table, get_score_sheet

log = logging.getLogger(__name__)


def load_config(path: str) -> dict:
    """クラス設定 JSON を読み込む"""
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    for k in ("class_name", "questions"):
        if k not in cfg:
            raise ValueError(f"config に必須キーがありません: {k}")
    cfg["total_max"] = sum(q["max_score"] for q in cfg["questions"])
    return cfg


def process_page(
    img: np.ndarray,
    config: dict,
    page_num: int,
    thresh: float = DEFAULT_MARK_THRESH,
    no_crop: bool = False,
    debug_dir: Optional[str] = None,
) -> dict:
    """
    1ページを処理して結果辞書を返す。

    Returns dict with keys:
        page, name, scores, total_mark, total_written, flags, page_flag
    """
    log.info(f"ページ {page_num} 処理中...")
    questions = config["questions"]

    # 採点シート取得
    sheet = get_score_sheet(img, no_crop=no_crop)

    # デバッグ: クロップ後画像を保存
    if debug_dir:
        os.makedirs(debug_dir, exist_ok=True)
        crop_path = os.path.join(debug_dir, f"page_{page_num:03d}_sheet.jpg")
        cv2.imwrite(crop_path, cv2.cvtColor(sheet, cv2.COLOR_RGB2BGR))

    # テーブル検出
    table = find_answer_table(sheet)
    if table is None:
        log.warning(f"  ページ {page_num}: テーブル未検出 → スキップ")
        return fail_result(page_num, len(questions))

    log.info(f"  テーブル: x={table[0]}, y={table[1]}, w={table[2]}, h={table[3]}")

    # マーク検出
    debug_path = None
    if debug_dir:
        debug_path = os.path.join(debug_dir, f"page_{page_num:03d}_detected.jpg")

    scores, flags = detect_scores(sheet, table, questions, thresh=thresh, debug_path=debug_path)

    # OCR（氏名・合計）
    name, total_written, needs_check = ocr_name_and_total(sheet, table)

    # マーク検出合計
    total_mark = sum(s for s in scores if s is not None) if all(s is not None for s in scores) else None

    # ページフラグ
    flag_parts = []
    if needs_check:
        flag_parts.append("要確認")
    if any(f == "複数塗り" for f in flags):
        flag_parts.append("複数塗り")
    if total_mark is not None and total_written is not None and total_mark != total_written:
        flag_parts.append("合計不一致")
    page_flag = " / ".join(flag_parts) if flag_parts else "正常"

    log.info(f"  結果: {name} | 得点={scores} | 合計={total_mark} | フラグ={page_flag}")

    return {
        "page": page_num,
        "name": name,
        "scores": scores,
        "total_mark": total_mark,
        "total_written": total_written,
        "flags": flags,
        "page_flag": page_flag,
    }


def fail_result(page_num: int, n_questions: int) -> dict:
    """読み取り失敗時の結果辞書"""
    return {
        "page": page_num,
        "name": "不明",
        "scores": [None] * n_questions,
        "total_mark": None,
        "total_written": None,
        "flags": [""] * n_questions,
        "page_flag": "読み取り失敗",
    }
