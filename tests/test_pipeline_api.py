from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.api.routes.pipeline import PipelineRequest, _runs


@pytest.fixture
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def clear_runs():
    _runs.clear()
    yield
    _runs.clear()


class TestPipelineRequest:
    def test_defaults(self):
        req = PipelineRequest()
        assert req.faculty_filter is None
        assert req.dept_filter is None
        assert req.force is False

    def test_force_true(self):
        req = PipelineRequest(force=True)
        assert req.force is True

    def test_with_filters(self):
        req = PipelineRequest(
            faculty_filter=["science"],
            dept_filter=["COMP"],
            force=True,
        )
        assert req.faculty_filter == ["science"]
        assert req.dept_filter == ["COMP"]
        assert req.force is True


class TestTriggerPipelineEndpoint:
    @patch("backend.api.routes.pipeline._execute_pipeline", new_callable=AsyncMock)
    def test_returns_run_id(self, mock_exec, client):
        resp = client.post("/api/v1/pipeline/run", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert "run_id" in data
        assert data["status"] == "pending"

    @patch("backend.api.routes.pipeline._execute_pipeline", new_callable=AsyncMock)
    def test_with_faculty_filter(self, mock_exec, client):
        resp = client.post(
            "/api/v1/pipeline/run",
            json={"faculty_filter": ["science"], "force": True},
        )
        assert resp.status_code == 200
        run_id = resp.json()["run_id"]
        assert run_id in _runs
        assert _runs[run_id]["config"]["faculty_filter"] == ["science"]
        assert _runs[run_id]["config"]["force"] is True

    @patch("backend.api.routes.pipeline._execute_pipeline", new_callable=AsyncMock)
    def test_with_dept_filter(self, mock_exec, client):
        resp = client.post(
            "/api/v1/pipeline/run",
            json={"dept_filter": ["COMP"], "force": False},
        )
        assert resp.status_code == 200
        assert _runs[resp.json()["run_id"]]["config"]["dept_filter"] == ["COMP"]

    @patch("backend.api.routes.pipeline._execute_pipeline", new_callable=AsyncMock)
    def test_force_defaults_false_in_config(self, mock_exec, client):
        resp = client.post("/api/v1/pipeline/run", json={})
        run_id = resp.json()["run_id"]
        assert _runs[run_id]["config"]["force"] is False


class TestPipelineStatusEndpoint:
    @patch("backend.api.routes.pipeline._execute_pipeline", new_callable=AsyncMock)
    def test_status_found(self, mock_exec, client):
        resp = client.post("/api/v1/pipeline/run", json={})
        run_id = resp.json()["run_id"]

        status_resp = client.get(f"/api/v1/pipeline/status/{run_id}")
        assert status_resp.status_code == 200
        assert status_resp.json()["status"] == "pending"

    def test_status_not_found(self, client):
        resp = client.get("/api/v1/pipeline/status/nonexistent-id")
        assert resp.status_code == 404
