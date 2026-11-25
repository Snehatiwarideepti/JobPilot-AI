"""
Hybrid retrieval engine for JobPilot AI.

Implements:
1. Keyword search  - PostgreSQL full-text search (tsvector/tsquery)
2. Semantic search - pgvector cosine similarity
3. Hybrid search   - RRF (Reciprocal Rank Fusion) of keyword + semantic
4. Reranking       - Multi-factor scoring (semantic + skill + experience + location)

The reranking weights are configurable via settings and are
labelled as "system ranking configuration", NOT scientifically optimal.
"""
from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import uuid

from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.embeddings.service import get_embedding_service
from app.models import Job, JobEmbedding, CandidateProfile, CandidateSkill

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass
class RetrievedJob:
    """A job returned from the retrieval pipeline with associated scores."""
    job: Job
    keyword_score: float = 0.0
    semantic_score: float = 0.0
    hybrid_score: float = 0.0
    skill_match_score: float = 0.0
    experience_match_score: float = 0.0
    location_score: float = 0.0
    final_score: float = 0.0
    matched_skills: List[str] = field(default_factory=list)
    missing_skills: List[str] = field(default_factory=list)
    rank: int = 0


# ---------------------------------------------------------------------------
# Keyword Search
# ---------------------------------------------------------------------------

async def keyword_search(
    db: AsyncSession,
    query: str,
    limit: int = 50,
    filters: Optional[Dict[str, Any]] = None,
) -> List[Tuple[Job, float]]:
    """
    PostgreSQL full-text search using tsvector.
    Returns (Job, rank_score) tuples ordered by relevance.
    """
    if not query.strip():
        return []

    # Build parameterized query - safe against SQL injection
    sql = text("""
        SELECT
            j.*,
            ts_rank_cd(
                to_tsvector('english',
                    coalesce(j.title, '') || ' ' ||
                    coalesce(j.company, '') || ' ' ||
                    coalesce(j.description, '') || ' ' ||
                    coalesce(j.requirements, '') || ' ' ||
                    coalesce(j.responsibilities, '')
                ),
                plainto_tsquery('english', :query)
            ) AS rank_score
        FROM jobs j
        WHERE
            j.is_active = true
            AND to_tsvector('english',
                coalesce(j.title, '') || ' ' ||
                coalesce(j.company, '') || ' ' ||
                coalesce(j.description, '') || ' ' ||
                coalesce(j.requirements, '') || ' ' ||
                coalesce(j.responsibilities, '')
            ) @@ plainto_tsquery('english', :query)
            {filter_clauses}
        ORDER BY rank_score DESC
        LIMIT :limit
    """.format(filter_clauses=_build_filter_clauses(filters)))

    params = {"query": query, "limit": limit}
    _add_filter_params(params, filters)

    result = await db.execute(sql, params)
    rows = result.fetchall()

    jobs_with_scores: List[Tuple[Job, float]] = []
    for row in rows:
        row_dict = dict(row._mapping)
        rank_score = float(row_dict.pop("rank_score", 0))
        # Reconstruct Job from row
        job = await db.get(Job, row_dict["id"])
        if job:
            jobs_with_scores.append((job, rank_score))

    return jobs_with_scores


# ---------------------------------------------------------------------------
# Candidate-Aware Query Synthesis
# ---------------------------------------------------------------------------

def build_candidate_search_query(
    candidate_profile: Optional[CandidateProfile] = None,
    base_query: Optional[str] = None,
) -> str:
    """
    Synthesize search text combining user base query and candidate profile data
    (skills, target roles, experience, projects, preferences).

    If candidate_profile is None, returns base_query or empty string.
    If base_query is empty, synthesizes purely from candidate_profile.
    """
    if not candidate_profile:
        return (base_query or "").strip()

    parts: List[str] = []

    # 1. Base query or Target roles
    if base_query and base_query.strip():
        parts.append(f"Target Role / Query: {base_query.strip()}")
    target_roles = getattr(candidate_profile, "target_roles", None)
    if target_roles and isinstance(target_roles, list):
        roles_str = ", ".join(str(r) for r in target_roles if r)
        if roles_str and not (base_query and roles_str.lower() in base_query.lower()):
            parts.append(f"Target Roles: {roles_str}")

    # 2. Skills
    skills = getattr(candidate_profile, "skills", None)
    if skills:
        skill_names = []
        for s in skills:
            if hasattr(s, "name") and s.name:
                skill_names.append(str(s.name).strip())
            elif isinstance(s, str) and s.strip():
                skill_names.append(s.strip())
        if skill_names:
            parts.append(f"Skills: {', '.join(skill_names)}")

    # 3. Experience level
    exp_level = getattr(candidate_profile, "experience_level", None)
    if exp_level and exp_level != "unspecified":
        parts.append(f"Experience Level: {exp_level}")

    # 4. Work Experience
    experiences = getattr(candidate_profile, "experience", None) or []
    if experiences:
        exp_entries = []
        for e in experiences[:3]:
            title = getattr(e, "title", None) or ""
            company = getattr(e, "company", None) or ""
            desc = (getattr(e, "description", None) or "")[:200]
            techs = getattr(e, "technologies", None) or []
            tech_str = f" ({', '.join(str(t) for t in techs)})" if techs else ""
            item = f"{title} at {company}{tech_str}".strip()
            if desc:
                item += f" - {desc}"
            if item:
                exp_entries.append(item)
        if exp_entries:
            parts.append(f"Experience: {' | '.join(exp_entries)}")

    # 5. Projects
    projects = getattr(candidate_profile, "projects", None) or []
    if projects:
        proj_entries = []
        for p in projects[:3]:
            name = getattr(p, "name", None) or ""
            desc = (getattr(p, "description", None) or "")[:200]
            techs = getattr(p, "technologies", None) or []
            tech_str = f" ({', '.join(str(t) for t in techs)})" if techs else ""
            item = f"{name}{tech_str}".strip()
            if desc:
                item += f" - {desc}"
            if item:
                proj_entries.append(item)
        if proj_entries:
            parts.append(f"Projects: {' | '.join(proj_entries)}")

    # 6. Workplace & Location preferences
    remote_pref = getattr(candidate_profile, "remote_preference", None)
    if remote_pref:
        parts.append(f"Workplace Preference: {remote_pref}")
    pref_locs = getattr(candidate_profile, "preferred_locations", None)
    if pref_locs and isinstance(pref_locs, list):
        loc_str = ", ".join(str(l) for l in pref_locs if l)
        if loc_str:
            parts.append(f"Preferred Locations: {loc_str}")

    # 7. Summary
    summary = getattr(candidate_profile, "summary", None)
    if summary and summary.strip():
        parts.append(f"Summary: {summary.strip()[:300]}")

    if not parts:
        return (base_query or "").strip()

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Semantic Search
# ---------------------------------------------------------------------------

async def semantic_search(
    db: AsyncSession,
    query: str,
    limit: int = 50,
    filters: Optional[Dict[str, Any]] = None,
    candidate_profile: Optional[CandidateProfile] = None,
) -> List[Tuple[Job, float]]:
    """
    pgvector cosine similarity search.
    Returns (Job, similarity_score) tuples ordered by similarity.
    If candidate_profile is provided, synthesizes a candidate-aware semantic search text.
    """
    search_text = build_candidate_search_query(candidate_profile, base_query=query)
    if not search_text.strip():
        return []

    embedding_service = get_embedding_service()
    query_vector = await embedding_service.embed_text(search_text)

    # Format as PostgreSQL array literal
    vec_str = "[" + ",".join(str(x) for x in query_vector) + "]"

    sql = text("""
        SELECT
            j.*,
            1 - (je.embedding <=> CAST(:query_vector AS vector)) AS similarity
        FROM jobs j
        INNER JOIN job_embeddings je ON je.job_id = j.id
        WHERE
            j.is_active = true
            {filter_clauses}
        ORDER BY je.embedding <=> CAST(:query_vector AS vector)
        LIMIT :limit
    """.format(filter_clauses=_build_filter_clauses(filters)))

    params = {"query_vector": vec_str, "limit": limit}
    _add_filter_params(params, filters)

    result = await db.execute(sql, params)
    rows = result.fetchall()

    jobs_with_scores: List[Tuple[Job, float]] = []
    for row in rows:
        row_dict = dict(row._mapping)
        similarity = float(row_dict.pop("similarity", 0))
        job = await db.get(Job, row_dict["id"])
        if job:
            jobs_with_scores.append((job, max(0.0, similarity)))

    return jobs_with_scores


# ---------------------------------------------------------------------------
# Hybrid Search (RRF)
# ---------------------------------------------------------------------------

def reciprocal_rank_fusion(
    keyword_results: List[Tuple[Job, float]],
    semantic_results: List[Tuple[Job, float]],
    k: int = 60,
    keyword_weight: float = 0.4,
    semantic_weight: float = 0.6,
) -> List[Tuple[Job, float]]:
    """
    Combine keyword and semantic results using Reciprocal Rank Fusion.
    RRF score = sum(weight / (k + rank)) for each result list.
    """
    scores: Dict[uuid.UUID, float] = {}
    job_map: Dict[uuid.UUID, Job] = {}

    # Keyword RRF
    for rank, (job, _) in enumerate(keyword_results, start=1):
        score = keyword_weight / (k + rank)
        scores[job.id] = scores.get(job.id, 0) + score
        job_map[job.id] = job

    # Semantic RRF
    for rank, (job, _) in enumerate(semantic_results, start=1):
        score = semantic_weight / (k + rank)
        scores[job.id] = scores.get(job.id, 0) + score
        job_map[job.id] = job

    # Sort by combined RRF score
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [(job_map[job_id], score) for job_id, score in ranked]


async def hybrid_search(
    db: AsyncSession,
    query: str,
    limit: int = 50,
    filters: Optional[Dict[str, Any]] = None,
    candidate_profile: Optional[CandidateProfile] = None,
) -> List[Tuple[Job, float]]:
    """
    Combines keyword and semantic search using RRF.
    Executes keyword and semantic searches sequentially on the same AsyncSession
    because SQLAlchemy AsyncSession does not permit concurrent operations.
    If candidate_profile is provided, semantic search uses candidate-aware synthesized query.
    """
    keyword_results = await keyword_search(db, query, limit=limit * 2, filters=filters)
    if candidate_profile is not None:
        semantic_results = await semantic_search(
            db, query, limit=limit * 2, filters=filters, candidate_profile=candidate_profile
        )
    else:
        semantic_results = await semantic_search(db, query, limit=limit * 2, filters=filters)

    # Preserve individual component scores so rerank_results can use actual
    # cosine similarity rather than max-normalized RRF scores.
    kw_scores = {job.id: score for job, score in keyword_results}
    sem_scores = {job.id: score for job, score in semantic_results}

    # If semantic search failed (e.g., no embeddings yet), fall back to keyword only
    if not semantic_results:
        logger.warning("Semantic search returned no results; using keyword only")
        for job, score in keyword_results:
            job._keyword_score = score
            job._semantic_similarity = 0.0
        return keyword_results[:limit]

    hybrid = reciprocal_rank_fusion(keyword_results, semantic_results)
    for job, _ in hybrid:
        job._keyword_score = kw_scores.get(job.id, 0.0)
        job._semantic_similarity = sem_scores.get(job.id, 0.0)
    return hybrid[:limit]


# ---------------------------------------------------------------------------
# Reranking
# ---------------------------------------------------------------------------

async def rerank_results(
    results: List[Tuple[Job, float]],
    candidate_profile: Optional[CandidateProfile] = None,
    query: Optional[str] = None,
) -> List[RetrievedJob]:
    """
    Rerank hybrid search results using multi-factor scoring.

    Weights (configurable, NOT scientifically optimal - system ranking configuration):
        55% - semantic similarity
        20% - skill match
        15% - experience level match
        10% - location/workplace compatibility
    """
    w_semantic = settings.semantic_weight
    w_skill = settings.skill_weight
    w_experience = settings.experience_weight
    w_location = settings.location_weight

    candidate_skills: set[str] = set()
    candidate_exp_level: Optional[str] = None
    candidate_remote_pref: Optional[str] = None

    if candidate_profile:
        candidate_skills = {s.name.lower() for s in (candidate_profile.skills or [])}
        candidate_exp_level = candidate_profile.experience_level
        candidate_remote_pref = candidate_profile.remote_preference

    retrieved: List[RetrievedJob] = []

    for idx, (job, raw_score) in enumerate(results):
        # Use actual pgvector cosine similarity if attached by hybrid_search;
        # otherwise use raw_score directly (clamped to [0, 1]) rather than
        # max-normalizing RRF scores.
        attached_sem = getattr(job, "_semantic_similarity", None)
        if attached_sem is not None:
            semantic_sim = min(1.0, max(0.0, float(attached_sem)))
        else:
            semantic_sim = min(1.0, max(0.0, float(raw_score)))

        keyword_score = float(getattr(job, "_keyword_score", 0.0))

        # Skill match score
        job_skills = {s.lower() for s in (job.skills or [])}
        if job_skills and candidate_skills:
            matched = candidate_skills & job_skills
            skill_match = len(matched) / len(job_skills)
            matched_list = sorted(matched)
            missing_list = sorted(job_skills - candidate_skills)
        else:
            skill_match = 0.0
            matched_list = []
            missing_list = sorted(job_skills)

        # Experience level match
        exp_score = _experience_match_score(candidate_exp_level, job.experience_level)

        # Location/workplace score
        loc_score = _location_match_score(candidate_remote_pref, job.workplace_type)

        # Composite score
        final = (
            w_semantic * semantic_sim
            + w_skill * skill_match
            + w_experience * exp_score
            + w_location * loc_score
        )

        retrieved.append(RetrievedJob(
            job=job,
            keyword_score=keyword_score,
            semantic_score=semantic_sim,
            hybrid_score=raw_score,
            skill_match_score=skill_match,
            experience_match_score=exp_score,
            location_score=loc_score,
            final_score=final,
            matched_skills=matched_list,
            missing_skills=missing_list,
            rank=idx + 1,
        ))

    # Sort by final score
    retrieved.sort(key=lambda r: r.final_score, reverse=True)
    for i, r in enumerate(retrieved):
        r.rank = i + 1

    return retrieved


def _experience_match_score(candidate_level: Optional[str], job_level: Optional[str]) -> float:
    """Score 0-1 for experience level compatibility."""
    if not job_level or job_level == "unspecified":
        return 0.5  # neutral
    if not candidate_level:
        return 0.3  # unknown candidate level
    if candidate_level == job_level:
        return 1.0

    # Ordered levels
    order = ["internship", "entry", "mid", "senior", "lead", "executive"]
    try:
        c_idx = order.index(candidate_level)
        j_idx = order.index(job_level)
        distance = abs(c_idx - j_idx)
        if distance == 1:
            return 0.7  # adjacent level
        if distance == 2:
            return 0.4
        return 0.1
    except ValueError:
        return 0.3


def _location_match_score(candidate_pref: Optional[str], job_workplace: Optional[str]) -> float:
    """Score 0-1 for location/workplace type compatibility."""
    if not job_workplace or job_workplace == "unspecified":
        return 0.5
    if not candidate_pref:
        return 0.4

    if candidate_pref == "remote" and job_workplace == "remote":
        return 1.0
    if candidate_pref == "hybrid" and job_workplace in ("hybrid", "remote"):
        return 0.9
    if candidate_pref == "on_site" and job_workplace == "on_site":
        return 1.0
    if candidate_pref == "flexible":
        return 0.8
    # Mismatch
    if candidate_pref == "remote" and job_workplace == "on_site":
        return 0.1
    return 0.4


# ---------------------------------------------------------------------------
# Filter helpers (parameterized - safe from SQL injection)
# ---------------------------------------------------------------------------

def _build_filter_clauses(filters: Optional[Dict[str, Any]]) -> str:
    """Build WHERE clause additions for filters (uses named params)."""
    if not filters:
        return ""
    clauses = []
    if filters.get("workplace_type"):
        clauses.append("AND j.workplace_type = :workplace_type")
    if filters.get("employment_type"):
        clauses.append("AND j.employment_type = :employment_type")
    if filters.get("experience_level"):
        clauses.append("AND j.experience_level = :experience_level")
    if filters.get("days"):
        clauses.append("AND j.posted_at >= NOW() - (:days * INTERVAL '1 day')")
    return " ".join(clauses)


def _add_filter_params(params: Dict, filters: Optional[Dict[str, Any]]) -> None:
    """Add filter values to the params dict."""
    if not filters:
        return
    for key in ("workplace_type", "employment_type", "experience_level", "days"):
        if filters.get(key) is not None:
            params[key] = filters[key]
