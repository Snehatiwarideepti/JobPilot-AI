import type {
  CandidateProfile,
  ChatResponse,
  EvaluationSummary,
  HealthResponse,
  Job,
  JobMatchAnalysis,
  JobMatchAnalysisV2,
  JobSearchResponse,
  RetrievalMethod,
  SkillGapAnalysis,
} from '../types';

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api';

/**
 * Persistent anonymous user UUID stored locally so profile, saved jobs,
 * and search history work seamlessly across reloads.
 */
export function getUserId(): string {
  const key = 'jobpilot_user_id';
  let uid = localStorage.getItem(key);
  if (!uid) {
    uid = crypto.randomUUID();
    localStorage.setItem(key, uid);
  }
  return uid;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      ...(options?.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
      ...(options?.headers || {}),
    },
  });

  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const err = await res.json();
      detail = err.detail || err.message || detail;
    } catch {
      // ignore non-json
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  getHealth: () => request<HealthResponse>('/health'),

  searchJobs: (params: {
    q: string;
    location?: string;
    workplace_type?: string;
    employment_type?: string;
    experience_level?: string;
    days?: number;
    page?: number;
    limit?: number;
    retrieval_method?: RetrievalMethod;
  }) => {
    const uid = getUserId();
    const body = Object.fromEntries(
      Object.entries(params).filter(([, v]) => v !== '' && v !== undefined && v !== null)
    );
    return request<JobSearchResponse>(`/jobs/search?user_id=${encodeURIComponent(uid)}`, {
      method: 'POST',
      body: JSON.stringify(body),
    });
  },

  getJob: (jobId: string) => request<Job>(`/jobs/${jobId}`),

  analyzeMatch: (jobId: string) => {
    const uid = getUserId();
    return request<JobMatchAnalysisV2>(`/jobs/${jobId}/match/v2?user_id=${encodeURIComponent(uid)}`);
  },

  saveJob: (jobId: string, notes?: string) => {
    const uid = getUserId();
    return request<{ message: string; saved: boolean }>(
      `/jobs/${jobId}/save?user_id=${encodeURIComponent(uid)}`,
      {
        method: 'POST',
        body: JSON.stringify({ job_id: jobId, notes }),
      }
    );
  },

  getSavedJobs: () => {
    const uid = getUserId();
    return request<{ id: string; job: Job; notes: string | null; created_at: string }[]>(
      `/jobs/saved/list?user_id=${encodeURIComponent(uid)}`
    );
  },

  getProfile: () => {
    const uid = getUserId();
    return request<CandidateProfile>(`/profile?user_id=${encodeURIComponent(uid)}`);
  },

  saveProfile: (profile: CandidateProfile) => {
    const uid = getUserId();
    return request<CandidateProfile>(`/profile?user_id=${encodeURIComponent(uid)}`, {
      method: 'POST',
      body: JSON.stringify(profile),
    });
  },

  uploadResume: (file: File) => {
    const uid = getUserId();
    const form = new FormData();
    form.append('file', file);
    return request<{
      filename: string;
      extracted_profile: CandidateProfile;
      uncertain_fields: string[];
      message: string;
    }>(`/profile/resume/upload?user_id=${encodeURIComponent(uid)}`, {
      method: 'POST',
      body: form,
    });
  },

  getSkillGaps: (query: string) => {
    const uid = getUserId();
    return request<SkillGapAnalysis>(
      `/skills/gaps?user_id=${encodeURIComponent(uid)}&query=${encodeURIComponent(query)}`
    );
  },

  chat: (message: string, sessionId?: string) => {
    const uid = getUserId();
    return request<ChatResponse>('/chat', {
      method: 'POST',
      body: JSON.stringify({ message, session_id: sessionId, user_id: uid }),
    });
  },

  getSearchHistory: () => {
    const uid = getUserId();
    return request<{ id: string; query: string; filters: Record<string, unknown> | null; result_count: number | null; created_at: string }[]>(
      `/search/history?user_id=${encodeURIComponent(uid)}`
    );
  },

  getEvaluationResults: () => request<EvaluationSummary>('/evaluation/results'),
  seedEvaluation: () => request<{ message: string; total: number }>('/evaluation/seed', { method: 'POST' }),
  runEvaluation: () => request<{ message: string; note: string }>('/evaluation/run', { method: 'POST' }),
};
