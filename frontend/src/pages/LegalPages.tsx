import React from 'react';

export const PrivacyPolicyPage: React.FC = () => (
  <article className="max-w-3xl bg-white border border-slate-200 rounded-md p-8 space-y-4 text-sm text-slate-700 leading-relaxed">
    <h1 className="text-2xl font-bold text-slate-900">Privacy Policy</h1>
    <p className="text-xs text-slate-500">Last updated: November 2026</p>
    <p>
      JobPilot AI stores your candidate profile, uploaded resume text, saved jobs, search history,
      and conversation messages in the configured PostgreSQL database solely to provide job matching,
      evidence analysis, and skill-gap reporting.
    </p>
    <h2 className="text-base font-semibold text-slate-900 pt-2">Data Handling</h2>
    <ul className="list-disc pl-5 space-y-1">
      <li>Uploaded resumes are parsed on the server and are never shared with third-party job boards.</li>
      <li>External job listings are retrieved server-side from Jobvetta without exposing your API keys or profile to the browser.</li>
      <li>You can update or clear your profile data at any time.</li>
    </ul>
  </article>
);

export const TermsPage: React.FC = () => (
  <article className="max-w-3xl bg-white border border-slate-200 rounded-md p-8 space-y-4 text-sm text-slate-700 leading-relaxed">
    <h1 className="text-2xl font-bold text-slate-900">Terms and Conditions</h1>
    <p className="text-xs text-slate-500">Last updated: November 2026</p>
    <p>
      JobPilot AI is an explainable career matching tool. Match scores and evidence tables reflect
      automated comparisons between job requirements and your stored profile, and do not represent
      hiring probabilities or guaranteed outcomes.
    </p>
    <h2 className="text-base font-semibold text-slate-900 pt-2">External Job Listings</h2>
    <p>
      Job listings are sourced from third-party providers including Jobvetta. Clicking Apply redirects
      you to the external employer or job source website, which is governed by its own terms.
    </p>
  </article>
);
