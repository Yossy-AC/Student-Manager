"""定数定義"""

# マーク検出
DEFAULT_MARK_THRESH = 0.35   # マーク判定閾値（黒ピクセル占有率）
DEFAULT_DPI = 300             # 処理解像度（固定推奨）
LABEL_COL_RATIO = 0.10        # □Nラベル列幅 / テーブル幅
N_VALUE_COLS = 11             # セル列数（値 0〜10 = 11列）
OCR_CONF_MIN = 60             # OCR信頼度下限

# Excel色
COLOR_HEADER = "D9D9D9"
COLOR_FLAG   = "FFFF99"
COLOR_MULTI  = "FFCC99"
COLOR_FAIL   = "FF9999"
