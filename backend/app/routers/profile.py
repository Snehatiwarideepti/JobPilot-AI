"""Profile router."""
import logging
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.config import get_settings
from app.models import (
    User, CandidateProfile, CandidateSkill, CandidateProject,
    CandidateExperience, CandidateEducation, CandidateCertification,
    CandidateEmbedding,
)
from app.schemas import (
    CandidateProfileCreate, CandidateProfileOut, ResumeUploadResponse, SkillGapAnalysis,
)
from app.services.resume import extract_resume_text, extract_profile_from_text
from app.embeddings.service import get_embedding_service

router = APIRouter()
settings = get_settings()
logger = logging.getLogger(__name__)


async def _get_or_create_user(db: AsyncSession, user_id: str) -> User:
    """Get or create a user record for the given ID."""
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user_id format")

    user = await db.get(User, uid)
    if not user:
        user = User(id=uid, email=f"user_{user_id[:8]}@jobpilot.local")
        db.add(user)
        await db.flush()
    return user


@router.post("", response_model=CandidateProfileOut)
async def create_or_update_profile(
    profile_data: CandidateProfileCreate,
    user_id: str = Query(..., description="User ID"),
    db: AsyncSession = Depends(get_db),
):
    """Create or update the candidate profile for a user."""
    user = await _get_or_create_user(db, user_id)
    uid = user.id

    # Find existing profile
    stmt = (
        select(CandidateProfile)
        .where(CandidateProfile.user_id == uid)
        .options(
            selectinload(CandidateProfile.skills),
            selectinload(CandidateProfile.projects),
            selectinload(CandidateProfile.experience),
            selectinload(CandidateProfile.education),
            selectinload(CandidateProfile.certifications),
        )
    )
    result = await db.execute(stmt)
    profile = result.scalar_one_or_none()

    is_new = False
    if not profile:
        profile = CandidateProfile(user_id=uid)
        db.add(profile)
        await db.flush()
        is_new = True

    # Update scalar fields
    for field in [
        "full_name", "email", "phone", "location", "linkedin_url", "github_url",
        "portfolio_url", "summary", "remote_preference", "experience_level",
        "preferred_salary_min", "preferred_salary_max", "preferred_salary_currency",
    ]:
        val = getattr(profile_data, field, None)
        if val is not None:
            setattr(profile, field, val)

    if profile_data.target_roles is not None:
        profile.target_roles = profile_data.target_roles
    if profile_data.preferred_locations is not None:
        profile.preferred_locations = profile_data.preferred_locations

    # Replace skills
    if profile_data.skills is not None:
        if not is_new:
            for s in list(profile.skills):
                await db.delete(s)
            await db.flush()
        for s_data in profile_data.skills:
            if s_data.name.strip():
                db.add(CandidateSkill(
                    profile_id=profile.id,
                    name=s_data.name.strip(),
                    category=s_data.category,
                    proficiency=s_data.proficiency,
                    years_of_experience=s_data.years_of_experience,
                    source="manual",
                ))

    # Replace projects
    if profile_data.projects is not None:
        if not is_new:
            for p in list(profile.projects):
                await db.delete(p)
            await db.flush()
        for p_data in profile_data.projects:
            if p_data.name.strip():
                db.add(CandidateProject(
                    profile_id=profile.id,
                    name=p_data.name.strip(),
                    description=p_data.description,
                    technologies=p_data.technologies,
                    url=p_data.url,
                    start_date=p_data.start_date,
                    end_date=p_data.end_date,
                    source="manual",
                ))

    # Replace experience
    if profile_data.experience is not None:
        if not is_new:
            for e in list(profile.experience):
                await db.delete(e)
            await db.flush()
        for e_data in profile_data.experience:
            if e_data.company.strip() and e_data.title.strip():
                db.add(CandidateExperience(
                    profile_id=profile.id,
                    company=e_data.company.strip(),
                    title=e_data.title.strip(),
                    location=e_data.location,
                    description=e_data.description,
                    technologies=e_data.technologies,
                    start_date=e_data.start_date,
                    end_date=e_data.end_date,
                    is_current=e_data.is_current,
                    source="manual",
                ))

    # Replace education
    if profile_data.education is not None:
        if not is_new:
            for ed in list(profile.education):
                await db.delete(ed)
            await db.flush()
        for ed_data in profile_data.education:
            if ed_data.institution.strip():
                db.add(CandidateEducation(
                    profile_id=profile.id,
                    institution=ed_data.institution.strip(),
                    degree=ed_data.degree,
                    field_of_study=ed_data.field_of_study,
                    gpa=ed_data.gpa,
                    start_date=ed_data.start_date,
                    end_date=ed_data.end_date,
                    is_current=ed_data.is_current,
                    source="manual",
                ))

    # Replace certifications
    if profile_data.certifications is not None:
        if not is_new:
            for c in list(profile.certifications):
                await db.delete(c)
            await db.flush()
        for c_data in profile_data.certifications:
            if c_data.name.strip():
                db.add(CandidateCertification(
                    profile_id=profile.id,
                    name=c_data.name.strip(),
                    issuer=c_data.issuer,
                    issued_date=c_data.issued_date,
                    expiry_date=c_data.expiry_date,
                    credential_id=c_data.credential_id,
                    credential_url=c_data.credential_url,
                    source="manual",
                ))

    await db.commit()
    await db.refresh(profile)

    # Reload with relationships
    stmt2 = (
        select(CandidateProfile)
        .where(CandidateProfile.id == profile.id)
        .options(
            selectinload(CandidateProfile.skills),
            selectinload(CandidateProfile.projects),
            selectinload(CandidateProfile.experience),
            selectinload(CandidateProfile.education),
            selectinload(CandidateProfile.certifications),
        )
    )
    result2 = await db.execute(stmt2)
    profile = result2.scalar_one()

    # Generate/update candidate embedding
    try:
        emb_service = get_embedding_service()
        text = emb_service.build_candidate_embedding_text(
            summary=profile.summary,
            skills=[s.name for s in profile.skills],
            experience_titles=[f"{e.title} at {e.company}" for e in profile.experience],
            project_descriptions=[p.description for p in profile.projects if p.description],
        )
        if text.strip():
            vector = await emb_service.embed_text(text)
            stmt3 = select(CandidateEmbedding).where(CandidateEmbedding.profile_id == profile.id)
            result3 = await db.execute(stmt3)
            emb_obj = result3.scalar_one_or_none()
            if emb_obj:
                emb_obj.embedding = vector
                emb_obj.model_name = emb_service._model_name
            else:
                db.add(CandidateEmbedding(
                    profile_id=profile.id,
                    embedding=vector,
                    model_name=emb_service._model_name,
                ))
            await db.commit()
    except Exception as e:
        logger.warning("Candidate embedding generation failed: %s", e)

    return CandidateProfileOut.model_validate(profile)


@router.get("", response_model=CandidateProfileOut)
async def get_profile(
    user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Get the candidate profile for a user."""
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user_id")

    stmt = (
        select(CandidateProfile)
        .where(CandidateProfile.user_id == uid)
        .options(
            selectinload(CandidateProfile.skills),
            selectinload(CandidateProfile.projects),
            selectinload(CandidateProfile.experience),
            selectinload(CandidateProfile.education),
            selectinload(CandidateProfile.certifications),
        )
    )
    result = await db.execute(stmt)
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found. Please create your profile.")
    return CandidateProfileOut.model_validate(profile)


@router.post("/resume/upload", response_model=ResumeUploadResponse)
async def upload_resume(
    file: UploadFile = File(...),
    user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a resume (PDF/DOCX/TXT), extract structured data, return for review.
    Does NOT auto-save - user must confirm and call POST /profile.
    """
    # Validate file type
    allowed_exts = settings.allowed_resume_exts
    filename = file.filename or ""
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in allowed_exts:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(allowed_exts)}"
        )

    # Validate size
    contents = await file.read()
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if len(contents) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size: {settings.max_upload_size_mb} MB"
        )

    # Extract text
    try:
        text = await extract_resume_text(contents, filename)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=422, detail=f"Resume extraction failed: {e}")

    if not text.strip():
        raise HTTPException(status_code=422, detail="Could not extract text from resume. File may be image-based or corrupted.")

    # Extract structured profile
    profile_data, uncertain_fields = await extract_profile_from_text(text)

    return ResumeUploadResponse(
        filename=filename,
        extracted_profile=profile_data,
        uncertain_fields=uncertain_fields,
        message=(
            "Resume extracted. Please review and correct the information below, "
            "then save your profile."
        ),
    )
