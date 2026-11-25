"""
Resume extraction service.
Extracts structured candidate profile information from resume text.
Uses OpenAI structured outputs with Pydantic schema validation.
"""
from __future__ import annotations
import logging
from typing import List, Optional

from app.config import get_settings
from app.schemas import (
    CandidateProfileCreate,
    CandidateSkillCreate,
    CandidateProjectCreate,
    CandidateExperienceCreate,
    CandidateEducationCreate,
    CandidateCertificationCreate,
)

logger = logging.getLogger(__name__)
settings = get_settings()


async def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract plain text from a PDF file."""
    try:
        import pdfminer.high_level as pdfminer
        import io
        return pdfminer.extract_text(io.BytesIO(file_bytes)).strip()
    except ImportError:
        raise RuntimeError("pdfminer.six is not installed. Run: pip install pdfminer.six")
    except Exception as e:
        raise ValueError(f"Failed to extract PDF text: {e}")


async def extract_text_from_docx(file_bytes: bytes) -> str:
    """Extract plain text from a DOCX file."""
    try:
        import docx
        import io
        doc = docx.Document(io.BytesIO(file_bytes))
        return "\n".join(para.text for para in doc.paragraphs if para.text.strip())
    except ImportError:
        raise RuntimeError("python-docx is not installed. Run: pip install python-docx")
    except Exception as e:
        raise ValueError(f"Failed to extract DOCX text: {e}")


async def extract_resume_text(file_bytes: bytes, filename: str) -> str:
    """Route to appropriate extractor based on file extension."""
    name_lower = filename.lower()
    if name_lower.endswith(".pdf"):
        return await extract_text_from_pdf(file_bytes)
    elif name_lower.endswith(".docx"):
        return await extract_text_from_docx(file_bytes)
    elif name_lower.endswith(".txt"):
        try:
            return file_bytes.decode("utf-8").strip()
        except UnicodeDecodeError:
            return file_bytes.decode("latin-1").strip()
    else:
        raise ValueError(f"Unsupported file type: {filename}. Supported: .pdf, .docx, .txt")


async def extract_profile_from_text(
    resume_text: str,
) -> tuple[CandidateProfileCreate, List[str]]:
    """
    Extract structured profile from resume text using OpenAI.
    Returns (profile, uncertain_fields).

    If OpenAI is not configured, falls back to minimal extraction.
    """
    if not settings.openai_api_key:
        logger.warning("OpenAI not configured; using minimal resume extraction")
        return _fallback_extraction(resume_text), ["All fields - OpenAI not configured for extraction"]

    return await _openai_extraction(resume_text)


async def _openai_extraction(
    resume_text: str,
) -> tuple[CandidateProfileCreate, List[str]]:
    """Use OpenAI to extract structured profile from resume text."""
    from openai import AsyncOpenAI
    import json

    client = AsyncOpenAI(api_key=settings.openai_api_key)

    # Truncate very long resumes to avoid token limits
    truncated_text = resume_text[:8000] if len(resume_text) > 8000 else resume_text

    system_prompt = """You are a resume parser. Extract structured information from the resume text.
Return ONLY valid JSON matching the schema. Do not invent information not present in the resume.
If a field is not found, use null or empty list. Mark uncertain fields in the 'uncertain_fields' array."""

    schema_prompt = """Extract the following JSON structure:
{
  "full_name": "string or null",
  "email": "string or null",
  "phone": "string or null",
  "location": "string or null",
  "linkedin_url": "string or null",
  "github_url": "string or null",
  "portfolio_url": "string or null",
  "summary": "string or null",
  "target_roles": ["role1", "role2"],
  "experience_level": "internship|entry|mid|senior|lead|executive or null",
  "skills": [
    {"name": "skill_name", "category": "language|framework|tool|database|cloud|other or null", "proficiency": "beginner|intermediate|advanced|expert or null"}
  ],
  "projects": [
    {"name": "project_name", "description": "description or null", "technologies": ["tech1"], "url": "url or null", "start_date": "YYYY-MM or null", "end_date": "YYYY-MM or null"}
  ],
  "experience": [
    {"company": "company_name", "title": "job_title", "location": "location or null", "description": "description or null", "technologies": ["tech1"], "start_date": "YYYY-MM or null", "end_date": "YYYY-MM or null", "is_current": false}
  ],
  "education": [
    {"institution": "school_name", "degree": "degree or null", "field_of_study": "field or null", "gpa": "gpa or null", "start_date": "YYYY-MM or null", "end_date": "YYYY-MM or null", "is_current": false}
  ],
  "certifications": [
    {"name": "cert_name", "issuer": "issuer or null", "issued_date": "YYYY-MM or null"}
  ],
  "uncertain_fields": ["list of field names where extraction was uncertain"]
}"""

    try:
        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"{schema_prompt}\n\nRESUME:\n{truncated_text}"},
            ],
            response_format={"type": "json_object"},
            max_tokens=4000,
            temperature=0,
        )

        raw_json = response.choices[0].message.content
        data = json.loads(raw_json)

        uncertain_fields = data.pop("uncertain_fields", [])

        # Build profile
        skills = [
            CandidateSkillCreate(
                name=s.get("name", "").strip(),
                category=s.get("category"),
                proficiency=s.get("proficiency"),
            )
            for s in (data.get("skills") or [])
            if s.get("name")
        ]

        projects = [
            CandidateProjectCreate(
                name=p.get("name", "").strip(),
                description=p.get("description"),
                technologies=p.get("technologies") or [],
                url=p.get("url"),
                start_date=p.get("start_date"),
                end_date=p.get("end_date"),
            )
            for p in (data.get("projects") or [])
            if p.get("name")
        ]

        experience = [
            CandidateExperienceCreate(
                company=e.get("company", "").strip(),
                title=e.get("title", "").strip(),
                location=e.get("location"),
                description=e.get("description"),
                technologies=e.get("technologies") or [],
                start_date=e.get("start_date"),
                end_date=e.get("end_date"),
                is_current=bool(e.get("is_current", False)),
            )
            for e in (data.get("experience") or [])
            if e.get("company") and e.get("title")
        ]

        education = [
            CandidateEducationCreate(
                institution=ed.get("institution", "").strip(),
                degree=ed.get("degree"),
                field_of_study=ed.get("field_of_study"),
                gpa=ed.get("gpa"),
                start_date=ed.get("start_date"),
                end_date=ed.get("end_date"),
                is_current=bool(ed.get("is_current", False)),
            )
            for ed in (data.get("education") or [])
            if ed.get("institution")
        ]

        certifications = [
            CandidateCertificationCreate(
                name=c.get("name", "").strip(),
                issuer=c.get("issuer"),
                issued_date=c.get("issued_date"),
            )
            for c in (data.get("certifications") or [])
            if c.get("name")
        ]

        profile = CandidateProfileCreate(
            full_name=data.get("full_name"),
            email=data.get("email"),
            phone=data.get("phone"),
            location=data.get("location"),
            linkedin_url=data.get("linkedin_url"),
            github_url=data.get("github_url"),
            portfolio_url=data.get("portfolio_url"),
            summary=data.get("summary"),
            target_roles=data.get("target_roles") or [],
            experience_level=data.get("experience_level"),
            skills=skills,
            projects=projects,
            experience=experience,
            education=education,
            certifications=certifications,
        )

        return profile, uncertain_fields

    except Exception as e:
        logger.error("OpenAI resume extraction failed: %s", e, exc_info=True)
        return _fallback_extraction(resume_text), [f"All fields - extraction error: {str(e)[:100]}"]


def _fallback_extraction(resume_text: str) -> CandidateProfileCreate:
    """
    Minimal rule-based extraction when OpenAI is not available.
    Only extracts what can be reliably pattern-matched.
    """
    import re

    email = None
    phone = None
    linkedin_url = None
    github_url = None

    email_match = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', resume_text)
    if email_match:
        email = email_match.group(0)

    phone_match = re.search(r'[\+]?[(]?[0-9]{3}[)]?[-\s\.]?[0-9]{3}[-\s\.]?[0-9]{4,6}', resume_text)
    if phone_match:
        phone = phone_match.group(0)

    linkedin_match = re.search(r'linkedin\.com/in/[\w-]+', resume_text, re.IGNORECASE)
    if linkedin_match:
        linkedin_url = "https://www." + linkedin_match.group(0)

    github_match = re.search(r'github\.com/[\w-]+', resume_text, re.IGNORECASE)
    if github_match:
        github_url = "https://www." + github_match.group(0)

    return CandidateProfileCreate(
        email=email,
        phone=phone,
        linkedin_url=linkedin_url,
        github_url=github_url,
        summary=resume_text[:500] if resume_text else None,
    )
