"""Tests for agent tool definitions and graceful degradation without LLM key."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.agents.job_agent import JobPilotAgent, TOOLS
from app.schemas import ChatResponse


def test_agent_tools_are_valid_openai_schemas():
    tool_names = [t["function"]["name"] for t in TOOLS]
    assert "search_live_jobs" in tool_names
    assert "get_job_details" in tool_names
    assert "analyze_job_fit" in tool_names
    assert "get_skill_gaps" in tool_names
    assert "save_job" in tool_names
    assert "get_saved_jobs" in tool_names


@pytest.mark.asyncio
async def test_agent_chat_without_openai_key_degrades_gracefully(monkeypatch):
    from app.agents import job_agent
    monkeypatch.setattr(job_agent.settings, "openai_api_key", None)
    mock_db = MagicMock()
    agent = JobPilotAgent(db=mock_db)
    resp = await agent.chat(message="Find Python jobs", session_id="sess_1")
    assert isinstance(resp, ChatResponse)
    assert resp.session_id == "sess_1"
    assert "OPENAI_API_KEY" in resp.response
