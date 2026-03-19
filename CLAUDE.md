# student-manager

## Project

塾の統合管理システム — 生徒・講座管理 + チェックテスト自動読み取り（OCR採点）。

- Admin Panel: `/admin` （生徒管理、講座管理、ダッシュボード統計）
- Checktest: `/checktest/` （テスト設定、PDFスキャン、レビュー、結果一覧、Excel出力）
- Student Dashboard: `/dashboard/{student_id}` （出席状況）
- CLI: `tools/checktest_reader.py` （PDF→Excel直接変換）

## Tech Stack

- Backend: FastAPI + Uvicorn
- Frontend: HTMX + Jinja2 テンプレート
- Data: SQLite + SQLAlchemy ORM（WALモード）
- Image Processing: PyMuPDF（PDF→画像）、OpenCV（マーク検出・OMR）
- OMR Template: ReportLab + qrcode（OMR採点欄テンプレートPDF生成）
- Excel: openpyxl
- Package Manager: uv
- Portal統合: yossy-portal-lib（認証・base_href・CSP nonce・ヘルスチェック）

## Commands

```bash
# 依存インストール（初回のみ）
uv sync

# サーバー起動（スタンドアロン）
SECRET_KEY=xxx ADMIN_PASSWORD=xxx python -m uvicorn app.main:app --port 8010

# ポータル経由（通常はこちら）
# yossy-portal の start-portal.sh で一括起動される
# 個別再起動: cd yossy-portal && bash restart.sh student-manager

# テスト実行
uv run pytest tests/ -v

# CLI（PDF→Excel直接変換）
uv run python tools/checktest_reader.py --pdf input/scan.pdf --config config/class_A.json --out output/results.xlsx
```

## ポータル統合

- **ポート**: 8010
- **Caddyルート**: `handle_path /staff/student-manager*` → `reverse_proxy localhost:8010`（max_size 200MB）
- **認証**: Caddy `forward_auth` → auth-gateway。`BEHIND_PORTAL=true` 時は自前認証スキップ
- **yossy-portal-lib**: `portal_auth_middleware` + `csp_middleware` + `base_href` + `add_health_endpoint`
- **CSP nonce**: 全 `<script>` タグに `nonce="{{ request.state.csp_nonce }}"` 付与
- **チェックテスト**: `/checktest/` 配下でテスト設定・PDFスキャン・結果一覧・Excel出力を提供

## Architecture

### ディレクトリ構成

```
app/
├── main.py              # FastAPI エントリーポイント
├── config.py            # 環境変数 + TEMP_PDF_DIR
├── database.py          # SQLAlchemy セッション・テーブル生成・WALモード
├── auth.py              # 認証ロジック (hmac.compare_digest)
├── dependencies.py      # require_auth / is_authenticated 依存関数
├── templates_config.py  # Jinja2Templates 共有インスタンス
├── core/checktest/      # チェックテスト処理ロジック（CLI・Web両用）
│   ├── constants.py     # 定数 (THRESH, DPI, COLORS, OMR設定)
│   ├── scanner.py       # pdf_to_images(generator), find_answer_table
│   ├── detector.py      # detect_scores（旧方式マーク検出、適応的閾値）
│   ├── omr_detector.py  # OMR方式検出（マーカー検出・透視変換・バブル判定）
│   ├── template_generator.py # OMRテンプレートPDF生成（ReportLab）
│   ├── ocr.py           # ocr_name_and_total（氏名OCR）
│   ├── processor.py     # process_page, load_config
│   └── excel_writer.py  # write_excel
├── models/
│   ├── class_.py        # Class テーブル
│   ├── student.py       # Student テーブル
│   ├── attendance.py    # Attendance テーブル
│   └── checktest.py     # ChecktestConfig/Question/Session/Page/Score テーブル
├── routers/
│   ├── pages.py         # 画面遷移 (/, /login, /admin, /admin/tabs/{tab}, /dashboard, /checktest/)
│   ├── auth.py          # POST /auth/login, POST /auth/logout
│   ├── students.py      # GET/POST /api/students
│   ├── classes.py       # GET/POST /api/classes, GET /api/classes/{id}/students
│   ├── attendance.py    # GET /api/attendance/student/{id}
│   ├── checktest_configs.py   # テスト設定 CRUD
│   ├── checktest_scan.py      # PDFアップロード + 処理 + レビュー
│   ├── checktest_results.py   # 結果一覧・詳細・集計
│   └── checktest_export.py    # Excel ダウンロード
└── templates/
    ├── base.html
    ├── login.html
    ├── admin/          # 管理画面（4タブ: ダッシュボード、生徒、講座、レポート）
    ├── dashboard/      # 生徒ダッシュボード（select.html + index.html）
    ├── checktest/      # チェックテスト（index, configs, scan, results）
    └── partials/       # HTMX 用 HTML 断片

static/css/styles.css    # スタイル
tools/checktest_reader.py # CLI エントリポイント
tests/                   # pytest テスト
```

### DBスキーマ

**students**: id(PK s001形式), name, name_kana, gender, high_school, class_id(FK), join_date 等
**classes**: id(PK c001形式), name, day, time, capacity
**attendance**: id(PK), student_id(FK), class_id(FK), date, status(出席/欠席/遅刻)

**checktest_configs**: id(PK), class_id, test_no（クラス×回次、ユニーク制約）
**checktest_questions**: id(PK), config_id(FK), question_index, label, max_score
**checktest_sessions**: id(PK), config_id(FK), scan_date, pdf_filename, total/ok/ng_pages, status(review/confirmed)
**checktest_pages**: id(PK), session_id(FK), page_number, student_name_ocr, student_id(nullable), total_mark, page_flag
**checktest_scores**: id(PK), page_id(FK), question_index, score(nullable=複数塗り), flag, edited

### チェックテスト処理フロー

1. テスト設定作成（クラス選択 + 大問定義）
2. **テンプレートDL** → OMR採点欄PDFを生成・DL → Word A4縦の最終ページ下半分に貼付 → B4/2in1印刷
3. PDFアップロード（設定選択 + 「OMRテンプレート使用」チェック + PDF送信、XHRで進捗表示）
4. PDF→画像変換（PyMuPDF 300dpi、ジェネレータで省メモリ）→ 右半分クロップ
5. **OMRモード**: マーカー検出 → 透視変換 → バブル塗りつぶし率判定
   **旧方式**: テーブル検出 → 黒ピクセル比率検出
6. 結果レビュー（色分け表示、インライン編集、生徒紐付け、診断画像表示）
7. セッション確定 → Excel DL

### OMR方式リニューアル（完了）

旧方式（小さな手書きマーク → 黒ピクセル比率検出）は精度が低いため、OMR方式に移行。

**テンプレートPDF生成（`template_generator.py`）:**
- 四隅アライメントマーカー（8mm黒正方形、透視変換用）
- QRコード（config_idエンコード、15mm）
- 大問ごとの塗りつぶし円（直径3mm、間隔5mm、常に1行配置）
  - バブル数が多い場合は間隔を自動圧縮して1行に収める
- 案内文: 「機械処理をします。得点は○を黒く塗りつぶし、文字は読みやすい字で記入してください。」
- 氏名欄（1/4幅）・コメント欄（ラベル右側配置、縦中央揃え）
- ページ高さは内容量に応じて動的算出（余白最小化）
- 幅180mm固定、A4下半分に貼付 → B4/2in1印刷の運用

**検出エンジン（`omr_detector.py`）:**
- OMR検出エンジン（`omr_detector.py`）: QR検出 + 4隅マーカー検出 + 透視変換 + バブル塗りつぶし率判定
  - `detect_qr()`: OpenCV QRCodeDetector でconfig_id自動取得
  - `find_alignment_markers()`: 二値化→輪郭→正方形フィルタ→4隅割当
  - `rectify_image()`: cv2.getPerspectiveTransform で正規化
  - `detect_bubble_fills()`: 円形ROI内の黒ピクセル率 + `_find_marked_cells`再利用（適応的閾値）
  - `process_omr()`: 上記を統合するメインエントリ
- テンプレートDL: `GET /api/configs/{id}/template` + configs一覧にDLボタン
- processor統合: `process_page(template_coords=...)` でOMR/旧方式を切り替え
- スキャンUI: 「OMRテンプレート使用」チェックボックス（閾値自動切替 0.15↔0.35）

**未実装:**
- Gemini OCR統合: 氏名・コメントの手書き読み取り（OMRモード時）
- QR自動検出: 現在は手動チェックボックスで切替（将来的にQRで自動判別）

### スキャン改善（完了）

- `pdf_to_images`: リスト一括読み込み → ジェネレータ（80ページ×50MB=4GB → 1ページずつ処理）
- XHRアップロード: フォーム送信 → XHR + 進捗表示（タイムアウト回避）
- 適応的閾値: 固定0.35 → 0.15 + 中央値×2.5フォールバック
- デバッグ画像: 処理時にsheet/detected画像を生成、レビュー画面で「画像」リンクから確認可能

### 認証フロー

1. 未認証 → `/login` にリダイレクト
2. POST `/auth/login` で `hmac.compare_digest(password, settings.ADMIN_PASSWORD)`
3. `require_auth` 依存関数が全 /api/* と /admin エンドポイントを保護
4. ポータル経由: `BEHIND_PORTAL=true` + `X-Portal-Role` で認証バイパス

## Key Details

**セキュリティ**:
- パスワード比較: `hmac.compare_digest`（タイミング攻撃対策）
- テンプレート: Jinja2 オートエスケープ（XSS対策）
- PDF一時ファイル: `data/temp_pdf/`に保存、処理後削除

**環境変数** (.env):
```
SECRET_KEY=your-secret-key-here        # スタンドアロン時のみ必須
ADMIN_PASSWORD=your-admin-password-here # スタンドアロン時のみ必須
DATABASE_URL=sqlite:///./data/student_manager.db
BEHIND_PORTAL=true                     # ポータル経由時（start-portal.shで自動設定）
```

**data/フォルダ**:
- `student_manager.db` — 全データ（生徒・講座・出席・チェックテスト）
- `temp_pdf/` — PDFアップロード一時保存
- `debug_img/` — デバッグ画像（セッション別サブディレクトリ）

## 統合履歴

- 旧grades/csv_importer（固定5カラム成績）は削除済み（未使用だったため）
