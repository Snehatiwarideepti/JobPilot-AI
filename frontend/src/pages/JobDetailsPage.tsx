import React, { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { ArrowLeft, Building2, MapPin, Calendar, ExternalLink, Bookmark, SearchCheck } from 'lucide-react';
import { api } from '../services/api';
import { MatchEvidenceView } from '../components/MatchEvidenceView';
import { ApplyModal } from '../components/ApplyModal';
import type { Job, JobMatchAnalysisV2 } from '../types';

export const JobDetailsPage: React.FC = () => {
  const { jobId } = useParams<{ jobId: string }>();
  const [job, setJob] = useState<Job | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [analysis, setAnalysis] = useState<JobMatchAnalysisV2 | null>(null);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [analysisError, setAnalysisError] = useState<string | null>(null);

  const [saved, setSaved] = useState(false);
  const [applyOpen, setApplyOpen] = useState(false);

  useEffect(() => {
    if (!jobId) return;
    setLoading(true);
    api
      .getJob(jobId)
      .then(setJob)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [jobId]);

  const runAnalysis = async () => {
    if (!jobId) return;
    setAnalysisLoading(true);
    setAnalysisError(null);
    try {
      const res = await api.analyzeMatch(jobId);
      setAnalysis(res);
    } catch (e: unknown) {
      setAnalysisError(e instanceof Error ? e.message : 'Analysis failed');
    } finally {
      setAnalysisLoading(false);
    }
  };

  const handleSave = async () => {
    if (!jobId) return;
    await api.saveJob(jobId);
    setSaved(true);
  };

  if (loading) return <div className="text-sm text-slate-600">Loading job details...</div>;
  if (error || !job) {
    return (
      <div className="bg-rose-50 border border-rose-200 text-rose-800 rounded-md p-5 text-sm">
        {error || 'Job not found.'}
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-4xl">
      <Link to="/search" className="inline-flex items-center gap-1.5 text-sm text-slate-600 hover:text-slate-900">
        <ArrowLeft className="h-4 w-4" />
        Back to Search
      </Link>

      <div className="bg-white border border-slate-200 rounded-md p-6 space-y-5">
        <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-2xl font-bold text-slate-900">{job.title}</h1>
              <span className="text-xs font-mono uppercase px-2 py-0.5 bg-slate-100 text-slate-600 rounded">
                Source: {job.source}
              </span>
            </div>

            <div className="flex flex-wrap items-center gap-4 text-sm text-slate-600">
              {job.company && (
                <span className="inline-flex items-center gap-1.5">
                  <Building2 className="h-4 w-4 text-slate-400" />
                  {job.company}
                </span>
              )}
              {job.location && (
                <span className="inline-flex items-center gap-1.5">
                  <MapPin className="h-4 w-4 text-slate-400" />
                  {job.location}
                </span>
              )}
              {job.posted_at && (
                <span className="inline-flex items-center gap-1.5">
                  <Calendar className="h-4 w-4 text-slate-400" />
                  {new Date(job.posted_at).toLocaleDateString()}
                </span>
              )}
            </div>

            {(job.salary_min || job.salary_max) && (
              <div className="text-sm font-mono text-slate-700">
                Compensation: {job.salary_currency || ''} {job.salary_min ?? ''}
                {job.salary_max ? ` - ${job.salary_max}` : ''} {job.salary_period || ''}
              </div>
            )}
          </div>

          <div className="flex flex-wrap gap-2 shrink-0">
            <button
              type="button"
              onClick={runAnalysis}
              disabled={analysisLoading}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 text-sm font-medium border border-teal-700 text-teal-800 rounded hover:bg-teal-50"
            >
              <SearchCheck className="h-4 w-4" />
              {analysisLoading ? 'Analyzing...' : 'Analyze Fit'}
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={saved}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 text-sm font-medium border border-slate-300 rounded text-slate-700 hover:bg-slate-50"
            >
              <Bookmark className="h-4 w-4" />
              {saved ? 'Saved' : 'Save'}
            </button>
            {job.application_url && (
              <button
                type="button"
                onClick={() => setApplyOpen(true)}
                className="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium bg-slate-900 text-white rounded hover:bg-slate-800"
              >
                Apply
                <ExternalLink className="h-4 w-4" />
              </button>
            )}
          </div>
        </div>

        {job.skills && job.skills.length > 0 && (
          <div className="pt-4 border-t border-slate-100">
            <h2 className="text-xs uppercase tracking-wider text-slate-500 font-medium mb-2">Listed Skills</h2>
            <div className="flex flex-wrap gap-1.5">
              {job.skills.map((s) => (
                <span key={s} className="px-2.5 py-0.5 text-xs bg-slate-100 text-slate-800 rounded">
                  {s}
                </span>
              ))}
            </div>
          </div>
        )}

        {job.description && (
          <div className="pt-4 border-t border-slate-100 space-y-2">
            <h2 className="text-sm font-semibold text-slate-900">Description</h2>
            <p className="text-sm text-slate-700 whitespace-pre-line leading-relaxed">{job.description}</p>
          </div>
        )}

        {job.requirements && (
          <div className="pt-4 border-t border-slate-100 space-y-2">
            <h2 className="text-sm font-semibold text-slate-900">Requirements</h2>
            <p className="text-sm text-slate-700 whitespace-pre-line leading-relaxed">{job.requirements}</p>
          </div>
        )}

        {job.responsibilities && (
          <div className="pt-4 border-t border-slate-100 space-y-2">
            <h2 className="text-sm font-semibold text-slate-900">Responsibilities</h2>
            <p className="text-sm text-slate-700 whitespace-pre-line leading-relaxed">{job.responsibilities}</p>
          </div>
        )}
      </div>

      {analysisError && (
        <div className="bg-rose-50 border border-rose-200 text-rose-800 rounded-md p-4 text-sm">
          {analysisError}
        </div>
      )}

      {analysis && <MatchEvidenceView analysis={analysis} />}

      <ApplyModal job={applyOpen ? job : null} onClose={() => setApplyOpen(false)} />
    </div>
  );
};
