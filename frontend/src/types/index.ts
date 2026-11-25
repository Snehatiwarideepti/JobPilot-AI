export type WorkplaceType = 'remote' | 'hybrid' | 'on_site' | 'unspecified';
export type EmploymentType = 'full_time' | 'part_time' | 'contract' | 'internship' | 'freelance' | 'unspecified';
export type ExperienceLevel = 'internship' | 'entry' | 'mid' | 'senior' | 'lead' | 'executive' | 'unspecified';
export type MatchDecision = 'MATCH' | 'PARTIAL' | 'GAP' | 'UNKNOWN';
export type RetrievalMethod = 'hybrid_rerank' | 'hybrid' | 'semantic' | 'keyword';

export interface Job {
  id: string;
  source: string;
  source_job_id: string;
  title: string;
  company: string | null;
  location: string | null;
  country: string | null;
  city: string | null;
  workplace_type: WorkplaceType | null;
  employment_type: EmploymentType | null;
  experience_level: ExperienceLevel | null;
  salary_min: number | null;
  salary_max: number | null;
  salary_currency: string | null;
  salary_period?: string | null;
  description: string | null;
  responsibilities?: string | null;
  requirements?: string | null;
  benefits?: string | null;
  skills: string[];
  application_url: string | null;
  source_url: string | null;
  posted_at: string | null;
  is_active: boolean;
  first_seen_at: string;
  last_seen_at: string;
  created_at: string;
  match_score?: number | null;
  semantic_score?: number | null;
  keyword_score?: number | null;
  top_matching_skills?: string[];
  skill_gaps?: string[];
}

export interface JobSearchResponse {
  total: number;
  page: number;
  limit: number;
  jobs: Job[];
  source: string;
  retrieval_method: string;
}

export interface RequirementEvidence {
  requirement: string;
  candidate_evidence: string | null;
  decision: MatchDecision;
  confidence: number;
  source_type: string | null;
}

export interface ScoreBreakdown {
  skill_score: number;
  experience_fit_score: number | null;
  workplace_fit_score: number | null;
  skill_weight: number;
  experience_weight: number;
  workplace_weight: number;
  overall_score: number;
}

export interface ExperienceFitResult {
  candidate_level: string | null;
  job_required_level: string | null;
  fit: MatchDecision;
  explanation: string;
}

export interface WorkplaceFitResult {
  candidate_preference: string | null;
  job_workplace_type: string | null;
  candidate_location: string | null;
  job_location: string | null;
  fit: MatchDecision;
  explanation: string;
}

export interface JobMatchAnalysisV2 {
  job_id: string | null;
  job_title: string;
  job_company: string | null;
  overall_match_score: number;
  score_breakdown: ScoreBreakdown;
  recommendation: string;
  matched_requirements: RequirementEvidence[];
  partial_matches: RequirementEvidence[];
  missing_requirements: RequirementEvidence[];
  unknown_requirements: RequirementEvidence[];
  experience_fit: ExperienceFitResult;
  workplace_fit: WorkplaceFitResult;
  candidate_strengths: string[];
  top_matching_skills: string[];
  missing_skills: string[];
  reasoning: string;
  total_requirements_evaluated: number;
  data_sources_used: string[];
}

export interface JobMatchAnalysis {
  overall_match_score: number;
  matched_requirements: RequirementEvidence[];
  partial_matches: RequirementEvidence[];
  skill_gaps: RequirementEvidence[];
  candidate_evidence: string[];
  reasoning: string;
  recommendation: string;
  top_matching_skills: string[];
  missing_skills: string[];
}

export interface SkillGapItem {
  skill: string;
  frequency_in_target_jobs: number;
  candidate_status: MatchDecision;
  candidate_evidence: string | null;
  priority: 'high' | 'medium' | 'low';
}

export interface SkillGapAnalysis {
  target_query: string;
  total_jobs_analyzed: number;
  skill_coverage: SkillGapItem[];
  recommended_skills_to_learn: string[];
  strong_skills: string[];
  partial_skills: string[];
  missing_skills: string[];
  data_source: string;
  note: string;
}

export interface CandidateSkill {
  id?: string;
  name: string;
  category?: string | null;
  proficiency?: string | null;
  years_of_experience?: number | null;
}

export interface CandidateProject {
  id?: string;
  name: string;
  description?: string | null;
  technologies: string[];
  url?: string | null;
  start_date?: string | null;
  end_date?: string | null;
}

export interface CandidateExperience {
  id?: string;
  company: string;
  title: string;
  location?: string | null;
  description?: string | null;
  technologies: string[];
  start_date?: string | null;
  end_date?: string | null;
  is_current: boolean;
}

export interface CandidateEducation {
  id?: string;
  institution: string;
  degree?: string | null;
  field_of_study?: string | null;
  gpa?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  is_current: boolean;
}

export interface CandidateProfile {
  id?: string;
  full_name?: string | null;
  email?: string | null;
  phone?: string | null;
  location?: string | null;
  linkedin_url?: string | null;
  github_url?: string | null;
  portfolio_url?: string | null;
  target_roles: string[];
  preferred_locations: string[];
  remote_preference?: string | null;
  experience_level?: string | null;
  summary?: string | null;
  skills: CandidateSkill[];
  projects: CandidateProject[];
  experience: CandidateExperience[];
  education: CandidateEducation[];
  certifications: { name: string; issuer?: string | null; issued_date?: string | null }[];
}

export interface ChatResponse {
  session_id: string;
  response: string;
  tool_calls_made: string[];
  jobs_found?: Job[] | null;
  match_analysis?: JobMatchAnalysis | null;
  skill_gap_analysis?: SkillGapAnalysis | null;
}

export interface EvaluationSummary {
  total_queries: number;
  methods: Record<string, { hit_at_5: number | null; hit_at_10: number | null; mrr: number | null }>;
  note: string;
}

export interface HealthResponse {
  status: string;
  database: string;
  embeddings: string;
  provider: string;
  llm: string;
  version: string;
}
