"""OMR テンプレート PDF 生成

テスト設定（大問数・配点）からOMR採点欄テンプレートPDFを生成する。
生成したPDFをWordに貼り付けて印刷・配布する運用。

レイアウト:
- 四隅にアライメントマーカー（黒正方形）
- 左上にQRコード（config_id エンコード）
- 大問ごとに塗りつぶし円（0〜max_score）を1行または2行で配置
- 下部に氏名欄・コメント欄
"""

import io
import json
import logging
import os
from typing import Any

import qrcode
from reportlab.lib.pagesizes import B5
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from .constants import (
    OMR_BUBBLE_DIAMETER_MM,
    OMR_BUBBLE_SPACING_MM,
    OMR_MARKER_SIZE_MM,
)

log = logging.getLogger(__name__)

# B5 縦 (182mm × 257mm) — B4見開きの右半分相当
PAGE_W, PAGE_H = B5

# マージン
MARGIN_TOP = 15 * mm
MARGIN_BOTTOM = 12 * mm
MARGIN_LEFT = 12 * mm
MARGIN_RIGHT = 12 * mm

# マーカー
MARKER = OMR_MARKER_SIZE_MM * mm

# バブル
BUBBLE_R = OMR_BUBBLE_DIAMETER_MM * mm / 2
BUBBLE_SPACING = OMR_BUBBLE_SPACING_MM * mm
MAX_BUBBLES_PER_ROW = 11  # 0〜10 の 11 個

# QRコード
QR_SIZE = 20 * mm

# 日本語フォント
_JP_FONT_NAME = "Gothic"
_JP_FONT_REGISTERED = False


def _register_jp_font():
    """Windows日本語フォントを登録（初回のみ）"""
    global _JP_FONT_REGISTERED, _JP_FONT_NAME
    if _JP_FONT_REGISTERED:
        return
    font_path = os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", "msgothic.ttc")
    if os.path.exists(font_path):
        pdfmetrics.registerFont(TTFont(_JP_FONT_NAME, font_path, subfontIndex=0))
    else:
        _JP_FONT_NAME = "Helvetica"
    _JP_FONT_REGISTERED = True


def generate_template_pdf(
    config_id: int,
    class_name: str,
    test_no: str,
    questions: list[dict[str, Any]],
) -> tuple[bytes, dict]:
    """
    OMRテンプレートPDFとバブル座標マップを生成する。

    Args:
        config_id: テスト設定ID
        class_name: クラス名（表示用）
        test_no: テスト番号（表示用）
        questions: [{"label": str, "max_score": int}, ...]

    Returns:
        (pdf_bytes, coords_map)
        coords_map: {"markers": [...], "bubbles": {"Q0": [{"value": 0, "cx": float, "cy": float}, ...], ...}}
    """
    _register_jp_font()
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=B5)

    # 座標マップ（OMR検出時に使用）
    coords: dict[str, Any] = {
        "page_size": {"w": float(PAGE_W), "h": float(PAGE_H)},
        "markers": [],
        "qr": {},
        "bubbles": {},
        "name_area": {},
        "comment_area": {},
    }

    # --- 四隅アライメントマーカー ---
    marker_positions = [
        (MARGIN_LEFT, PAGE_H - MARGIN_TOP - MARKER),                    # 左上
        (PAGE_W - MARGIN_RIGHT - MARKER, PAGE_H - MARGIN_TOP - MARKER), # 右上
        (MARGIN_LEFT, MARGIN_BOTTOM),                                    # 左下
        (PAGE_W - MARGIN_RIGHT - MARKER, MARGIN_BOTTOM),                # 右下
    ]
    for x, y in marker_positions:
        c.setFillColorRGB(0, 0, 0)
        c.rect(x, y, MARKER, MARKER, fill=1, stroke=0)
        coords["markers"].append({
            "x": float(x), "y": float(y),
            "w": float(MARKER), "h": float(MARKER),
        })

    # --- QRコード（左上マーカーの右隣） ---
    qr_data = json.dumps({"config_id": config_id})
    qr_img = _generate_qr_image(qr_data)
    qr_x = MARGIN_LEFT + MARKER + 3 * mm
    qr_y = PAGE_H - MARGIN_TOP - QR_SIZE
    c.drawInlineImage(qr_img, qr_x, qr_y, QR_SIZE, QR_SIZE)
    coords["qr"] = {"x": float(qr_x), "y": float(qr_y), "size": float(QR_SIZE)}

    # --- ヘッダー ---
    header_y = PAGE_H - MARGIN_TOP - MARKER - 2 * mm
    c.setFont(_JP_FONT_NAME, 9)
    c.drawString(qr_x + QR_SIZE + 5 * mm, header_y - 5 * mm, f"{class_name}  {test_no}")

    c.setFont(_JP_FONT_NAME, 7)
    c.drawString(qr_x + QR_SIZE + 5 * mm, header_y - 11 * mm,
                 "該当する得点の○を黒く塗りつぶしてください")

    # --- 採点欄ヘッダーの開始位置 ---
    content_top = header_y - 18 * mm
    content_left = MARGIN_LEFT + MARKER + 2 * mm
    content_right = PAGE_W - MARGIN_RIGHT - MARKER - 2 * mm
    available_width = content_right - content_left

    # --- 大問ごとのバブル配置 ---
    label_width = 22 * mm  # ラベル列幅
    bubble_area_left = content_left + label_width
    y_cursor = content_top

    for qi, q in enumerate(questions):
        label = q["label"]
        max_score = q["max_score"]

        # 必要な行数
        n_bubbles = max_score + 1  # 0〜max_score
        if n_bubbles <= MAX_BUBBLES_PER_ROW:
            n_rows = 1
        else:
            n_rows = 2

        row_height = BUBBLE_SPACING + 2 * mm
        block_height = n_rows * row_height

        # ラベル描画
        c.setFont(_JP_FONT_NAME, 8)
        label_y = y_cursor - row_height / 2 - 1 * mm
        c.setFillColorRGB(0, 0, 0)
        c.drawString(content_left, label_y, label)

        # バブル描画
        q_coords = []
        for i in range(n_bubbles):
            if i < MAX_BUBBLES_PER_ROW:
                row = 0
                col = i
            else:
                row = 1
                col = i - MAX_BUBBLES_PER_ROW

            cx = bubble_area_left + col * BUBBLE_SPACING + BUBBLE_SPACING / 2
            cy = y_cursor - row * row_height - row_height / 2

            # 円（塗りつぶし枠）
            c.setStrokeColorRGB(0, 0, 0)
            c.setFillColorRGB(1, 1, 1)
            c.setLineWidth(0.5)
            c.circle(cx, cy, BUBBLE_R, fill=1, stroke=1)

            # 値ラベル
            c.setFont(_JP_FONT_NAME, 5)
            c.setFillColorRGB(0.4, 0.4, 0.4)
            c.drawCentredString(cx, cy - 1.5 * mm, str(i))

            q_coords.append({
                "value": i,
                "cx": float(cx),
                "cy": float(cy),
                "r": float(BUBBLE_R),
            })

        coords["bubbles"][f"Q{qi}"] = q_coords
        y_cursor -= block_height + 3 * mm

    # --- 氏名欄 ---
    y_cursor -= 5 * mm
    name_y = y_cursor
    c.setFont(_JP_FONT_NAME, 8)
    c.setFillColorRGB(0, 0, 0)
    c.drawString(content_left, name_y, "氏 名:")
    name_box_x = content_left + 18 * mm
    name_box_w = available_width - 18 * mm
    name_box_h = 8 * mm
    c.setStrokeColorRGB(0, 0, 0)
    c.setLineWidth(0.3)
    c.rect(name_box_x, name_y - 2 * mm, name_box_w, name_box_h, fill=0, stroke=1)
    coords["name_area"] = {
        "x": float(name_box_x), "y": float(name_y - 2 * mm),
        "w": float(name_box_w), "h": float(name_box_h),
    }

    # --- コメント欄 ---
    y_cursor = name_y - name_box_h - 6 * mm
    comment_y = y_cursor
    c.setFont(_JP_FONT_NAME, 8)
    c.drawString(content_left, comment_y, "コメント:")
    comment_box_x = content_left
    comment_box_w = available_width
    comment_box_h = 20 * mm
    comment_box_y = comment_y - comment_box_h - 2 * mm
    c.rect(comment_box_x, comment_box_y, comment_box_w, comment_box_h, fill=0, stroke=1)
    coords["comment_area"] = {
        "x": float(comment_box_x), "y": float(comment_box_y),
        "w": float(comment_box_w), "h": float(comment_box_h),
    }

    c.save()
    pdf_bytes = buf.getvalue()

    log.info(f"OMRテンプレート生成: config_id={config_id}, {len(questions)}問, {len(pdf_bytes)} bytes")
    return pdf_bytes, coords


def _generate_qr_image(data: str):
    """QRコードをPIL Imageとして生成"""
    qr = qrcode.QRCode(version=1, box_size=10, border=1)
    qr.add_data(data)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white").get_image()
