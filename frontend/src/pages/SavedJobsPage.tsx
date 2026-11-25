import React, { useEffect, useState } from 'react';
import { api } from '../services/api';
import { JobCard } from '../components/JobCard';
import { ApplyModal } from '../components/ApplyModal';
import type { Job } from '../types';

export const SavedJobsPage: React.FC = () => {
  const [items, setItems] = useState<{ id: string; job: Job; notes: string | null; created_at: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [applyJob, setApplyJob] = useState<Job | null>(null);

  useEffect(() => {
    api
      .getSavedJobs()
      .then(setItems)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">Saved Jobs</h1>
        <p className="text-sm text-slate-600 mt-1">Jobs bookmarked to your profile.</p>
      </div>

      {loading && <p className="text-sm text-slate-600">Loading saved jobs...</p>}
      {error && <div className="bg-rose-50 border border-rose-200 text-rose-800 p-4 rounded text-sm">{error}</div>}

      {!loading && !error && items.length === 0 && (
        <div className="bg-white border border-slate-200 rounded-md p-8 text-center text-sm text-slate-600">
          No saved jobs yet. Save jobs from Search Jobs or the AI Agent.
        </div>
      )}

      <div className="space-y-4">
        {items.map((item) => (
          <JobCard key={item.id} job={item.job} saved onApply={setApplyJob} />
        ))}
      </div>

      <ApplyModal job={applyJob} onClose={() => setApplyJob(null)} />
    </div>
  );
};
