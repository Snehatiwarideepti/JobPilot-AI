import React, { useEffect, useState } from 'react';
import { api } from '../services/api';

export const SearchHistoryPage: React.FC = () => {
  const [history, setHistory] = useState<
    { id: string; query: string; filters: Record<string, unknown> | null; result_count: number | null; created_at: string }[]
  >([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getSearchHistory()
      .then(setHistory)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="max-w-4xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">Search History</h1>
        <p className="text-sm text-slate-600 mt-1">Recorded job searches from your session.</p>
      </div>

      {loading && <p className="text-sm text-slate-600">Loading search history...</p>}
      {error && <div className="bg-rose-50 border border-rose-200 text-rose-800 p-4 rounded text-sm">{error}</div>}

      {!loading && !error && history.length === 0 && (
        <div className="bg-white border border-slate-200 rounded-md p-8 text-center text-sm text-slate-600">
          No searches recorded yet.
        </div>
      )}

      {history.length > 0 && (
        <div className="bg-white border border-slate-200 rounded-md overflow-hidden">
          <table className="w-full text-left border-collapse text-sm">
            <thead className="bg-stone-50 border-b border-slate-200 text-xs uppercase tracking-wider text-slate-500">
              <tr>
                <th className="py-3 px-4 font-medium">Query</th>
                <th className="py-3 px-4 font-medium">Results</th>
                <th className="py-3 px-4 font-medium">Timestamp</th>
              </tr>
            </thead>
            <tbody>
              {history.map((h) => (
                <tr key={h.id} className="border-t border-slate-200">
                  <td className="py-3 px-4 font-medium text-slate-900">{h.query}</td>
                  <td className="py-3 px-4 font-mono text-slate-600">{h.result_count ?? '-'}</td>
                  <td className="py-3 px-4 text-xs text-slate-500">
                    {new Date(h.created_at).toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
