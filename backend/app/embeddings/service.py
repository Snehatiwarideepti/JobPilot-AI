"""
Embedding service for JobPilot AI.

Supports two backends:
1. Local sentence-transformers (default) - runs on CPU, free, private.
2. OpenAI text-embedding-3-small - requires API key, faster for large batches.

The choice is controlled by settings.use_openai_embeddings.
"""
from __future__ import annotations
import asyncio
import logging
from functools import lru_cache
from typing import List, Optional

import numpy as np

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class EmbeddingService:
    """
    Manages embedding generation.
    Call embed_text() or embed_texts() to get vectors.
    """

    def __init__(self):
        self._model = None
        self._openai_client = None
        self._model_name = settings.embedding_model
        self._dimension = settings.embedding_dimension
        self._use_openai = settings.use_openai_embeddings

    def _load_local_model(self):
        """Lazy-load the sentence-transformers model."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                logger.info("Loading embedding model: %s", self._model_name)
                self._model = SentenceTransformer(self._model_name)
                logger.info("Embedding model loaded. Dimension: %d", self._dimension)
            except ImportError as e:
                raise RuntimeError(
                    "sentence-transformers is not installed. "
                    "Run: pip install sentence-transformers"
                ) from e

    def _get_openai_client(self):
        """Lazy-init OpenAI client."""
        if self._openai_client is None:
            try:
                from openai import AsyncOpenAI
                if not settings.openai_api_key:
                    raise RuntimeError("OPENAI_API_KEY not configured for OpenAI embeddings")
                self._openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
            except ImportError as e:
                raise RuntimeError("openai package is not installed. Run: pip install openai") from e
        return self._openai_client

    def build_job_embedding_text(
        self,
        title: Optional[str],
        description: Optional[str],
        requirements: Optional[str],
        responsibilities: Optional[str],
        skills: Optional[List[str]],
    ) -> str:
        """
        Construct the text to embed for a job.
        Focuses on semantically meaningful content.
        """
        parts = []
        if title:
            parts.append(f"Job Title: {title}")
        if skills:
            parts.append(f"Skills: {', '.join(skills)}")
        if requirements:
            parts.append(f"Requirements: {requirements[:1000]}")
        if responsibilities:
            parts.append(f"Responsibilities: {responsibilities[:800]}")
        if description:
            parts.append(f"Description: {description[:1500]}")
        return "\n\n".join(parts)

    def build_candidate_embedding_text(
        self,
        summary: Optional[str],
        skills: Optional[List[str]],
        experience_titles: Optional[List[str]],
        project_descriptions: Optional[List[str]],
    ) -> str:
        """
        Construct the text to embed for a candidate profile.
        """
        parts = []
        if summary:
            parts.append(f"Summary: {summary}")
        if skills:
            parts.append(f"Skills: {', '.join(skills)}")
        if experience_titles:
            parts.append(f"Experience: {', '.join(experience_titles)}")
        if project_descriptions:
            combined = " | ".join(project_descriptions[:5])
            parts.append(f"Projects: {combined}")
        return "\n\n".join(parts)

    async def embed_text(self, text: str) -> List[float]:
        """Embed a single text string. Returns a float list."""
        results = await self.embed_texts([text])
        return results[0]

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of text strings. Returns list of float lists."""
        if not texts:
            return []

        if self._use_openai:
            return await self._embed_openai(texts)
        else:
            return await self._embed_local(texts)

    async def _embed_local(self, texts: List[str]) -> List[List[float]]:
        """Run sentence-transformers embedding in a thread pool to avoid blocking the event loop."""
        self._load_local_model()

        def _run():
            embeddings = self._model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
            return embeddings.tolist()

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _run)
        return result

    async def _embed_openai(self, texts: List[str]) -> List[List[float]]:
        """Call OpenAI Embeddings API."""
        client = self._get_openai_client()
        model = settings.openai_embedding_model

        # OpenAI has a max of 8191 tokens per input; truncate at char level as safety
        safe_texts = [t[:8000] for t in texts]

        response = await client.embeddings.create(input=safe_texts, model=model)
        return [item.embedding for item in response.data]


@lru_cache()
def get_embedding_service() -> EmbeddingService:
    """Singleton embedding service (cached for the app lifetime)."""
    return EmbeddingService()
