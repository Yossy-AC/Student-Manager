# CLAUDE.md

Guidance for working with this repository.

## Communication Style

Role: Dedicated engineer and assistant for a university prep school English teacher.
Style: Conclusion first, concise, direct, no token waste.
Prohibited: greetings, prefaces, apologies, emojis/kaomoji.

## Project

塾成績管理システム - 生徒向けダッシュボード、講師向け管理画面、CSV一括アップロード機能を持つWeb アプリケーション。

- Student Dashboard: `/dashboard/{student_id}` （個人成績推移、クラス平均との比較）
- Teacher Admin Panel: `/admin` （成績入力、生徒・講座管理、6タブ構成）
- CSV Upload: `/upload` （生徒・成績データの一括登録）

## Tech Stack (移行完了)

**旧スタック** (src/, public/ ディレクトリ): 参照のみ、本番利用しない
- Frontend: Vanilla JavaScript (ES6+), HTML5, CSS3
- Data: JSON files + localStorage キャッシング

**現行スタック** (app/ ディレクトリ):
- Backend: FastAPI + Uvicorn
- Frontend: HTMX + Jinja2 テンプレート
- Data: SQLite/PostgreSQL + SQLAlchemy ORM
- Package Manager: uv
- Deployment: Railway/Render
- Local Dev: `python -m uvicorn app.main:app --port 8000`

## Commands

```bash
# 依存インストール（初回のみ）
uv sync

# DB 初期化（初回のみ）
PYTHONIOENCODING=utf-8 python scripts/import_json.py

# サーバー起動
python -m uvicorn app.main:app --port 8000

# Windows で自動再起動付き（Git Bash非推奨 → run.bat 使用）
run.bat
```

## Architecture

### ディレクトリ構成（現行スタック）

```
app/
├── main.py              # FastAPI エントリーポイント
├── config.py            # 環境変数 (SECRET_KEY, ADMIN_PASSWORD, DATABASE_URL)
├── database.py          # SQLAlchemy セッション・テーブル生成
├── auth.py              # 認証ロジック (hmac.compare_digest)
├── dependencies.py      # require_auth / is_authenticated 依存関数
├── templates_config.py  # Jinja2Templates 共有インスタンス
├── models/
│   ├── class_.py        # Class テーブル
│   ├── student.py       # Student テーブル
│   ├── grade.py         # Grade テーブル（5科目スコア＋合計）
│   └── attendance.py    # Attendance テーブル
├── routers/
│   ├── pages.py         # 画面遷移 (/, /login, /admin, /admin/tabs/{tab}, /dashboard/{id}, /upload)
│   ├── auth.py          # POST /auth/login, POST /auth/logout
│   ├── students.py      # GET/POST /api/students
│   ├── grades.py        # GET/POST /api/grades, GET /api/grades/student/{id}, /comparison/{id}, /advice/{id}
│   ├── classes.py       # GET /api/classes, GET /api/classes/{id}/students
│   ├── attendance.py    # GET /api/attendance/student/{id}
│   └── upload.py        # POST /api/upload/csv, POST /api/upload/save, GET /api/upload/template
├── services/
│   ├── grade_calculator.py  # 成績計算・クラス平均・出席率（8関数）
│   └── csv_importer.py      # CSV解析・生徒IDマッチング・upsert保存
└── templates/
    ├── base.html
    ├── login.html
    ├── admin/          # 管理画面（6タブ）
    ├── dashboard/      # 生徒ダッシュボード（4セクション）
    ├── upload/
    └── partials/       # HTMX 用 HTML 断片（grades_table, students_table 等 11ファイル）

static/css/styles.css    # スタイル（.htmx-indicator 含む）
scripts/import_json.py   # data/*.json → SQLite 移行スクリプト
```

### データモデル

**grades テーブルスコア列**: `score_comprehension`, `score_unseen`, `score_grammar`, `score_vocabulary`, `score_listening`, `score_total`（各科目 0-20、合計 0-100）

**students.id 採番**: `s001`, `s002`, ... 最大値+1 で自動採番

**grades.id 採番**: `g_{student_id}_{date}_{lesson_number}` 形式

### CSV フォーマット

```
【生徒データ】セクション
教室コード,教室,氏名,ｼﾒｲ,性,高校,学科,学校ｸﾗｽ,部活,志望大学,志望学部

【チェックテスト成績】セクション
氏名,授業回,授業内容,日付,授業内容の理解,初見問題,文法語法,単語,リスニング,合計
```

テンプレートダウンロード: GET `/api/upload/template`

### HTMX パターン

**タブ切り替え（管理画面）**:
```html
<button hx-get="/admin/tabs/grades" hx-target="#tab-content" hx-swap="innerHTML">成績入力</button>
```

**連鎖セレクト（講座→生徒）**:
```html
<select hx-get="/api/classes/{id}/students" hx-trigger="change" hx-target="#student-select">
```

**遅延ロード**:
```html
<section hx-get="/api/grades/comparison/{id}" hx-trigger="load" hx-swap="innerHTML">
```

### 認証フロー

1. 未認証 → `/login` にリダイレクト
2. POST `/auth/login` で `hmac.compare_digest(password, settings.ADMIN_PASSWORD)`
3. セッション `authenticated=True` 設定
4. `require_auth` 依存関数が全 /api/* と /admin エンドポイントを保護

## Key Details

**セキュリティ**:
- パスワード比較: `hmac.compare_digest`（タイミング攻撃対策）
- テンプレート: Jinja2 オートエスケープ（XSS対策）
- エラー詳細: 外部には一般メッセージのみ、内部はログ出力
- CSV プレビューキャッシュ: UUID キーをセッションに保存（外部改ざん防止）

**環境変数** (.env):
```
SECRET_KEY=your-secret-key-here
ADMIN_PASSWORD=your-admin-password-here
DATABASE_URL=sqlite:///./data/student_manager.db
```

**data/フォルダ**:
- OneDriveへのシンボリックリンク（`Dev/setup.sh` で作成）
- `student_manager.db` を複数PC間で共有。同時起動禁止。
- セットアップ: `bash setup.sh <OneDriveのDO_NOT_CHANGE_NAMEパス>`（Dev/で1回実行）

**Windows での起動注意**:
- `--reload` フラグは Windows で multiprocessing エラーが発生する場合あり
- 推奨: `python -m uvicorn app.main:app --port 8000`（リロードなし）
- または: `run.bat`

## Migration to FastAPI + HTMX + uv

### Status（全フェーズ完了）

- **Phase 1**: ✅ 基盤セットアップ (pyproject.toml, SQLAlchemy モデル, FastAPI ルーター, テンプレート)
- **Phase 2**: ✅ 生徒ダッシュボード HTMX 実装 (grade_calculator.py, 動的セクション)
- **Phase 3**: ✅ 管理画面 6タブ HTMX 実装 (成績入力, 生徒管理, 講座管理)
- **Phase 4**: ✅ CSV アップロード機能 (csv_importer.py, プレビュー/保存ワークフロー)
- **Phase 5**: ✅ 認証機能 (SessionMiddleware, hmac, require_auth)
- **Phase 6**: ✅ Railway デプロイ設定 (railway.toml, Dockerfile, DEPLOYMENT.md)
- **追加**: ✅ セキュリティ修正 (XSS対策, タイミング攻撃対策, エラー情報漏洩防止, templates_config.py分離, uv有効化)

### Key Files

- [app/main.py](app/main.py) - FastAPI エントリーポイント
- [app/models/](app/models/) - SQLAlchemy モデル
- [app/routers/](app/routers/) - API エンドポイント定義
- [app/services/grade_calculator.py](app/services/grade_calculator.py) - 成績計算ロジック
- [app/services/csv_importer.py](app/services/csv_importer.py) - CSV解析ロジック
- [app/templates/](app/templates/) - Jinja2 テンプレート + HTMX
- [app/templates_config.py](app/templates_config.py) - Jinja2Templates 共有インスタンス
- [scripts/import_json.py](scripts/import_json.py) - JSON → SQLite 移行スクリプト
- [QUICKSTART.md](QUICKSTART.md) - ローカル開発ガイド
- [DEPLOYMENT.md](DEPLOYMENT.md) - Railway デプロイガイド
