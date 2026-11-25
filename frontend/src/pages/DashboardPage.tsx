import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, CheckCircle2, AlertTriangle, Search, User, Layers, ShieldCheck } from 'lucide-react';
import { api } from '../services/api';
import type { HealthResponse } from '../types';

export const DashboardPage: React.FC = () => {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);

  useEffect(() => {
    api.getHealth().then(setHealth).catch((e) => setHealthError(e.message));
  }, []);

  return (
    <div className="space-y-12">
      {/* Editorial Hero */}
      <section className="bg-white border border-slate-200 rounded-md p-8 sm:p-12">
        <div className="max-w-3xl space-y-5">
          <div className="text-xs font-mono uppercase tracking-widest text-teal-800 font-medium">
            Explainable AI Career Matching Agent
          </div>
          <h1 className="text-3xl sm:text-4xl font-bold tracking-tight text-slate-900">
            Find jobs that actually fit.
          </h1>
          <p className="text-base sm:text-lg text-slate-600 leading-relaxed">
            JobPilot searches current job listings, compares them with your profile, and shows
            exactly where you match, where you fall short, and why each recommendation was selected.
          </p>
          <div className="flex flex-wrap items-center gap-3 pt-2">
            <Link
              to="/search"
              className="inline-flex items-center gap-2 px-5 py-2.5 bg-slate-900 text-white text-sm font-medium rounded hover:bg-slate-800 transition-colors"
            >
              <Search className="h-4 w-4" />
              Find Jobs
            </Link>
            <Link
              to="/profile"
              className="inline-flex items-center gap-2 px-5 py-2.5 bg-white border border-slate-300 text-slate-800 text-sm font-medium rounded hover:bg-slate-50 transition-colors"
            >
              <User className="h-4 w-4" />
              Build My Profile
            </Link>
          </div>
        </div>
      </section>

      {/* Architecture / How Evidence Matching Works */}
      <section className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-white border border-slate-200 rounded-md p-6 space-y-2.5">
          <div className="inline-flex p-2 bg-stone-100 rounded text-slate-700">
            <Layers className="h-5 w-5" />
          </div>
          <h2 className="text-base font-semibold text-slate-900">Hybrid Retrieval + Reranking</h2>
          <p className="text-sm text-slate-600 leading-relaxed">
            Combines PostgreSQL full-text keyword search with pgvector semantic similarity, then
            reranks results by semantic fit, skill overlap, experience level, and workplace compatibility.
          </p>
        </div>

        <div className="bg-white border border-slate-200 rounded-md p-6 space-y-2.5">
          <div className="inline-flex p-2 bg-stone-100 rounded text-slate-700">
            <ShieldCheck className="h-5 w-5" />
          </div>
          <h2 className="text-base font-semibold text-slate-900">Evidence-Grounded Decisions</h2>
          <p className="text-sm text-slate-600 leading-relaxed">
            Every requirement is traced to stored skills, projects, or work experience and classified
            as Strong Match, Partial Match, Skill Gap, or Unknown.
          </p>
        </div>

        <div className="bg-white border border-slate-200 rounded-md p-6 space-y-2.5">
          <div className="inline-flex p-2 bg-stone-100 rounded text-slate-700">
            <ArrowRight className="h-5 w-5" />
          </div>
          <h2 className="text-base font-semibold text-slate-900">Observed Skill Gaps</h2>
          <p className="text-sm text-slate-600 leading-relaxed">
            Aggregates skills requested across real retrieved listings so learning priorities come
            from current market requirements rather than generic advice.
          </p>
        </div>
      </section>

      {/* Real System Status */}
      <section className="bg-white border border-slate-200 rounded-md p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-700">
            Live System Status
          </h2>
          {health && (
            <span className="inline-flex items-center gap-1.5 text-xs font-mono px-2 py-0.5 rounded bg-stone-100 text-slate-700">
              {health.status === 'ok' ? (
                <CheckCircle2 className="h-3.5 w-3.5 text-emerald-700" />
              ) : (
                <AlertTriangle className="h-3.5 w-3.5 text-amber-600" />
              )}
              {health.status}
            </span>
          )}
        </div>

        {healthError ? (
          <p className="text-sm text-rose-700">Backend unreachable: {healthError}</p>
        ) : health ? (
          <dl className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 text-sm">
            <div className="border border-slate-200 rounded p-3 bg-stone-50">
              <dt className="text-xs text-slate-500">Database</dt>
              <dd className="font-mono text-xs text-slate-900 mt-1 break-words">{health.database}</dd>
            </div>
            <div className="border border-slate-200 rounded p-3 bg-stone-50">
              <dt className="text-xs text-slate-500">Live Job Provider</dt>
              <dd className="font-mono text-xs text-slate-900 mt-1 break-words">{health.provider}</dd>
            </div>
            <div className="border border-slate-200 rounded p-3 bg-stone-50">
              <dt className="text-xs text-slate-500">Embeddings</dt>
              <dd className="font-mono text-xs text-slate-900 mt-1 break-words">{health.embeddings}</dd>
            </div>
            <div className="border border-slate-200 rounded p-3 bg-stone-50">
              <dt className="text-xs text-slate-500">LLM Agent</dt>
              <dd className="font-mono text-xs text-slate-900 mt-1 break-words">{health.llm}</dd>
            </div>
          </dl>
        ) : (
          <p className="text-sm text-slate-500">Checking backend subsystems...</p>
        )}
      </section>
    </div>
  );
};
