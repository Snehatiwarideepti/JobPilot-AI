"""
Pydantic schemas for JobPilot AI.
Used for API request/response validation and structured LLM outputs.
"""
from __future__ import annotations
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, HttpUrl, field_validator
from enum import Enum


# ============================================================
# ENUMS
# ============================================================

class WorkplaceType(str, Enum):
    remote = "remote"
    hybrid = "hybrid"
    on_site = "on_site"
    unspecified = "unspecified"


class EmploymentType(str, Enum):
    full_time = "full_time"
    part_time = "part_time"
    contract = "contract"
    internship = "internship"
    freelance = "freelance"
    unspecified = "unspecified"


class ExperienceLevel(str, Enum):
    internship = "internship"
    entry = "entry"
    mid = "mid"
    senior = "senior"
    lead = "lead"
    executive = "executive"
    unspecified = "unspecified"


class MatchDecision(str, Enum):
    strong_match = "MATCH"
    partial_match = "PARTIAL"
    gap = "GAP"
    unknown = "UNKNOWN"


class RetrievalMethod(str, Enum):
    keyword = "keyword"
    semantic = "semantic"
    hybrid = "hybrid"
    hybrid_rerank = "hybrid_rerank"


# ============================================================
# JOB SCHEMAS
# ============================================================

class JobBase(BaseModel):
    title: str
    company: Optional[str] = None
    location: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    workplace_type: Optional[WorkplaceType] = None
    employment_type: Optional[EmploymentType] = None
    experience_level: Optional[ExperienceLevel] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_currency: Optional[str] = None
    salary_period: Optional[str] = None
    description: Optional[str] = None
    responsibilities: Optional[str] = None
    requirements: Optional[str] = None
    benefits: Optional[str] = None
    skills: List[str] = Field(default_factory=list)
    application_url: Optional[str] = None
    source_url: Optional[str] = None
    posted_at: Optional[datetime] = None


class JobCreate(JobBase):
    source: str
    source_job_id: str
    raw_data: Optional[Dict[str, Any]] = None


class JobUpdate(BaseModel):
    title: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    is_active: Optional[bool] = None
    last_seen_at: Optional[datetime] = None
    raw_data: Optional[Dict[str, Any]] = None


class JobOut(JobBase):
    id: uuid.UUID
    source: str
    source_job_id: str
    is_active: bool
    first_seen_at: datetime
    last_seen_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class JobSearchParams(BaseModel):
    q: Optional[str] = Field(None, description="Search keyword or phrase")
    location: Optional[str] = None
    workplace_type: Optional[WorkplaceType] = None
    employment_type: Optional[EmploymentType] = None
    experience_level: Optional[ExperienceLevel] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    days: Optional[int] = Field(None, ge=1, le=365, description="Only jobs posted within last N days")
    page: int = Field(1, ge=1)
    limit: int = Field(20, ge=1, le=100)
    retrieval_method: RetrievalMethod = RetrievalMethod.hybrid_rerank


class JobSearchResponse(BaseModel):
    total: int
    page: int
    limit: int
    jobs: List["JobWithScore"]
    source: str
    retrieval_method: str


class JobWithScore(JobOut):
    match_score: Optional[float] = None
    semantic_score: Optional[float] = None
    keyword_score: Optional[float] = None
    skill_match_count: Optional[int] = None
    skill_gap_count: Optional[int] = None
    top_matching_skills: List[str] = Field(default_factory=list)
    skill_gaps: List[str] = Field(default_factory=list)


# ============================================================
# CANDIDATE SCHEMAS
# ============================================================

class CandidateSkillCreate(BaseModel):
    name: str
    category: Optional[str] = None
    proficiency: Optional[str] = None
    years_of_experience: Optional[float] = None


class CandidateSkillOut(CandidateSkillCreate):
    id: uuid.UUID
    source: Optional[str] = None
    model_config = {"from_attributes": True}


class CandidateProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None
    technologies: List[str] = Field(default_factory=list)
    url: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class CandidateProjectOut(CandidateProjectCreate):
    id: uuid.UUID
    model_config = {"from_attributes": True}


class CandidateExperienceCreate(BaseModel):
    company: str
    title: str
    location: Optional[str] = None
    description: Optional[str] = None
    technologies: List[str] = Field(default_factory=list)
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    is_current: bool = False


class CandidateExperienceOut(CandidateExperienceCreate):
    id: uuid.UUID
    model_config = {"from_attributes": True}


class CandidateEducationCreate(BaseModel):
    institution: str
    degree: Optional[str] = None
    field_of_study: Optional[str] = None
    gpa: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    is_current: bool = False


class CandidateEducationOut(CandidateEducationCreate):
    id: uuid.UUID
    model_config = {"from_attributes": True}


class CandidateCertificationCreate(BaseModel):
    name: str
    issuer: Optional[str] = None
    issued_date: Optional[str] = None
    expiry_date: Optional[str] = None
    credential_id: Optional[str] = None
    credential_url: Optional[str] = None


class CandidateCertificationOut(CandidateCertificationCreate):
    id: uuid.UUID
    model_config = {"from_attributes": True}


class CandidateProfileCreate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    linkedin_url: Optional[str] = None
    github_url: Optional[str] = None
    portfolio_url: Optional[str] = None
    target_roles: List[str] = Field(default_factory=list)
    preferred_locations: List[str] = Field(default_factory=list)
    remote_preference: Optional[str] = None
    experience_level: Optional[str] = None
    preferred_salary_min: Optional[int] = None
    preferred_salary_max: Optional[int] = None
    preferred_salary_currency: Optional[str] = None
    summary: Optional[str] = None
    skills: List[CandidateSkillCreate] = Field(default_factory=list)
    projects: List[CandidateProjectCreate] = Field(default_factory=list)
    experience: List[CandidateExperienceCreate] = Field(default_factory=list)
    education: List[CandidateEducationCreate] = Field(default_factory=list)
    certifications: List[CandidateCertificationCreate] = Field(default_factory=list)


class CandidateProfileOut(BaseModel):
    id: uuid.UUID
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    linkedin_url: Optional[str] = None
    github_url: Optional[str] = None
    portfolio_url: Optional[str] = None
    target_roles: List[str] = Field(default_factory=list)
    preferred_locations: List[str] = Field(default_factory=list)
    remote_preference: Optional[str] = None
    experience_level: Optional[str] = None
    summary: Optional[str] = None
    skills: List[CandidateSkillOut] = Field(default_factory=list)
    projects: List[CandidateProjectOut] = Field(default_factory=list)
    experience: List[CandidateExperienceOut] = Field(default_factory=list)
    education: List[CandidateEducationOut] = Field(default_factory=list)
    certifications: List[CandidateCertificationOut] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    model_config = {"from_attributes": True}


# ============================================================
# MATCH ANALYSIS SCHEMAS (Structured LLM Output)
# ============================================================

class RequirementEvidence(BaseModel):
    requirement: str = Field(description="The job requirement being evaluated")
    candidate_evidence: Optional[str] = Field(None, description="Actual evidence from candidate profile, or None if not found")
    decision: MatchDecision = Field(description="MATCH, PARTIAL, GAP, or UNKNOWN")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence in this decision (0-1)")
    source_type: Optional[str] = Field(None, description="Where evidence was found: skill, project, experience, education")


class JobMatchAnalysis(BaseModel):
    overall_match_score: float = Field(ge=0, le=100, description="Composite match score 0-100")
    matched_requirements: List[RequirementEvidence] = Field(default_factory=list)
    partial_matches: List[RequirementEvidence] = Field(default_factory=list)
    skill_gaps: List[RequirementEvidence] = Field(default_factory=list)
    candidate_evidence: List[str] = Field(default_factory=list, description="Key evidence statements")
    reasoning: str = Field(description="Overall reasoning for the match score")
    recommendation: str = Field(description="Strong match / Moderate match / Weak match / Not recommended")
    top_matching_skills: List[str] = Field(default_factory=list)
    missing_skills: List[str] = Field(default_factory=list)


# ============================================================
# MATCH ANALYSIS V2 SCHEMAS (Full explainable pipeline)
# ============================================================

class ScoreBreakdown(BaseModel):
    """
    Transparent scoring breakdown so the final score is fully auditable.

    Formula:
      skill_score     = weighted_avg(evidence_items) * 100           [0-100]
      experience_fit  = 100 if levels match, 50 if adjacent, 0 if mismatch, None if unknown
      workplace_fit   = 100 if match, 50 if flexible/unspecified, 0 if mismatch, None if unknown
      overall         = skill_score * 0.70
                      + (experience_fit  or 50) * 0.20
                      + (workplace_fit   or 50) * 0.10
      Rounded to 1 decimal place.
    """
    skill_score: float = Field(ge=0, le=100, description="Skill/requirement match score 0-100")
    experience_fit_score: Optional[float] = Field(None, ge=0, le=100,
        description="Experience level fit 0-100; None if job level unknown")
    workplace_fit_score: Optional[float] = Field(None, ge=0, le=100,
        description="Workplace/location fit 0-100; None if job type unknown")
    skill_weight: float = Field(0.70, description="Weight applied to skill_score")
    experience_weight: float = Field(0.20, description="Weight applied to experience_fit_score")
    workplace_weight: float = Field(0.10, description="Weight applied to workplace_fit_score")
    overall_score: float = Field(ge=0, le=100, description="Weighted composite score 0-100")


class ExperienceFitResult(BaseModel):
    candidate_level: Optional[str] = Field(None, description="Candidate's self-reported level")
    job_required_level: Optional[str] = Field(None, description="Level required by the job; None if not specified")
    fit: MatchDecision = Field(description="MATCH / PARTIAL / GAP / UNKNOWN")
    explanation: str = Field(description="Why this fit decision was made")


class WorkplaceFitResult(BaseModel):
    candidate_preference: Optional[str] = Field(None, description="Candidate's preferred work mode")
    job_workplace_type: Optional[str] = Field(None, description="Job's work mode; None if not specified")
    candidate_location: Optional[str] = Field(None, description="Candidate's location")
    job_location: Optional[str] = Field(None, description="Job's location")
    fit: MatchDecision = Field(description="MATCH / PARTIAL / GAP / UNKNOWN")
    explanation: str = Field(description="Why this fit decision was made")


class JobMatchAnalysisV2(BaseModel):
    """
    Full explainable match analysis.
    All fields are grounded in actual candidate and job data.
    Nothing is invented.
    """
    # Job identity (for context)
    job_id: Optional[str] = Field(None, description="Internal job ID")
    job_title: str
    job_company: Optional[str] = None

    # Core scoring
    overall_match_score: float = Field(ge=0, le=100, description="Composite match score 0-100")
    score_breakdown: ScoreBreakdown
    recommendation: str = Field(description="Strong match / Moderate match / Weak match / Not recommended")

    # Requirement evidence
    matched_requirements: List[RequirementEvidence] = Field(default_factory=list,
        description="Requirements with strong candidate evidence")
    partial_matches: List[RequirementEvidence] = Field(default_factory=list,
        description="Requirements with partial candidate evidence")
    missing_requirements: List[RequirementEvidence] = Field(default_factory=list,
        description="Requirements where no candidate evidence was found (GAP)")
    unknown_requirements: List[RequirementEvidence] = Field(default_factory=list,
        description="Requirements that could not be evaluated (UNKNOWN)")

    # Fit dimensions
    experience_fit: ExperienceFitResult
    workplace_fit: WorkplaceFitResult

    # Strengths and gaps
    candidate_strengths: List[str] = Field(default_factory=list,
        description="Candidate skills/experience relevant to this job, grounded in profile")
    top_matching_skills: List[str] = Field(default_factory=list)
    missing_skills: List[str] = Field(default_factory=list)

    # Narrative (deterministic fallback; LLM-enriched if key present)
    reasoning: str = Field(description="Deterministic explanation of the match")

    # Traceability
    total_requirements_evaluated: int = Field(0)
    data_sources_used: List[str] = Field(default_factory=list,
        description="Which profile sections contributed evidence")


class BulkMatchRequest(BaseModel):
    """Analyze a candidate against a list of jobs by their internal IDs."""
    user_id: str = Field(description="UUID of the user whose profile to use")
    job_ids: List[str] = Field(description="List of internal job UUIDs to analyze")
    max_jobs: int = Field(20, ge=1, le=50, description="Cap on number of jobs analyzed")


class BulkMatchResponse(BaseModel):
    user_id: str
    total_analyzed: int
    analyses: List[JobMatchAnalysisV2]
    note: str = "All analyses are grounded in actual candidate profile and job data. Nothing is invented."


# ============================================================
# SKILL GAP ANALYSIS SCHEMAS
# ============================================================

class SkillGapItem(BaseModel):
    skill: str
    frequency_in_target_jobs: int = Field(description="How many retrieved jobs require this skill")
    candidate_status: MatchDecision
    candidate_evidence: Optional[str] = None
    priority: str = Field(description="high / medium / low based on frequency and gap")


class SkillGapAnalysis(BaseModel):
    target_query: str
    total_jobs_analyzed: int
    skill_coverage: List[SkillGapItem]
    recommended_skills_to_learn: List[str]
    strong_skills: List[str]
    partial_skills: List[str]
    missing_skills: List[str]
    data_source: str = "Retrieved job listings"
    note: str = "Recommendations are based on observed skill frequency in retrieved job listings, not general career advice."


# ============================================================
# AGENT SCHEMAS
# ============================================================

class SearchIntent(BaseModel):
    query: str
    keywords: List[str] = Field(default_factory=list)
    location: Optional[str] = None
    workplace_type: Optional[WorkplaceType] = None
    employment_type: Optional[EmploymentType] = None
    experience_level: Optional[ExperienceLevel] = None
    is_refinement: bool = Field(False, description="True if this refines a previous search")
    previous_context: Optional[str] = None


class AgentToolCall(BaseModel):
    tool_name: str
    arguments: Dict[str, Any]
    result: Optional[Any] = None
    error: Optional[str] = None


class AgentResponse(BaseModel):
    message: str
    tool_calls: List[AgentToolCall] = Field(default_factory=list)
    jobs: Optional[List[JobWithScore]] = None
    match_analysis: Optional[JobMatchAnalysis] = None
    skill_gap_analysis: Optional[SkillGapAnalysis] = None
    session_id: str


# ============================================================
# CHAT SCHEMAS
# ============================================================

class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=5000)
    session_id: Optional[str] = None
    user_id: Optional[str] = None  # anonymous if not provided


class ChatResponse(BaseModel):
    session_id: str
    response: str
    tool_calls_made: List[str] = Field(default_factory=list)
    jobs_found: Optional[List[JobWithScore]] = None
    match_analysis: Optional[JobMatchAnalysis] = None
    skill_gap_analysis: Optional[SkillGapAnalysis] = None


# ============================================================
# EVALUATION SCHEMAS
# ============================================================

class EvaluationQueryCreate(BaseModel):
    query_text: str
    expected_job_ids: List[str] = Field(default_factory=list)
    relevance_judgments: Optional[Dict[str, int]] = None  # job_id -> relevance score (0/1/2)
    category: Optional[str] = None


class EvaluationResultOut(BaseModel):
    retrieval_method: str
    hit_at_5: Optional[float] = None
    hit_at_10: Optional[float] = None
    mrr: Optional[float] = None
    run_at: datetime
    model_config = {"from_attributes": True}


class EvaluationSummary(BaseModel):
    total_queries: int
    methods: Dict[str, Dict[str, Optional[float]]]  # method -> metric -> avg value
    note: str = "All metrics computed by actually running queries against the retrieval system."


# ============================================================
# USER SCHEMAS
# ============================================================

class UserCreate(BaseModel):
    email: str
    full_name: Optional[str] = None
    password: Optional[str] = None  # optional for now


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: Optional[str] = None
    is_active: bool
    created_at: datetime
    model_config = {"from_attributes": True}


# ============================================================
# HEALTH / GENERAL
# ============================================================

class HealthResponse(BaseModel):
    status: str
    database: str
    embeddings: str
    provider: str
    llm: str
    version: str = "1.0.0"


class ResumeUploadResponse(BaseModel):
    filename: str
    extracted_profile: CandidateProfileCreate
    uncertain_fields: List[str] = Field(default_factory=list, description="Fields the extraction was unsure about")
    message: str


class SavedJobCreate(BaseModel):
    job_id: str
    notes: Optional[str] = None


class SavedJobOut(BaseModel):
    id: uuid.UUID
    job: JobOut
    notes: Optional[str] = None
    created_at: datetime
    model_config = {"from_attributes": True}
