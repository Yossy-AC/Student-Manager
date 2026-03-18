"""チェックテスト統合テスト"""

from app.models.class_ import Class
from app.models.checktest import ChecktestConfig, ChecktestQuestion


def test_checktest_dashboard(client, db):
    """チェックテストダッシュボードがロードされる"""
    resp = client.get("/checktest/")
    assert resp.status_code == 200


def test_configs_page(client, db):
    """テスト設定一覧がロードされる"""
    resp = client.get("/checktest/configs")
    assert resp.status_code == 200


def test_create_config(client, db):
    """テスト設定を作成できる"""
    db.add(Class(id="c001", name="高3英語"))
    db.commit()

    resp = client.post("/checktest/api/configs", data={
        "class_id": "c001",
        "test_no": "第1回",
        "q_label": ["理解", "初見"],
        "q_max_score": ["20", "20"],
    }, follow_redirects=False)
    assert resp.status_code == 303

    config = db.query(ChecktestConfig).first()
    assert config is not None
    assert config.class_id == "c001"
    assert config.test_no == "第1回"
    assert len(config.questions) == 2


def test_scan_page(client, db):
    """スキャンページがロードされる"""
    resp = client.get("/checktest/scan")
    assert resp.status_code == 200


def test_results_page(client, db):
    """結果一覧がロードされる"""
    resp = client.get("/checktest/results")
    assert resp.status_code == 200


def test_nav_has_checktest_link(client):
    """ナビバーにチェックテストリンクがある"""
    resp = client.get("/admin")
    assert "チェックテスト" in resp.text
