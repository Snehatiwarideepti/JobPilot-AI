"""
AI Agent for JobPilot.
Implements tool-calling architecture where the LLM decides which tools to use.
Maintains conversation memory via PostgreSQL.
"""
from __future__ import annotations
import json
import logging
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Message, CandidateProfile
from app.schemas import AgentResponse, AgentToolCall, ChatResponse, JobWithScore
from app.providers import get_provider
from app.services.ingestion import upsert_job, generate_and_store_embedding
from app.retrieval.engine import hybrid_search, semantic_search, keyword_search, rerank_results
from app.matching.analyzer import analyze_job_match, build_skill_gap_analysis

logger = logging.getLogger(__name__)
settings = get_settings()

# ============================================================
# Tool definitions (passed to OpenAI)
# ============================================================

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_live_jobs",
            "description": "Search for current job listings from the live job provider. Use this when the user asks to find, search, or look for jobs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Job search query, e.g. 'Python data science internship'"},
                    "location": {"type": "string", "description": "Location filter, e.g. 'India', 'Remote'"},
                    "workplace_type": {"type": "string", "enum": ["remote", "hybrid", "on_site"], "description": "Work arrangement filter"},
                    "employment_type": {"type": "string", "enum": ["full_time", "part_time", "contract", "internship"], "description": "Employment type filter"},
                    "experience_level": {"type": "string", "enum": ["internship", "entry", "mid", "senior"], "description": "Experience level filter"},
                    "days": {"type": "integer", "description": "Only jobs posted in the last N days", "minimum": 1, "maximum": 90},
                    "limit": {"type": "integer", "description": "Number of results to return", "default": 10, "maximum": 20},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_job_details",
            "description": "Get detailed information about a specific job by its ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "The internal job ID"},
                },
                "required": ["job_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_job_fit",
            "description": "Analyze how well a job matches the candidate's profile. Shows matched skills, gaps, and evidence.",
            "parameters": {
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "The internal job ID to analyze"},
                },
                "required": ["job_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_skill_gaps",
            "description": "Analyze skill gaps across retrieved jobs for the current search query.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The job search query to analyze skill gaps for"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_job",
            "description": "Save a job to the user's saved jobs list.",
            "parameters": {
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "The internal job ID to save"},
                    "notes": {"type": "string", "description": "Optional notes about why to save this job"},
                },
                "required": ["job_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_saved_jobs",
            "description": "Retrieve the list of jobs the user has saved.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


# ============================================================
# Agent
# ============================================================

class JobPilotAgent:
    """
    Tool-calling AI agent for job search and career matching.
    Uses OpenAI function calling to decide which tools to invoke.
    Maintains conversation memory in PostgreSQL.
    """

    MAX_CONTEXT_MESSAGES = 10  # Recent messages to include in LLM context

    def __init__(self, db: AsyncSession):
        self.db = db
        self._last_jobs: List[Any] = []  # Cache of last search results for follow-ups

    async def _get_openai_client(self):
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured. Set it in .env to use the AI agent.")
        from openai import AsyncOpenAI
        return AsyncOpenAI(api_key=settings.openai_api_key)

    async def _load_conversation_history(self, session_id: str, user_id: Optional[str]) -> List[Dict]:
        """Load recent messages for context, excluding tool internals."""
        stmt = (
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at.desc())
            .limit(self.MAX_CONTEXT_MESSAGES)
        )
        result = await self.db.execute(stmt)
        messages = list(reversed(result.scalars().all()))

        history = []
        for msg in messages:
            if msg.role in ("user", "assistant"):
                history.append({"role": msg.role, "content": msg.content})
        return history

    async def _save_message(
        self,
        session_id: str,
        user_id: Optional[str],
        role: str,
        content: str,
        metadata: Optional[Dict] = None,
    ) -> None:
        """Persist a message to the database."""
        try:
            uid = uuid.UUID(user_id) if user_id else None
        except (ValueError, TypeError):
            uid = None

        msg = Message(
            user_id=uid,
            session_id=session_id,
            role=role,
            content=content,
            extra_metadata=metadata or {},
        )
        self.db.add(msg)
        await self.db.flush()

    async def _load_candidate_profile(self, user_id: Optional[str]) -> Optional[CandidateProfile]:
        """Load the candidate profile for the current user."""
        if not user_id:
            return None
        try:
            uid = uuid.UUID(user_id)
        except (ValueError, TypeError):
            return None

        from app.models import CandidateProfile as CP
        from sqlalchemy.orm import selectinload
        stmt = (
            select(CP)
            .where(CP.user_id == uid)
            .options(
                selectinload(CP.skills),
                selectinload(CP.projects),
                selectinload(CP.experience),
                selectinload(CP.education),
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Tool Implementations
    # ------------------------------------------------------------------

    async def _tool_search_live_jobs(self, **kwargs) -> Dict[str, Any]:
        """Execute live job search via provider + store results in DB."""
        provider = get_provider("jobvetta")
        try:
            search_result = await provider.search_jobs(
                query=kwargs.get("query", ""),
                location=kwargs.get("location"),
                workplace_type=kwargs.get("workplace_type"),
                employment_type=kwargs.get("employment_type"),
                experience_level=kwargs.get("experience_level"),
                days=kwargs.get("days"),
                limit=min(kwargs.get("limit", 10), 20),
            )

            jobs_data = []
            self._last_jobs = []

            for job_result in search_result.jobs:
                job, _ = await upsert_job(self.db, job_result)
                # Try to generate embedding (non-blocking)
                try:
                    await generate_and_store_embedding(self.db, job)
                except Exception:
                    pass
                self._last_jobs.append(job)
                jobs_data.append({
                    "id": str(job.id),
                    "title": job.title,
                    "company": job.company,
                    "location": job.location,
                    "workplace_type": job.workplace_type,
                    "employment_type": job.employment_type,
                    "experience_level": job.experience_level,
                    "skills": job.skills or [],
                    "application_url": job.application_url,
                    "posted_at": job.posted_at.isoformat() if job.posted_at else None,
                })

            await self.db.commit()

            return {
                "total": search_result.total,
                "returned": len(jobs_data),
                "jobs": jobs_data,
                "source": "jobvetta",
            }

        except Exception as e:
            logger.error("Job search tool error: %s", e)
            return {"error": str(e), "jobs": []}

    async def _tool_get_job_details(self, job_id: str) -> Dict[str, Any]:
        """Retrieve job details from DB."""
        from app.models import Job
        try:
            job_uuid = uuid.UUID(job_id)
            job = await self.db.get(Job, job_uuid)
            if not job:
                return {"error": f"Job {job_id} not found"}
            return {
                "id": str(job.id),
                "title": job.title,
                "company": job.company,
                "location": job.location,
                "workplace_type": job.workplace_type,
                "employment_type": job.employment_type,
                "experience_level": job.experience_level,
                "salary_min": job.salary_min,
                "salary_max": job.salary_max,
                "description": (job.description or "")[:1000],
                "requirements": (job.requirements or "")[:800],
                "skills": job.skills or [],
                "application_url": job.application_url,
                "posted_at": job.posted_at.isoformat() if job.posted_at else None,
            }
        except (ValueError, Exception) as e:
            return {"error": str(e)}

    async def _tool_analyze_job_fit(self, job_id: str, user_id: Optional[str]) -> Dict[str, Any]:
        """Run the evidence engine for a specific job."""
        from app.models import Job
        try:
            job_uuid = uuid.UUID(job_id)
            job = await self.db.get(Job, job_uuid)
            if not job:
                return {"error": f"Job {job_id} not found"}

            profile = await self._load_candidate_profile(user_id)
            if not profile:
                return {"error": "No candidate profile found. Please build your profile first."}

            analysis = await analyze_job_match(job, profile)
            return analysis.model_dump()
        except Exception as e:
            logger.error("Job fit analysis error: %s", e)
            return {"error": str(e)}

    async def _tool_get_skill_gaps(self, query: str, user_id: Optional[str]) -> Dict[str, Any]:
        """Build skill gap analysis from recent search results."""
        profile = await self._load_candidate_profile(user_id)
        if not profile:
            return {"error": "No candidate profile found. Please build your profile first."}

        if not self._last_jobs:
            return {"error": "No recent search results. Please search for jobs first."}

        analysis = await build_skill_gap_analysis(profile, self._last_jobs, query)
        return analysis.model_dump()

    async def _tool_save_job(self, job_id: str, user_id: Optional[str], notes: Optional[str] = None) -> Dict[str, Any]:
        """Save a job for the user."""
        from app.models import SavedJob, Job
        if not user_id:
            return {"error": "Must be logged in to save jobs"}
        try:
            uid = uuid.UUID(user_id)
            job_uuid = uuid.UUID(job_id)
            job = await self.db.get(Job, job_uuid)
            if not job:
                return {"error": f"Job {job_id} not found"}

            stmt = select(SavedJob).where(SavedJob.user_id == uid, SavedJob.job_id == job_uuid)
            existing = (await self.db.execute(stmt)).scalar_one_or_none()
            if existing:
                return {"message": "Job already saved", "saved": True}

            saved = SavedJob(user_id=uid, job_id=job_uuid, notes=notes)
            self.db.add(saved)
            await self.db.commit()
            return {"message": f"Saved: {job.title} at {job.company}", "saved": True}
        except Exception as e:
            return {"error": str(e)}

    async def _tool_get_saved_jobs(self, user_id: Optional[str]) -> Dict[str, Any]:
        """Return saved jobs for the user."""
        from app.models import SavedJob, Job
        if not user_id:
            return {"error": "Must be logged in to view saved jobs"}
        try:
            uid = uuid.UUID(user_id)
            stmt = select(SavedJob).where(SavedJob.user_id == uid)
            result = await self.db.execute(stmt)
            saved_jobs = result.scalars().all()
            jobs_list = []
            for sj in saved_jobs:
                job = await self.db.get(Job, sj.job_id)
                if job:
                    jobs_list.append({"id": str(job.id), "title": job.title, "company": job.company})
            return {"saved_jobs": jobs_list, "count": len(jobs_list)}
        except Exception as e:
            return {"error": str(e)}

    # ------------------------------------------------------------------
    # Main Chat Method
    # ------------------------------------------------------------------

    async def chat(
        self,
        message: str,
        session_id: str,
        user_id: Optional[str] = None,
    ) -> ChatResponse:
        """
        Process a user message through the agent.
        Returns a structured ChatResponse.
        """
        if not settings.openai_api_key:
            # Graceful degradation without LLM
            return ChatResponse(
                session_id=session_id,
                response=(
                    "The AI agent requires an OpenAI API key to function. "
                    "Please set OPENAI_API_KEY in your .env file. "
                    "You can still use the job search and profile features directly."
                ),
                tool_calls_made=[],
            )

        # Save user message
        await self._save_message(session_id, user_id, "user", message)

        # Load conversation history
        history = await self._load_conversation_history(session_id, user_id)

        # Build system prompt
        profile = await self._load_candidate_profile(user_id)
        profile_summary = ""
        if profile:
            skills = ", ".join(s.name for s in (profile.skills or []))[:300]
            profile_summary = (
                f"\nCandidate profile loaded: {profile.full_name or 'Unknown'}, "
                f"level: {profile.experience_level or 'unspecified'}, "
                f"skills: {skills or 'none listed'}."
            )

        system_prompt = f"""You are JobPilot, an AI career matching assistant.
You help users find relevant jobs, understand how well they match, and identify skill gaps.

Your tools:
- search_live_jobs: Search current job listings from Jobvetta
- get_job_details: Get full details for a specific job
- analyze_job_fit: Show detailed evidence-based match analysis for a job
- get_skill_gaps: Analyze skill gaps across retrieved jobs
- save_job: Save a job to the user's list
- get_saved_jobs: Retrieve saved jobs

Rules:
1. Always use search_live_jobs for job searches - never invent jobs.
2. For follow-up queries ("only remote", "only internships"), refine the previous search intent.
3. When showing match analysis, always cite actual evidence from the candidate profile.
4. Never claim the user has a skill unless it appears in their profile.
5. Be concise, factual, and professional.
{profile_summary}"""

        client = await self._get_openai_client()
        messages = [{"role": "system", "content": system_prompt}] + history + [{"role": "user", "content": message}]

        tool_calls_made: List[str] = []
        jobs_found = None
        match_analysis = None
        skill_gap_analysis = None

        # Agentic loop - allow up to 5 tool call rounds
        for _iteration in range(5):
            response = await client.chat.completions.create(
                model=settings.openai_model,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                max_tokens=1500,
                temperature=0.3,
            )

            msg = response.choices[0].message

            if msg.tool_calls:
                # Process each tool call
                messages.append({"role": "assistant", "content": msg.content or "", "tool_calls": [
                    {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in msg.tool_calls
                ]})

                for tc in msg.tool_calls:
                    tool_name = tc.function.name
                    tool_calls_made.append(tool_name)
                    try:
                        args = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        args = {}

                    # Dispatch tool
                    if tool_name == "search_live_jobs":
                        result = await self._tool_search_live_jobs(**args)
                        if result.get("jobs"):
                            jobs_found = result.get("jobs")
                    elif tool_name == "get_job_details":
                        result = await self._tool_get_job_details(**args)
                    elif tool_name == "analyze_job_fit":
                        result = await self._tool_analyze_job_fit(user_id=user_id, **args)
                        if "overall_match_score" in result:
                            from app.schemas import JobMatchAnalysis
                            try:
                                match_analysis = JobMatchAnalysis(**result)
                            except Exception:
                                pass
                    elif tool_name == "get_skill_gaps":
                        result = await self._tool_get_skill_gaps(user_id=user_id, **args)
                        if "skill_coverage" in result:
                            from app.schemas import SkillGapAnalysis
                            try:
                                skill_gap_analysis = SkillGapAnalysis(**result)
                            except Exception:
                                pass
                    elif tool_name == "save_job":
                        result = await self._tool_save_job(user_id=user_id, **args)
                    elif tool_name == "get_saved_jobs":
                        result = await self._tool_get_saved_jobs(user_id=user_id)
                    else:
                        result = {"error": f"Unknown tool: {tool_name}"}

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result, default=str),
                    })

            else:
                # Final response
                final_text = msg.content or "I'm here to help you find jobs. What are you looking for?"

                # Save assistant response
                await self._save_message(session_id, user_id, "assistant", final_text, {
                    "tool_calls": tool_calls_made,
                })
                await self.db.commit()

                return ChatResponse(
                    session_id=session_id,
                    response=final_text,
                    tool_calls_made=tool_calls_made,
                    jobs_found=jobs_found,
                    match_analysis=match_analysis,
                    skill_gap_analysis=skill_gap_analysis,
                )

        # If we exhausted iterations
        await self._save_message(session_id, user_id, "assistant", "I processed your request.")
        await self.db.commit()
        return ChatResponse(
            session_id=session_id,
            response="I processed your request. Please check the results.",
            tool_calls_made=tool_calls_made,
            jobs_found=jobs_found,
        )
