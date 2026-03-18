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


def _cell_ratio(cell_rgb: np.ndarray) -> float:
    """セル内の黒ピクセル占有率を返す"""
    if cell_rgb.size == 0:
        return 0.0
    gray = cv2.cvtColor(cell_rgb, cv2.COLOR_RGB2GRAY) if len(cell_rgb.shape) == 3 else cell_rgb
    _, bw = cv2.threshold(gray, 128, 255, cv2.THRESH_BINARY_INV)
    return float(bw.sum() / (255 * bw.size))


def is_marked(cell_rgb: np.ndarray, threshold: float) -> bool:
    """黒ピクセル占有率が threshold を超えるか判定"""
    return _cell_ratio(cell_rgb) > threshold


def _find_marked_cells(ratios: list[float], thresh: float) -> list[int]:
    """
    セル比率リストからマークされたセルを特定する。
    固定閾値で検出し、見つからない場合は適応的閾値（中央値の2.5倍）でフォールバック。
    """
    # 固定閾値で検出
    marked = [i for i, r in enumerate(ratios) if r > thresh]
    if marked:
        return marked

    # 適応的閾値: 中央値の2.5倍かつ最低0.08
    if not ratios:
        return []
    median = sorted(ratios)[len(ratios) // 2]
    adaptive_thresh = max(median * 2.5, 0.08)
    marked = [i for i, r in enumerate(ratios) if r > adaptive_thresh]

    # 適応的検出で2つ以上見つかった場合、最大値のみ採用（隣接セルへのはみ出し対策）
    if len(marked) >= 2:
        max_ratio = max(ratios[i] for i in marked)
        # 最大値の70%未満のものは除外
        marked = [i for i in marked if ratios[i] >= max_ratio * 0.7]

    return marked


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
        cv2.rectangle(debug_img, (tx, ty), (tx + tw, ty + th), (255, 0, 0), 3)

    scores: list = []
    flags: list = []

    for qi, q in enumerate(questions):
        max_score = q["max_score"]
        block_y = ty + int(qi * block_h)
        row1_y = block_y
        row2_y = block_y + int(row_h)

        # Row 1: 値 0 〜 min(10, max_score) の比率を収集
        n_row1 = min(N_VALUE_COLS, max_score + 1)
        row1_ratios = []
        row1_coords = []
        for ci in range(n_row1):
            cx = tx + label_w + int(ci * cell_w)
            cell = _crop_cell(img, cx, row1_y, int(cell_w), int(row_h))
            row1_ratios.append(_cell_ratio(cell))
            row1_coords.append(cx)

        # Row 2: 値 11 〜 max_score の比率を収集
        row2_ratios = []
        row2_coords = []
        if max_score > 10:
            n_row2 = max_score - 10
            for ci in range(n_row2):
                cx = tx + label_w + int(ci * cell_w)
                cell = _crop_cell(img, cx, row2_y, int(cell_w), int(row_h))
                row2_ratios.append(_cell_ratio(cell))
                row2_coords.append(cx)

        # 全セルの比率を結合してマーク検出
        all_ratios = row1_ratios + row2_ratios
        marked_indices = _find_marked_cells(all_ratios, thresh)

        # インデックスを値に変換
        marked_values = []
        for idx in marked_indices:
            if idx < len(row1_ratios):
                marked_values.append(idx)  # Row 1: 値 = インデックス
            else:
                marked_values.append(11 + (idx - len(row1_ratios)))  # Row 2: 値 11+

        # デバッグ画像描画
        if debug_img is not None:
            for ci in range(n_row1):
                cx = row1_coords[ci]
                hit = ci in marked_indices
                color = (220, 50, 50) if hit else (50, 200, 50)
                cv2.rectangle(
                    debug_img,
                    (cx, row1_y),
                    (cx + int(cell_w), row1_y + int(row_h)),
                    color, 2 if hit else 1,
                )
                # 比率テキスト
                ratio_text = f"{row1_ratios[ci]:.2f}"
                cv2.putText(debug_img, ratio_text, (cx + 2, row1_y + 15),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.35, color, 1)

            for ci in range(len(row2_ratios)):
                cx = row2_coords[ci]
                idx = len(row1_ratios) + ci
                hit = idx in marked_indices
                color = (220, 50, 50) if hit else (50, 200, 50)
                cv2.rectangle(
                    debug_img,
                    (cx, row2_y),
                    (cx + int(cell_w), row2_y + int(row_h)),
                    color, 2 if hit else 1,
                )
                ratio_text = f"{row2_ratios[ci]:.2f}"
                cv2.putText(debug_img, ratio_text, (cx + 2, row2_y + 15),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.35, color, 1)

        # スコア判定
        if len(marked_values) == 0:
            scores.append(0)
            flags.append("")
        elif len(marked_values) == 1:
            scores.append(marked_values[0])
            flags.append("")
        else:
            scores.append(None)
            flags.append("複数塗り")
            log.warning(f"  大問{qi + 1} ({q['label']}): 複数塗り {marked_values}")

    if debug_path and debug_img is not None:
        os.makedirs(os.path.dirname(os.path.abspath(debug_path)), exist_ok=True)
        cv2.imwrite(debug_path, cv2.cvtColor(debug_img, cv2.COLOR_RGB2BGR))
        log.debug(f"  デバッグ画像: {debug_path}")

    return scores, flags
