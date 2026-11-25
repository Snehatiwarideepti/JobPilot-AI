"""Tests for retrieval RRF, reranking, and evaluation metrics."""
import uuid
from types import SimpleNamespace
import pytest

from app.retrieval.engine import (
    reciprocal_rank_fusion,
    rerank_results,
    build_candidate_search_query,
    semantic_search,
)
from app.evaluation.pipeline import compute_hit_at_k, compute_mrr


def _job(title: str, skills: list[str], workplace: str = "remote", exp: str = "internship"):
    return SimpleNamespace(
        id=uuid.uuid4(),
        title=title,
        skills=skills,
        workplace_type=workplace,
        experience_level=exp,
    )


def test_reciprocal_rank_fusion_combines_lists():
    j1 = _job("ML Intern", ["Python"])
    j2 = _job("Data Analyst", ["SQL"])
    j3 = _job("Backend Dev", ["Go"])

    kw = [(j1, 0.9), (j2, 0.5)]
    sem = [(j2, 0.8), (j3, 0.7), (j1, 0.4)]

    fused = reciprocal_rank_fusion(kw, sem)
    ids = [j.id for j, _ in fused]
    assert len(ids) == 3
    assert j2.id in ids and j1.id in ids and j3.id in ids


@pytest.mark.asyncio
async def test_rerank_results_respects_candidate_profile():
    j_good = _job("Python ML Intern", ["Python", "SQL"], workplace="remote", exp="internship")
    j_bad = _job("Senior Java Onsite", ["Java", "Spring"], workplace="on_site", exp="senior")

    profile = SimpleNamespace(
        skills=[SimpleNamespace(name="Python"), SimpleNamespace(name="SQL")],
        experience_level="internship",
        remote_preference="remote",
    )

    ranked = await rerank_results([(j_bad, 0.8), (j_good, 0.8)], candidate_profile=profile)
    assert ranked[0].job.id == j_good.id
    assert ranked[0].final_score > ranked[1].final_score
    assert "python" in ranked[0].matched_skills


def test_evaluation_metrics():
    retrieved = ["a", "b", "c", "d", "e"]
    relevant = ["c"]
    assert compute_hit_at_k(retrieved, relevant, 5) == 1.0
    assert compute_hit_at_k(retrieved, relevant, 2) == 0.0
    assert compute_mrr(retrieved, relevant) == pytest.approx(1 / 3)


@pytest.mark.asyncio
async def test_hybrid_search_no_concurrent_session_error(monkeypatch):
    """Regression test: hybrid_search must not run concurrent DB operations on the same AsyncSession."""
    import asyncio
    from app.retrieval import engine as retrieval_engine

    j1 = _job("Python Engineer", ["Python", "SQL"])
    j2 = _job("Java Engineer", ["Java"])

    in_flight = 0

    class GuardedSession:
        pass

    async def fake_keyword(db, query, limit=50, filters=None):
        nonlocal in_flight
        if in_flight > 0:
            raise RuntimeError("Concurrent AsyncSession operation detected")
        in_flight += 1
        await asyncio.sleep(0.01)
        in_flight -= 1
        return [(j1, 0.6), (j2, 0.4)]

    async def fake_semantic(db, query, limit=50, filters=None, candidate_profile=None):
        nonlocal in_flight
        if in_flight > 0:
            raise RuntimeError("Concurrent AsyncSession operation detected")
        in_flight += 1
        await asyncio.sleep(0.01)
        in_flight -= 1
        return [(j1, 0.65), (j2, 0.50)]

    monkeypatch.setattr(retrieval_engine, "keyword_search", fake_keyword)
    monkeypatch.setattr(retrieval_engine, "semantic_search", fake_semantic)

    results = await retrieval_engine.hybrid_search(GuardedSession(), "engineer", limit=5)
    assert len(results) == 2
    assert results[0][0].id == j1.id
    assert getattr(results[0][0], "_semantic_similarity") == pytest.approx(0.65)
    assert getattr(results[0][0], "_keyword_score") == pytest.approx(0.6)


@pytest.mark.asyncio
async def test_rerank_results_preserves_semantic_similarity_over_rrf():
    """Regression test: semantic_score must reflect actual similarity, not max-normalized RRF."""
    j1 = _job("ML Engineer", ["Python"], workplace="remote", exp="mid")
    j2 = _job("Backend Engineer", ["Python"], workplace="remote", exp="mid")

    # Simulate hybrid_search attaching real pgvector cosine similarities
    j1._semantic_similarity = 0.62
    j1._keyword_score = 0.50
    j2._semantic_similarity = 0.45
    j2._keyword_score = 0.40

    # RRF scores are tiny and close together (0.0160 vs 0.0155)
    profile = SimpleNamespace(
        skills=[SimpleNamespace(name="Python")],
        experience_level="mid",
        remote_preference="remote",
    )

    ranked = await rerank_results([(j1, 0.0160), (j2, 0.0155)], candidate_profile=profile)
    assert ranked[0].semantic_score == pytest.approx(0.62)
    assert ranked[1].semantic_score == pytest.approx(0.45)
    assert ranked[0].hybrid_score == pytest.approx(0.0160)
    assert ranked[1].hybrid_score == pytest.approx(0.0155)
    # Neither should be inflated to 1.0 or ~0.97
    assert ranked[0].semantic_score < 0.70
    assert ranked[1].semantic_score < 0.50


def test_build_candidate_search_query_without_profile():
    """Verify fallback to raw query when candidate profile is None."""
    assert build_candidate_search_query(None, "software engineer") == "software engineer"
    assert build_candidate_search_query(None, "") == ""


def test_build_candidate_search_query_with_candidate_info():
    """Verify synthesized search text includes candidate skills, roles, experience, and workplace preferences."""
    profile = SimpleNamespace(
        target_roles=["Data Engineer"],
        skills=[SimpleNamespace(name="Python"), SimpleNamespace(name="SQL"), SimpleNamespace(name="AWS")],
        experience_level="mid",
        remote_preference="remote",
        experience=[
            SimpleNamespace(
                title="Software Engineer",
                company="TechCo",
                description="Built ETL pipelines",
                technologies=["Python", "PostgreSQL"],
            )
        ],
        projects=[
            SimpleNamespace(
                name="Cloud Migration",
                description="Migrated DB to AWS RDS",
                technologies=["AWS", "Terraform"],
            )
        ],
        summary="Experienced backend developer specializing in data infrastructure.",
    )

    query = build_candidate_search_query(profile, base_query="engineer")
    assert "engineer" in query
    assert "Data Engineer" in query
    assert "Python" in query
    assert "SQL" in query
    assert "AWS" in query
    assert "mid" in query
    assert "remote" in query
    assert "TechCo" in query
    assert "Cloud Migration" in query


@pytest.mark.asyncio
async def test_candidate_aware_semantic_search_embeds_profile(monkeypatch):
    """Verify semantic_search uses candidate-aware search text when candidate_profile is provided."""
    from unittest.mock import AsyncMock, MagicMock

    profile = SimpleNamespace(
        skills=[SimpleNamespace(name="Python"), SimpleNamespace(name="SQL")],
        experience_level="mid",
        remote_preference="remote",
    )

    embedded_texts = []

    class MockEmbeddingService:
        async def embed_text(self, text: str):
            embedded_texts.append(text)
            return [0.1] * 384

    from app.retrieval import engine as retrieval_engine
    monkeypatch.setattr(retrieval_engine, "get_embedding_service", lambda: MockEmbeddingService())

    # Mock DB execute returning empty
    db = AsyncMock()
    mock_res = MagicMock()
    mock_res.fetchall.return_value = []
    db.execute.return_value = mock_res

    await semantic_search(db, query="backend", candidate_profile=profile)

    assert len(embedded_texts) == 1
    assert "backend" in embedded_texts[0]
    assert "Python" in embedded_texts[0]
    assert "SQL" in embedded_texts[0]

