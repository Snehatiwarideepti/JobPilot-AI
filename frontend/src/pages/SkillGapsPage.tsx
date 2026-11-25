import React, { useState } from 'react';
import { BarChart3 } from 'lucide-react';
import { api } from '../services/api';
import type { SkillGapAnalysis } from '../types';

export const SkillGapsPage: React.FC = () => {
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<SkillGapAnalysis | null>(null);

  const handleAnalyze = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.getSkillGaps(query.trim());
      setData(res);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Skill gap analysis failed');
      setData(null);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-4xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">Skill Gap Analysis</h1>
        <p className="text-sm text-slate-600 mt-1">
          Compares your profile against skills actually observed in retrieved job listings for a target role.
        </p>
      </div>

      <form onSubmit={handleAnalyze} className="bg-white border border-slate-200 rounded-md p-5 flex flex-col sm:flex-row gap-3">
        <input
          type="text"
          required
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Target role (e.g. Machine Learning Engineer)"
          className="flex-1 px-3 py-2 text-sm border border-slate-300 rounded focus:outline-none focus:ring-2 focus:ring-teal-700"
        />
        <button
          type="submit"
          disabled={loading}
          className="inline-flex items-center justify-center gap-2 px-4 py-2 bg-slate-900 text-white text-sm font-medium rounded hover:bg-slate-800 disabled:opacity-50"
        >
          <BarChart3 className="h-4 w-4" />
          {loading ? 'Analyzing...' : 'Analyze Skill Gaps'}
        </button>
      </form>

      {error && (
        <div className="bg-rose-50 border border-rose-200 text-rose-800 rounded-md p-4 text-sm">
          {error}
        </div>
      )}

      {data && (
        <div className="space-y-6">
          <div className="bg-white border border-slate-200 rounded-md p-5 space-y-2">
            <div className="text-xs font-mono text-slate-500">
              {data.data_source} · {data.total_jobs_analyzed} jobs analyzed
            </div>
            <p className="text-xs text-slate-600">{data.note}</p>

            {data.recommended_skills_to_learn.length > 0 && (
              <div className="pt-3">
                <div className="text-xs font-semibold uppercase tracking-wider text-slate-700 mb-2">
                  Observed in retrieved jobs · Recommended next skills
                </div>
                <div className="flex flex-wrap gap-2">
                  {data.recommended_skills_to_learn.map((s) => (
                    <span key={s} className="px-2.5 py-1 text-xs font-medium bg-rose-50 text-rose-800 border border-rose-200 rounded">
                      {s}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>

          <div className="bg-white border border-slate-200 rounded-md overflow-hidden">
            <table className="w-full text-left border-collapse text-sm">
              <thead className="bg-stone-50 border-b border-slate-200 text-xs uppercase tracking-wider text-slate-500">
                <tr>
                  <th className="py-3 px-4 font-medium">Skill</th>
                  <th className="py-3 px-4 font-medium">Job Frequency</th>
                  <th className="py-3 px-4 font-medium">Your Status</th>
                  <th className="py-3 px-4 font-medium">Evidence</th>
                </tr>
              </thead>
              <tbody>
                {data.skill_coverage.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="py-6 px-4 text-center text-slate-500">
                      No structured skills found across retrieved jobs for this query. Search for live jobs first.
                    </td>
                  </tr>
                ) : (
                  data.skill_coverage.map((item) => (
                    <tr key={item.skill} className="border-t border-slate-200">
                      <td className="py-3 px-4 font-medium text-slate-900">{item.skill}</td>
                      <td className="py-3 px-4 font-mono text-slate-600">{item.frequency_in_target_jobs}</td>
                      <td className="py-3 px-4">
                        <span
                          className={`px-2 py-0.5 text-xs font-medium rounded border ${
                            item.candidate_status === 'MATCH'
                              ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
                              : item.candidate_status === 'PARTIAL'
                              ? 'bg-amber-50 text-amber-800 border-amber-200'
                              : 'bg-rose-50 text-rose-800 border-rose-200'
                          }`}
                        >
                          {item.candidate_status}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-xs text-slate-600">
                        {item.candidate_evidence || 'No evidence found'}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
