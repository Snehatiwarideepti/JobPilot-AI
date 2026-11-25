import React, { useEffect, useState } from 'react';
import { Play, Database } from 'lucide-react';
import { api } from '../services/api';
import type { EvaluationSummary } from '../types';

const METHOD_LABELS: Record<string, string> = {
  keyword: 'Keyword',
  semantic: 'Semantic',
  hybrid: 'Hybrid',
  hybrid_rerank: 'Hybrid + Rerank',
};

export const EvaluationPage: React.FC = () => {
  const [summary, setSummary] = useState<EvaluationSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionMsg, setActionMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    api
      .getEvaluationResults()
      .then(setSummary)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  const handleSeed = async () => {
    setActionMsg(null);
    setError(null);
    try {
      const res = await api.seedEvaluation();
      setActionMsg(res.message);
      load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Seed failed');
    }
  };

  const handleRun = async () => {
    setActionMsg(null);
    setError(null);
    try {
      const res = await api.runEvaluation();
      setActionMsg(`${res.message} ${res.note}`);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Evaluation run failed');
    }
  };

  const methodEntries = summary ? Object.entries(summary.methods) : [];

  return (
    <div className="max-w-4xl space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">Retrieval Evaluation</h1>
          <p className="text-sm text-slate-600 mt-1">
            Measures Hit@5, Hit@10, and MRR across retrieval strategies using actual database queries.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleSeed}
            className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-medium border border-slate-300 rounded text-slate-700 hover:bg-slate-50"
          >
            <Database className="h-3.5 w-3.5" />
            Seed Queries
          </button>
          <button
            type="button"
            onClick={handleRun}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 text-xs font-medium bg-slate-900 text-white rounded hover:bg-slate-800"
          >
            <Play className="h-3.5 w-3.5" />
            Run Evaluation
          </button>
        </div>
      </div>

      {actionMsg && (
        <div className="bg-stone-100 border border-slate-200 text-slate-800 rounded p-3.5 text-sm">
          {actionMsg}
        </div>
      )}
      {error && (
        <div className="bg-rose-50 border border-rose-200 text-rose-800 rounded p-3.5 text-sm">
          {error}
        </div>
      )}

      {loading ? (
        <p className="text-sm text-slate-600">Loading evaluation metrics...</p>
      ) : !summary || methodEntries.length === 0 ? (
        <div className="bg-white border border-slate-200 rounded-md p-8 text-center space-y-2">
          <p className="text-sm font-medium text-slate-900">Evaluation not run yet.</p>
          <p className="text-xs text-slate-500">
            Seed the 25 benchmark queries and run the evaluation pipeline after ingesting jobs to measure real metrics.
          </p>
        </div>
      ) : (
        <div className="bg-white border border-slate-200 rounded-md overflow-hidden">
          <table className="w-full text-left border-collapse text-sm">
            <thead className="bg-stone-50 border-b border-slate-200 text-xs uppercase tracking-wider text-slate-500">
              <tr>
                <th className="py-3 px-4 font-medium">Method</th>
                <th className="py-3 px-4 font-medium">Hit@5</th>
                <th className="py-3 px-4 font-medium">Hit@10</th>
                <th className="py-3 px-4 font-medium">MRR</th>
              </tr>
            </thead>
            <tbody>
              {methodEntries.map(([method, metrics]) => (
                <tr key={method} className="border-t border-slate-200">
                  <td className="py-3 px-4 font-medium text-slate-900">
                    {METHOD_LABELS[method] || method}
                  </td>
                  <td className="py-3 px-4 font-mono text-slate-700">
                    {metrics.hit_at_5 !== null ? metrics.hit_at_5.toFixed(3) : 'N/A'}
                  </td>
                  <td className="py-3 px-4 font-mono text-slate-700">
                    {metrics.hit_at_10 !== null ? metrics.hit_at_10.toFixed(3) : 'N/A'}
                  </td>
                  <td className="py-3 px-4 font-mono text-slate-700">
                    {metrics.mrr !== null ? metrics.mrr.toFixed(3) : 'N/A'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="px-4 py-3 bg-stone-50 border-t border-slate-200 text-xs text-slate-500">
            Total queries: {summary.total_queries} · {summary.note}
          </div>
        </div>
      )}
    </div>
  );
};
