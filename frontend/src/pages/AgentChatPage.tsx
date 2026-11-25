import React, { useState } from 'react';
import { Send, Wrench } from 'lucide-react';
import { api } from '../services/api';
import { JobCard } from '../components/JobCard';
import { MatchEvidenceView } from '../components/MatchEvidenceView';
import { ApplyModal } from '../components/ApplyModal';
import type { Job, JobMatchAnalysis } from '../types';

interface ChatItem {
  role: 'user' | 'assistant';
  content: string;
  tools?: string[];
  jobs?: Job[] | null;
  matchAnalysis?: JobMatchAnalysis | null;
}

export const AgentChatPage: React.FC = () => {
  const [sessionId, setSessionId] = useState<string>(() => {
    const existing = localStorage.getItem('jobpilot_chat_session');
    if (existing) return existing;
    const id = crypto.randomUUID();
    localStorage.setItem('jobpilot_chat_session', id);
    return id;
  });

  const [messages, setMessages] = useState<ChatItem[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [applyJob, setApplyJob] = useState<Job | null>(null);

  const sendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    const text = input.trim();
    if (!text || loading) return;

    setMessages((prev) => [...prev, { role: 'user', content: text }]);
    setInput('');
    setLoading(true);

    try {
      const res = await api.chat(text, sessionId);
      setSessionId(res.session_id);
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: res.response,
          tools: res.tool_calls_made,
          jobs: res.jobs_found,
          matchAnalysis: res.match_analysis,
        },
      ]);
    } catch (err: unknown) {
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: `Error: ${err instanceof Error ? err.message : 'Agent request failed'}`,
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-4xl space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">Career Matching Agent</h1>
          <p className="text-sm text-slate-600 mt-1">
            Ask in natural language. The agent invokes live search, fit analysis, and skill-gap tools with session memory.
          </p>
        </div>
        <button
          type="button"
          onClick={() => {
            const id = crypto.randomUUID();
            localStorage.setItem('jobpilot_chat_session', id);
            setSessionId(id);
            setMessages([]);
          }}
          className="px-3 py-1.5 text-xs font-medium border border-slate-300 rounded text-slate-700 hover:bg-slate-50"
        >
          New Session
        </button>
      </div>

      <div className="bg-white border border-slate-200 rounded-md p-5 min-h-[420px] max-h-[65vh] overflow-y-auto space-y-5">
        {messages.length === 0 && (
          <div className="text-sm text-slate-500 space-y-2 py-8 text-center">
            <p className="font-medium text-slate-700">Example queries</p>
            <p>Find me remote Python data science internships.</p>
            <p>Only show ones posted in the last 7 days.</p>
            <p>Analyze my fit for the first one.</p>
          </div>
        )}

        {messages.map((m, idx) => (
          <div key={idx} className={`space-y-3 ${m.role === 'user' ? 'text-right' : 'text-left'}`}>
            <div
              className={`inline-block max-w-[85%] rounded-md px-4 py-3 text-sm whitespace-pre-wrap text-left ${
                m.role === 'user'
                  ? 'bg-slate-900 text-white'
                  : 'bg-stone-50 border border-slate-200 text-slate-800'
              }`}
            >
              {m.tools && m.tools.length > 0 && (
                <div className="flex flex-wrap items-center gap-1.5 mb-2 text-[11px] font-mono text-teal-800">
                  <Wrench className="h-3 w-3" />
                  <span>Tools: {m.tools.join(', ')}</span>
                </div>
              )}
              {m.content}
            </div>

            {m.jobs && m.jobs.length > 0 && (
              <div className="space-y-3 text-left">
                {m.jobs.map((job) => (
                  <JobCard key={job.id} job={job} onApply={setApplyJob} />
                ))}
              </div>
            )}

            {m.matchAnalysis && (
              <div className="text-left">
                <MatchEvidenceView analysis={m.matchAnalysis} />
              </div>
            )}
          </div>
        ))}

        {loading && (
          <div className="text-xs font-mono text-slate-500">Agent is running tools and reasoning...</div>
        )}
      </div>

      <form onSubmit={sendMessage} className="flex gap-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask JobPilot to search jobs, refine filters, or explain a match..."
          className="flex-1 px-3.5 py-2.5 text-sm border border-slate-300 rounded bg-white focus:outline-none focus:ring-2 focus:ring-teal-700"
        />
        <button
          type="submit"
          disabled={loading || !input.trim()}
          className="inline-flex items-center gap-1.5 px-4 py-2.5 bg-slate-900 text-white text-sm font-medium rounded hover:bg-slate-800 disabled:opacity-50"
        >
          <Send className="h-4 w-4" />
          Send
        </button>
      </form>

      <ApplyModal job={applyJob} onClose={() => setApplyJob(null)} />
    </div>
  );
};
