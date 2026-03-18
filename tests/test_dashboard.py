"""生徒ダッシュボードのテスト"""

from app.models.student import Student
from app.models.class_ import Class


def test_dashboard_select_shows_students(client, db):
    """生徒選択ページにDB登録済みの生徒がselectで表示される"""
    db.add(Class(id="c001", name="テスト講座"))
    db.add(Student(id="s001", name="山田太郎", class_id="c001"))
    db.add(Student(id="s002", name="鈴木花子", class_id="c001"))
    db.commit()

    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert "山田太郎" in resp.text
    assert "鈴木花子" in resp.text
    assert "<select" in resp.text
    # 旧UIの手入力フォームがない
    assert 'placeholder="例: s001"' not in resp.text


def test_dashboard_select_empty_db(client):
    """生徒が0人でもページがロードされる"""
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert "選択してください" in resp.text
