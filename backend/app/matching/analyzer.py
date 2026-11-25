"""
Match Analysis service.
Combines evidence engine + LLM for structured, grounded job match explanations.

V1: analyze_job_match()       — original, unchanged
V2: analyze_job_match_v2()    — full explainable pipeline with experience/workplace fit,
                                 score breakdown, candidate strengths, unknown requirements

Scoring formula (V2):
  skill_score     = EvidenceEngine.compute_match_score(evidence_items)  [0-100]
                    MATCH=1.0, PARTIAL=0.5, GAP=0.0, UNKNOWN=0.3  × confidence, normalised × 100

  experience_fit  = 100 (exact level match)
                  |  50 (adjacent level or unknown job level)
                  |   0 (clear mismatch)

  workplace_fit   = 100 (candidate preference matches job type)
                  |  50 (job type unspecified, or candidate is 'flexible')
                  |   0 (clear mismatch, e.g. candidate remote-only but job is on_site)

  overall = skill_score × 0.70
           + experience_fit_score × 0.20
           + workplace_fit_score  × 0.10
  Rounded to 1 decimal place.
"""
from __future__ import annotations
import logging
from typing import List, Optional

from app.config import get_settings
from app.matching.evidence import EvidenceEngine, EvidenceItem
from app.models import CandidateProfile, Job
from app.schemas import (
    BulkMatchResponse,
    ExperienceFitResult,
    JobMatchAnalysis,
    JobMatchAnalysisV2,
    MatchDecision,
    RequirementEvidence,
    ScoreBreakdown,
    SkillGapAnalysis,
    SkillGapItem,
    WorkplaceFitResult,
)

logger = logging.getLogger(__name__)
settings = get_settings()

evidence_engine = EvidenceEngine()

# ---------------------------------------------------------------------------
# Experience level adjacency map (ordered)
# ---------------------------------------------------------------------------
_EXP_ORDER = ["internship", "entry", "mid", "senior", "lead", "executive"]


def _experience_fit(candidate_level: Optional[str], job_level: Optional[str]) -> ExperienceFitResult:
    """
    Compare candidate experience level against job requirement.
    Returns MATCH (100), PARTIAL (50), GAP (0), or UNKNOWN when job level absent.
    Decision is fully grounded in stored level strings — nothing is invented.
    """
    if not job_level or job_level == "unspecified":
        return ExperienceFitResult(
            candidate_level=candidate_level,
            job_required_level=None,
            fit=MatchDecision.unknown,
            explanation="Job listing does not specify a required experience level.",
        )

    if not candidate_level or candidate_level == "unspecified":
        return ExperienceFitResult(
            candidate_level=None,
            job_required_level=job_level,
            fit=MatchDecision.unknown,
            explanation="Candidate profile does not specify an experience level.",
        )

    c_lvl = candidate_level.lower()
    j_lvl = job_level.lower()

    if c_lvl == j_lvl:
        return ExperienceFitResult(
            candidate_level=candidate_level,
            job_required_level=job_level,
            fit=MatchDecision.strong_match,
            explanation=f"Candidate level '{candidate_level}' exactly matches job requirement '{job_level}'.",
        )

    # Adjacent levels → partial
    c_idx = _EXP_ORDER.index(c_lvl) if c_lvl in _EXP_ORDER else -1
    j_idx = _EXP_ORDER.index(j_lvl) if j_lvl in _EXP_ORDER else -1

    if c_idx != -1 and j_idx != -1:
        diff = abs(c_idx - j_idx)
        if diff == 1:
            direction = "above" if c_idx > j_idx else "below"
            return ExperienceFitResult(
                candidate_level=candidate_level,
                job_required_level=job_level,
                fit=MatchDecision.partial_match,
                explanation=(
                    f"Candidate level '{candidate_level}' is one step {direction} the required '{job_level}'."
                ),
            )
        else:
            direction = "overqualified" if c_idx > j_idx else "underqualified"
            return ExperienceFitResult(
                candidate_level=candidate_level,
                job_required_level=job_level,
                fit=MatchDecision.gap,
                explanation=(
                    f"Candidate level '{candidate_level}' is {direction} for the required '{job_level}' "
                    f"({diff} levels apart)."
                ),
            )

    return ExperienceFitResult(
        candidate_level=candidate_level,
        job_required_level=job_level,
        fit=MatchDecision.unknown,
        explanation=f"Cannot compare levels '{candidate_level}' and '{job_level}'.",
    )


def _workplace_fit(
    candidate_preference: Optional[str],
    job_workplace_type: Optional[str],
    candidate_location: Optional[str],
    job_location: Optional[str],
) -> WorkplaceFitResult:
    """
    Compare candidate work-mode preference against job type.
    If job type unspecified → UNKNOWN (scored as 50).
    If candidate is 'flexible' or no preference → UNKNOWN (scored as 50).
    Location mismatch is noted but only downgrades on-site vs remote hard mismatch.
    """
    j_type = (job_workplace_type or "").lower()
    c_pref = (candidate_preference or "").lower()

    if not j_type or j_type == "unspecified":
        return WorkplaceFitResult(
            candidate_preference=candidate_preference,
            job_workplace_type=None,
            candidate_location=candidate_location,
            job_location=job_location,
            fit=MatchDecision.unknown,
            explanation="Job listing does not specify a workplace type.",
        )

    if not c_pref or c_pref == "flexible":
        return WorkplaceFitResult(
            candidate_preference=candidate_preference,
            job_workplace_type=job_workplace_type,
            candidate_location=candidate_location,
            job_location=job_location,
            fit=MatchDecision.partial_match,
            explanation=(
                f"Candidate has no specific workplace preference; job is '{job_workplace_type}'."
            ),
        )

    if c_pref == j_type:
        return WorkplaceFitResult(
            candidate_preference=candidate_preference,
            job_workplace_type=job_workplace_type,
            candidate_location=candidate_location,
            job_location=job_location,
            fit=MatchDecision.strong_match,
            explanation=f"Candidate preference '{candidate_preference}' matches job type '{job_workplace_type}'.",
        )

    # Hard mismatch: remote-only candidate vs on_site job or vice-versa
    hard_mismatch = (
        (c_pref == "remote" and j_type == "on_site") or
        (c_pref == "on_site" and j_type == "remote")
    )
    if hard_mismatch:
        return WorkplaceFitResult(
            candidate_preference=candidate_preference,
            job_workplace_type=job_workplace_type,
            candidate_location=candidate_location,
            job_location=job_location,
            fit=MatchDecision.gap,
            explanation=(
                f"Candidate requires '{candidate_preference}' but job is '{job_workplace_type}'. "
                "Hard workplace mismatch."
            ),
        )

    # Hybrid is compatible with remote or on_site
    return WorkplaceFitResult(
        candidate_preference=candidate_preference,
        job_workplace_type=job_workplace_type,
        candidate_location=candidate_location,
        job_location=job_location,
        fit=MatchDecision.partial_match,
        explanation=(
            f"Candidate prefers '{candidate_preference}'; job is '{job_workplace_type}'. "
            "Partial compatibility."
        ),
    )


async def analyze_job_match(
    job: Job,
    profile: CandidateProfile,
) -> JobMatchAnalysis:
    """
    Generate a full explainable match analysis.

    1. Run deterministic evidence engine (no LLM)
    2. Optionally call LLM for narrative reasoning (grounded in evidence)
    3. Return structured JobMatchAnalysis
    """
    # Step 1: Deterministic evidence evaluation
    evidence_items = evidence_engine.evaluate_job_requirements(
        profile=profile,
        job_skills=job.skills or [],
        additional_requirements=job.requirements,
    )

    # Step 2: Classify
    matched: List[RequirementEvidence] = []
    partial: List[RequirementEvidence] = []
    gaps: List[RequirementEvidence] = []

    for item in evidence_items:
        req_ev = RequirementEvidence(
            requirement=item.requirement,
            candidate_evidence=item.evidence_text,
            decision=item.decision,
            confidence=item.confidence,
            source_type=item.source_type,
        )
        if item.decision == MatchDecision.strong_match:
            matched.append(req_ev)
        elif item.decision == MatchDecision.partial_match:
            partial.append(req_ev)
        elif item.decision == MatchDecision.gap:
            gaps.append(req_ev)

    # Step 3: Compute score
    score = evidence_engine.compute_match_score(evidence_items)

    # Step 4: Generate LLM narrative (if OpenAI is configured)
    reasoning = _build_fallback_reasoning(matched, partial, gaps, score)
    if settings.openai_api_key:
        try:
            reasoning = await _generate_llm_reasoning(job, profile, evidence_items, score)
        except Exception as e:
            logger.warning("LLM reasoning generation failed; using fallback: %s", e)

    # Step 5: Recommendation
    if score >= 75:
        recommendation = "Strong match"
    elif score >= 50:
        recommendation = "Moderate match"
    elif score >= 25:
        recommendation = "Weak match"
    else:
        recommendation = "Not recommended"

    return JobMatchAnalysis(
        overall_match_score=score,
        matched_requirements=matched,
        partial_matches=partial,
        skill_gaps=gaps,
        candidate_evidence=[item.evidence_text for item in evidence_items if item.evidence_text],
        reasoning=reasoning,
        recommendation=recommendation,
        top_matching_skills=[r.requirement for r in matched[:5]],
        missing_skills=[r.requirement for r in gaps[:10]],
    )


def _build_fallback_reasoning(
    matched: list,
    partial: list,
    gaps: list,
    score: float,
) -> str:
    """Generate a deterministic reasoning string without LLM."""
    parts = []
    if matched:
        parts.append(f"{len(matched)} requirement(s) matched: {', '.join(r.requirement for r in matched[:5])}.")
    if partial:
        parts.append(f"{len(partial)} partial match(es): {', '.join(r.requirement for r in partial[:3])}.")
    if gaps:
        parts.append(f"{len(gaps)} skill gap(s): {', '.join(r.requirement for r in gaps[:5])}.")
    parts.append(f"Overall match score: {score}/100.")
    return " ".join(parts) if parts else "No requirements evaluated."


async def _generate_llm_reasoning(
    job: Job,
    profile: CandidateProfile,
    evidence_items: list[EvidenceItem],
    score: float,
) -> str:
    """
    Call OpenAI to generate a concise narrative explanation.
    The LLM receives only the retrieved evidence - it cannot invent information.
    """
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    evidence_text = "\n".join([
        f"- {item.requirement}: [{item.decision.value}] "
        + (f"Evidence: {item.evidence_text}" if item.evidence_text else "No evidence found.")
        for item in evidence_items
    ])

    candidate_summary = f"""
Name: {profile.full_name or 'Unknown'}
Experience level: {profile.experience_level or 'Not specified'}
Target roles: {', '.join(profile.target_roles or []) or 'Not specified'}
Skills: {', '.join(s.name for s in (profile.skills or []))[:500]}
""".strip()

    prompt = f"""You are a career advisor analyzing a job match.

JOB:
Title: {job.title}
Company: {job.company or 'Unknown'}
Location: {job.location or 'Unknown'}

CANDIDATE SUMMARY:
{candidate_summary}

EVIDENCE (do not add information not shown here):
{evidence_text}

MATCH SCORE: {score}/100

Write a concise 2-3 sentence explanation of this match. Refer only to the evidence above.
Do not invent experience the candidate doesn't have. Be direct and factual."""

    response = await client.chat.completions.create(
        model=settings.openai_model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=300,
        temperature=0.3,
    )
    return response.choices[0].message.content.strip()


async def build_skill_gap_analysis(
    profile: CandidateProfile,
    jobs: List[Job],
    target_query: str,
) -> SkillGapAnalysis:
    """
    Analyze skill gaps across a set of retrieved jobs.
    Reports which skills appear frequently and whether the candidate has them.
    All recommendations come from actual retrieved job requirements.
    """
    # Count skill frequency across jobs
    skill_frequency: dict[str, int] = {}
    for job in jobs:
        for skill in (job.skills or []):
            norm = skill.strip()
            if norm:
                skill_frequency[norm] = skill_frequency.get(norm, 0) + 1

    if not skill_frequency:
        return SkillGapAnalysis(
            target_query=target_query,
            total_jobs_analyzed=len(jobs),
            skill_coverage=[],
            recommended_skills_to_learn=[],
            strong_skills=[],
            partial_skills=[],
            missing_skills=[],
        )

    # Sort by frequency
    sorted_skills = sorted(skill_frequency.items(), key=lambda x: x[1], reverse=True)

    # Evaluate each skill against candidate profile
    skill_coverage: List[SkillGapItem] = []
    strong_skills: List[str] = []
    partial_skills: List[str] = []
    missing_skills: List[str] = []

    for skill_name, freq in sorted_skills[:30]:  # analyze top 30 skills
        evidence = evidence_engine.evaluate_requirement(profile, skill_name)

        # Priority based on frequency
        if freq >= len(jobs) * 0.5:
            priority = "high"
        elif freq >= len(jobs) * 0.2:
            priority = "medium"
        else:
            priority = "low"

        item = SkillGapItem(
            skill=skill_name,
            frequency_in_target_jobs=freq,
            candidate_status=evidence.decision,
            candidate_evidence=evidence.evidence_text,
            priority=priority,
        )
        skill_coverage.append(item)

        if evidence.decision == MatchDecision.strong_match:
            strong_skills.append(skill_name)
        elif evidence.decision == MatchDecision.partial_match:
            partial_skills.append(skill_name)
        elif evidence.decision == MatchDecision.gap:
            missing_skills.append(skill_name)

    # Recommend missing high-priority skills
    recommended = [
        item.skill
        for item in skill_coverage
        if item.candidate_status == MatchDecision.gap and item.priority == "high"
    ][:8]

    return SkillGapAnalysis(
        target_query=target_query,
        total_jobs_analyzed=len(jobs),
        skill_coverage=skill_coverage,
        recommended_skills_to_learn=recommended,
        strong_skills=strong_skills,
        partial_skills=partial_skills,
        missing_skills=missing_skills,
        data_source=f"Retrieved {len(jobs)} job listings for query: '{target_query}'",
        note="Recommendations are based on observed skill frequency in retrieved job listings, not general career advice.",
    )


# ---------------------------------------------------------------------------
# V2 Score Computation
# ---------------------------------------------------------------------------

_FIT_SCORES: dict[MatchDecision, float] = {
    MatchDecision.strong_match: 100.0,
    MatchDecision.partial_match: 50.0,
    MatchDecision.gap: 0.0,
    MatchDecision.unknown: 50.0,  # neutral when unknown
}

_SKILL_WEIGHT = 0.70
_EXP_WEIGHT = 0.20
_WORKPLACE_WEIGHT = 0.10


def _compute_score_breakdown(
    skill_score: float,
    exp_fit: ExperienceFitResult,
    workplace_fit: WorkplaceFitResult,
) -> ScoreBreakdown:
    exp_score = _FIT_SCORES[exp_fit.fit]
    wp_score = _FIT_SCORES[workplace_fit.fit]
    overall = round(
        skill_score * _SKILL_WEIGHT
        + exp_score * _EXP_WEIGHT
        + wp_score * _WORKPLACE_WEIGHT,
        1,
    )
    # Clamp to [0, 100]
    overall = max(0.0, min(100.0, overall))
    return ScoreBreakdown(
        skill_score=skill_score,
        experience_fit_score=None if exp_fit.fit == MatchDecision.unknown else exp_score,
        workplace_fit_score=None if workplace_fit.fit == MatchDecision.unknown else wp_score,
        skill_weight=_SKILL_WEIGHT,
        experience_weight=_EXP_WEIGHT,
        workplace_weight=_WORKPLACE_WEIGHT,
        overall_score=overall,
    )


def _candidate_strengths(
    profile: CandidateProfile,
    matched: list[RequirementEvidence],
) -> list[str]:
    """
    Build a list of candidate strengths relevant to this job.
    Grounded only in evidence that produced a MATCH decision.
    """
    strengths: list[str] = []
    seen: set[str] = set()

    # From matched requirements — take evidence texts
    for ev in matched[:5]:
        if ev.candidate_evidence and ev.candidate_evidence not in seen:
            seen.add(ev.candidate_evidence)
            strengths.append(ev.candidate_evidence)

    # Also surface proficiency info from skills
    skills = getattr(profile, "skills", []) or []
    for skill in skills:
        prof = getattr(skill, "proficiency", None)
        yoe = getattr(skill, "years_of_experience", None)
        if prof in ("advanced", "expert"):
            stmt = f"{skill.name}: {prof} proficiency"
            if yoe:
                stmt += f" ({yoe} years)"
            if stmt not in seen:
                seen.add(stmt)
                strengths.append(stmt)

    return strengths[:8]


def _data_sources_used(evidence_items: list[EvidenceItem]) -> list[str]:
    sources: set[str] = set()
    for item in evidence_items:
        if item.source_type:
            sources.add(item.source_type)
    return sorted(sources)


def _build_v2_reasoning(
    matched: list[RequirementEvidence],
    partial: list[RequirementEvidence],
    gaps: list[RequirementEvidence],
    unknowns: list[RequirementEvidence],
    exp_fit: ExperienceFitResult,
    wp_fit: WorkplaceFitResult,
    score: float,
) -> str:
    parts = []
    if matched:
        parts.append(f"{len(matched)} requirement(s) matched: {', '.join(r.requirement for r in matched[:5])}.")
    if partial:
        parts.append(f"{len(partial)} partial match(es): {', '.join(r.requirement for r in partial[:3])}.")
    if gaps:
        parts.append(f"{len(gaps)} skill gap(s): {', '.join(r.requirement for r in gaps[:5])}.")
    if unknowns:
        parts.append(f"{len(unknowns)} requirement(s) could not be evaluated (UNKNOWN).")
    parts.append(f"Experience fit: {exp_fit.explanation}")
    parts.append(f"Workplace fit: {wp_fit.explanation}")
    parts.append(f"Overall match score: {score}/100.")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Public V2 API
# ---------------------------------------------------------------------------

async def analyze_job_match_v2(
    job: "Job",
    profile: "CandidateProfile",
) -> JobMatchAnalysisV2:
    """
    Full explainable match analysis (V2).

    Pipeline:
      1. EvidenceEngine → per-requirement MATCH / PARTIAL / GAP / UNKNOWN
      2. Experience fit  → deterministic level comparison
      3. Workplace fit   → deterministic work-mode + location comparison
      4. Score breakdown → weighted composite (skill 70%, exp 20%, workplace 10%)
      5. Candidate strengths → grounded in matched evidence only
      6. Deterministic reasoning text (no LLM)
    """
    # 1. Evidence evaluation
    evidence_items = evidence_engine.evaluate_job_requirements(
        profile=profile,
        job_skills=getattr(job, "skills", None) or [],
        additional_requirements=getattr(job, "requirements", None),
    )

    matched: list[RequirementEvidence] = []
    partial: list[RequirementEvidence] = []
    gaps: list[RequirementEvidence] = []
    unknowns: list[RequirementEvidence] = []

    for item in evidence_items:
        req_ev = RequirementEvidence(
            requirement=item.requirement,
            candidate_evidence=item.evidence_text,
            decision=item.decision,
            confidence=item.confidence,
            source_type=item.source_type,
        )
        if item.decision == MatchDecision.strong_match:
            matched.append(req_ev)
        elif item.decision == MatchDecision.partial_match:
            partial.append(req_ev)
        elif item.decision == MatchDecision.gap:
            gaps.append(req_ev)
        else:
            unknowns.append(req_ev)

    # 2. Skill score (EvidenceEngine weighted average)
    skill_score = evidence_engine.compute_match_score(evidence_items)

    # 3. Experience fit
    exp_fit = _experience_fit(
        candidate_level=getattr(profile, "experience_level", None),
        job_level=getattr(job, "experience_level", None),
    )

    # 4. Workplace fit
    wp_fit = _workplace_fit(
        candidate_preference=getattr(profile, "remote_preference", None),
        job_workplace_type=getattr(job, "workplace_type", None),
        candidate_location=getattr(profile, "location", None),
        job_location=getattr(job, "location", None),
    )

    # 5. Score breakdown
    breakdown = _compute_score_breakdown(skill_score, exp_fit, wp_fit)
    overall_score = breakdown.overall_score

    # 6. Recommendation
    if overall_score >= 75:
        recommendation = "Strong match"
    elif overall_score >= 50:
        recommendation = "Moderate match"
    elif overall_score >= 25:
        recommendation = "Weak match"
    else:
        recommendation = "Not recommended"

    # 7. Candidate strengths — grounded in matched evidence
    strengths = _candidate_strengths(profile, matched)

    # 8. Deterministic reasoning
    reasoning = _build_v2_reasoning(matched, partial, gaps, unknowns, exp_fit, wp_fit, overall_score)

    job_id = getattr(job, "id", None)

    return JobMatchAnalysisV2(
        job_id=str(job_id) if job_id else None,
        job_title=getattr(job, "title", "Unknown"),
        job_company=getattr(job, "company", None),
        overall_match_score=overall_score,
        score_breakdown=breakdown,
        recommendation=recommendation,
        matched_requirements=matched,
        partial_matches=partial,
        missing_requirements=gaps,
        unknown_requirements=unknowns,
        experience_fit=exp_fit,
        workplace_fit=wp_fit,
        candidate_strengths=strengths,
        top_matching_skills=[r.requirement for r in matched[:5]],
        missing_skills=[r.requirement for r in gaps[:10]],
        reasoning=reasoning,
        total_requirements_evaluated=len(evidence_items),
        data_sources_used=_data_sources_used(evidence_items),
    )
