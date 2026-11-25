import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { Layout } from './components/Layout';
import { DashboardPage } from './pages/DashboardPage';
import { SearchJobsPage } from './pages/SearchJobsPage';
import { JobDetailsPage } from './pages/JobDetailsPage';
import { AgentChatPage } from './pages/AgentChatPage';
import { ProfilePage } from './pages/ProfilePage';
import { SkillGapsPage } from './pages/SkillGapsPage';
import { SavedJobsPage } from './pages/SavedJobsPage';
import { SearchHistoryPage } from './pages/SearchHistoryPage';
import { EvaluationPage } from './pages/EvaluationPage';
import { PrivacyPolicyPage, TermsPage } from './pages/LegalPages';

export function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/search" element={<SearchJobsPage />} />
          <Route path="/jobs/:jobId" element={<JobDetailsPage />} />
          <Route path="/agent" element={<AgentChatPage />} />
          <Route path="/profile" element={<ProfilePage />} />
          <Route path="/skill-gaps" element={<SkillGapsPage />} />
          <Route path="/saved" element={<SavedJobsPage />} />
          <Route path="/history" element={<SearchHistoryPage />} />
          <Route path="/evaluation" element={<EvaluationPage />} />
          <Route path="/privacy" element={<PrivacyPolicyPage />} />
          <Route path="/terms" element={<TermsPage />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  );
}

export default App;
