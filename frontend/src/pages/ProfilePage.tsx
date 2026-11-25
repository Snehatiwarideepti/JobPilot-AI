import React, { useEffect, useState } from 'react';
import { Upload, Plus, Trash2, Save, AlertTriangle, CheckCircle2 } from 'lucide-react';
import { api } from '../services/api';
import type { CandidateProfile } from '../types';

const EMPTY_PROFILE: CandidateProfile = {
  full_name: '',
  email: '',
  location: '',
  remote_preference: 'flexible',
  experience_level: 'entry',
  summary: '',
  target_roles: [],
  preferred_locations: [],
  skills: [],
  projects: [],
  experience: [],
  education: [],
  certifications: [],
};

export const ProfilePage: React.FC = () => {
  const [profile, setProfile] = useState<CandidateProfile>(EMPTY_PROFILE);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uncertainFields, setUncertainFields] = useState<string[]>([]);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const [newSkill, setNewSkill] = useState('');
  const [newProjectName, setNewProjectName] = useState('');
  const [newProjectTech, setNewProjectTech] = useState('');
  const [newProjectDesc, setNewProjectDesc] = useState('');

  useEffect(() => {
    api
      .getProfile()
      .then((p) => setProfile({ ...EMPTY_PROFILE, ...p }))
      .catch(() => {
        // Profile not created yet - keep empty
      })
      .finally(() => setLoading(false));
  }, []);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setStatusMsg(null);
    setErrorMsg(null);
    try {
      const saved = await api.saveProfile(profile);
      setProfile({ ...EMPTY_PROFILE, ...saved });
      setUncertainFields([]);
      setStatusMsg('Profile saved and candidate embedding updated.');
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to save profile');
    } finally {
      setSaving(false);
    }
  };

  const handleResumeUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setStatusMsg(null);
    setErrorMsg(null);
    try {
      const res = await api.uploadResume(file);
      setProfile({ ...EMPTY_PROFILE, ...res.extracted_profile });
      setUncertainFields(res.uncertain_fields || []);
      setStatusMsg(`Extracted from ${res.filename}. Review the fields below and click Save Profile.`);
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : 'Resume extraction failed');
    } finally {
      setUploading(false);
    }
  };

  const addSkill = () => {
    const name = newSkill.trim();
    if (!name) return;
    if (profile.skills.some((s) => s.name.toLowerCase() === name.toLowerCase())) return;
    setProfile((p) => ({ ...p, skills: [...p.skills, { name, proficiency: 'intermediate' }] }));
    setNewSkill('');
  };

  const addProject = () => {
    if (!newProjectName.trim()) return;
    const techs = newProjectTech.split(',').map((t) => t.trim()).filter(Boolean);
    setProfile((p) => ({
      ...p,
      projects: [
        ...p.projects,
        { name: newProjectName.trim(), description: newProjectDesc.trim() || null, technologies: techs },
      ],
    }));
    setNewProjectName('');
    setNewProjectTech('');
    setNewProjectDesc('');
  };

  if (loading) return <div className="text-sm text-slate-600">Loading profile...</div>;

  return (
    <div className="max-w-4xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">Candidate Profile</h1>
        <p className="text-sm text-slate-600 mt-1">
          The Evidence Engine only cites skills, projects, and experience stored here.
        </p>
      </div>

      {/* Resume Upload */}
      <section className="bg-white border border-slate-200 rounded-md p-5 space-y-3">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-slate-900">Import from Resume</h2>
            <p className="text-xs text-slate-500">
              Supports PDF, DOCX, and TXT (max 10 MB). Extracted fields require your confirmation before saving.
            </p>
          </div>
          <label className="inline-flex items-center gap-2 px-4 py-2 text-xs font-medium bg-slate-900 text-white rounded cursor-pointer hover:bg-slate-800">
            <Upload className="h-4 w-4" />
            {uploading ? 'Extracting...' : 'Upload Resume'}
            <input type="file" accept=".pdf,.docx,.txt" onChange={handleResumeUpload} className="sr-only" />
          </label>
        </div>

        {uncertainFields.length > 0 && (
          <div className="bg-amber-50 border border-amber-200 rounded p-3 text-xs text-amber-900 flex items-start gap-2">
            <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
            <div>
              <span className="font-medium">Uncertain extracted fields:</span> {uncertainFields.join(', ')}.
              Please verify these before saving.
            </div>
          </div>
        )}
      </section>

      {statusMsg && (
        <div className="bg-emerald-50 border border-emerald-200 text-emerald-900 rounded p-3.5 text-sm flex items-center gap-2">
          <CheckCircle2 className="h-4 w-4 shrink-0" />
          {statusMsg}
        </div>
      )}

      {errorMsg && (
        <div className="bg-rose-50 border border-rose-200 text-rose-800 rounded p-3.5 text-sm">
          {errorMsg}
        </div>
      )}

      <form onSubmit={handleSave} className="space-y-6">
        <section className="bg-white border border-slate-200 rounded-md p-5 space-y-4">
          <h2 className="text-sm font-semibold text-slate-900">Basic Details & Preferences</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs text-slate-600 mb-1">Full Name</label>
              <input
                type="text"
                value={profile.full_name || ''}
                onChange={(e) => setProfile({ ...profile, full_name: e.target.value })}
                className="w-full px-3 py-2 text-sm border border-slate-300 rounded"
              />
            </div>
            <div>
              <label className="block text-xs text-slate-600 mb-1">Email</label>
              <input
                type="email"
                value={profile.email || ''}
                onChange={(e) => setProfile({ ...profile, email: e.target.value })}
                className="w-full px-3 py-2 text-sm border border-slate-300 rounded"
              />
            </div>
            <div>
              <label className="block text-xs text-slate-600 mb-1">Location</label>
              <input
                type="text"
                value={profile.location || ''}
                onChange={(e) => setProfile({ ...profile, location: e.target.value })}
                placeholder="e.g. Bengaluru, India"
                className="w-full px-3 py-2 text-sm border border-slate-300 rounded"
              />
            </div>
            <div>
              <label className="block text-xs text-slate-600 mb-1">Experience Level</label>
              <select
                value={profile.experience_level || 'entry'}
                onChange={(e) => setProfile({ ...profile, experience_level: e.target.value })}
                className="w-full px-3 py-2 text-sm border border-slate-300 rounded bg-white"
              >
                <option value="internship">Internship</option>
                <option value="entry">Entry</option>
                <option value="mid">Mid</option>
                <option value="senior">Senior</option>
                <option value="lead">Lead</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-slate-600 mb-1">Workplace Preference</label>
              <select
                value={profile.remote_preference || 'flexible'}
                onChange={(e) => setProfile({ ...profile, remote_preference: e.target.value })}
                className="w-full px-3 py-2 text-sm border border-slate-300 rounded bg-white"
              >
                <option value="remote">Remote</option>
                <option value="hybrid">Hybrid</option>
                <option value="on_site">On-site</option>
                <option value="flexible">Flexible</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-slate-600 mb-1">Target Roles (comma-separated)</label>
              <input
                type="text"
                value={(profile.target_roles || []).join(', ')}
                onChange={(e) =>
                  setProfile({
                    ...profile,
                    target_roles: e.target.value.split(',').map((s) => s.trim()).filter(Boolean),
                  })
                }
                placeholder="ML Engineer, Data Scientist"
                className="w-full px-3 py-2 text-sm border border-slate-300 rounded"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs text-slate-600 mb-1">Summary</label>
            <textarea
              rows={3}
              value={profile.summary || ''}
              onChange={(e) => setProfile({ ...profile, summary: e.target.value })}
              className="w-full px-3 py-2 text-sm border border-slate-300 rounded"
            />
          </div>
        </section>

        {/* Skills */}
        <section className="bg-white border border-slate-200 rounded-md p-5 space-y-4">
          <h2 className="text-sm font-semibold text-slate-900">Skills</h2>
          <div className="flex gap-2">
            <input
              type="text"
              value={newSkill}
              onChange={(e) => setNewSkill(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  addSkill();
                }
              }}
              placeholder="Add skill (e.g. Python, SQL, FastAPI)"
              className="flex-1 px-3 py-2 text-sm border border-slate-300 rounded"
            />
            <button
              type="button"
              onClick={addSkill}
              className="inline-flex items-center gap-1 px-3.5 py-2 text-sm font-medium border border-slate-300 rounded hover:bg-slate-50"
            >
              <Plus className="h-4 w-4" />
              Add
            </button>
          </div>
          <div className="flex flex-wrap gap-2">
            {profile.skills.map((skill, idx) => (
              <span
                key={`${skill.name}-${idx}`}
                className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs bg-stone-100 border border-slate-200 rounded"
              >
                {skill.name}
                <button
                  type="button"
                  onClick={() =>
                    setProfile((p) => ({ ...p, skills: p.skills.filter((_, i) => i !== idx) }))
                  }
                  className="text-slate-400 hover:text-rose-700"
                  aria-label={`Remove ${skill.name}`}
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              </span>
            ))}
          </div>
        </section>

        {/* Projects */}
        <section className="bg-white border border-slate-200 rounded-md p-5 space-y-4">
          <h2 className="text-sm font-semibold text-slate-900">Projects (used for Evidence Engine)</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <input
              type="text"
              value={newProjectName}
              onChange={(e) => setNewProjectName(e.target.value)}
              placeholder="Project name (e.g. Phishing Detection)"
              className="px-3 py-2 text-sm border border-slate-300 rounded"
            />
            <input
              type="text"
              value={newProjectTech}
              onChange={(e) => setNewProjectTech(e.target.value)}
              placeholder="Technologies (e.g. Python, Flask, scikit-learn)"
              className="px-3 py-2 text-sm border border-slate-300 rounded"
            />
          </div>
          <div className="flex gap-2">
            <input
              type="text"
              value={newProjectDesc}
              onChange={(e) => setNewProjectDesc(e.target.value)}
              placeholder="Short description of what you built"
              className="flex-1 px-3 py-2 text-sm border border-slate-300 rounded"
            />
            <button
              type="button"
              onClick={addProject}
              className="inline-flex items-center gap-1 px-3.5 py-2 text-sm font-medium border border-slate-300 rounded hover:bg-slate-50"
            >
              <Plus className="h-4 w-4" />
              Add Project
            </button>
          </div>

          <div className="space-y-2">
            {profile.projects.map((proj, idx) => (
              <div key={`${proj.name}-${idx}`} className="border border-slate-200 rounded p-3 flex items-start justify-between gap-3">
                <div>
                  <div className="text-sm font-medium text-slate-900">{proj.name}</div>
                  {proj.description && <p className="text-xs text-slate-600 mt-0.5">{proj.description}</p>}
                  {proj.technologies.length > 0 && (
                    <div className="text-xs font-mono text-slate-500 mt-1">{proj.technologies.join(', ')}</div>
                  )}
                </div>
                <button
                  type="button"
                  onClick={() =>
                    setProfile((p) => ({ ...p, projects: p.projects.filter((_, i) => i !== idx) }))
                  }
                  className="text-slate-400 hover:text-rose-700"
                  aria-label={`Remove ${proj.name}`}
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            ))}
          </div>
        </section>

        <div className="flex justify-end">
          <button
            type="submit"
            disabled={saving}
            className="inline-flex items-center gap-2 px-5 py-2.5 bg-slate-900 text-white text-sm font-medium rounded hover:bg-slate-800 disabled:opacity-50"
          >
            <Save className="h-4 w-4" />
            {saving ? 'Saving...' : 'Save Profile'}
          </button>
        </div>
      </form>
    </div>
  );
};
