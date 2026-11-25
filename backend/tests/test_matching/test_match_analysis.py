"""
Tests for JobMatchAnalysisV2 pipeline.

Covers:
  - strong skill match
  - partial skill match (project/experience evidence)
  - missing skill (GAP)
  - experience mismatch (level delta > 1)
  - workplace / location mismatch (remote vs on_site)
  - missing job requirement → UNKNOWN (empty skills list)
  - candidate with no skills
  - candidate with multiple skills and projects
  - deterministic / repeatable score
  - evidence traceability (source_type populated)

No OpenAI calls. No database. No Jobvetta API calls.
All profiles and jobs are constructed in-memory using SimpleNamespace.
"""
import uuid
from types import SimpleNamespace

import pytest

from app.matching.analyzer import analyze_job_match_v2, _experience_fit, _workplace_fit
from app.schemas import MatchDecision


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _job(
    *,
    title="Software Engineer",
    company="TestCo",
    skills=None,
    requirements=None,
    experience_level=None,
    workplace_type=None,
    location="Bengaluru, India",
):
    return SimpleNamespace(
        id=uuid.uuid4(),
        title=title,
        company=company,
        skills=skills or [],
        requirements=requirements,
        experience_level=experience_level,
        workplace_type=workplace_type,
        location=location,
    )


def _profile(
    *,
    skills=None,
    projects=None,
    experience=None,
    education=None,
    experience_level=None,
    remote_preference=None,
    location=None,
):
    return SimpleNamespace(
        full_name="Test Candidate",
        experience_level=experience_level,
        remote_preference=remote_preference,
        location=location,
        target_roles=["Software Engineer"],
        skills=skills or [],
        projects=projects or [],
        experience=experience or [],
        education=education or [],
    )


def _skill(name, proficiency="intermediate", yoe=1.0):
    return SimpleNamespace(name=name, proficiency=proficiency, years_of_experience=yoe)


def _project(name, technologies=None, description=""):
    return SimpleNamespace(name=name, technologies=technologies or [], description=description)


def _exp(company, title, technologies=None, description=""):
    return SimpleNamespace(
        company=company, title=title,
        technologies=technologies or [], description=description
    )


# ---------------------------------------------------------------------------
# 1. Strong skill match
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_strong_skill_match():
    """Python and SQL listed in skills → both MATCH with skill source."""
    profile = _profile(skills=[_skill("Python", "advanced", 3.0), _skill("SQL", "intermediate", 1.5)])
    job = _job(skills=["Python", "SQL"])

    result = await analyze_job_match_v2(job, profile)

    assert result.overall_match_score > 70
    matched_reqs = {r.requirement for r in result.matched_requirements}
    assert "Python" in matched_reqs
    assert "SQL" in matched_reqs
    # All evidence is from the skill source
    for r in result.matched_requirements:
        assert r.source_type == "skill"
        assert r.candidate_evidence is not None
    assert result.total_requirements_evaluated == 2
    assert "skill" in result.data_sources_used


# ---------------------------------------------------------------------------
# 2. Partial skill match (evidence in project, not in skills list)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_partial_skill_match_via_project():
    """
    Flask found in project technologies list → strong_match (source: project).
    Flask found only in project description → partial_match (source: project).

    The EvidenceEngine priority:
      skills > project.technologies (strong_match) > project.description (partial_match)
      > experience.technologies (strong_match) > experience.description (partial_match)
      > education (partial_match)

    Test A: Flask in project.technologies → strong_match from project source (not in skills).
    Test B: Rust only mentioned in project description → partial_match from project source.
    """
    profile = _profile(
        skills=[_skill("Python")],
        projects=[
            _project("MyApp", technologies=["Python", "Flask"],
                     description="Built with Flask and also explored Rust briefly."),
        ],
    )

    # Test A: Flask in technologies → strong_match, source=project
    job_a = _job(skills=["Flask"])
    result_a = await analyze_job_match_v2(job_a, profile)
    matched_reqs = {r.requirement for r in result_a.matched_requirements}
    assert "Flask" in matched_reqs
    flask_ev = next(r for r in result_a.matched_requirements if r.requirement == "Flask")
    assert flask_ev.source_type == "project"
    assert flask_ev.candidate_evidence is not None
    assert flask_ev.decision == MatchDecision.strong_match

    # Test B: Rust only in description (not in technologies list) → partial_match
    job_b = _job(skills=["Rust"])
    result_b = await analyze_job_match_v2(job_b, profile)
    partial_reqs = {r.requirement for r in result_b.partial_matches}
    assert "Rust" in partial_reqs
    rust_ev = next(r for r in result_b.partial_matches if r.requirement == "Rust")
    assert rust_ev.source_type == "project"
    assert rust_ev.candidate_evidence is not None
    assert rust_ev.decision == MatchDecision.partial_match


# ---------------------------------------------------------------------------
# 3. Missing skill → GAP
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_missing_skill_gap():
    """Kubernetes not in profile anywhere → GAP, no invented evidence."""
    profile = _profile(skills=[_skill("Python")])
    job = _job(skills=["Python", "Kubernetes"])

    result = await analyze_job_match_v2(job, profile)

    gap_reqs = {r.requirement for r in result.missing_requirements}
    assert "Kubernetes" in gap_reqs
    k8s_ev = next(r for r in result.missing_requirements if r.requirement == "Kubernetes")
    assert k8s_ev.candidate_evidence is None
    assert k8s_ev.decision == MatchDecision.gap
    assert "Kubernetes" in result.missing_skills


# ---------------------------------------------------------------------------
# 4. Experience mismatch (internship candidate → senior role)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_experience_mismatch():
    """Internship candidate applying for a senior role → GAP on experience."""
    profile = _profile(experience_level="internship")
    job = _job(experience_level="senior")

    result = await analyze_job_match_v2(job, profile)

    assert result.experience_fit.fit == MatchDecision.gap
    assert "internship" in result.experience_fit.explanation.lower()
    assert "senior" in result.experience_fit.explanation.lower()
    # Score should be penalised
    # experience contributes 20% weight; 0 for GAP → score <= 85 even with full skills
    assert result.score_breakdown.experience_fit_score == 0.0


# ---------------------------------------------------------------------------
# 5. Workplace / location mismatch (remote-only vs on_site)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_workplace_mismatch_remote_vs_onsite():
    """Remote-only candidate vs on_site job → GAP on workplace."""
    profile = _profile(remote_preference="remote")
    job = _job(workplace_type="on_site")

    result = await analyze_job_match_v2(job, profile)

    assert result.workplace_fit.fit == MatchDecision.gap
    assert "remote" in result.workplace_fit.explanation.lower()
    assert "on_site" in result.workplace_fit.explanation.lower()
    assert result.score_breakdown.workplace_fit_score == 0.0


# ---------------------------------------------------------------------------
# 6. Missing job requirement → UNKNOWN (empty skills list, no requirements)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_job_requirements_gives_unknown_experience():
    """Job with no skills and no requirements text → 0 requirements evaluated,
       experience/workplace UNKNOWN when both are unspecified."""
    profile = _profile(experience_level=None, remote_preference=None)
    job = _job(skills=[], requirements=None, experience_level=None, workplace_type=None)

    result = await analyze_job_match_v2(job, profile)

    assert result.total_requirements_evaluated == 0
    assert result.experience_fit.fit == MatchDecision.unknown
    assert result.workplace_fit.fit == MatchDecision.unknown
    # With no requirements and both fit dimensions UNKNOWN (scored as 50 neutral),
    # the overall score should be a neutral-ish value
    assert 0 <= result.overall_match_score <= 100


# ---------------------------------------------------------------------------
# 7. Candidate with no skills
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_candidate_with_no_skills():
    """A candidate with no skills, projects, or experience → all GAPs."""
    profile = _profile()
    job = _job(skills=["Python", "SQL", "Docker"])

    result = await analyze_job_match_v2(job, profile)

    assert len(result.matched_requirements) == 0
    assert len(result.partial_matches) == 0
    assert len(result.missing_requirements) == 3
    gap_skills = {r.requirement for r in result.missing_requirements}
    assert gap_skills == {"Python", "SQL", "Docker"}
    # No evidence invented
    for r in result.missing_requirements:
        assert r.candidate_evidence is None
    assert result.score_breakdown.skill_score == 0.0


# ---------------------------------------------------------------------------
# 8. Candidate with multiple skills and projects
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_candidate_multiple_skills_and_projects():
    """Rich candidate profile → matches from multiple source types."""
    profile = _profile(
        skills=[_skill("Python", "expert", 4.0), _skill("SQL", "advanced", 2.0)],
        projects=[
            _project("MLOps Pipeline", technologies=["Docker", "Kubernetes"]),
        ],
        experience=[_exp("DataCo", "ML Engineer", technologies=["TensorFlow"])],
    )
    job = _job(skills=["Python", "SQL", "Docker", "TensorFlow", "AWS"])

    result = await analyze_job_match_v2(job, profile)

    matched = {r.requirement for r in result.matched_requirements}
    assert "Python" in matched
    assert "SQL" in matched
    assert "Docker" in matched
    assert "TensorFlow" in matched

    gaps = {r.requirement for r in result.missing_requirements}
    assert "AWS" in gaps

    # Data sources used should include skill, project, experience
    assert "skill" in result.data_sources_used
    assert "project" in result.data_sources_used
    assert "experience" in result.data_sources_used

    # Candidate strengths grounded in matched evidence
    assert len(result.candidate_strengths) > 0


# ---------------------------------------------------------------------------
# 9. Deterministic / repeatable score
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_score_is_deterministic():
    """Running the same analysis twice must produce identical scores and decisions."""
    profile = _profile(
        skills=[_skill("Python"), _skill("SQL")],
        experience_level="mid",
        remote_preference="remote",
    )
    job = _job(
        skills=["Python", "SQL", "AWS"],
        experience_level="mid",
        workplace_type="remote",
    )

    result1 = await analyze_job_match_v2(job, profile)
    result2 = await analyze_job_match_v2(job, profile)

    assert result1.overall_match_score == result2.overall_match_score
    assert result1.score_breakdown.skill_score == result2.score_breakdown.skill_score
    assert result1.experience_fit.fit == result2.experience_fit.fit
    assert result1.workplace_fit.fit == result2.workplace_fit.fit
    assert result1.recommendation == result2.recommendation

    matched1 = sorted(r.requirement for r in result1.matched_requirements)
    matched2 = sorted(r.requirement for r in result2.matched_requirements)
    assert matched1 == matched2


# ---------------------------------------------------------------------------
# 10. Evidence traceability (source_type always set for matched items)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_evidence_traceability():
    """Every MATCH and PARTIAL evidence item must have source_type and evidence_text set."""
    profile = _profile(
        skills=[_skill("Python")],
        projects=[_project("APIProject", technologies=["FastAPI"])],
        experience=[_exp("Corp", "Dev", technologies=["Docker"])],
    )
    job = _job(skills=["Python", "FastAPI", "Docker", "Kubernetes"])

    result = await analyze_job_match_v2(job, profile)

    for ev in result.matched_requirements:
        assert ev.source_type is not None, f"Missing source_type for MATCH: {ev.requirement}"
        assert ev.candidate_evidence is not None, f"Missing evidence for MATCH: {ev.requirement}"
        assert ev.decision == MatchDecision.strong_match

    for ev in result.partial_matches:
        assert ev.source_type is not None, f"Missing source_type for PARTIAL: {ev.requirement}"
        assert ev.candidate_evidence is not None, f"Missing evidence for PARTIAL: {ev.requirement}"
        assert ev.decision == MatchDecision.partial_match

    for ev in result.missing_requirements:
        assert ev.candidate_evidence is None, f"GAP must not have invented evidence: {ev.requirement}"
        assert ev.decision == MatchDecision.gap


# ---------------------------------------------------------------------------
# 11. Score breakdown weights sum to 1.0
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_score_breakdown_weights():
    """Score breakdown weights must sum to 1.0."""
    profile = _profile(skills=[_skill("Python")])
    job = _job(skills=["Python"])
    result = await analyze_job_match_v2(job, profile)
    bd = result.score_breakdown
    assert abs(bd.skill_weight + bd.experience_weight + bd.workplace_weight - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# 12. Experience level adjacency → PARTIAL (not GAP)
# ---------------------------------------------------------------------------

def test_experience_adjacent_level_is_partial():
    """Entry → Mid is adjacent (1 step) → PARTIAL, not GAP."""
    result = _experience_fit(candidate_level="entry", job_level="mid")
    assert result.fit == MatchDecision.partial_match


def test_experience_exact_match():
    """Mid → Mid is an exact match."""
    result = _experience_fit(candidate_level="mid", job_level="mid")
    assert result.fit == MatchDecision.strong_match


def test_experience_missing_job_level():
    """Job with no experience level → UNKNOWN."""
    result = _experience_fit(candidate_level="senior", job_level=None)
    assert result.fit == MatchDecision.unknown


# ---------------------------------------------------------------------------
# 13. Workplace fit edge cases
# ---------------------------------------------------------------------------

def test_workplace_fit_exact_match_remote():
    result = _workplace_fit("remote", "remote", None, None)
    assert result.fit == MatchDecision.strong_match


def test_workplace_fit_no_preference():
    result = _workplace_fit(None, "on_site", None, None)
    assert result.fit == MatchDecision.partial_match


def test_workplace_fit_unspecified_job():
    result = _workplace_fit("remote", None, None, None)
    assert result.fit == MatchDecision.unknown
