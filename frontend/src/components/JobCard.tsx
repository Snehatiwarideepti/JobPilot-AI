import React from 'react';
import { Link } from 'react-router-dom';
import { MapPin, Building2, Bookmark, ExternalLink, SearchCheck, ArrowRight } from 'lucide-react';
import type { Job } from '../types';

interface JobCardProps {
  job: Job;
  onAnalyze?: (job: Job) => void;
  onSave?: (job: Job) => void;
  onApply?: (job: Job) => void;
  saving?: boolean;
  saved?: boolean;
}

const formatLabel = (val?: string | null) => {
  if (!val || val === 'unspecified') return null;
  return val.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
};

export const JobCard: React.FC<JobCardProps> = ({
  job,
  onAnalyze,
  onSave,
  onApply,
  saving,
  saved,
}) => {
  const workplace = formatLabel(job.workplace_type);
  const employment = formatLabel(job.employment_type);
  const experience = formatLabel(job.experience_level);

  return (
    <article className="bg-white border border-slate-200 rounded-md p-5 hover:border-slate-300 transition-colors">
      <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
        <div className="space-y-1.5 min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-base font-semibold text-slate-900 truncate">
              <Link to={`/jobs/${job.id}`} className="hover:text-teal-700 hover:underline underline-offset-2">
                {job.title}
              </Link>
            </h3>
            <span className="text-[11px] font-mono uppercase tracking-wider px-1.5 py-0.5 bg-slate-100 text-slate-600 rounded">
              Source: {job.source}
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-slate-600">
            {job.company && (
              <span className="inline-flex items-center gap-1">
                <Building2 className="h-3.5 w-3.5 text-slate-400" />
                {job.company}
              </span>
            )}
            {job.location && (
              <span className="inline-flex items-center gap-1">
                <MapPin className="h-3.5 w-3.5 text-slate-400" />
                {job.location}
              </span>
            )}
          </div>

          <div className="flex flex-wrap gap-2 pt-1 text-xs text-slate-600">
            {workplace && <span className="px-2 py-0.5 border border-slate-200 rounded bg-stone-50">{workplace}</span>}
            {employment && <span className="px-2 py-0.5 border border-slate-200 rounded bg-stone-50">{employment}</span>}
            {experience && <span className="px-2 py-0.5 border border-slate-200 rounded bg-stone-50">{experience}</span>}
          </div>
        </div>

        {job.match_score !== undefined && job.match_score !== null && (
          <div className="shrink-0 sm:text-right border-t sm:border-t-0 pt-3 sm:pt-0 border-slate-100">
            <div className="text-xs uppercase tracking-wide text-slate-500 font-medium">Match Score</div>
            <div className="text-2xl font-semibold font-mono text-teal-700">
              {Math.round(job.match_score)}
              <span className="text-xs text-slate-400 font-normal">/100</span>
            </div>
          </div>
        )}
      </div>

      {(job.top_matching_skills?.length || job.skill_gaps?.length) ? (
        <div className="mt-4 pt-4 border-t border-slate-100 grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
          {job.top_matching_skills && job.top_matching_skills.length > 0 && (
            <div>
              <span className="font-medium text-slate-700 block mb-1">Matched skills</span>
              <div className="flex flex-wrap gap-1.5">
                {job.top_matching_skills.map((s) => (
                  <span key={s} className="px-2 py-0.5 bg-emerald-50 text-emerald-800 border border-emerald-200 rounded">
                    {s}
                  </span>
                ))}
              </div>
            </div>
          )}
          {job.skill_gaps && job.skill_gaps.length > 0 && (
            <div>
              <span className="font-medium text-slate-700 block mb-1">Skill gaps</span>
              <div className="flex flex-wrap gap-1.5">
                {job.skill_gaps.map((s) => (
                  <span key={s} className="px-2 py-0.5 bg-rose-50 text-rose-800 border border-rose-200 rounded">
                    {s}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      ) : job.skills && job.skills.length > 0 ? (
        <div className="mt-4 pt-3 border-t border-slate-100 flex flex-wrap gap-1.5 text-xs">
          {job.skills.slice(0, 8).map((s) => (
            <span key={s} className="px-2 py-0.5 bg-slate-100 text-slate-700 rounded">
              {s}
            </span>
          ))}
        </div>
      ) : null}

      <div className="mt-4 pt-3 border-t border-slate-100 flex flex-wrap items-center gap-2">
        <Link
          to={`/jobs/${job.id}`}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-slate-300 rounded text-slate-700 hover:bg-slate-50"
        >
          View Job
          <ArrowRight className="h-3.5 w-3.5" />
        </Link>

        {onAnalyze && (
          <button
            type="button"
            onClick={() => onAnalyze(job)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-teal-700 text-teal-800 rounded hover:bg-teal-50"
          >
            <SearchCheck className="h-3.5 w-3.5" />
            Analyze Fit
          </button>
        )}

        {onSave && (
          <button
            type="button"
            disabled={saving || saved}
            onClick={() => onSave(job)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-slate-300 rounded text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            <Bookmark className="h-3.5 w-3.5" />
            {saved ? 'Saved' : saving ? 'Saving...' : 'Save'}
          </button>
        )}

        {job.application_url && onApply && (
          <button
            type="button"
            onClick={() => onApply(job)}
            className="ml-auto inline-flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-medium bg-slate-900 text-white rounded hover:bg-slate-800"
          >
            Apply
            <ExternalLink className="h-3.5 w-3.5" />
          </button>
        )}
      </div>
    </article>
  );
};
