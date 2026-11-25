"""Tests for ingestion service: upsert_job protection of existing fields and skill handling."""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.models import Job
from app.providers.base import ProviderJobResult
from app.services.ingestion import upsert_job, _is_empty_value, _update_field


def test_is_empty_value():
    assert _is_empty_value(None) is True
    assert _is_empty_value("") is True
    assert _is_empty_value("   ") is True
    assert _is_empty_value([]) is True
    assert _is_empty_value({}) is True
    assert _is_empty_value(set()) is True

    assert _is_empty_value("Python") is False
    assert _is_empty_value(["Python"]) is False
    assert _is_empty_value({"a": 1}) is False
    assert _is_empty_value(0) is False
    assert _is_empty_value(False) is False


def test_update_field_preserves_non_empty_data():
    # None/empty does not overwrite existing
    assert _update_field("Original Description", None) == "Original Description"
    assert _update_field("Original Description", "") == "Original Description"
    assert _update_field("Original Description", "   ") == "Original Description"
    assert _update_field(["Python", "SQL"], []) == ["Python", "SQL"]
    assert _update_field("https://apply.com", None) == "https://apply.com"

    # Specified does not get overwritten by unspecified
    assert _update_field("senior", "unspecified", preserve_specified=True) == "senior"
    assert _update_field("remote", "unspecified", preserve_specified=True) == "remote"

    # Unspecified can be replaced by a concrete value
    assert _update_field("unspecified", "senior", preserve_specified=True) == "senior"
    assert _update_field(None, "remote", preserve_specified=True) == "remote"

    # Valid incoming updates
    assert _update_field("Old title", "New Title") == "New Title"
    assert _update_field(["Python"], ["Python", "FastAPI"]) == ["Python", "FastAPI"]


@pytest.mark.asyncio
async def test_upsert_job_protects_existing_data_on_empty_incoming():
    """Verify that an incoming refresh with None/empty does NOT wipe existing fields."""
    existing_job = Job(
        id=uuid.uuid4(),
        source="jobvetta",
        source_job_id="job_123",
        title="Senior Python Engineer",
        company="TechCorp",
        location="Remote, US",
        workplace_type="remote",
        employment_type="full_time",
        experience_level="senior",
        salary_min=120000,
        salary_max=160000,
        description="Detailed description of the role.",
        responsibilities="Build APIs and pipelines.",
        requirements="Python, AWS, PostgreSQL.",
        benefits="Health, 401k.",
        skills=["Python", "AWS", "PostgreSQL"],
        application_url="https://techcorp.com/apply/123",
        source_url="https://jobvetta.com/jobs/123",
        raw_data={"orig": "data"},
    )

    incoming_minimal = ProviderJobResult(
        source="jobvetta",
        source_job_id="job_123",
        title=None,
        company=None,
        location=None,
        workplace_type=None,
        employment_type=None,
        experience_level="unspecified",
        salary_min=None,
        salary_max=None,
        description=None,
        responsibilities="",
        requirements=None,
        benefits=None,
        skills=[],
        application_url=None,
        source_url="",
        raw_data={},
    )

    db = AsyncMock()
    mock_execute_result = MagicMock()
    mock_execute_result.scalar_one_or_none.return_value = existing_job
    db.execute.return_value = mock_execute_result

    with patch("app.services.ingestion._upsert_job_skills") as mock_upsert_skills:
        job, created = await upsert_job(db, incoming_minimal)

        assert created is False
        assert job.title == "Senior Python Engineer"
        assert job.company == "TechCorp"
        assert job.location == "Remote, US"
        assert job.workplace_type == "remote"
        assert job.experience_level == "senior"
        assert job.description == "Detailed description of the role."
        assert job.responsibilities == "Build APIs and pipelines."
        assert job.requirements == "Python, AWS, PostgreSQL."
        assert job.benefits == "Health, 401k."
        assert job.skills == ["Python", "AWS", "PostgreSQL"]
        assert job.application_url == "https://techcorp.com/apply/123"
        assert job.source_url == "https://jobvetta.com/jobs/123"

        # Relational job skills must NOT be cleared when incoming skills is empty
        mock_upsert_skills.assert_not_called()
        db.flush.assert_awaited()


@pytest.mark.asyncio
async def test_upsert_job_updates_with_non_empty_incoming():
    """Verify that incoming non-empty fields do update existing job."""
    existing_job = Job(
        id=uuid.uuid4(),
        source="jobvetta",
        source_job_id="job_456",
        title="Engineer",
        company="OldCo",
        experience_level="unspecified",
        description="Old short description",
        skills=["Python"],
    )

    incoming_enriched = ProviderJobResult(
        source="jobvetta",
        source_job_id="job_456",
        title="Lead Engineer",
        company="NewCo",
        experience_level="lead",
        description="Comprehensive 2000-character job description",
        skills=["Python", "FastAPI", "Docker"],
        application_url="https://newco.com/apply",
    )

    db = AsyncMock()
    mock_execute_result = MagicMock()
    mock_execute_result.scalar_one_or_none.return_value = existing_job
    db.execute.return_value = mock_execute_result

    with patch("app.services.ingestion._upsert_job_skills", new=AsyncMock()) as mock_upsert_skills:
        job, created = await upsert_job(db, incoming_enriched)

        assert created is False
        assert job.title == "Lead Engineer"
        assert job.company == "NewCo"
        assert job.experience_level == "lead"
        assert job.description == "Comprehensive 2000-character job description"
        assert job.skills == ["Python", "FastAPI", "Docker"]
        assert job.application_url == "https://newco.com/apply"
        mock_upsert_skills.assert_awaited_once_with(db, existing_job.id, ["Python", "FastAPI", "Docker"])
