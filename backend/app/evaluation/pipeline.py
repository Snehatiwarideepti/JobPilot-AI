"""
Evaluation pipeline.
Runs actual retrieval methods against test queries and computes real metrics.
"""
from __future__ import annotations
import asyncio
import logging
from typing import List, Optional

from app.database import AsyncSessionLocal
from app.models import EvaluationQuery, EvaluationResult
from app.retrieval.engine import keyword_search, semantic_search, hybrid_search, rerank_results
from sqlalchemy import select

logger = logging.getLogger(__name__)


def compute_hit_at_k(retrieved_ids: List[str], relevant_ids: List[str], k: int) -> float:
    """
    Hit@K: 1 if any relevant item appears in top-K results, else 0.
    """
    if not relevant_ids:
        return 0.0
    top_k = set(retrieved_ids[:k])
    return 1.0 if any(str(r) in top_k for r in relevant_ids) else 0.0


def compute_mrr(retrieved_ids: List[str], relevant_ids: List[str]) -> float:
    """
    Mean Reciprocal Rank: 1/rank of first relevant result.
    """
    if not relevant_ids:
        return 0.0
    relevant_set = set(str(r) for r in relevant_ids)
    for rank, job_id in enumerate(retrieved_ids, start=1):
        if str(job_id) in relevant_set:
            return 1.0 / rank
    return 0.0


async def run_evaluation_pipeline():
    """
    Main evaluation pipeline.
    For each stored query, runs all retrieval methods and computes metrics.
    Metrics are stored in the database - never fabricated.
    """
    async with AsyncSessionLocal() as db:
        try:
            stmt = select(EvaluationQuery)
            result = await db.execute(stmt)
            queries = result.scalars().all()

            if not queries:
                logger.warning("No evaluation queries found. Run POST /evaluation/seed first.")
                return

            logger.info("Starting evaluation for %d queries", len(queries))

            methods = ["keyword", "semantic", "hybrid", "hybrid_rerank"]

            for query in queries:
                query_text = query.query_text
                expected_ids = [str(i) for i in (query.expected_job_ids or [])]

                for method in methods:
                    try:
                        if method == "keyword":
                            results = await keyword_search(db, query_text, limit=10)
                            retrieved_ids = [str(j.id) for j, _ in results]
                        elif method == "semantic":
                            results = await semantic_search(db, query_text, limit=10)
                            retrieved_ids = [str(j.id) for j, _ in results]
                        elif method == "hybrid":
                            results = await hybrid_search(db, query_text, limit=10)
                            retrieved_ids = [str(j.id) for j, _ in results]
                        elif method == "hybrid_rerank":
                            results = await hybrid_search(db, query_text, limit=20)
                            ranked = await rerank_results(results)
                            retrieved_ids = [str(r.job.id) for r in ranked[:10]]

                        # Compute metrics only if expected IDs are set
                        hit5 = compute_hit_at_k(retrieved_ids, expected_ids, 5) if expected_ids else None
                        hit10 = compute_hit_at_k(retrieved_ids, expected_ids, 10) if expected_ids else None
                        mrr = compute_mrr(retrieved_ids, expected_ids) if expected_ids else None

                        # Store result
                        eval_result = EvaluationResult(
                            query_id=query.id,
                            retrieval_method=method,
                            hit_at_5=hit5,
                            hit_at_10=hit10,
                            mrr=mrr,
                            retrieved_job_ids=retrieved_ids,
                        )
                        db.add(eval_result)

                    except Exception as e:
                        logger.error("Evaluation error for query=%r method=%s: %s", query_text, method, e)

            await db.commit()
            logger.info("Evaluation pipeline completed")

        except Exception as e:
            logger.error("Evaluation pipeline failed: %s", e, exc_info=True)
