import React, { useState } from 'react';
import { Search, AlertCircle, X } from 'lucide-react';
import { api } from '../services/api';
import { JobCard } from '../components/JobCard';
import { MatchEvidenceView } from '../components/MatchEvidenceView';
import { ApplyModal } from '../components/ApplyModal';
import type { Job, JobMatchAnalysisV2, RetrievalMethod } from '../types';

export const SearchJobsPage: React.FC = () => {
  const [query, setQuery] = useState('');
  const [location, setLocation] = useState('');
  const [workplaceType, setWorkplaceType] = useState('');
  const [employmentType, setEmploymentType] = useState('');
  const [experienceLevel, setExperienceLevel] = useState('');
  const [days, setDays] = useState('');
  const [retrievalMethod, setRetrievalMethod] = useState<RetrievalMethod>('hybrid_rerank');

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  const [hasSearched, setHasSearched] = useState(false);

  const [savedIds, setSavedIds] = useState<Set<string>>(new Set());
  const [savingId, setSavingId] = useState<string | null>(null);
  const [applyJob, setApplyJob] = useState<Job | null>(null);

  const [analyzingJob, setAnalyzingJob] = useState<Job | null>(null);
  const [analysis, setAnalysis] = useState<JobMatchAnalysisV2 | null>(null);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [analysisError, setAnalysisError] = useState<string | null>(null);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    setHasSearched(true);

    try {
      const res = await api.searchJobs({
        q: query.trim(),
        location: location.trim() || undefined,
        workplace_type: workplaceType || undefined,
        employment_type: employmentType || undefined,
        experience_level: experienceLevel || undefined,
        days: days ? Number(days) : undefined,
        retrieval_method: retrievalMethod,
      });
      setJobs(res.jobs);
      setTotal(res.total);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Search failed');
      setJobs([]);
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async (job: Job) => {
    setSavingId(job.id);
    try {
      await api.saveJob(job.id);
      setSavedIds((prev) => new Set(prev).add(job.id));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Could not save job');
    } finally {
      setSavingId(null);
    }
  };

  const handleAnalyze = async (job: Job) => {
    setAnalyzingJob(job);
    setAnalysis(null);
    setAnalysisError(null);
    setAnalysisLoading(true);
    try {
      const res = await api.analyzeMatch(job.id);
      setAnalysis(res);
    } catch (err: unknown) {
      setAnalysisError(err instanceof Error ? err.message : 'Match analysis failed');
    } finally {
      setAnalysisLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">Search Live Jobs</h1>
        <p className="text-sm text-slate-600 mt-1">
          Queries live listings via Jobvetta and ranks them using hybrid retrieval against your profile.
        </p>
      </div>

      <form onSubmit={handleSearch} className="bg-white border border-slate-200 rounded-md p-5 space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-12 gap-3">
          <div className="md:col-span-5">
            <label htmlFor="search-q" className="block text-xs font-medium text-slate-700 mb-1">
              Role or Keywords
            </label>
            <input
              id="search-q"
              type="text"
              required
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="e.g. Python machine learning internship"
              className="w-full px-3 py-2 text-sm border border-slate-300 rounded focus:outline-none focus:ring-2 focus:ring-teal-700"
            />
          </div>

          <div className="md:col-span-4">
            <label htmlFor="search-loc" className="block text-xs font-medium text-slate-700 mb-1">
              Location
            </label>
            <input
              id="search-loc"
              type="text"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              placeholder="e.g. India, Remote, Bengaluru"
              className="w-full px-3 py-2 text-sm border border-slate-300 rounded focus:outline-none focus:ring-2 focus:ring-teal-700"
            />
          </div>

          <div className="md:col-span-3 flex items-end">
            <button
              type="submit"
              disabled={loading}
              className="w-full inline-flex items-center justify-center gap-2 px-4 py-2 bg-slate-900 text-white text-sm font-medium rounded hover:bg-slate-800 disabled:opacity-50"
            >
              <Search className="h-4 w-4" />
              {loading ? 'Searching...' : 'Search Jobs'}
            </button>
          </div>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 pt-1">
          <div>
            <label htmlFor="f-workplace" className="block text-xs text-slate-600 mb-1">Workplace</label>
            <select
              id="f-workplace"
              value={workplaceType}
              onChange={(e) => setWorkplaceType(e.target.value)}
              className="w-full px-2.5 py-1.5 text-sm border border-slate-300 rounded bg-white"
            >
              <option value="">Any</option>
              <option value="remote">Remote</option>
              <option value="hybrid">Hybrid</option>
              <option value="on_site">On-site</option>
            </select>
          </div>

          <div>
            <label htmlFor="f-employment" className="block text-xs text-slate-600 mb-1">Employment Type</label>
            <select
              id="f-employment"
              value={employmentType}
              onChange={(e) => setEmploymentType(e.target.value)}
              className="w-full px-2.5 py-1.5 text-sm border border-slate-300 rounded bg-white"
            >
              <option value="">Any</option>
              <option value="full_time">Full-time</option>
              <option value="internship">Internship</option>
              <option value="part_time">Part-time</option>
              <option value="contract">Contract</option>
            </select>
          </div>

          <div>
            <label htmlFor="f-exp" className="block text-xs text-slate-600 mb-1">Experience Level</label>
            <select
              id="f-exp"
              value={experienceLevel}
              onChange={(e) => setExperienceLevel(e.target.value)}
              className="w-full px-2.5 py-1.5 text-sm border border-slate-300 rounded bg-white"
            >
              <option value="">Any</option>
              <option value="internship">Internship</option>
              <option value="entry">Entry</option>
              <option value="mid">Mid</option>
              <option value="senior">Senior</option>
            </select>
          </div>

          <div>
            <label htmlFor="f-days" className="block text-xs text-slate-600 mb-1">Posted Within</label>
            <select
              id="f-days"
              value={days}
              onChange={(e) => setDays(e.target.value)}
              className="w-full px-2.5 py-1.5 text-sm border border-slate-300 rounded bg-white"
            >
              <option value="">Any time</option>
              <option value="1">Last 24 hours</option>
              <option value="7">Last 7 days</option>
              <option value="30">Last 30 days</option>
            </select>
          </div>

          <div>
            <label htmlFor="f-retrieval" className="block text-xs text-slate-600 mb-1">Retrieval Mode</label>
            <select
              id="f-retrieval"
              value={retrievalMethod}
              onChange={(e) => setRetrievalMethod(e.target.value as RetrievalMethod)}
              className="w-full px-2.5 py-1.5 text-sm border border-slate-300 rounded bg-white"
            >
              <option value="hybrid_rerank">Hybrid + Rerank</option>
              <option value="hybrid">Hybrid (RRF)</option>
              <option value="semantic">Semantic</option>
              <option value="keyword">Keyword</option>
            </select>
          </div>
        </div>
      </form>

      {error && (
        <div className="bg-rose-50 border border-rose-200 text-rose-800 rounded-md p-4 flex items-start gap-3 text-sm" role="alert">
          <AlertCircle className="h-5 w-5 shrink-0 mt-0.5" />
          <div>
            <div className="font-medium">Could not complete search</div>
            <div className="mt-0.5">{error}</div>
          </div>
        </div>
      )}

      {hasSearched && !loading && !error && (
        <div className="text-xs font-mono text-slate-500">
          Showing {jobs.length} results{total !== null ? ` (provider reported ${total} total)` : ''} · Source: Jobvetta
        </div>
      )}

      <div className="space-y-4">
        {hasSearched && !loading && !error && jobs.length === 0 && (
          <div className="bg-white border border-slate-200 rounded-md p-8 text-center text-sm text-slate-600">
            No matching jobs found for this query. Try broadening your keywords or filters.
          </div>
        )}

        {jobs.map((job) => (
          <JobCard
            key={job.id}
            job={job}
            onAnalyze={handleAnalyze}
            onSave={handleSave}
            onApply={setApplyJob}
            saving={savingId === job.id}
            saved={savedIds.has(job.id)}
          />
        ))}
      </div>

      {/* Match Analysis Modal */}
      {analyzingJob && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4 overflow-y-auto" role="dialog" aria-modal="true">
          <div className="bg-stone-50 border border-slate-200 rounded-md max-w-3xl w-full max-h-[90vh] overflow-y-auto p-6 space-y-4">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="text-lg font-semibold text-slate-900">{analyzingJob.title}</h2>
                <p className="text-sm text-slate-600">{analyzingJob.company || 'Unknown company'}</p>
              </div>
              <button
                type="button"
                onClick={() => setAnalyzingJob(null)}
                className="p-1 text-slate-400 hover:text-slate-700"
                aria-label="Close analysis"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {analysisLoading && (
              <div className="bg-white border border-slate-200 rounded p-6 text-sm text-slate-600">
                Evaluating requirements against your candidate profile...
              </div>
            )}
            {analysisError && (
              <div className="bg-rose-50 border border-rose-200 rounded p-4 text-sm text-rose-800">
                {analysisError}
              </div>
            )}
            {analysis && <MatchEvidenceView analysis={analysis} />}
          </div>
        </div>
      )}

      <ApplyModal job={applyJob} onClose={() => setApplyJob(null)} />
    </div>
  );
};
