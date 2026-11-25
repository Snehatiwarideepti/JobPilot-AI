"""
Skill-gap analysis router.
Exposes GET /skills/gaps to analyze skill frequency across retrieved/stored jobs
compared against the candidate's actual profile.
"""
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import CandidateProfile, Job
from app.schemas import SkillGapAnalysis
from app.matching.analyzer import build_skill_gap_analysis
from app.retrieval.engine import hybrid_search, keyword_search

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/gaps", response_model=SkillGapAnalysis)
async def get_skill_gaps(
    user_id: str = Query(..., description="User ID for candidate profile"),
    query: str = Query(..., min_length=1, description="Target role or search query"),
    limit: int = Query(25, ge=5, le=100),
    db: AsyncSession = Depends(get_db),
):
    """
    Analyze skill gaps for a target role/query using active jobs in the database
    and the candidate's stored profile.
    """
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user_id format")

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
    profile = (await db.execute(stmt)).scalar_one_or_none()
    if not profile:
        raise HTTPException(
            status_code=404,
            detail="Candidate profile not found. Please create your profile first.",
        )

    # Retrieve relevant active jobs from DB
    jobs_with_scores = await hybrid_search(db, query, limit=limit)
    if not jobs_with_scores:
        jobs_with_scores = await keyword_search(db, query, limit=limit)

    jobs = [j for j, _ in jobs_with_scores]

    # Fallback: if no search match, get most recent active jobs matching query tokens
    if not jobs:
        stmt_jobs = select(Job).where(Job.is_active == True).order_by(Job.last_seen_at.desc()).limit(limit)
        jobs = list((await db.execute(stmt_jobs)).scalars().all())

    return await build_skill_gap_analysis(profile=profile, jobs=jobs, target_query=query)
