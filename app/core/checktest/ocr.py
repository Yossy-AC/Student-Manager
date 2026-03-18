"""OCR（氏名・合計）"""

import logging

import cv2
import numpy as np

from .constants import OCR_CONF_MIN

log = logging.getLogger(__name__)


def ocr_name_and_total(img: np.ndarray, table: tuple) -> tuple:
    """
    テーブル下の氏名欄・合計欄を OCR する。
    pytesseract が未インストールの場合はスキップ。

    Returns: (name: str, total: int|None, needs_check: bool)
    """
    try:
        import pytesseract  # noqa: F401
    except ImportError:
        log.warning("pytesseract 未インストール。OCR をスキップします（氏名は『不明』）。")
        return "不明", None, True

    tx, ty, tw, th = table
    h_img = img.shape[0]

    # 氏名・合計欄: テーブル直下の帯状領域（テーブル高さの最大 25%）
    box_y = ty + th
    box_h = min(int(th * 0.25), h_img - box_y)
    if box_h <= 0:
        return "不明", None, True

    # 氏名: テーブル左側 0〜50%
    name_roi = img[box_y:box_y + box_h, tx:tx + int(tw * 0.50)]
    # 合計: テーブル中央右寄り 55〜85%
    total_roi = img[box_y:box_y + box_h, tx + int(tw * 0.55):tx + int(tw * 0.85)]

    name, name_low_conf = _ocr_region(name_roi, lang="jpn", config="--psm 7")
    total_str, _ = _ocr_region(
        total_roi, lang="eng",
        config="--psm 7 -c tessedit_char_whitelist=0123456789",
    )
    total = int(total_str) if total_str.isdigit() else None

    if not name:
        name = "不明"
        name_low_conf = True

    return name, total, name_low_conf


def _ocr_region(roi: np.ndarray, lang: str = "jpn", config: str = "--psm 7") -> tuple:
    """ROI 画像を OCR して (text, low_confidence) を返す"""
    try:
        import pytesseract
    except ImportError:
        return "", True

    gray = cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY) if len(roi.shape) == 3 else roi
    _, binary = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)

    try:
        data = pytesseract.image_to_data(
            binary, lang=lang, config=config,
            output_type=pytesseract.Output.DICT,
        )
        texts, confs = [], []
        for t, c in zip(data["text"], data["conf"]):
            t = t.strip()
            if t:
                texts.append(t)
                confs.append(int(c))
        text = " ".join(texts).strip()
        avg_conf = sum(confs) / len(confs) if confs else 0
        return text, avg_conf < OCR_CONF_MIN
    except Exception as e:
        log.debug(f"OCR 失敗: {e}")
        return "", True
