"""
Jobs router - search, detail, match, save.
"""
import logging
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.config import get_settings
from app.models import Job, SavedJob, CandidateProfile
from app.schemas import (
    JobOut, JobWithScore, JobSearchParams, JobSearchResponse,
    JobMatchAnalysis, JobMatchAnalysisV2, BulkMatchRequest, BulkMatchResponse,
    SavedJobCreate, SavedJobOut,
)
from app.providers import get_provider, ProviderError, ProviderAuthError, ProviderRateLimitError
from app.services.ingestion import upsert_job, generate_and_store_embedding
from app.retrieval.engine import hybrid_search, keyword_search, semantic_search, rerank_results
from app.matching.analyzer import analyze_job_match, analyze_job_match_v2, build_skill_gap_analysis
from app.routers.search import record_search

router = APIRouter()
settings = get_settings()
logger = logging.getLogger(__name__)


@router.post("/search", response_model=JobSearchResponse)
async def search_jobs(
    params: JobSearchParams,
    user_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Search for jobs using live provider + hybrid retrieval.
    Results are real jobs from Jobvetta; never fabricated.
    """
    if not params.q:
        raise HTTPException(status_code=400, detail="Search query 'q' is required")

    # Step 1: Fetch from live provider and upsert to DB
    provider = get_provider("jobvetta")
    try:
        provider_results = await provider.search_jobs(
            query=params.q,
            location=params.location,
            workplace_type=params.workplace_type.value if params.workplace_type else None,
            employment_type=params.employment_type.value if params.employment_type else None,
            experience_level=params.experience_level.value if params.experience_level else None,
            days=params.days,
            limit=min(params.limit * 3, 100),  # Fetch more than needed for reranking
        )
    except ProviderAuthError as e:
        raise HTTPException(status_code=503, detail=f"Job provider authentication failed: {e}")
    except ProviderRateLimitError as e:
        raise HTTPException(status_code=429, detail=str(e))
    except ProviderError as e:
        raise HTTPException(status_code=503, detail=f"Job provider error: {e}")

    if not provider_results.jobs:
        return JobSearchResponse(
            total=0, page=params.page, limit=params.limit,
            jobs=[], source="jobvetta", retrieval_method=params.retrieval_method.value,
        )

    # Upsert jobs and generate embeddings
    db_jobs = []
    for job_result in provider_results.jobs:
        job, _ = await upsert_job(db, job_result)
        try:
            await generate_and_store_embedding(db, job)
        except Exception as e:
            logger.warning("Embedding generation failed for job %s: %s", job.id, e)
        db_jobs.append(job)
    await db.commit()

    # Step 2: Record search in history & run hybrid retrieval on the indexed data
    await record_search(
        db=db,
        query=params.q,
        user_id=user_id,
        filters=params.model_dump(exclude={"q", "page", "limit", "retrieval_method"}, exclude_none=True),
        result_count=provider_results.total,
        source="search_page",
    )
    await db.commit()
    retrieval_method = params.retrieval_method.value
    filters = {}
    if params.workplace_type:
        filters["workplace_type"] = params.workplace_type.value
    if params.employment_type:
        filters["employment_type"] = params.employment_type.value
    if params.experience_level:
        filters["experience_level"] = params.experience_level.value
    if params.days:
        filters["days"] = params.days

    hybrid_results = await hybrid_search(db, params.q, limit=min(params.limit * 2, 50), filters=filters)

    # Step 3: Load candidate profile for reranking
    profile = None
    if user_id:
        try:
            uid = uuid.UUID(user_id)
            stmt = (
                select(CandidateProfile)
                .where(CandidateProfile.user_id == uid)
                .options(selectinload(CandidateProfile.skills))
            )
            result = await db.execute(stmt)
            profile = result.scalar_one_or_none()
        except (ValueError, Exception):
            pass

    # Step 4: Rerank
    ranked = await rerank_results(hybrid_results, candidate_profile=profile, query=params.q)

    # Step 5: Paginate
    start = (params.page - 1) * params.limit
    page_ranked = ranked[start: start + params.limit]

    # Step 6: Build response with match info
    response_jobs: List[JobWithScore] = []
    for r in page_ranked:
        job = r.job
        job_out = JobWithScore(
            id=job.id,
            source=job.source,
            source_job_id=job.source_job_id,
            title=job.title,
            company=job.company,
            location=job.location,
            country=job.country,
            city=job.city,
            workplace_type=job.workplace_type,
            employment_type=job.employment_type,
            experience_level=job.experience_level,
            salary_min=job.salary_min,
            salary_max=job.salary_max,
            salary_currency=job.salary_currency,
            description=(job.description or "")[:500],
            skills=job.skills or [],
            application_url=job.application_url,
            source_url=job.source_url,
            posted_at=job.posted_at,
            is_active=job.is_active,
            first_seen_at=job.first_seen_at,
            last_seen_at=job.last_seen_at,
            created_at=job.created_at,
            match_score=round(r.final_score * 100, 1) if profile else None,
            semantic_score=round(r.semantic_score * 100, 1),
            top_matching_skills=r.matched_skills[:5],
            skill_gaps=r.missing_skills[:5],
        )
        response_jobs.append(job_out)

    return JobSearchResponse(
        total=provider_results.total,
        page=params.page,
        limit=params.limit,
        jobs=response_jobs,
        source="jobvetta",
        retrieval_method=retrieval_method,
    )


@router.get("/{job_id}", response_model=JobOut)
async def get_job(job_id: str, db: AsyncSession = Depends(get_db)):
    """Get a job by its internal ID."""
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job ID format")

    job = await db.get(Job, job_uuid)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/{job_id}/match", response_model=JobMatchAnalysis)
async def analyze_match(
    job_id: str,
    user_id: str = Query(..., description="User ID for profile lookup"),
    db: AsyncSession = Depends(get_db),
):
    """
    Perform evidence-based match analysis for a job.
    Returns structured evidence for each requirement.
    """
    try:
        job_uuid = uuid.UUID(job_id)
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid ID format")

    job = await db.get(Job, job_uuid)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    stmt = (
        select(CandidateProfile)
        .where(CandidateProfile.user_id == uid)
        .options(
            selectinload(CandidateProfile.skills),
            selectinload(CandidateProfile.projects),
            selectinload(CandidateProfile.experience),
            selectinload(CandidateProfile.education),
        )
    )
    result = await db.execute(stmt)
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Candidate profile not found. Please build your profile first.")

    return await analyze_job_match(job, profile)


@router.get("/{job_id}/match/v2", response_model=JobMatchAnalysisV2)
async def analyze_match_v2(
    job_id: str,
    user_id: str = Query(..., description="User ID for profile lookup"),
    db: AsyncSession = Depends(get_db),
):
    """
    Full explainable match analysis (V2) for a single job.

    Returns:
    - Requirement evidence with MATCH / PARTIAL / GAP / UNKNOWN per requirement
    - Experience fit (candidate level vs job level)
    - Workplace/location fit (remote preference vs job type)
    - Transparent score breakdown (skill 70%, experience 20%, workplace 10%)
    - Candidate strengths grounded in profile data
    - Skill gaps
    - Deterministic reasoning

    No OpenAI call is made.
    """
    try:
        job_uuid = uuid.UUID(job_id)
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid ID format")

    job = await db.get(Job, job_uuid)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    stmt = (
        select(CandidateProfile)
        .where(CandidateProfile.user_id == uid)
        .options(
            selectinload(CandidateProfile.skills),
            selectinload(CandidateProfile.projects),
            selectinload(CandidateProfile.experience),
            selectinload(CandidateProfile.education),
        )
    )
    result = await db.execute(stmt)
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(
            status_code=404,
            detail="Candidate profile not found. Please build your profile first.",
        )

    return await analyze_job_match_v2(job, profile)


@router.post("/match/bulk", response_model=BulkMatchResponse)
async def bulk_match(
    body: BulkMatchRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Analyze a candidate profile against multiple jobs at once.

    Accepts a list of internal job UUIDs and runs the full V2 analysis
    for each. Capped at `max_jobs` (default 20, max 50).

    No OpenAI calls are made.
    No Jobvetta API calls are made.
    """
    try:
        uid = uuid.UUID(body.user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user_id format")

    # Load profile with all relationships
    stmt = (
        select(CandidateProfile)
        .where(CandidateProfile.user_id == uid)
        .options(
            selectinload(CandidateProfile.skills),
            selectinload(CandidateProfile.projects),
            selectinload(CandidateProfile.experience),
            selectinload(CandidateProfile.education),
        )
    )
    result = await db.execute(stmt)
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(
            status_code=404,
            detail="Candidate profile not found. Please build your profile first.",
        )

    # Validate and cap job IDs
    job_ids_to_analyze = body.job_ids[: body.max_jobs]
    analyses = []

    for jid_str in job_ids_to_analyze:
        try:
            jid = uuid.UUID(jid_str)
        except ValueError:
            logger.warning("Skipping invalid job_id in bulk match: %s", jid_str)
            continue

        job = await db.get(Job, jid)
        if not job:
            logger.warning("Job not found in bulk match: %s", jid_str)
            continue

        analysis = await analyze_job_match_v2(job, profile)
        analyses.append(analysis)

    return BulkMatchResponse(
        user_id=body.user_id,
        total_analyzed=len(analyses),
        analyses=analyses,
    )


@router.post("/{job_id}/save")
async def save_job(
    job_id: str,
    body: SavedJobCreate,
    user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Save a job to the user's saved list."""
    try:
        job_uuid = uuid.UUID(job_id)
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid ID format")

    job = await db.get(Job, job_uuid)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Check if already saved
    stmt = select(SavedJob).where(SavedJob.user_id == uid, SavedJob.job_id == job_uuid)
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing:
        return {"message": "Job already saved", "saved": True}

    saved = SavedJob(user_id=uid, job_id=job_uuid, notes=body.notes)
    db.add(saved)
    await db.commit()
    return {"message": f"Saved: {job.title}", "saved": True}


@router.get("/saved/list", response_model=List[SavedJobOut])
async def get_saved_jobs(
    user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Get all saved jobs for a user."""
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID")

    stmt = (
        select(SavedJob)
        .where(SavedJob.user_id == uid)
        .options(selectinload(SavedJob.job))
    )
    result = await db.execute(stmt)
    return result.scalars().all()
