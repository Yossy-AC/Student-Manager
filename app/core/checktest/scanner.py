"""PDF→画像変換、採点欄領域検出"""

import logging
from typing import Optional

import cv2
import fitz  # PyMuPDF
import numpy as np

from .constants import DEFAULT_DPI

log = logging.getLogger(__name__)


def pdf_to_images(
    pdf_path: str,
    dpi: int = DEFAULT_DPI,
    page_list: Optional[list] = None,
) -> list:
    """PDF 各ページを numpy 配列 (RGB) に変換して返す（PyMuPDF 使用）"""
    log.info(f"PDF 変換: {pdf_path} @ {dpi}dpi")
    doc = fitz.open(pdf_path)
    scale = dpi / 72.0
    mat = fitz.Matrix(scale, scale)
    images = []
    for i, page in enumerate(doc):
        page_num_1based = i + 1
        if page_list and page_num_1based not in page_list:
            continue
        pix = page.get_pixmap(matrix=mat)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        if pix.n == 4:   # RGBA → RGB
            img = img[:, :, :3]
        images.append(img)
    doc.close()
    log.info(f"  {len(images)} ページ読み込み完了")
    return images


def get_score_sheet(img: np.ndarray, no_crop: bool = False) -> np.ndarray:
    """
    採点シート画像を返す。
    - landscape（幅 > 高さ）かつ no_crop=False → 右半分を切り出す（B4 横置きスキャン）
    - portrait または no_crop=True → そのまま返す
    """
    h, w = img.shape[:2]
    if no_crop or h >= w:
        return img.copy()
    return img[:, w // 2:].copy()


def find_answer_table(img_rgb: np.ndarray) -> Optional[tuple]:
    """
    採点欄テーブルの外接矩形 (x, y, w, h) を検出する。
    ページ下 60% から最大面積のグリッド構造を探す。
    Returns None if not found.
    """
    h, w = img_rgb.shape[:2]
    gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)

    # 上 40% を除いた領域を検索（テーブルは下部に固定）
    search_start = h * 4 // 10
    region = gray[search_start:]
    rh, rw = region.shape

    _, binary = cv2.threshold(region, 180, 255, cv2.THRESH_BINARY_INV)

    # 水平線検出（テーブルの行区切り）
    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(rw // 5, 10), 2))
    h_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, h_kernel)

    # 垂直線検出
    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, max(rh // 25, 5)))
    v_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, v_kernel)

    # グリッド = 水平 + 垂直線 → 膨張して輪郭をつなぐ
    grid = cv2.add(h_lines, v_lines)
    dk = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
    dilated = cv2.dilate(grid, dk, iterations=3)

    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    best = None
    best_area = 0
    for cnt in contours:
        x, y, cw, ch = cv2.boundingRect(cnt)
        if cw < rw * 0.4:
            continue
        area = cw * ch
        if area > best_area:
            best = (x, y + search_start, cw, ch)
            best_area = area

    if best is None:
        log.warning("テーブルを検出できませんでした")
    return best
