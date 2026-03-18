"""定数定義"""

# マーク検出（旧方式）
DEFAULT_MARK_THRESH = 0.15   # マーク判定閾値（黒ピクセル占有率、適応的閾値のフォールバック付き）
DEFAULT_DPI = 300             # 処理解像度（固定推奨）
LABEL_COL_RATIO = 0.10        # □Nラベル列幅 / テーブル幅
N_VALUE_COLS = 11             # セル列数（値 0〜10 = 11列）
OCR_CONF_MIN = 60             # OCR信頼度下限

# OMR テンプレート
OMR_MARKER_SIZE_MM = 8        # 四隅アライメントマーカーのサイズ (mm)
OMR_BUBBLE_DIAMETER_MM = 5    # 塗りつぶし円の直径 (mm)
OMR_BUBBLE_SPACING_MM = 7     # 円の中心間距離 (mm)
OMR_MARK_THRESH = 0.35        # OMR方式のマーク判定閾値（円が大きいので高め）

# Excel色
COLOR_HEADER = "D9D9D9"
COLOR_FLAG   = "FFFF99"
COLOR_MULTI  = "FFCC99"
COLOR_FAIL   = "FF9999"
