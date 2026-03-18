from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from datetime import datetime
from yossy_portal_lib import base_href as _base_href
from app.auth import authenticate_admin, clear_session

router = APIRouter()


def _redirect(request: Request, path: str) -> RedirectResponse:
    return RedirectResponse(url=f"{_base_href(request)}{path}", status_code=302)


@router.post("/login", response_class=HTMLResponse)
async def login(request: Request, password: str = ""):
    """ログイン処理"""
    form_data = await request.form()
    password = form_data.get("password", "")
    bh = _base_href(request)

    if not password:
        return f"""
        <div style="background: #ffebee; color: #c62828; padding: 1rem; border-radius: 8px; text-align: center;">
            <p><strong>エラー:</strong> パスワードを入力してください</p>
            <p style="margin-top: 1rem;"><a href="{bh}login" style="color: #0066cc; text-decoration: underline;">ログイン画面に戻る</a></p>
        </div>
        """

    if authenticate_admin(password):
        request.session["authenticated"] = True
        request.session["login_time"] = datetime.now().isoformat()
        return _redirect(request, "admin")
    else:
        return f"""
        <html>
            <head>
                <meta charset="UTF-8">
                <title>ログイン失敗</title>
                <link rel="stylesheet" href="/portal-assets/portal.css">
            </head>
            <body>
                <div class="login-container">
                    <div class="login-card">
                        <div style="background: #ffebee; color: #c62828; padding: 1rem; border-radius: 8px; margin-bottom: 1.5rem;">
                            <p style="margin: 0;"><strong>パスワードが正しくありません</strong></p>
                        </div>
                        <p><a href="{bh}login" style="color: #0066cc; text-decoration: underline;">もう一度ログイン</a></p>
                    </div>
                </div>
            </body>
        </html>
        """

@router.post("/logout")
async def logout(request: Request):
    """ログアウト処理"""
    clear_session(request.session)
    return RedirectResponse(url="/auth/logout", status_code=302)
