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

# 幅は固定、高さはコンテンツに応じて動的算出
PAGE_W = 180 * mm

# マージン（コンパクト化）
MARGIN_TOP = 8 * mm
MARGIN_BOTTOM = 6 * mm
MARGIN_LEFT = 8 * mm
MARGIN_RIGHT = 8 * mm

# マーカー
MARKER = OMR_MARKER_SIZE_MM * mm

# バブル
BUBBLE_R = OMR_BUBBLE_DIAMETER_MM * mm / 2
BUBBLE_SPACING = OMR_BUBBLE_SPACING_MM * mm
MAX_BUBBLES_PER_ROW = 11  # 0〜10 の 11 個

# QRコード
QR_SIZE = 15 * mm

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

    # --- ページ高さを動的算出 ---
    row_height = BUBBLE_SPACING + 1 * mm
    label_col_w = 22 * mm
    field_box_h = 7 * mm

    # ヘッダー部: マージン + QR(マーカーより大) + 余白
    header_h = MARGIN_TOP + max(QR_SIZE, MARKER) + 2 * mm

    # 大問部（常に1行）
    questions_h = len(questions) * (row_height + 1 * mm)

    # 氏名+コメント部
    fields_h = 4 * mm + field_box_h + 2 * mm + field_box_h

    # フッター: マーカー + マージン
    footer_h = MARGIN_BOTTOM + MARKER + 2 * mm

    page_h = header_h + questions_h + fields_h + footer_h

    # --- Canvas作成 ---
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(PAGE_W, page_h))

    # 座標マップ（OMR検出時に使用）
    coords: dict[str, Any] = {
        "page_size": {"w": float(PAGE_W), "h": float(page_h)},
        "markers": [],
        "qr": {},
        "bubbles": {},
        "name_area": {},
        "comment_area": {},
    }

    # --- 四隅アライメントマーカー ---
    marker_positions = [
        (MARGIN_LEFT, page_h - MARGIN_TOP - MARKER),                    # 左上
        (PAGE_W - MARGIN_RIGHT - MARKER, page_h - MARGIN_TOP - MARKER), # 右上
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

    # --- QRコード・ヘッダー（上端をマーカー上端に揃える） ---
    top_line = page_h - MARGIN_TOP  # マーカー上端
    qr_data = json.dumps({"config_id": config_id})
    qr_img = _generate_qr_image(qr_data)
    qr_x = MARGIN_LEFT + MARKER + 3 * mm
    qr_y = top_line - QR_SIZE  # QR上端 = top_line
    c.drawInlineImage(qr_img, qr_x, qr_y, QR_SIZE, QR_SIZE)
    coords["qr"] = {"x": float(qr_x), "y": float(qr_y), "size": float(QR_SIZE)}

    # 講座名・回次（上端をマーカー上端に揃え）
    text_x = qr_x + QR_SIZE + 3 * mm
    c.setFont(_JP_FONT_NAME, 8)
    c.drawString(text_x, top_line - 3 * mm, f"{class_name}  {test_no}")

    c.setFont(_JP_FONT_NAME, 6)
    c.drawString(text_x, top_line - 8 * mm,
                 "該当する得点の○を黒く塗りつぶしてください")

    # --- 採点欄の開始位置 ---
    content_top = min(qr_y, top_line - MARKER) - 2 * mm
    content_left = MARGIN_LEFT + MARKER + 2 * mm
    content_right = PAGE_W - MARGIN_RIGHT - MARKER - 2 * mm
    available_width = content_right - content_left

    # --- 大問ごとのバブル配置 ---
    bubble_area_left = content_left + label_col_w
    y_cursor = content_top

    bubble_area_width = content_right - bubble_area_left

    for qi, q in enumerate(questions):
        label = q["label"]
        max_score = q["max_score"]

        n_bubbles = max_score + 1
        # 間隔を動的算出（全バブルが1行に収まるように）
        q_spacing = min(BUBBLE_SPACING, bubble_area_width / n_bubbles)

        # ラベル描画
        c.setFont(_JP_FONT_NAME, 8)
        label_y = y_cursor - row_height / 2 - 1 * mm
        c.setFillColorRGB(0, 0, 0)
        c.drawString(content_left, label_y, label)

        # バブル描画（常に1行）
        q_coords = []
        for i in range(n_bubbles):
            cx = bubble_area_left + i * q_spacing + q_spacing / 2
            cy = y_cursor - row_height / 2

            c.setStrokeColorRGB(0, 0, 0)
            c.setFillColorRGB(1, 1, 1)
            c.setLineWidth(0.5)
            c.circle(cx, cy, BUBBLE_R, fill=1, stroke=1)

            c.setFont(_JP_FONT_NAME, 4)
            c.setFillColorRGB(0.4, 0.4, 0.4)
            c.drawCentredString(cx, cy - 0.5 * mm, str(i))

            q_coords.append({
                "value": i,
                "cx": float(cx),
                "cy": float(cy),
                "r": float(BUBBLE_R),
            })

        coords["bubbles"][f"Q{qi}"] = q_coords
        y_cursor -= row_height + 1 * mm

    # --- 氏名欄（ラベルとボックスを縦中央揃え） ---
    y_cursor -= 4 * mm
    name_box_y = y_cursor - field_box_h
    name_box_x = content_left + label_col_w
    name_box_w = (available_width - label_col_w) / 4
    c.setStrokeColorRGB(0, 0, 0)
    c.setLineWidth(0.3)
    c.rect(name_box_x, name_box_y, name_box_w, field_box_h, fill=0, stroke=1)
    c.setFont(_JP_FONT_NAME, 8)
    c.setFillColorRGB(0, 0, 0)
    name_label_y = name_box_y + field_box_h / 2 - 1.2 * mm
    c.drawString(content_left, name_label_y, "氏 名:")
    coords["name_area"] = {
        "x": float(name_box_x), "y": float(name_box_y),
        "w": float(name_box_w), "h": float(field_box_h),
    }

    # --- コメント欄（ラベル右側にボックス、氏名欄と同レイアウト） ---
    y_cursor = name_box_y - 2 * mm
    comment_box_y = y_cursor - field_box_h
    comment_box_x = content_left + label_col_w
    comment_box_w = available_width - label_col_w
    c.rect(comment_box_x, comment_box_y, comment_box_w, field_box_h, fill=0, stroke=1)
    comment_label_y = comment_box_y + field_box_h / 2 - 1.2 * mm
    c.drawString(content_left, comment_label_y, "コメント:")
    coords["comment_area"] = {
        "x": float(comment_box_x), "y": float(comment_box_y),
        "w": float(comment_box_w), "h": float(field_box_h),
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
