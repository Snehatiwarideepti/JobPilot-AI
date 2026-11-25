"""Tests for JobvettaProvider: normalization, auth, error handling, rate limiting, search."""
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch

from app.providers.jobvetta import (
    JobvettaProvider,
    _normalize_raw_job,
    _normalize_workplace_type,
    _normalize_employment_type,
    _normalize_experience_level,
    _extract_skills_from_job,
)
from app.providers.base import (
    ProviderAuthError,
    ProviderError,
    ProviderNotFoundError,
    ProviderRateLimitError,
    ProviderServerError,
    ProviderNetworkError,
)


def test_normalize_workplace_type():
    assert _normalize_workplace_type("Remote") == "remote"
    assert _normalize_workplace_type("Hybrid - 3 days") == "hybrid"
    assert _normalize_workplace_type("On-site") == "on_site"
    assert _normalize_workplace_type(None) == "unspecified"


def test_normalize_employment_type():
    assert _normalize_employment_type("Full-time") == "full_time"
    assert _normalize_employment_type("Internship") == "internship"
    assert _normalize_employment_type("Contract") == "contract"
    assert _normalize_employment_type(None) == "unspecified"


def test_normalize_experience_level():
    assert _normalize_experience_level("Internship") == "internship"
    assert _normalize_experience_level("Entry Level / Junior") == "entry"
    assert _normalize_experience_level("Senior") == "senior"
    assert _normalize_experience_level(None) == "unspecified"


def test_extract_skills_from_job():
    raw = {"skills": ["Python", "SQL", "Python"], "tags": "Docker, AWS"}
    skills = _extract_skills_from_job(raw)
    assert skills == ["AWS", "Docker", "Python", "SQL"]


def test_normalize_raw_job_does_not_invent_missing_fields():
    raw = {
        "job_id": "jv_123",
        "title": "ML Engineer",
        "company": "Acme Corp",
        "location": "Bengaluru, India",
        "employment_type": "Full-time",
        "apply_url": "https://acme.example.com/apply/123",
    }
    res = _normalize_raw_job(raw, "jobvetta")
    assert res.source == "jobvetta"
    assert res.source_job_id == "jv_123"
    assert res.title == "ML Engineer"
    assert res.company == "Acme Corp"
    assert res.salary_min is None
    assert res.salary_max is None
    assert res.description is None
    assert res.application_url == "https://acme.example.com/apply/123"


def test_normalize_raw_job_missing_id_raises():
    with pytest.raises(ProviderError):
        _normalize_raw_job({"title": "No ID"}, "jobvetta")


@pytest.mark.asyncio
async def test_provider_missing_api_key_raises_auth_error():
    provider = JobvettaProvider()
    provider._api_key = None
    with pytest.raises(ProviderAuthError):
        await provider.search_jobs("python")


@pytest.mark.asyncio
async def test_provider_handles_error_status_codes():
    provider = JobvettaProvider()
    provider._api_key = "fake_key"

    for status_code, exc_cls in [
        (401, ProviderAuthError),
        (403, ProviderAuthError),
        (404, ProviderNotFoundError),
        (429, ProviderRateLimitError),
        (500, ProviderServerError),
        (400, ProviderError),
    ]:
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = status_code
        resp.json.return_value = {"message": f"Error {status_code}"}
        with pytest.raises(exc_cls):
            provider._handle_error_response(resp)


@pytest.mark.asyncio
async def test_provider_search_success():
    provider = JobvettaProvider()
    provider._api_key = "fake_key"

    mock_response = {
        "total": 1,
        "jobs": [
            {
                "job_id": "jv_001",
                "title": "Python Developer",
                "company": "TechCo",
                "location": "Remote",
                "workplace_type": "remote",
                "employment_type": "Full-time",
                "skills": ["Python", "FastAPI"],
                "application_url": "https://techco.example/apply",
            }
        ],
    }

    with patch.object(provider, "_request_with_retry", new=AsyncMock(return_value=mock_response)):
        res = await provider.search_jobs("python", limit=10)
        assert res.total == 1
        assert len(res.jobs) == 1
        assert res.jobs[0].source_job_id == "jv_001"
        assert res.jobs[0].workplace_type == "remote"
