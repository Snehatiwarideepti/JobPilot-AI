import React from 'react';
import {
  CheckCircle2,
  AlertCircle,
  XCircle,
  HelpCircle,
  Briefcase,
  MapPin,
  Sparkles,
  BarChart3,
} from 'lucide-react';
import type { JobMatchAnalysis, JobMatchAnalysisV2, MatchDecision, RequirementEvidence } from '../types';

const DECISION_STYLE: Record<MatchDecision, { label: string; cls: string; Icon: React.ElementType }> = {
  MATCH: { label: 'Strong match', cls: 'bg-emerald-50 text-emerald-800 border-emerald-200', Icon: CheckCircle2 },
  PARTIAL: { label: 'Partial match', cls: 'bg-amber-50 text-amber-800 border-amber-200', Icon: AlertCircle },
  GAP: { label: 'Skill gap', cls: 'bg-rose-50 text-rose-800 border-rose-200', Icon: XCircle },
  UNKNOWN: { label: 'Unknown', cls: 'bg-slate-100 text-slate-700 border-slate-200', Icon: HelpCircle },
};

const EvidenceRow: React.FC<{ item: RequirementEvidence }> = ({ item }) => {
  const meta = DECISION_STYLE[item.decision] || DECISION_STYLE.UNKNOWN;
  const Icon = meta.Icon;
  return (
    <tr className="border-t border-slate-200 align-top">
      <td className="py-3 pr-4 font-medium text-slate-900 text-sm">
        {item.requirement}
        {item.source_type && (
          <span className="ml-2 text-xs text-slate-400 font-normal">
            ({item.source_type})
          </span>
        )}
      </td>
      <td className="py-3 pr-4 text-sm text-slate-700">
        {item.candidate_evidence ? (
          <span>{item.candidate_evidence}</span>
        ) : (
          <span className="text-slate-400 italic">No evidence found in candidate profile.</span>
        )}
      </td>
      <td className="py-3 whitespace-nowrap">
        <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 text-xs font-medium border rounded ${meta.cls}`}>
          <Icon className="h-3.5 w-3.5" />
          {meta.label}
        </span>
      </td>
    </tr>
  );
};

export const MatchEvidenceView: React.FC<{ analysis: JobMatchAnalysisV2 | JobMatchAnalysis }> = ({ analysis }) => {
  const isV2 = 'score_breakdown' in analysis;
  const v2 = isV2 ? (analysis as JobMatchAnalysisV2) : null;
  const missingReqs = v2 ? v2.missing_requirements : (analysis as JobMatchAnalysis).skill_gaps;
  const unknownReqs = v2 ? v2.unknown_requirements : [];

  const allItems = [
    ...(analysis.matched_requirements || []),
    ...(analysis.partial_matches || []),
    ...(missingReqs || []),
    ...(unknownReqs || []),
  ];

  const breakdown = v2?.score_breakdown;
  const expFit = v2?.experience_fit;
  const wpFit = v2?.workplace_fit;

  const expMeta = expFit ? (DECISION_STYLE[expFit.fit] || DECISION_STYLE.UNKNOWN) : null;
  const wpMeta = wpFit ? (DECISION_STYLE[wpFit.fit] || DECISION_STYLE.UNKNOWN) : null;

  return (
    <div className="bg-white border border-slate-200 rounded-md p-6 space-y-6">
      {/* Header & Overall Score */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-200 pb-4">
        <div>
          <div className="text-xs uppercase tracking-wider text-slate-500 font-medium">
            {isV2 ? 'Explainable V2 Analysis' : 'Evidence-Based Analysis'}
          </div>
          <h3 className="text-lg font-semibold text-slate-900 mt-0.5">{analysis.recommendation}</h3>
          <p className="text-xs text-slate-500 mt-1">
            Grounded in actual candidate profile & job listing requirements
          </p>
        </div>
        <div className="text-left sm:text-right">
          <div className="text-xs text-slate-500 font-medium">Overall Match Score</div>
          <div className="text-3xl font-semibold font-mono text-teal-700">
            {analysis.overall_match_score}
            <span className="text-sm text-slate-400 font-normal">/100</span>
          </div>
        </div>
      </div>

      {/* Score Breakdown Section */}
      {breakdown && (
        <div className="bg-slate-50 border border-slate-200 rounded-lg p-4 space-y-3">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-slate-700">
            <BarChart3 className="h-4 w-4 text-slate-500" />
            Score Breakdown (Explainable Formula)
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-1">
            <div className="bg-white p-3 rounded border border-slate-200 shadow-sm">
              <div className="text-xs text-slate-500">Skills Weight (70%)</div>
              <div className="text-lg font-mono font-bold text-slate-800 mt-0.5">
                {breakdown.skill_score}
                <span className="text-xs font-normal text-slate-400">/100</span>
              </div>
              <div className="text-[11px] text-slate-500 mt-1">Requirements evidence</div>
            </div>

            <div className="bg-white p-3 rounded border border-slate-200 shadow-sm">
              <div className="text-xs text-slate-500">Experience Weight (20%)</div>
              <div className="text-lg font-mono font-bold text-slate-800 mt-0.5">
                {breakdown.experience_fit_score !== null ? breakdown.experience_fit_score : '50 (Neutral)'}
                <span className="text-xs font-normal text-slate-400">/100</span>
              </div>
              <div className="text-[11px] text-slate-500 mt-1">Level comparison</div>
            </div>

            <div className="bg-white p-3 rounded border border-slate-200 shadow-sm">
              <div className="text-xs text-slate-500">Workplace Weight (10%)</div>
              <div className="text-lg font-mono font-bold text-slate-800 mt-0.5">
                {breakdown.workplace_fit_score !== null ? breakdown.workplace_fit_score : '50 (Neutral)'}
                <span className="text-xs font-normal text-slate-400">/100</span>
              </div>
              <div className="text-[11px] text-slate-500 mt-1">Remote/on-site fit</div>
            </div>
          </div>
        </div>
      )}

      {/* Fit Dimensions: Experience Fit & Workplace Fit */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {expFit && expMeta && (
          <div className="border border-slate-200 rounded-lg p-4 space-y-2 bg-white">
            <div className="flex items-center justify-between">
              <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-800">
                <Briefcase className="h-4 w-4 text-slate-500" />
                Experience Fit
              </span>
              <span className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium border rounded ${expMeta.cls}`}>
                <expMeta.Icon className="h-3 w-3" />
                {expMeta.label}
              </span>
            </div>
            <p className="text-xs text-slate-600 leading-relaxed">{expFit.explanation}</p>
            <div className="flex items-center gap-3 text-xs text-slate-500 pt-1">
              <span>Candidate: <strong className="text-slate-700">{expFit.candidate_level || 'Not set'}</strong></span>
              <span>•</span>
              <span>Job requires: <strong className="text-slate-700">{expFit.job_required_level || 'Unspecified'}</strong></span>
            </div>
          </div>
        )}

        {wpFit && wpMeta && (
          <div className="border border-slate-200 rounded-lg p-4 space-y-2 bg-white">
            <div className="flex items-center justify-between">
              <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-800">
                <MapPin className="h-4 w-4 text-slate-500" />
                Workplace Fit
              </span>
              <span className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium border rounded ${wpMeta.cls}`}>
                <wpMeta.Icon className="h-3 w-3" />
                {wpMeta.label}
              </span>
            </div>
            <p className="text-xs text-slate-600 leading-relaxed">{wpFit.explanation}</p>
            <div className="flex items-center gap-3 text-xs text-slate-500 pt-1">
              <span>Candidate: <strong className="text-slate-700">{wpFit.candidate_preference || 'Flexible'}</strong></span>
              <span>•</span>
              <span>Job type: <strong className="text-slate-700">{wpFit.job_workplace_type || 'Unspecified'}</strong></span>
            </div>
          </div>
        )}
      </div>

      {/* Candidate Strengths */}
      {v2?.candidate_strengths && v2.candidate_strengths.length > 0 && (
        <div className="border border-emerald-200 bg-emerald-50/50 rounded-lg p-4 space-y-2">
          <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-emerald-900">
            <Sparkles className="h-4 w-4 text-emerald-600" />
            Candidate Strengths (Grounded in Verified Profile Data)
          </div>
          <ul className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs text-slate-700 pt-1">
            {v2.candidate_strengths.map((str, idx) => (
              <li key={idx} className="flex items-start gap-1.5">
                <span className="text-emerald-600 font-bold">✓</span>
                <span>{str}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Reasoning Narrative */}
      {analysis.reasoning && (
        <div className="space-y-1">
          <div className="text-xs font-semibold uppercase tracking-wider text-slate-500">Analysis Summary</div>
          <p className="text-sm text-slate-700 leading-relaxed bg-slate-50 p-3 rounded border border-slate-100">
            {analysis.reasoning}
          </p>
        </div>
      )}

      {/* Requirements Evidence Table */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
            Requirements Breakdown ({allItems.length} evaluated)
          </h4>
          <div className="flex items-center gap-3 text-xs text-slate-500">
            <span className="text-emerald-700 font-medium">{analysis.matched_requirements?.length || 0} Matched</span>
            <span>•</span>
            <span className="text-amber-700 font-medium">{analysis.partial_matches?.length || 0} Partial</span>
            <span>•</span>
            <span className="text-rose-700 font-medium">{(missingReqs?.length) || 0} Gaps</span>
            {(unknownReqs?.length) > 0 && (
              <>
                <span>•</span>
                <span className="text-slate-600 font-medium">{unknownReqs.length} Unknown</span>
              </>
            )}
          </div>
        </div>

        {allItems.length > 0 ? (
          <div className="overflow-x-auto border border-slate-200 rounded-md">
            <table className="w-full text-left border-collapse">
              <thead className="bg-slate-50 border-b border-slate-200">
                <tr className="text-xs uppercase tracking-wider text-slate-500">
                  <th className="py-2.5 px-3 font-medium">Job Requirement</th>
                  <th className="py-2.5 px-3 font-medium">Candidate Evidence</th>
                  <th className="py-2.5 px-3 font-medium">Decision</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 bg-white">
                {allItems.map((item, idx) => (
                  <EvidenceRow key={`${item.requirement}-${idx}`} item={item} />
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-sm text-slate-500">No structured requirements were listed on this job posting.</p>
        )}
      </div>
    </div>
  );
};
