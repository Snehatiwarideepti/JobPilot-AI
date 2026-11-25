"""
Evidence Engine - the core of JobPilot's explainability.

For each job requirement, searches the candidate profile
to find actual evidence (skills, projects, experience, education).

Decision values:
  MATCH   - strong evidence found
  PARTIAL - partial evidence found
  GAP     - requirement present, no evidence found
  UNKNOWN - cannot determine (ambiguous requirement)

NEVER hallucinate candidate experience.
Every decision is grounded in stored profile data.
"""
from __future__ import annotations
import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from app.models import CandidateProfile, CandidateSkill, CandidateProject, CandidateExperience
from app.schemas import MatchDecision

logger = logging.getLogger(__name__)


@dataclass
class EvidenceItem:
    """Evidence for a single requirement."""
    requirement: str
    decision: MatchDecision
    evidence_text: Optional[str]  # actual text from profile; None if no evidence
    source_type: Optional[str]    # "skill" | "project" | "experience" | "education" | None
    confidence: float             # 0-1


class EvidenceEngine:
    """
    Searches candidate profile data for evidence matching job requirements.
    Does NOT call an LLM - this is deterministic pattern matching.
    LLM is called separately for the narrative explanation, grounded by this evidence.
    """

    def __init__(self):
        # Common skill aliases and synonyms for fuzzy matching
        self._synonyms: dict[str, list[str]] = {
            "python": ["python", "py"],
            "javascript": ["javascript", "js", "typescript", "ts"],
            "java": ["java"],
            "sql": ["sql", "mysql", "postgresql", "postgres", "sqlite", "oracle"],
            "nosql": ["mongodb", "nosql", "dynamodb", "cassandra", "redis"],
            "machine learning": ["machine learning", "ml", "scikit-learn", "sklearn", "xgboost", "lightgbm"],
            "deep learning": ["deep learning", "dl", "tensorflow", "pytorch", "keras", "neural network"],
            "docker": ["docker", "containerization"],
            "kubernetes": ["kubernetes", "k8s"],
            "aws": ["aws", "amazon web services", "ec2", "s3", "lambda", "sagemaker"],
            "gcp": ["gcp", "google cloud", "bigquery"],
            "azure": ["azure", "microsoft azure"],
            "git": ["git", "github", "gitlab", "version control"],
            "react": ["react", "reactjs", "react.js"],
            "node.js": ["node.js", "nodejs", "node"],
            "fastapi": ["fastapi", "fast api"],
            "flask": ["flask"],
            "django": ["django"],
            "data analysis": ["data analysis", "data analytics", "analytics", "pandas", "numpy"],
            "nlp": ["nlp", "natural language processing", "transformers", "bert", "gpt"],
            "computer vision": ["computer vision", "cv", "opencv", "image recognition"],
            "rest api": ["rest api", "restful", "api design", "rest"],
            "agile": ["agile", "scrum", "kanban", "jira"],
        }

    def _normalize_term(self, term: str) -> str:
        return term.lower().strip()

    def _get_synonyms(self, term: str) -> list[str]:
        """Get all synonyms/aliases for a term."""
        normalized = self._normalize_term(term)
        for canonical, aliases in self._synonyms.items():
            if normalized == canonical or normalized in aliases:
                return aliases
        return [normalized]

    def _text_contains_term(self, text: Optional[str], term: str) -> bool:
        """Check if text contains term or any of its synonyms."""
        if not text:
            return False
        text_lower = text.lower()
        for synonym in self._get_synonyms(term):
            # Word boundary matching to avoid false positives (e.g., "java" in "javascript")
            if synonym == "java":
                # Special case: don't match "javascript" as "java"
                if re.search(r'\bjava\b(?!script)', text_lower):
                    return True
            elif re.search(r'\b' + re.escape(synonym) + r'\b', text_lower):
                return True
        return False

    def _search_skill(
        self,
        profile: CandidateProfile,
        requirement: str,
    ) -> Optional[EvidenceItem]:
        """Check if requirement appears in candidate's skills."""
        skills = getattr(profile, "skills", []) or []
        for skill in skills:
            if self._text_contains_term(skill.name, requirement):
                proficiency = getattr(skill, "proficiency", None)
                yoe = getattr(skill, "years_of_experience", None)
                evidence_parts = [f"{skill.name} listed in candidate skills"]
                if proficiency:
                    evidence_parts.append(f"proficiency: {proficiency}")
                if yoe:
                    evidence_parts.append(f"{yoe} years")
                return EvidenceItem(
                    requirement=requirement,
                    decision=MatchDecision.strong_match,
                    evidence_text=". ".join(evidence_parts),
                    source_type="skill",
                    confidence=0.95,
                )
        return None

    def _search_projects(
        self,
        profile: CandidateProfile,
        requirement: str,
    ) -> Optional[EvidenceItem]:
        """Check if requirement appears in candidate's projects."""
        projects = getattr(profile, "projects", []) or []
        for project in projects:
            # Check technologies list
            techs = getattr(project, "technologies", []) or []
            if any(self._text_contains_term(tech, requirement) for tech in techs):
                return EvidenceItem(
                    requirement=requirement,
                    decision=MatchDecision.strong_match,
                    evidence_text=f"{requirement} used in project: {project.name}. Technologies: {', '.join(techs)}",
                    source_type="project",
                    confidence=0.9,
                )
            # Check description
            if self._text_contains_term(getattr(project, "description", ""), requirement):
                return EvidenceItem(
                    requirement=requirement,
                    decision=MatchDecision.partial_match,
                    evidence_text=f"{requirement} mentioned in project '{project.name}': {(project.description or '')[:200]}",
                    source_type="project",
                    confidence=0.75,
                )
        return None

    def _search_experience(
        self,
        profile: CandidateProfile,
        requirement: str,
    ) -> Optional[EvidenceItem]:
        """Check if requirement appears in candidate's work experience."""
        experiences = getattr(profile, "experience", []) or []
        for exp in experiences:
            techs = getattr(exp, "technologies", []) or []
            if any(self._text_contains_term(tech, requirement) for tech in techs):
                return EvidenceItem(
                    requirement=requirement,
                    decision=MatchDecision.strong_match,
                    evidence_text=f"{requirement} used at {exp.company} as {exp.title}",
                    source_type="experience",
                    confidence=0.9,
                )
            if self._text_contains_term(getattr(exp, "description", ""), requirement):
                return EvidenceItem(
                    requirement=requirement,
                    decision=MatchDecision.partial_match,
                    evidence_text=f"{requirement} mentioned in experience at {exp.company} ({exp.title})",
                    source_type="experience",
                    confidence=0.7,
                )
        return None

    def _search_education(
        self,
        profile: CandidateProfile,
        requirement: str,
    ) -> Optional[EvidenceItem]:
        """Check if requirement appears in education."""
        education = getattr(profile, "education", []) or []
        for edu in education:
            field_of_study = getattr(edu, "field_of_study", "") or ""
            degree = getattr(edu, "degree", "") or ""
            if self._text_contains_term(field_of_study + " " + degree, requirement):
                return EvidenceItem(
                    requirement=requirement,
                    decision=MatchDecision.partial_match,
                    evidence_text=f"Related education: {degree} in {field_of_study} from {edu.institution}",
                    source_type="education",
                    confidence=0.6,
                )
        return None

    def evaluate_requirement(
        self,
        profile: CandidateProfile,
        requirement: str,
    ) -> EvidenceItem:
        """
        Evaluate a single requirement against the candidate profile.
        Searches in priority order: skills > projects > experience > education.
        Returns GAP if no evidence found.
        """
        requirement_clean = requirement.strip()
        if not requirement_clean:
            return EvidenceItem(
                requirement=requirement,
                decision=MatchDecision.unknown,
                evidence_text=None,
                source_type=None,
                confidence=0.0,
            )

        # Search in priority order
        for search_fn in [
            self._search_skill,
            self._search_projects,
            self._search_experience,
            self._search_education,
        ]:
            evidence = search_fn(profile, requirement_clean)
            if evidence:
                return evidence

        # No evidence found
        return EvidenceItem(
            requirement=requirement_clean,
            decision=MatchDecision.gap,
            evidence_text=None,
            source_type=None,
            confidence=0.95,
        )

    def evaluate_job_requirements(
        self,
        profile: CandidateProfile,
        job_skills: List[str],
        additional_requirements: Optional[str] = None,
    ) -> List[EvidenceItem]:
        """
        Evaluate all requirements for a job against the candidate profile.

        Args:
            profile: The candidate's profile (with skills, projects, experience loaded)
            job_skills: List of skill names from the job
            additional_requirements: Free-text requirements field (parsed for skills)

        Returns:
            List of EvidenceItem for each requirement evaluated
        """
        requirements_to_check: list[str] = []

        # From structured skills list
        for skill in job_skills:
            if skill.strip():
                requirements_to_check.append(skill.strip())

        # Extract additional requirements from free text (basic extraction)
        if additional_requirements:
            extracted = self._extract_tech_terms_from_text(additional_requirements)
            for term in extracted:
                if term not in requirements_to_check:
                    requirements_to_check.append(term)

        # Deduplicate
        seen: set[str] = set()
        unique_reqs: list[str] = []
        for req in requirements_to_check:
            norm = req.lower()
            if norm not in seen:
                seen.add(norm)
                unique_reqs.append(req)

        evidence_items = []
        for req in unique_reqs[:30]:  # cap at 30 requirements
            item = self.evaluate_requirement(profile, req)
            evidence_items.append(item)

        return evidence_items

    def _extract_tech_terms_from_text(self, text: str) -> List[str]:
        """
        Basic extraction of technology/skill terms from requirements text.
        Uses known technology patterns. NOT an NLP model.
        """
        known_terms = [
            "Python", "SQL", "Java", "JavaScript", "TypeScript", "Go", "Rust", "C++", "C#",
            "R", "Scala", "Kotlin", "Swift", "PHP", "Ruby", "MATLAB",
            "Machine Learning", "Deep Learning", "NLP", "Computer Vision",
            "Docker", "Kubernetes", "AWS", "GCP", "Azure", "Linux",
            "React", "Vue", "Angular", "Node.js", "Django", "Flask", "FastAPI",
            "PostgreSQL", "MySQL", "MongoDB", "Redis", "Elasticsearch",
            "Git", "CI/CD", "Terraform", "Spark", "Kafka",
            "TensorFlow", "PyTorch", "scikit-learn", "Pandas", "NumPy",
            "REST API", "GraphQL", "Microservices", "Agile", "Scrum",
            "Data Analysis", "Statistics", "A/B Testing",
        ]
        found = []
        text_lower = text.lower()
        for term in known_terms:
            if re.search(r'\b' + re.escape(term.lower()) + r'\b', text_lower):
                found.append(term)
        return found

    def compute_match_score(self, evidence_items: List[EvidenceItem]) -> float:
        """
        Compute an overall match score (0-100) from evidence items.
        MATCH=1.0, PARTIAL=0.5, GAP=0.0, UNKNOWN=0.3 (weighted by confidence)
        """
        if not evidence_items:
            return 0.0

        total_weight = 0.0
        weighted_score = 0.0

        decision_weights = {
            MatchDecision.strong_match: 1.0,
            MatchDecision.partial_match: 0.5,
            MatchDecision.gap: 0.0,
            MatchDecision.unknown: 0.3,
        }

        for item in evidence_items:
            w = item.confidence
            total_weight += w
            weighted_score += w * decision_weights.get(item.decision, 0.0)

        if total_weight == 0:
            return 0.0

        raw_ratio = weighted_score / total_weight
        # Scale to 0-100
        return round(raw_ratio * 100, 1)
