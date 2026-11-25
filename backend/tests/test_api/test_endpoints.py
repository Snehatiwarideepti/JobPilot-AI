"""Tests for FastAPI endpoints and validation."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock

from app.main import app
from app.database import get_db


@pytest.fixture
def client():
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = mock_result

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


def test_health_endpoint(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "database" in data
    assert "provider" in data
    assert "llm" in data


def test_jobs_search_requires_query(client):
    resp = client.post("/jobs/search", json={})
    assert resp.status_code == 400


def test_invalid_job_id_returns_400(client):
    resp = client.get("/jobs/not-a-uuid")
    assert resp.status_code == 400


def test_evaluation_results_when_not_run(client):
    resp = client.get("/evaluation/results")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_queries"] == 0
    assert "not run yet" in data["note"].lower()
