"""管理画面タブのテスト"""

from app.models.student import Student
from app.models.class_ import Class


def test_admin_page_loads(client):
    """管理画面がロードされ、自動ロード属性が含まれる"""
    resp = client.get("/admin")
    assert resp.status_code == 200
    assert 'hx-get="admin/tabs/dashboard"' in resp.text
    assert 'hx-trigger="load"' in resp.text
    assert "Phase 2-3" not in resp.text


def test_dashboard_tab_dynamic_counts(client, db):
    """ダッシュボードタブがDBの実数値を返す"""
    resp = client.get("/admin/tabs/dashboard")
    assert resp.status_code == 200
    assert "サンプルデータ" not in resp.text
    assert "Phase" not in resp.text

    db.add(Class(id="c001", name="テスト講座"))
    db.add(Student(id="s001", name="山田太郎", class_id="c001"))
    db.add(Student(id="s002", name="鈴木花子", class_id="c001"))
    db.commit()

    resp = client.get("/admin/tabs/dashboard")
    html = resp.text
    assert ">2<" in html  # student_count
    assert ">1<" in html  # class_count


def test_classes_tab_no_placeholder(client):
    """講座管理タブにPhaseプレースホルダーがない"""
    resp = client.get("/admin/tabs/classes")
    assert resp.status_code == 200
    assert "Phase" not in resp.text
    assert "新規講座を追加" in resp.text


def test_create_class(client, db):
    """POST /api/classes で講座を追加"""
    resp = client.post("/api/classes", data={
        "name": "新規テスト講座",
        "day": "火",
        "time": "18:00-19:30",
        "capacity": "20",
    })
    assert resp.status_code == 200
    assert "新規テスト講座" in resp.text

    cls = db.query(Class).filter(Class.name == "新規テスト講座").first()
    assert cls is not None
    assert cls.day == "火"


def test_reports_tab_no_placeholder(client):
    """レポートタブにPhaseプレースホルダーがない"""
    resp = client.get("/admin/tabs/reports")
    assert resp.status_code == 200
    assert "Phase" not in resp.text


def test_admin_no_grades_upload_tabs(client):
    """成績入力・アップロードタブが削除されている"""
    resp = client.get("/admin")
    assert "成績入力" not in resp.text
    assert "アップロード" not in resp.text
