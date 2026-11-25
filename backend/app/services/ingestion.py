"""
Job ingestion service.
Handles: normalize -> deduplicate -> upsert -> embed -> mark stale.
Idempotent: safe to run multiple times.
"""
from __future__ import annotations
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Job, JobEmbedding, JobSkill
from app.providers.base import ProviderJobResult
from app.embeddings.service import get_embedding_service

logger = logging.getLogger(__name__)


def _is_empty_value(val: Any) -> bool:
    """Check if value is None, whitespace string, or empty container."""
    if val is None:
        return True
    if isinstance(val, str) and not val.strip():
        return True
    if isinstance(val, (list, dict, set, tuple)) and len(val) == 0:
        return True
    return False


def _update_field(existing_val: Any, new_val: Any, preserve_specified: bool = False) -> Any:
    """
    Return new_val if valid and non-empty, otherwise preserve existing_val.
    If preserve_specified is True, do not overwrite a specific existing value
    (anything other than None/unspecified) with 'unspecified'.
    """
    if _is_empty_value(new_val):
        return existing_val
    if preserve_specified and new_val == "unspecified":
        if existing_val and existing_val != "unspecified":
            return existing_val
    return new_val


async def upsert_job(
    db: AsyncSession,
    job_result: ProviderJobResult,
) -> tuple[Job, bool]:
    """
    Upsert a job into the database.
    Returns (job, created) where created=True if newly inserted.
    Guarantees that a refresh/enrichment does NOT overwrite existing non-empty
    fields with None, empty strings, empty lists, or empty dicts.
    """
    # Check if job already exists
    stmt = select(Job).where(
        Job.source == job_result.source,
        Job.source_job_id == job_result.source_job_id,
    )
    result = await db.execute(stmt)
    existing: Optional[Job] = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)

    if existing:
        # Update existing job without wiping non-empty existing data
        existing.title = _update_field(existing.title, job_result.title)
        existing.company = _update_field(existing.company, job_result.company)
        existing.location = _update_field(existing.location, job_result.location)
        existing.country = _update_field(existing.country, job_result.country)
        existing.city = _update_field(existing.city, job_result.city)
        existing.workplace_type = _update_field(existing.workplace_type, job_result.workplace_type, preserve_specified=True)
        existing.employment_type = _update_field(existing.employment_type, job_result.employment_type, preserve_specified=True)
        existing.experience_level = _update_field(existing.experience_level, job_result.experience_level, preserve_specified=True)
        if job_result.salary_min is not None:
            existing.salary_min = job_result.salary_min
        if job_result.salary_max is not None:
            existing.salary_max = job_result.salary_max
        existing.salary_currency = _update_field(existing.salary_currency, job_result.salary_currency)
        existing.salary_period = _update_field(existing.salary_period, job_result.salary_period)
        existing.description = _update_field(existing.description, job_result.description)
        existing.responsibilities = _update_field(existing.responsibilities, job_result.responsibilities)
        existing.requirements = _update_field(existing.requirements, job_result.requirements)
        existing.benefits = _update_field(existing.benefits, job_result.benefits)
        
        # Only overwrite skills if incoming skills are non-empty
        if not _is_empty_value(job_result.skills):
            existing.skills = job_result.skills
            await _upsert_job_skills(db, existing.id, job_result.skills)

        existing.application_url = _update_field(existing.application_url, job_result.application_url)
        existing.source_url = _update_field(existing.source_url, job_result.source_url)
        existing.raw_data = _update_field(existing.raw_data, job_result.raw_data)
        existing.last_seen_at = now
        existing.is_active = True

        if job_result.posted_at:
            try:
                existing.posted_at = datetime.fromisoformat(job_result.posted_at.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass

        await db.flush()
        return existing, False

    else:
        # Create new job
        posted_at = None
        if job_result.posted_at:
            try:
                posted_at = datetime.fromisoformat(job_result.posted_at.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass

        job = Job(
            source=job_result.source,
            source_job_id=job_result.source_job_id,
            title=job_result.title or "Untitled",
            company=job_result.company,
            location=job_result.location,
            country=job_result.country,
            city=job_result.city,
            workplace_type=job_result.workplace_type,
            employment_type=job_result.employment_type,
            experience_level=job_result.experience_level,
            salary_min=job_result.salary_min,
            salary_max=job_result.salary_max,
            salary_currency=job_result.salary_currency,
            salary_period=job_result.salary_period,
            description=job_result.description,
            responsibilities=job_result.responsibilities,
            requirements=job_result.requirements,
            benefits=job_result.benefits,
            skills=job_result.skills,
            application_url=job_result.application_url,
            source_url=job_result.source_url,
            raw_data=job_result.raw_data,
            posted_at=posted_at,
            first_seen_at=now,
            last_seen_at=now,
            is_active=True,
        )
        db.add(job)
        await db.flush()

        # Create job skills if provided
        if not _is_empty_value(job_result.skills):
            await _upsert_job_skills(db, job.id, job_result.skills)

        return job, True


async def _upsert_job_skills(
    db: AsyncSession,
    job_id: uuid.UUID,
    skills: List[str],
) -> None:
    """Replace job skills for a given job."""
    # Delete existing
    stmt = select(JobSkill).where(JobSkill.job_id == job_id)
    result = await db.execute(stmt)
    existing_skills = result.scalars().all()
    for s in existing_skills:
        await db.delete(s)
    await db.flush()

    # Insert new
    for skill_name in skills:
        if skill_name and skill_name.strip():
            db.add(JobSkill(
                job_id=job_id,
                skill_name=skill_name.strip(),
                is_required=True,
            ))
    await db.flush()


async def generate_and_store_embedding(
    db: AsyncSession,
    job: Job,
) -> None:
    """
    Generate embedding for a job and store/update in job_embeddings table.
    """
    embedding_service = get_embedding_service()

    text = embedding_service.build_job_embedding_text(
        title=job.title,
        description=job.description,
        requirements=job.requirements,
        responsibilities=job.responsibilities,
        skills=job.skills or [],
    )

    if not text.strip():
        logger.warning("Job %s has no embeddable text; skipping embedding.", job.id)
        return

    vector = await embedding_service.embed_text(text)

    # Check if embedding already exists
    stmt = select(JobEmbedding).where(JobEmbedding.job_id == job.id)
    result = await db.execute(stmt)
    existing: Optional[JobEmbedding] = result.scalar_one_or_none()

    model_name = embedding_service._model_name

    if existing:
        existing.embedding = vector
        existing.model_name = model_name
        existing.embedding_text = text[:5000]
    else:
        emb = JobEmbedding(
            job_id=job.id,
            embedding=vector,
            model_name=model_name,
            embedding_text=text[:5000],
        )
        db.add(emb)

    await db.flush()


async def mark_stale_jobs(
    db: AsyncSession,
    source: str,
    active_source_ids: List[str],
    cutoff_hours: int = 48,
) -> int:
    """
    Mark jobs from a source as inactive if they were not seen in this ingestion run.
    Returns the count of jobs marked inactive.
    """
    if not active_source_ids:
        logger.warning("No active source IDs provided; not marking any jobs stale to avoid data loss.")
        return 0

    stmt = (
        update(Job)
        .where(
            Job.source == source,
            Job.source_job_id.notin_(active_source_ids),
            Job.is_active == True,
        )
        .values(is_active=False)
        .returning(Job.id)
    )
    result = await db.execute(stmt)
    count = len(result.fetchall())
    logger.info("Marked %d stale jobs as inactive for source=%s", count, source)
    return count
