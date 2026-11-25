import React from 'react';
import { ExternalLink, X } from 'lucide-react';
import type { Job } from '../types';

interface ApplyModalProps {
  job: Job | null;
  onClose: () => void;
}

export const ApplyModal: React.FC<ApplyModalProps> = ({ job, onClose }) => {
  if (!job || !job.application_url) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4" role="dialog" aria-modal="true">
      <div className="bg-white border border-slate-200 rounded-md max-w-md w-full p-6 space-y-4">
        <div className="flex items-start justify-between gap-3">
          <h3 className="text-base font-semibold text-slate-900">External Application</h3>
          <button type="button" onClick={onClose} className="text-slate-400 hover:text-slate-700" aria-label="Close">
            <X className="h-5 w-5" />
          </button>
        </div>

        <p className="text-sm text-slate-600 leading-relaxed">
          You are leaving JobPilot to apply on the employer or job source website for{' '}
          <span className="font-medium text-slate-900">{job.title}</span>
          {job.company ? ` at ${job.company}` : ''}.
        </p>

        <div className="text-xs font-mono bg-stone-50 border border-slate-200 rounded p-2.5 text-slate-600 break-all">
          {job.application_url}
        </div>

        <div className="flex items-center justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onClose}
            className="px-3.5 py-2 text-sm font-medium border border-slate-300 rounded text-slate-700 hover:bg-slate-50"
          >
            Cancel
          </button>
          <a
            href={job.application_url}
            target="_blank"
            rel="noopener noreferrer"
            onClick={onClose}
            className="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium bg-slate-900 text-white rounded hover:bg-slate-800"
          >
            Continue to Application
            <ExternalLink className="h-4 w-4" />
          </a>
        </div>
      </div>
    </div>
  );
};
