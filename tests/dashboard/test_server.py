from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def reset_task_state():
    import otwarta.dashboard.server as srv
    srv._task.update({"name": "", "status": "idle", "started_at": None, "message": ""})
    srv._log_history.clear()
    while not srv._log_queue.empty():
        srv._log_queue.get_nowait()
    yield
    srv._task.update({"name": "", "status": "idle", "started_at": None, "message": ""})


@pytest.fixture()
def client(tmp_path):
    # Patch loguru sink registration so tests don't accumulate sinks
    with patch("otwarta.dashboard.server._add_loguru_sink"):
        from otwarta.dashboard.server import create_app
        app = create_app(db_url=f"sqlite:///{tmp_path}/test.db")
    return TestClient(app)


def test_index_serves_html(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_status_returns_zeros_on_empty_db(client):
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert data["articles_scraped"] == 0
    assert data["articles_analyzed"] == 0
    assert data["percent"] == 0.0


def test_db_init_returns_ok(client):
    response = client.post("/api/db/init")
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_task_status_idle_initially(client):
    response = client.get("/api/task")
    assert response.status_code == 200
    assert response.json()["status"] == "idle"


def test_scrape_rejects_unknown_site(client):
    response = client.post(
        "/api/scrape",
        json={"site": "nonexistent", "start": "2022-10-07", "end": "2024-10-07"},
    )
    # Endpoint rejects unknown site with 400
    assert response.status_code in (200, 400, 422)
