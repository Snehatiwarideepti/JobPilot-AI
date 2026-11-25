"""Tests for EvidenceEngine and MatchAnalysis."""
import uuid
from types import SimpleNamespace
import pytest

from app.matching.evidence import EvidenceEngine
from app.matching.analyzer import analyze_job_match, build_skill_gap_analysis
from app.schemas import MatchDecision


def _make_profile():
    return SimpleNamespace(
        full_name="Test Candidate",
        experience_level="internship",
        target_roles=["ML Engineer", "Data Scientist"],
        remote_preference="remote",
        skills=[
            SimpleNamespace(name="Python", proficiency="advanced", years_of_experience=2.0),
            SimpleNamespace(name="SQL", proficiency="intermediate", years_of_experience=1.0),
        ],
        projects=[
            SimpleNamespace(
                name="Phishing Detection",
                description="Built a phishing URL classifier using Python, Flask, and scikit-learn.",
                technologies=["Python", "Flask", "scikit-learn"],
            ),
            SimpleNamespace(
                name="EventPulse",
                description="Deployed an event service with Docker.",
                technologies=["Docker"],
            ),
        ],
        experience=[],
        education=[
            SimpleNamespace(
                institution="State University",
                degree="B.Tech",
                field_of_study="Computer Science",
            )
        ],
    )


def test_evidence_engine_strong_match_from_skill_and_project():
    engine = EvidenceEngine()
    profile = _make_profile()

    ev_python = engine.evaluate_requirement(profile, "Python")
    assert ev_python.decision == MatchDecision.strong_match
    assert ev_python.evidence_text is not None
    assert "Python" in ev_python.evidence_text

    ev_flask = engine.evaluate_requirement(profile, "Flask")
    assert ev_flask.decision == MatchDecision.strong_match
    assert ev_flask.source_type == "project"
    assert "Phishing Detection" in ev_flask.evidence_text


def test_evidence_engine_gap_never_hallucinates():
    engine = EvidenceEngine()
    profile = _make_profile()

    ev_aws = engine.evaluate_requirement(profile, "AWS")
    assert ev_aws.decision == MatchDecision.gap
    assert ev_aws.evidence_text is None


def test_evidence_engine_java_vs_javascript_boundary():
    engine = EvidenceEngine()
    profile = SimpleNamespace(
        skills=[SimpleNamespace(name="JavaScript", proficiency="advanced", years_of_experience=2.0)],
        projects=[],
        experience=[],
        education=[],
    )
    ev_java = engine.evaluate_requirement(profile, "Java")
    assert ev_java.decision == MatchDecision.gap


def test_evidence_engine_score_calculation():
    engine = EvidenceEngine()
    profile = _make_profile()
    items = engine.evaluate_job_requirements(
        profile=profile,
        job_skills=["Python", "SQL", "Docker", "AWS"],
    )
    score = engine.compute_match_score(items)
    # 3 strong matches (Python, SQL, Docker) + 1 gap (AWS) -> ~75
    assert 70.0 <= score <= 80.0


@pytest.mark.asyncio
async def test_analyze_job_match_deterministic_fallback(monkeypatch):
    from app.matching import analyzer
    monkeypatch.setattr(analyzer.settings, "openai_api_key", None)
    profile = _make_profile()
    job = SimpleNamespace(
        id=uuid.uuid4(),
        title="ML Intern",
        company="DataCorp",
        location="Remote",
        skills=["Python", "SQL", "AWS"],
        requirements="Looking for Python, SQL, and AWS experience.",
    )
    analysis = await analyze_job_match(job, profile)
    assert "Python" in analysis.top_matching_skills
    assert "SQL" in analysis.top_matching_skills
    assert "AWS" in analysis.missing_skills
    assert len(analysis.skill_gaps) == 1
    assert analysis.skill_gaps[0].candidate_evidence is None


@pytest.mark.asyncio
async def test_skill_gap_analysis_from_retrieved_jobs():
    profile = _make_profile()
    jobs = [
        SimpleNamespace(skills=["Python", "SQL", "AWS", "PyTorch"]),
        SimpleNamespace(skills=["Python", "AWS", "Docker"]),
        SimpleNamespace(skills=["Python", "AWS", "Kubernetes"]),
    ]
    gap = await build_skill_gap_analysis(profile, jobs, "Machine Learning Engineer")
    assert gap.total_jobs_analyzed == 3
    assert "Python" in gap.strong_skills
    assert "AWS" in gap.missing_skills
    assert "AWS" in gap.recommended_skills_to_learn
