"""マーク検出"""

import logging
import os
from typing import Optional

import cv2
import numpy as np

from .constants import DEFAULT_MARK_THRESH, LABEL_COL_RATIO, N_VALUE_COLS

log = logging.getLogger(__name__)


def _crop_cell(img: np.ndarray, x: int, y: int, w: int, h: int, margin: int = 4) -> np.ndarray:
    """座標 (x, y, w, h) のセル画像を余白付きで切り出す"""
    ih, iw = img.shape[:2]
    y1, y2 = max(0, y + margin), min(ih, y + h - margin)
    x1, x2 = max(0, x + margin), min(iw, x + w - margin)
    return img[y1:y2, x1:x2]


def is_marked(cell_rgb: np.ndarray, threshold: float) -> bool:
    """黒ピクセル占有率が threshold を超えるか判定"""
    if cell_rgb.size == 0:
        return False
    gray = cv2.cvtColor(cell_rgb, cv2.COLOR_RGB2GRAY) if len(cell_rgb.shape) == 3 else cell_rgb
    _, bw = cv2.threshold(gray, 128, 255, cv2.THRESH_BINARY_INV)
    return (bw.sum() / (255 * bw.size)) > threshold


def detect_scores(
    img: np.ndarray,
    table: tuple,
    questions: list,
    thresh: float = DEFAULT_MARK_THRESH,
    debug_path: Optional[str] = None,
) -> tuple:
    """
    テーブル内の各大問のマークを検出する。

    テーブル構造（1大問あたり）:
        | □N | [0] [1] ... [10] |   ← Row 1（値 0〜10）
        |    | [11][12]...[max] |   ← Row 2（値 11〜max_score、max_score>10 の場合）

    Returns:
        scores: list[int | None]  得点（複数塗りは None、未記入は 0）
        flags:  list[str]         フラグ（"複数塗り" or ""）
    """
    tx, ty, tw, th = table
    n_q = len(questions)

    label_w = int(tw * LABEL_COL_RATIO)
    cell_w = (tw - label_w) / N_VALUE_COLS
    block_h = th / n_q
    row_h = block_h / 2

    debug_img = img.copy() if debug_path else None
    if debug_img is not None:
        cv2.rectangle(debug_img, (tx, ty), (tx + tw, ty + th), (0, 0, 255), 3)

    scores: list = []
    flags: list = []

    for qi, q in enumerate(questions):
        max_score = q["max_score"]
        block_y = ty + int(qi * block_h)
        row1_y = block_y
        row2_y = block_y + int(row_h)

        marked: list = []

        # Row 1: 値 0 〜 min(10, max_score)
        n_row1 = min(N_VALUE_COLS, max_score + 1)
        for ci in range(n_row1):
            cx = tx + label_w + int(ci * cell_w)
            cell = _crop_cell(img, cx, row1_y, int(cell_w), int(row_h))
            hit = is_marked(cell, thresh)
            if hit:
                marked.append(ci)
            if debug_img is not None:
                color = (220, 50, 50) if hit else (50, 200, 50)
                cv2.rectangle(
                    debug_img,
                    (cx, row1_y),
                    (cx + int(cell_w), row1_y + int(row_h)),
                    color, 1,
                )

        # Row 2: 値 11 〜 max_score（max_score > 10 のとき）
        if max_score > 10:
            n_row2 = max_score - 10
            for ci in range(n_row2):
                val = 11 + ci
                cx = tx + label_w + int(ci * cell_w)
                cell = _crop_cell(img, cx, row2_y, int(cell_w), int(row_h))
                hit = is_marked(cell, thresh)
                if hit:
                    marked.append(val)
                if debug_img is not None:
                    color = (220, 50, 50) if hit else (50, 200, 50)
                    cv2.rectangle(
                        debug_img,
                        (cx, row2_y),
                        (cx + int(cell_w), row2_y + int(row_h)),
                        color, 1,
                    )

        if len(marked) == 0:
            scores.append(0)
            flags.append("")
        elif len(marked) == 1:
            scores.append(marked[0])
            flags.append("")
        else:
            scores.append(None)
            flags.append("複数塗り")
            log.warning(f"  大問{qi + 1} ({q['label']}): 複数塗り {marked}")

    if debug_path and debug_img is not None:
        os.makedirs(os.path.dirname(os.path.abspath(debug_path)), exist_ok=True)
        cv2.imwrite(debug_path, cv2.cvtColor(debug_img, cv2.COLOR_RGB2BGR))
        log.debug(f"  デバッグ画像: {debug_path}")

    return scores, flags
