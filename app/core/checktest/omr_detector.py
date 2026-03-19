"""OMR方式マーク検出

テンプレートPDFの座標マップを使い、スキャン画像からスコアを読み取る。

処理フロー:
1. QRコード検出 → config_id 取得
2. 四隅アライメントマーカー検出
3. 透視変換で画像を正規化
4. テンプレート座標に基づきバブル塗りつぶし率を判定
5. スコア抽出
"""

import json
import logging
import os
from typing import Optional

import cv2
import numpy as np

from .constants import DEFAULT_DPI, OMR_MARK_THRESH, OMR_MARKER_SIZE_MM
from .detector import _find_marked_cells

log = logging.getLogger(__name__)

# 1mm = 2.834645669 pt (ReportLab)
_PT_PER_MM = 2.834645669


def detect_qr(img: np.ndarray) -> Optional[int]:
    """スキャン画像からQRコードを読み取り、config_id を返す。

    OpenCV の QRCodeDetector を使用（追加依存なし）。
    検出失敗時は None。
    """
    detector = cv2.QRCodeDetector()
    data, points, _ = detector.detectAndDecode(img)
    if not data:
        return None
    try:
        parsed = json.loads(data)
        return int(parsed["config_id"])
    except (json.JSONDecodeError, KeyError, ValueError, TypeError):
        log.warning(f"QRコードのパース失敗: {data!r}")
        return None


def find_alignment_markers(
    img: np.ndarray,
    expected_size_px: float = OMR_MARKER_SIZE_MM * _PT_PER_MM * DEFAULT_DPI / 72,
) -> Optional[list[tuple[float, float]]]:
    """四隅の黒正方形マーカーを検出する。

    Args:
        img: RGB画像
        expected_size_px: マーカーの期待辺長(px)。デフォルト8mm@300DPI≈94.5px

    Returns:
        [TL, TR, BL, BR] の中心座標(cx, cy)リスト、または None
    """
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY) if len(img.shape) == 3 else img
    _, binary = cv2.threshold(gray, 128, 255, cv2.THRESH_BINARY_INV)

    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    expected_area = expected_size_px ** 2
    area_lo = expected_area * 0.3
    area_hi = expected_area * 2.5

    h, w = img.shape[:2]

    candidates = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < area_lo or area > area_hi:
            continue

        x, y, bw, bh = cv2.boundingRect(cnt)
        # アスペクト比フィルタ（正方形に近い）
        aspect = bw / bh if bh > 0 else 0
        if aspect < 0.6 or aspect > 1.7:
            continue

        # 充填率フィルタ（黒く塗りつぶされた正方形）
        fill_rate = area / (bw * bh) if bw * bh > 0 else 0
        if fill_rate < 0.7:
            continue

        cx = x + bw / 2
        cy = y + bh / 2
        candidates.append((cx, cy, area))

    if len(candidates) < 4:
        log.warning(f"マーカー候補が4つ未満: {len(candidates)}個")
        return None

    # ページ四隅に最も近い候補を選出
    corners = [
        (0, 0),          # TL
        (w, 0),          # TR
        (0, h),          # BL
        (w, h),          # BR
    ]

    result = []
    used = set()
    for corner_x, corner_y in corners:
        best_idx = -1
        best_dist = float("inf")
        for i, (cx, cy, _) in enumerate(candidates):
            if i in used:
                continue
            dist = (cx - corner_x) ** 2 + (cy - corner_y) ** 2
            if dist < best_dist:
                best_dist = dist
                best_idx = i
        if best_idx < 0:
            log.warning("マーカーの四隅割当に失敗")
            return None
        used.add(best_idx)
        result.append((candidates[best_idx][0], candidates[best_idx][1]))

    return result  # [TL, TR, BL, BR]


def _coords_to_pixels(
    coords: dict,
    dpi: int = DEFAULT_DPI,
) -> tuple[np.ndarray, dict, tuple[int, int]]:
    """テンプレート座標(ReportLab points, 原点左下)をピクセル座標(原点左上)に変換。

    Returns:
        (expected_marker_centers_4x2, bubbles_px, output_size_wh)
    """
    scale = dpi / 72.0
    page_w_pt = coords["page_size"]["w"]
    page_h_pt = coords["page_size"]["h"]

    output_w = int(page_w_pt * scale)
    output_h = int(page_h_pt * scale)

    # マーカー中心 → ピクセル
    marker_centers = []
    for m in coords["markers"]:
        cx = (m["x"] + m["w"] / 2) * scale
        cy = (page_h_pt - m["y"] - m["h"] / 2) * scale
        marker_centers.append([cx, cy])

    expected_markers = np.array(marker_centers, dtype=np.float32)

    # バブル → ピクセル
    bubbles_px: dict[str, list[dict]] = {}
    for q_key, bubbles in coords["bubbles"].items():
        q_list = []
        for b in bubbles:
            q_list.append({
                "value": b["value"],
                "cx": b["cx"] * scale,
                "cy": (page_h_pt - b["cy"]) * scale,
                "r": b["r"] * scale,
            })
        bubbles_px[q_key] = q_list

    return expected_markers, bubbles_px, (output_w, output_h)


def rectify_image(
    img: np.ndarray,
    detected_markers: list[tuple[float, float]],
    expected_markers: np.ndarray,
    output_size: tuple[int, int],
) -> np.ndarray:
    """透視変換で画像を正規化する。

    Args:
        img: 入力画像
        detected_markers: 検出されたマーカー中心 [TL, TR, BL, BR]
        expected_markers: テンプレート上の期待マーカー中心 (4x2)
        output_size: 出力画像サイズ (w, h)

    Returns:
        正規化された画像
    """
    src = np.array(detected_markers, dtype=np.float32)
    dst = expected_markers

    M = cv2.getPerspectiveTransform(src, dst)
    rectified = cv2.warpPerspective(img, M, output_size)
    return rectified


def detect_bubble_fills(
    rectified_gray: np.ndarray,
    bubbles_px: dict[str, list[dict]],
    questions: list[dict],
    thresh: float = OMR_MARK_THRESH,
) -> tuple[list[Optional[int]], list[str]]:
    """バブルの塗りつぶし率を検出し、スコアとフラグを返す。

    Args:
        rectified_gray: 透視変換後のグレースケール画像
        bubbles_px: {"Q0": [{"value", "cx", "cy", "r"}, ...], ...}
        questions: [{"label": str, "max_score": int}, ...]
        thresh: 塗りつぶし判定閾値

    Returns:
        (scores, flags) — 各大問のスコアとフラグ
    """
    h, w = rectified_gray.shape[:2]
    scores: list[Optional[int]] = []
    flags: list[str] = []

    for qi, q in enumerate(questions):
        q_key = f"Q{qi}"
        bubbles = bubbles_px.get(q_key, [])
        if not bubbles:
            scores.append(None)
            flags.append("バブル未定義")
            continue

        # 各バブルの塗りつぶし率を計算
        ratios = []
        for b in bubbles:
            cx, cy, r = int(round(b["cx"])), int(round(b["cy"])), int(round(b["r"]))

            # 画像範囲外チェック
            if cx - r < 0 or cy - r < 0 or cx + r >= w or cy + r >= h:
                ratios.append(0.0)
                continue

            # 円形マスクでROI抽出
            mask = np.zeros((2 * r + 1, 2 * r + 1), dtype=np.uint8)
            cv2.circle(mask, (r, r), r, 255, -1)

            roi = rectified_gray[cy - r: cy + r + 1, cx - r: cx + r + 1]
            if roi.shape[0] != mask.shape[0] or roi.shape[1] != mask.shape[1]:
                ratios.append(0.0)
                continue

            # 黒ピクセル率
            _, bw = cv2.threshold(roi, 128, 255, cv2.THRESH_BINARY_INV)
            masked = cv2.bitwise_and(bw, mask)
            fill_rate = float(masked.sum()) / float(mask.sum()) if mask.sum() > 0 else 0.0
            ratios.append(fill_rate)

        # マーク検出（既存ロジック再利用: 固定閾値 + 適応的フォールバック）
        marked_indices = _find_marked_cells(ratios, thresh)

        # インデックス → 値
        marked_values = [bubbles[i]["value"] for i in marked_indices if i < len(bubbles)]

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

    return scores, flags


def process_omr(
    img: np.ndarray,
    coords: dict,
    questions: list[dict],
    thresh: float = OMR_MARK_THRESH,
    debug_path: Optional[str] = None,
) -> tuple[list[Optional[int]], list[str]]:
    """OMR方式のメインエントリポイント。

    Args:
        img: スキャン画像（RGB、クロップ済み）
        coords: テンプレート座標マップ（generate_template_pdf の戻り値）
        questions: [{"label": str, "max_score": int}, ...]
        thresh: 塗りつぶし判定閾値
        debug_path: デバッグ画像保存先パス（None=保存しない）

    Returns:
        (scores, flags) — 各大問のスコアとフラグ
    """
    # 座標変換
    expected_markers, bubbles_px, output_size = _coords_to_pixels(coords)

    # マーカー検出
    markers = find_alignment_markers(img)
    if markers is None:
        log.error("アライメントマーカー検出失敗")
        return [None] * len(questions), ["マーカー未検出"] * len(questions)

    # 透視変換
    rectified = rectify_image(img, markers, expected_markers, output_size)
    rectified_gray = cv2.cvtColor(rectified, cv2.COLOR_RGB2GRAY)

    # デバッグ画像（透視変換後 + バブル検出結果）
    debug_img = rectified.copy() if debug_path else None

    # バブル検出
    scores, flags = detect_bubble_fills(rectified_gray, bubbles_px, questions, thresh)

    # デバッグ画像描画
    if debug_img is not None and debug_path:
        # マーカー位置を描画（変換後の期待位置）
        for mx, my in expected_markers:
            cv2.drawMarker(debug_img, (int(mx), int(my)), (255, 0, 0),
                           cv2.MARKER_CROSS, 20, 2)

        # バブル状態を描画
        for qi in range(len(questions)):
            q_key = f"Q{qi}"
            bubbles = bubbles_px.get(q_key, [])

            # 各バブルの塗りつぶし率を再計算（表示用）
            for b in bubbles:
                cx, cy, r = int(round(b["cx"])), int(round(b["cy"])), int(round(b["r"]))
                value = b["value"]

                # 塗りつぶし率を再計算
                h_img, w_img = rectified_gray.shape[:2]
                if cx - r >= 0 and cy - r >= 0 and cx + r < w_img and cy + r < h_img:
                    mask = np.zeros((2 * r + 1, 2 * r + 1), dtype=np.uint8)
                    cv2.circle(mask, (r, r), r, 255, -1)
                    roi = rectified_gray[cy - r: cy + r + 1, cx - r: cx + r + 1]
                    if roi.shape == mask.shape:
                        _, bw = cv2.threshold(roi, 128, 255, cv2.THRESH_BINARY_INV)
                        fill = float(cv2.bitwise_and(bw, mask).sum()) / float(mask.sum())
                    else:
                        fill = 0.0
                else:
                    fill = 0.0

                is_marked = fill > thresh
                color = (220, 50, 50) if is_marked else (50, 200, 50)
                cv2.circle(debug_img, (cx, cy), r, color, 2 if is_marked else 1)
                cv2.putText(debug_img, f"{value}:{fill:.2f}",
                            (cx - r, cy - r - 3),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.3, color, 1)

        os.makedirs(os.path.dirname(os.path.abspath(debug_path)), exist_ok=True)
        cv2.imwrite(debug_path, cv2.cvtColor(debug_img, cv2.COLOR_RGB2BGR))
        log.debug(f"  OMRデバッグ画像: {debug_path}")

    return scores, flags
