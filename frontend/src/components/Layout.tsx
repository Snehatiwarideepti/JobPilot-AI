import React, { useState } from 'react';
import { NavLink, Link } from 'react-router-dom';
import {
  Briefcase,
  Search,
  MessageSquare,
  User,
  BarChart3,
  Bookmark,
  History,
  FlaskConical,
  Menu,
  X,
  Compass,
} from 'lucide-react';

const NAV_ITEMS = [
  { to: '/', label: 'Overview', icon: Compass },
  { to: '/search', label: 'Search Jobs', icon: Search },
  { to: '/agent', label: 'AI Agent', icon: MessageSquare },
  { to: '/profile', label: 'My Profile', icon: User },
  { to: '/skill-gaps', label: 'Skill Gaps', icon: BarChart3 },
  { to: '/saved', label: 'Saved Jobs', icon: Bookmark },
  { to: '/history', label: 'Search History', icon: History },
  { to: '/evaluation', label: 'Evaluation', icon: FlaskConical },
];

export const Layout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  return (
    <div className="min-h-screen flex flex-col bg-stone-50 text-slate-900">
      <header className="sticky top-0 z-30 bg-white border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2.5 focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-700 rounded">
            <span className="inline-flex h-8 w-8 items-center justify-center rounded bg-slate-900 text-white">
              <Briefcase className="h-4 w-4" />
            </span>
            <div className="leading-tight">
              <span className="font-semibold tracking-tight text-slate-900 text-base">JobPilot AI</span>
              <span className="hidden sm:inline-block ml-2 text-xs text-slate-500 font-normal">
                Search less. Match smarter.
              </span>
            </div>
          </Link>

          <nav className="hidden lg:flex items-center gap-1" aria-label="Main navigation">
            {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                end={to === '/'}
                className={({ isActive }) =>
                  `inline-flex items-center gap-1.5 px-3 py-1.5 rounded text-sm font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-700 ${
                    isActive
                      ? 'bg-slate-900 text-white'
                      : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
                  }`
                }
              >
                <Icon className="h-4 w-4" />
                {label}
              </NavLink>
            ))}
          </nav>

          <button
            type="button"
            onClick={() => setMobileMenuOpen((v) => !v)}
            className="lg:hidden p-2 rounded text-slate-600 hover:bg-slate-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-700"
            aria-label="Toggle navigation menu"
            aria-expanded={mobileMenuOpen}
          >
            {mobileMenuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>

        {mobileMenuOpen && (
          <nav className="lg:hidden border-t border-slate-200 bg-white px-4 py-3 space-y-1" aria-label="Mobile navigation">
            {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                end={to === '/'}
                onClick={() => setMobileMenuOpen(false)}
                className={({ isActive }) =>
                  `flex items-center gap-2.5 px-3 py-2 rounded text-sm font-medium ${
                    isActive ? 'bg-slate-900 text-white' : 'text-slate-700 hover:bg-slate-100'
                  }`
                }
              >
                <Icon className="h-4 w-4" />
                {label}
              </NavLink>
            ))}
          </nav>
        )}
      </header>

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {children}
      </main>

      <footer className="border-t border-slate-200 bg-white py-6 mt-12">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 text-xs text-slate-500">
          <div>
            <span className="font-medium text-slate-700">JobPilot AI</span> · Explainable Career Matching · Live job data sourced via Jobvetta API.
          </div>
          <div className="flex items-center gap-5">
            <Link to="/privacy" className="hover:text-slate-900 underline underline-offset-2">
              Privacy Policy
            </Link>
            <Link to="/terms" className="hover:text-slate-900 underline underline-offset-2">
              Terms and Conditions
            </Link>
          </div>
        </div>
      </footer>
    </div>
  );
};
