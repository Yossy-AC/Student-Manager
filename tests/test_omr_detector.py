"""OMR検出エンジンのユニットテスト

テンプレートPDF → 画像化 → OMR検出のパイプラインをテストする。
"""

import numpy as np
import cv2
import fitz  # PyMuPDF

from app.core.checktest.template_generator import generate_template_pdf
from app.core.checktest.omr_detector import (
    _coords_to_pixels,
    detect_bubble_fills,
    detect_qr,
    find_alignment_markers,
    process_omr,
    rectify_image,
)


def _template_to_image(pdf_bytes: bytes, dpi: int = 300) -> np.ndarray:
    """テンプレートPDFを画像(RGB numpy配列)に変換する"""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc[0]
    scale = dpi / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale))
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    if pix.n == 4:
        img = img[:, :, :3].copy()
    else:
        img = img.copy()
    doc.close()
    return img


def _make_template(questions=None):
    """テスト用テンプレートとそのメタデータを生成"""
    if questions is None:
        questions = [
            {"label": "大問1", "max_score": 10},
            {"label": "大問2", "max_score": 5},
        ]
    pdf_bytes, coords = generate_template_pdf(
        config_id=999, class_name="テスト", test_no="第1回", questions=questions,
    )
    img = _template_to_image(pdf_bytes)
    return img, coords, questions


class TestCoordConversion:
    """座標変換のテスト"""

    def test_marker_count(self):
        _, coords, _ = _make_template()
        expected_markers, bubbles_px, output_size = _coords_to_pixels(coords)
        assert expected_markers.shape == (4, 2)

    def test_bubble_count(self):
        questions = [{"label": "Q1", "max_score": 10}]
        _, coords, _ = _make_template(questions)
        _, bubbles_px, _ = _coords_to_pixels(coords)
        assert "Q0" in bubbles_px
        assert len(bubbles_px["Q0"]) == 11  # 0-10

    def test_output_size_positive(self):
        _, coords, _ = _make_template()
        _, _, output_size = _coords_to_pixels(coords)
        assert output_size[0] > 0 and output_size[1] > 0


class TestQRDetection:
    """QRコード検出のテスト"""

    def test_detect_qr_from_template(self):
        img, coords, _ = _make_template()
        config_id = detect_qr(img)
        assert config_id == 999

    def test_detect_qr_blank_image(self):
        blank = np.ones((500, 500, 3), dtype=np.uint8) * 255
        assert detect_qr(blank) is None


class TestMarkerDetection:
    """マーカー検出のテスト"""

    def test_find_markers_from_template(self):
        img, _, _ = _make_template()
        markers = find_alignment_markers(img)
        assert markers is not None
        assert len(markers) == 4

    def test_markers_in_correct_quadrants(self):
        img, _, _ = _make_template()
        h, w = img.shape[:2]
        markers = find_alignment_markers(img)
        assert markers is not None
        tl, tr, bl, br = markers
        # TL: 左上象限
        assert tl[0] < w / 2 and tl[1] < h / 2
        # TR: 右上象限
        assert tr[0] > w / 2 and tr[1] < h / 2
        # BL: 左下象限
        assert bl[0] < w / 2 and bl[1] > h / 2
        # BR: 右下象限
        assert br[0] > w / 2 and br[1] > h / 2

    def test_blank_image_returns_none(self):
        blank = np.ones((500, 500, 3), dtype=np.uint8) * 255
        assert find_alignment_markers(blank) is None


class TestRectification:
    """透視変換のテスト"""

    def test_rectify_identity(self):
        """マーカーが正確に期待位置にある場合、ほぼ恒等変換になる"""
        img, coords, _ = _make_template()
        expected_markers, _, output_size = _coords_to_pixels(coords)
        markers = find_alignment_markers(img)
        assert markers is not None

        rectified = rectify_image(img, markers, expected_markers, output_size)
        assert rectified.shape[0] == output_size[1]  # h
        assert rectified.shape[1] == output_size[0]  # w


class TestBubbleDetection:
    """バブル塗りつぶし検出のテスト"""

    def test_unfilled_template_all_zero(self):
        """未塗りテンプレート → 全スコア0"""
        img, coords, questions = _make_template()
        scores, flags = process_omr(img, coords, questions)

        # 未塗りなので全て0
        for s in scores:
            assert s == 0, f"未塗りなのにスコアが{s}"

    def test_filled_bubble_detected(self):
        """特定のバブルを塗りつぶし → 正しいスコアが検出される"""
        img, coords, questions = _make_template()
        expected_markers, bubbles_px, output_size = _coords_to_pixels(coords)

        # マーカー検出 → 透視変換
        markers = find_alignment_markers(img)
        assert markers is not None
        rectified = rectify_image(img, markers, expected_markers, output_size)

        # Q0のvalue=7のバブルを黒く塗る
        b = bubbles_px["Q0"][7]  # value=7
        cx, cy, r = int(round(b["cx"])), int(round(b["cy"])), int(round(b["r"]))
        cv2.circle(rectified, (cx, cy), r, (0, 0, 0), -1)

        # Q1のvalue=3のバブルを黒く塗る
        b1 = bubbles_px["Q1"][3]  # value=3
        cx1, cy1, r1 = int(round(b1["cx"])), int(round(b1["cy"])), int(round(b1["r"]))
        cv2.circle(rectified, (cx1, cy1), r1, (0, 0, 0), -1)

        # 変換後画像で直接バブル検出
        rectified_gray = cv2.cvtColor(rectified, cv2.COLOR_RGB2GRAY)
        scores, flags = detect_bubble_fills(rectified_gray, bubbles_px, questions)

        assert scores[0] == 7, f"Q0のスコアが{scores[0]}（期待: 7）"
        assert scores[1] == 3, f"Q1のスコアが{scores[1]}（期待: 3）"

    def test_multi_mark_detected(self):
        """2つ塗りつぶし → 複数塗りフラグ"""
        img, coords, questions = _make_template()
        expected_markers, bubbles_px, output_size = _coords_to_pixels(coords)

        markers = find_alignment_markers(img)
        assert markers is not None
        rectified = rectify_image(img, markers, expected_markers, output_size)

        # Q0のvalue=3とvalue=5を両方塗る
        for val in [3, 5]:
            b = bubbles_px["Q0"][val]
            cx, cy, r = int(round(b["cx"])), int(round(b["cy"])), int(round(b["r"]))
            cv2.circle(rectified, (cx, cy), r, (0, 0, 0), -1)

        rectified_gray = cv2.cvtColor(rectified, cv2.COLOR_RGB2GRAY)
        scores, flags = detect_bubble_fills(rectified_gray, bubbles_px, questions)

        assert scores[0] is None, "複数塗りでスコアがNoneになるはず"
        assert flags[0] == "複数塗り"


class TestProcessOMR:
    """process_omr 統合テスト"""

    def test_marker_not_found(self):
        """マーカーなし画像 → 全None + マーカー未検出フラグ"""
        blank = np.ones((500, 500, 3), dtype=np.uint8) * 255
        questions = [{"label": "Q1", "max_score": 10}]
        _, coords, _ = _make_template(questions)

        scores, flags = process_omr(blank, coords, questions)
        assert all(s is None for s in scores)
        assert all("マーカー未検出" in f for f in flags)

    def test_rotated_image_detection(self):
        """わずかに回転した画像でもマーカー検出できる"""
        img, coords, questions = _make_template()
        h, w = img.shape[:2]

        # 2度回転
        center = (w / 2, h / 2)
        M = cv2.getRotationMatrix2D(center, 2, 1.0)
        rotated = cv2.warpAffine(img, M, (w, h), borderValue=(255, 255, 255))

        markers = find_alignment_markers(rotated)
        assert markers is not None, "2度回転でもマーカーが検出されるべき"

    def test_template_download_endpoint(self):
        """テンプレートDLエンドポイントのインポートエラーがないことを確認"""
        from app.routers.checktest_configs import download_template  # noqa: F401
