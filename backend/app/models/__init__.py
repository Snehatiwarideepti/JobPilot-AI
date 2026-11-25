"""
SQLAlchemy ORM models for JobPilot AI.
Covers: users, candidate profiles/skills/projects/experience/education,
        jobs, job_skills, job_embeddings, candidate_embeddings,
        saved_jobs, messages, search_history, job_match_evidence,
        evaluation_queries, evaluation_results.
"""
import uuid
from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    String, Text, Integer, Float, Boolean, DateTime, ForeignKey,
    UniqueConstraint, Index, JSON, Enum as SAEnum, BigInteger
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
from app.database import Base
from app.config import get_settings

settings = get_settings()
EMBED_DIM = settings.embedding_dimension  # 384


# ============================================================
# USERS
# ============================================================

class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    profile: Mapped[Optional["CandidateProfile"]] = relationship("CandidateProfile", back_populates="user", uselist=False)
    saved_jobs: Mapped[List["SavedJob"]] = relationship("SavedJob", back_populates="user")
    messages: Mapped[List["Message"]] = relationship("Message", back_populates="user")
    search_history: Mapped[List["SearchHistory"]] = relationship("SearchHistory", back_populates="user")


# ============================================================
# CANDIDATE PROFILE
# ============================================================

class CandidateProfile(Base):
    __tablename__ = "candidate_profiles"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)

    # Basic info
    full_name: Mapped[Optional[str]] = mapped_column(String(255))
    email: Mapped[Optional[str]] = mapped_column(String(255))
    phone: Mapped[Optional[str]] = mapped_column(String(50))
    location: Mapped[Optional[str]] = mapped_column(String(255))
    linkedin_url: Mapped[Optional[str]] = mapped_column(String(500))
    github_url: Mapped[Optional[str]] = mapped_column(String(500))
    portfolio_url: Mapped[Optional[str]] = mapped_column(String(500))

    # Career preferences
    target_roles: Mapped[Optional[List]] = mapped_column(JSONB, default=list)  # ["ML Engineer", "Data Scientist"]
    preferred_locations: Mapped[Optional[List]] = mapped_column(JSONB, default=list)
    remote_preference: Mapped[Optional[str]] = mapped_column(
        SAEnum("remote", "hybrid", "on_site", "flexible", name="remote_pref_enum"), nullable=True
    )
    experience_level: Mapped[Optional[str]] = mapped_column(
        SAEnum("internship", "entry", "mid", "senior", "lead", "executive", name="exp_level_enum"), nullable=True
    )
    preferred_salary_min: Mapped[Optional[int]] = mapped_column(Integer)
    preferred_salary_max: Mapped[Optional[int]] = mapped_column(Integer)
    preferred_salary_currency: Mapped[Optional[str]] = mapped_column(String(10))

    # Resume
    resume_raw_text: Mapped[Optional[str]] = mapped_column(Text)
    resume_filename: Mapped[Optional[str]] = mapped_column(String(255))
    resume_uploaded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Summary (extracted or written)
    summary: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="profile")
    skills: Mapped[List["CandidateSkill"]] = relationship("CandidateSkill", back_populates="profile", cascade="all, delete-orphan")
    projects: Mapped[List["CandidateProject"]] = relationship("CandidateProject", back_populates="profile", cascade="all, delete-orphan")
    experience: Mapped[List["CandidateExperience"]] = relationship("CandidateExperience", back_populates="profile", cascade="all, delete-orphan")
    education: Mapped[List["CandidateEducation"]] = relationship("CandidateEducation", back_populates="profile", cascade="all, delete-orphan")
    certifications: Mapped[List["CandidateCertification"]] = relationship("CandidateCertification", back_populates="profile", cascade="all, delete-orphan")
    embeddings: Mapped[List["CandidateEmbedding"]] = relationship("CandidateEmbedding", back_populates="profile", cascade="all, delete-orphan")


class CandidateSkill(Base):
    __tablename__ = "candidate_skills"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("candidate_profiles.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[Optional[str]] = mapped_column(String(100))  # language, framework, tool, etc.
    proficiency: Mapped[Optional[str]] = mapped_column(
        SAEnum("beginner", "intermediate", "advanced", "expert", name="proficiency_enum"), nullable=True
    )
    years_of_experience: Mapped[Optional[float]] = mapped_column(Float)
    source: Mapped[Optional[str]] = mapped_column(String(50))  # "resume", "manual", "extracted"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    profile: Mapped["CandidateProfile"] = relationship("CandidateProfile", back_populates="skills")

    __table_args__ = (
        UniqueConstraint("profile_id", "name", name="uq_candidate_skill"),
        Index("ix_candidate_skills_name", "name"),
    )


class CandidateProject(Base):
    __tablename__ = "candidate_projects"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("candidate_profiles.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    technologies: Mapped[Optional[List]] = mapped_column(JSONB, default=list)  # ["Python", "Flask", "scikit-learn"]
    url: Mapped[Optional[str]] = mapped_column(String(500))
    start_date: Mapped[Optional[str]] = mapped_column(String(20))
    end_date: Mapped[Optional[str]] = mapped_column(String(20))
    source: Mapped[Optional[str]] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    profile: Mapped["CandidateProfile"] = relationship("CandidateProfile", back_populates="projects")


class CandidateExperience(Base):
    __tablename__ = "candidate_experience"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("candidate_profiles.id", ondelete="CASCADE"), index=True)
    company: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[Optional[str]] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text)
    technologies: Mapped[Optional[List]] = mapped_column(JSONB, default=list)
    start_date: Mapped[Optional[str]] = mapped_column(String(20))
    end_date: Mapped[Optional[str]] = mapped_column(String(20))
    is_current: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[Optional[str]] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    profile: Mapped["CandidateProfile"] = relationship("CandidateProfile", back_populates="experience")


class CandidateEducation(Base):
    __tablename__ = "candidate_education"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("candidate_profiles.id", ondelete="CASCADE"), index=True)
    institution: Mapped[str] = mapped_column(String(255), nullable=False)
    degree: Mapped[Optional[str]] = mapped_column(String(255))
    field_of_study: Mapped[Optional[str]] = mapped_column(String(255))
    gpa: Mapped[Optional[str]] = mapped_column(String(20))
    start_date: Mapped[Optional[str]] = mapped_column(String(20))
    end_date: Mapped[Optional[str]] = mapped_column(String(20))
    is_current: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[Optional[str]] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    profile: Mapped["CandidateProfile"] = relationship("CandidateProfile", back_populates="education")


class CandidateCertification(Base):
    __tablename__ = "candidate_certifications"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("candidate_profiles.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    issuer: Mapped[Optional[str]] = mapped_column(String(255))
    issued_date: Mapped[Optional[str]] = mapped_column(String(20))
    expiry_date: Mapped[Optional[str]] = mapped_column(String(20))
    credential_id: Mapped[Optional[str]] = mapped_column(String(255))
    credential_url: Mapped[Optional[str]] = mapped_column(String(500))
    source: Mapped[Optional[str]] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    profile: Mapped["CandidateProfile"] = relationship("CandidateProfile", back_populates="certifications")


class CandidateEmbedding(Base):
    __tablename__ = "candidate_embeddings"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("candidate_profiles.id", ondelete="CASCADE"), index=True, unique=True)
    embedding: Mapped[Optional[object]] = mapped_column(Vector(EMBED_DIM))
    model_name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    profile: Mapped["CandidateProfile"] = relationship("CandidateProfile", back_populates="embeddings")


# ============================================================
# JOBS
# ============================================================

class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Provider tracking
    source: Mapped[str] = mapped_column(String(100), nullable=False, index=True)       # "jobvetta"
    source_job_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # Core fields
    title: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    company: Mapped[Optional[str]] = mapped_column(String(500), index=True)
    location: Mapped[Optional[str]] = mapped_column(String(500))
    country: Mapped[Optional[str]] = mapped_column(String(100))
    city: Mapped[Optional[str]] = mapped_column(String(255))
    workplace_type: Mapped[Optional[str]] = mapped_column(
        SAEnum("remote", "hybrid", "on_site", "unspecified", name="workplace_type_enum"), nullable=True
    )
    employment_type: Mapped[Optional[str]] = mapped_column(
        SAEnum("full_time", "part_time", "contract", "internship", "freelance", "unspecified", name="emp_type_enum"), nullable=True
    )
    experience_level: Mapped[Optional[str]] = mapped_column(
        SAEnum("internship", "entry", "mid", "senior", "lead", "executive", "unspecified", name="job_exp_level_enum"), nullable=True
    )

    # Compensation
    salary_min: Mapped[Optional[int]] = mapped_column(Integer)
    salary_max: Mapped[Optional[int]] = mapped_column(Integer)
    salary_currency: Mapped[Optional[str]] = mapped_column(String(10))
    salary_period: Mapped[Optional[str]] = mapped_column(String(50))  # "annual", "monthly", etc.

    # Content
    description: Mapped[Optional[str]] = mapped_column(Text)
    responsibilities: Mapped[Optional[str]] = mapped_column(Text)
    requirements: Mapped[Optional[str]] = mapped_column(Text)
    benefits: Mapped[Optional[str]] = mapped_column(Text)
    skills: Mapped[Optional[List]] = mapped_column(JSONB, default=list)       # extracted skill list

    # URLs
    application_url: Mapped[Optional[str]] = mapped_column(String(2048))
    source_url: Mapped[Optional[str]] = mapped_column(String(2048))

    # Full-text search vector (computed column or maintained separately)
    search_vector: Mapped[Optional[str]] = mapped_column(Text)  # for tsvector via trigger/function

    # Provider raw metadata (flexible)
    raw_data: Mapped[Optional[dict]] = mapped_column(JSONB)

    # Timestamps
    posted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    skills_rel: Mapped[List["JobSkill"]] = relationship("JobSkill", back_populates="job", cascade="all, delete-orphan")
    embeddings: Mapped[List["JobEmbedding"]] = relationship("JobEmbedding", back_populates="job", cascade="all, delete-orphan")
    saved_by: Mapped[List["SavedJob"]] = relationship("SavedJob", back_populates="job")
    match_evidence: Mapped[List["JobMatchEvidence"]] = relationship("JobMatchEvidence", back_populates="job", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("source", "source_job_id", name="uq_job_source"),
        Index("ix_jobs_title_company", "title", "company"),
        Index("ix_jobs_workplace_type", "workplace_type"),
        Index("ix_jobs_employment_type", "employment_type"),
        Index("ix_jobs_experience_level", "experience_level"),
        Index("ix_jobs_posted_at", "posted_at"),
        Index("ix_jobs_is_active", "is_active"),
    )


class JobSkill(Base):
    __tablename__ = "job_skills"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    skill_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    is_required: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    job: Mapped["Job"] = relationship("Job", back_populates="skills_rel")

    __table_args__ = (
        UniqueConstraint("job_id", "skill_name", name="uq_job_skill"),
    )


class JobEmbedding(Base):
    __tablename__ = "job_embeddings"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), index=True, unique=True)
    embedding: Mapped[Optional[object]] = mapped_column(Vector(EMBED_DIM))
    model_name: Mapped[str] = mapped_column(String(255))
    embedding_text: Mapped[Optional[str]] = mapped_column(Text)  # the text that was embedded
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    job: Mapped["Job"] = relationship("Job", back_populates="embeddings")


# ============================================================
# SAVED JOBS
# ============================================================

class SavedJob(Base):
    __tablename__ = "saved_jobs"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship("User", back_populates="saved_jobs")
    job: Mapped["Job"] = relationship("Job", back_populates="saved_by")

    __table_args__ = (
        UniqueConstraint("user_id", "job_id", name="uq_saved_job"),
    )


# ============================================================
# MESSAGES (Conversation Memory)
# ============================================================

class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    session_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    role: Mapped[str] = mapped_column(SAEnum("user", "assistant", "tool", name="message_role_enum"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tool_calls: Mapped[Optional[dict]] = mapped_column(JSONB)       # tool invocations by agent
    tool_results: Mapped[Optional[dict]] = mapped_column(JSONB)     # tool results
    extra_metadata: Mapped[Optional[dict]] = mapped_column("metadata", JSONB)         # search context, job IDs, etc.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship("User", back_populates="messages")

    __table_args__ = (
        Index("ix_messages_session_created", "session_id", "created_at"),
    )


# ============================================================
# SEARCH HISTORY
# ============================================================

class SearchHistory(Base):
    __tablename__ = "search_history"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    filters: Mapped[Optional[dict]] = mapped_column(JSONB)
    result_count: Mapped[Optional[int]] = mapped_column(Integer)
    source: Mapped[Optional[str]] = mapped_column(String(50))  # "search_page", "chat", "api"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[Optional["User"]] = relationship("User", back_populates="search_history")


# ============================================================
# JOB MATCH EVIDENCE
# ============================================================

class JobMatchEvidence(Base):
    __tablename__ = "job_match_evidence"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    profile_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("candidate_profiles.id", ondelete="CASCADE"), index=True)

    overall_match_score: Mapped[Optional[float]] = mapped_column(Float)
    matched_requirements: Mapped[Optional[List]] = mapped_column(JSONB, default=list)
    partial_matches: Mapped[Optional[List]] = mapped_column(JSONB, default=list)
    skill_gaps: Mapped[Optional[List]] = mapped_column(JSONB, default=list)
    candidate_evidence: Mapped[Optional[List]] = mapped_column(JSONB, default=list)
    reasoning: Mapped[Optional[str]] = mapped_column(Text)
    recommendation: Mapped[Optional[str]] = mapped_column(String(100))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    job: Mapped["Job"] = relationship("Job", back_populates="match_evidence")

    __table_args__ = (
        UniqueConstraint("job_id", "profile_id", name="uq_job_match_evidence"),
    )


# ============================================================
# EVALUATION
# ============================================================

class EvaluationQuery(Base):
    __tablename__ = "evaluation_queries"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    expected_job_ids: Mapped[Optional[List]] = mapped_column(JSONB, default=list)
    relevance_judgments: Mapped[Optional[dict]] = mapped_column(JSONB)
    category: Mapped[Optional[str]] = mapped_column(String(100))  # "internship", "remote", etc.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    results: Mapped[List["EvaluationResult"]] = relationship("EvaluationResult", back_populates="query", cascade="all, delete-orphan")


class EvaluationResult(Base):
    __tablename__ = "evaluation_results"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    query_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("evaluation_queries.id", ondelete="CASCADE"), index=True)
    retrieval_method: Mapped[str] = mapped_column(
        SAEnum("keyword", "semantic", "hybrid", "hybrid_rerank", name="retrieval_method_enum"), nullable=False
    )
    hit_at_5: Mapped[Optional[float]] = mapped_column(Float)
    hit_at_10: Mapped[Optional[float]] = mapped_column(Float)
    mrr: Mapped[Optional[float]] = mapped_column(Float)
    retrieved_job_ids: Mapped[Optional[List]] = mapped_column(JSONB, default=list)
    scores: Mapped[Optional[List]] = mapped_column(JSONB)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    query: Mapped["EvaluationQuery"] = relationship("EvaluationQuery", back_populates="results")
