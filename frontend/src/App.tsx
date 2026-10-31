import React, { FormEvent, useEffect, useMemo, useState } from 'react';
import './style.css';

type User = { id: string; email: string; display_name: string; role: string };
type Course = { id: string; name: string; role: 'owner' | 'member'; created_at?: string };
type CourseDetail = { id: string; name: string; role: 'owner' | 'member'; created_at: string };

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

let csrfToken = '';
async function api<T>(path: string, options: { method?: string; body?: unknown } = {}): Promise<T> {
  const method = options.method ?? 'GET';
  if (method !== 'GET' && !csrfToken) {
    const csrfResponse = await fetch('/api/auth/csrf', { credentials: 'same-origin' });
    if (!csrfResponse.ok) throw new Error('Could not initialize a secure session. Refresh and try again.');
    const csrfData = (await csrfResponse.json()) as { csrf_token: string };
    csrfToken = csrfData.csrf_token;
  }
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (options.body !== undefined) headers['Content-Type'] = 'application/json';
  if (method !== 'GET') headers['X-CSRF-Token'] = csrfToken;
  const response = await fetch(path, {
    method,
    credentials: 'same-origin',
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });
  const data = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) {
    const message = typeof data?.detail === 'string' ? data.detail : 'Something went wrong. Please try again.';
    throw new ApiError(response.status, message);
  }
  return data as T;
}

function Icon({ name, size = 18 }: { name: 'book' | 'plus' | 'arrow' | 'users' | 'moon' | 'sun' | 'shield' | 'spark' | 'copy' | 'back'; size?: number }) {
  const common = { width: size, height: size, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.7, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const, 'aria-hidden': true as const };
  const paths: Record<string, React.ReactNode> = {
    book: <><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v16H6.5A2.5 2.5 0 0 0 4 21.5z"/><path d="M4 5.5v16M8 7h8M8 11h7"/><path d="m13 16 2 2 5-6"/></>,
    plus: <><path d="M12 5v14M5 12h14"/></>,
    arrow: <><path d="M5 12h14M13 6l6 6-6 6"/></>,
    users: <><path d="M16 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="10" cy="7" r="4"/><path d="M20 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/></>,
    moon: <><path d="M20.9 13A9 9 0 0 1 11 3.1 9 9 0 1 0 20.9 13Z"/></>,
    sun: <><circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M4.93 4.93l1.42 1.42m11.3 11.3 1.42 1.42M2 12h2m16 0h2M4.93 19.07l1.42-1.42m11.3-11.3 1.42-1.42"/></>,
    shield: <><path d="M12 22s8-4 8-11V5l-8-3-8 3v6c0 7 8 11 8 11Z"/><path d="m9 12 2 2 4-4"/></>,
    spark: <><path d="m12 3 1.9 5.8L20 11l-6.1 2.2L12 19l-1.9-5.8L4 11l6.1-2.2z"/><path d="m19 14 1.2 2.8L23 18l-2.8 1.2L19 22l-1.2-2.8L15 18l2.8-1.2z"/></>,
    copy: <><rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/></>,
    back: <><path d="M19 12H5m7 7-7-7 7-7"/></>,
  };
  return <svg {...common}>{paths[name]}</svg>;
}

function Brand({ compact = false }: { compact?: boolean }) {
  return <div className={`brand ${compact ? 'brand-compact' : ''}`}>
    <span className="brand-mark"><Icon name="book" size={21} /></span>
    <span className="brand-name">Study<span>RAG</span></span>
  </div>;
}

function Field({ label, type = 'text', value, onChange, autoComplete, required = true, minLength, placeholder }: {
  label: string; type?: string; value: string; onChange: (value: string) => void; autoComplete?: string; required?: boolean; minLength?: number; placeholder?: string;
}) {
  const id = `field-${label.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`;
  return <label className="field" htmlFor={id}>
    <span>{label}</span>
    <input id={id} type={type} value={value} onChange={(event) => onChange(event.target.value)} autoComplete={autoComplete} required={required} minLength={minLength} placeholder={placeholder} />
  </label>;
}

function AuthPage({ onAuthenticated, notice, resetToken, onClearReset, invitePending }: {
  onAuthenticated: (user: User) => Promise<void>; notice: string; resetToken: string | null; onClearReset: () => void; invitePending: boolean;
}) {
  const [mode, setMode] = useState<'login' | 'signup' | 'forgot' | 'reset'>(resetToken ? 'reset' : 'login');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState(notice);
  const [googleEnabled, setGoogleEnabled] = useState(false);
  const [googleBusy, setGoogleBusy] = useState(false);

  useEffect(() => setMessage(notice), [notice]);
  useEffect(() => { if (resetToken) setMode('reset'); }, [resetToken]);
  useEffect(() => { void api<{ google: boolean }>('/api/auth/providers').then((providers) => setGoogleEnabled(providers.google)).catch(() => setGoogleEnabled(false)); }, []);

  const startGoogle = async () => {
    setGoogleBusy(true);
    setError('');
    try {
      const result = await api<{ authorization_url: string }>('/api/auth/google/start', { method: 'POST' });
      window.location.assign(result.authorization_url);
    } catch (caught) {
      setError((caught as Error).message || 'Google sign-in could not start.');
      setGoogleBusy(false);
    }
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setBusy(true);
    setError('');
    setMessage('');
    try {
      if (mode === 'signup') {
        const result = await api<{ message: string }>('/api/auth/signup', { method: 'POST', body: { display_name: name, email, password } });
        setMessage(result.message);
      } else if (mode === 'login') {
        await api<{ message: string }>('/api/auth/login', { method: 'POST', body: { email, password } });
        const user = await api<User>('/api/auth/me');
        await onAuthenticated(user);
      } else if (mode === 'forgot') {
        const result = await api<{ message: string }>('/api/auth/password/forgot', { method: 'POST', body: { email } });
        setMessage(result.message);
      } else if (mode === 'reset' && resetToken) {
        const result = await api<{ message: string }>('/api/auth/password/reset', { method: 'POST', body: { token: resetToken, password } });
        setMessage(result.message);
        onClearReset();
        setMode('login');
        setPassword('');
      }
    } catch (caught) {
      const apiError = caught as ApiError;
      setError(apiError.message || 'Please try again.');
      if (apiError.status === 403 && apiError.message.toLowerCase().includes('verify')) {
        setMessage('Need a fresh link? Request another below.');
      }
    } finally {
      setBusy(false);
    }
  };

  const resend = async () => {
    if (!email) { setError('Enter your email address first.'); return; }
    setBusy(true); setError('');
    try {
      const result = await api<{ message: string }>('/api/auth/verification/resend', { method: 'POST', body: { email } });
      setMessage(result.message);
    } catch (caught) { setError((caught as Error).message); }
    finally { setBusy(false); }
  };

  const title = mode === 'signup' ? 'Make room for better study.' : mode === 'forgot' ? 'Reset your password.' : mode === 'reset' ? 'Choose a new password.' : 'Study from what you have.';
  const subtitle = mode === 'signup' ? 'Create an account to start a private course workspace.' : mode === 'forgot' ? 'We’ll send a one-time reset link if your account is verified.' : mode === 'reset' ? 'Use at least 12 characters.' : 'Answers grounded in your course material, not the open web.';

  return <main className="auth-shell">
    <section className="auth-story">
      <div className="story-top"><Brand /></div>
      <div className="story-content">
        <p className="eyebrow"><span className="eyebrow-line" /> YOUR MATERIAL. YOUR SOURCE OF TRUTH.</p>
        <h1>Find the answer<br /><em>in your notes.</em></h1>
        <p className="story-lede">A quieter way to study. Bring your course materials together and keep every answer close to its source.</p>
        <div className="story-proof"><span className="proof-icon"><Icon name="shield" size={19} /></span><span><strong>Evidence stays visible.</strong><br />Course spaces are private to their members.</span></div>
      </div>
      <div className="story-footer"><span>Built for the way students actually study.</span><span className="footer-index">FIELD NOTE&nbsp; / &nbsp;01</span></div>
      <div className="story-orbit orbit-a" /><div className="story-orbit orbit-b" />
    </section>
    <section className="auth-panel">
      <div className="auth-topline"><span>COURSE-AWARE STUDY ASSISTANT</span><a href="/privacy">Privacy</a></div>
      <div className="auth-card">
        <p className="auth-kicker">{mode === 'signup' ? 'A workspace for every course' : mode === 'forgot' || mode === 'reset' ? 'Account recovery' : 'Welcome back to your desk'}</p>
        <h2>{title}</h2>
        <p className="auth-subtitle">{subtitle}</p>
        {invitePending && <div className="notice invite-notice"><Icon name="users" size={17} /> Sign in or create an account to join the shared course.</div>}
        {message && <div className="notice" role="status">{message}</div>}
        {error && <div className="error-box" role="alert">{error}</div>}
        <form onSubmit={submit} className="auth-form">
          {mode === 'signup' && <Field label="Your name" value={name} onChange={setName} autoComplete="name" placeholder="Name as it appears in class" />}
          {mode !== 'reset' && <Field label="University email" type="email" value={email} onChange={setEmail} autoComplete={mode === 'signup' ? 'email' : 'username'} placeholder="you@university.edu" />}
          {mode !== 'forgot' && <Field label={mode === 'reset' ? 'New password' : 'Password'} type="password" value={password} onChange={setPassword} autoComplete={mode === 'signup' || mode === 'reset' ? 'new-password' : 'current-password'} minLength={mode === 'signup' || mode === 'reset' ? 12 : undefined} placeholder={mode === 'signup' || mode === 'reset' ? 'At least 12 characters' : 'Your password'} />}
          {mode === 'login' && <button type="button" className="text-button forgot-link" onClick={() => { setMode('forgot'); setError(''); setMessage(''); }}>Forgot password?</button>}
          <button className="primary-button auth-submit" type="submit" disabled={busy}>{busy ? 'Please wait…' : mode === 'signup' ? 'Create account' : mode === 'forgot' ? 'Send reset link' : mode === 'reset' ? 'Save new password' : 'Sign in'} <Icon name="arrow" size={17} /></button>
        </form>
        {googleEnabled && (mode === 'login' || mode === 'signup') && <button type="button" className="google-button" onClick={() => void startGoogle()} disabled={busy || googleBusy}><span className="google-g" aria-hidden="true">G</span>{googleBusy ? 'Connecting…' : 'Continue with Google'}</button>}
        {mode === 'login' && error.toLowerCase().includes('verify') && <button className="text-button resend-button" onClick={resend} disabled={busy}>Resend verification email</button>}
        {mode === 'forgot' || mode === 'reset' ? <button className="back-link" onClick={() => { setMode('login'); setError(''); setMessage(''); if (mode === 'reset') onClearReset(); }}><Icon name="back" size={16} /> Back to sign in</button> : <div className="auth-switch">{mode === 'signup' ? 'Already have an account?' : 'New to StudyRAG?'} <button className="text-button" onClick={() => { setMode(mode === 'signup' ? 'login' : 'signup'); setError(''); setMessage(''); }}>{mode === 'signup' ? 'Sign in' : 'Create an account'}</button></div>}
        <div className="auth-divider"><span>DESIGNED AROUND YOUR SOURCES</span></div>
        <p className="auth-footnote">No sample courses or pre-filled answers. Your space starts with what you add.</p>
      </div>
      <div className="auth-bottom"><span>StudyRAG</span><span>One course at a time.</span></div>
    </section>
  </main>;
}

function PrivacyPage({ onBack }: { onBack: () => void }) {
  return <main className="privacy-page">
    <header className="privacy-header"><Brand /><button className="back-link" onClick={onBack}><Icon name="back" size={16} /> Back</button></header>
    <article className="privacy-copy">
      <p className="eyebrow"><span className="eyebrow-line" /> PLAIN-LANGUAGE PRIVACY</p>
      <h1>Your course material<br /><em>stays yours.</em></h1>
      <p className="privacy-intro">StudyRAG is designed to answer from material you choose to bring into your course workspaces.</p>
      <section><h2>Course material</h2><p>Uploaded course files are processed to answer questions from the course spaces you are authorized to access. They are not used as public content. Only you and people you deliberately admit to a shared course should be able to retrieve material from that course.</p></section>
      <section><h2>Your account</h2><p>Your email address and account details support sign-in, verification, password recovery, and course membership. Verification and recovery links are time-limited and single-use.</p></section>
      <section><h2>External services</h2><p>StudyRAG requires configured infrastructure to store course data, deliver account email, and—when the study assistant is enabled—process search and answer requests. The operator must configure these services before those features are available. Do not upload sensitive material unless you are comfortable with your institution’s and service providers’ policies.</p></section>
      <section><h2>Your choices</h2><p>Account deletion and complete data export are planned for a later delivery stage. They are not available in this initial workspace release; contact the operator before relying on StudyRAG as the only copy of any material.</p></section>
      <p className="privacy-updated">Privacy information for the current Stage 1 release.</p>
    </article>
  </main>;
}

function App() {
  const [user, setUser] = useState<User | null>(null);
  const [courses, setCourses] = useState<Course[]>([]);
  const [selected, setSelected] = useState<CourseDetail | null>(null);
  const [booting, setBooting] = useState(true);
  const [privacy, setPrivacy] = useState(window.location.pathname === '/privacy');
  const [showCreate, setShowCreate] = useState(false);
  const [newCourse, setNewCourse] = useState('');
  const [creating, setCreating] = useState(false);
  const [inviteUrl, setInviteUrl] = useState('');
  const [inviteBusy, setInviteBusy] = useState(false);
  const [flash, setFlash] = useState('');
  const [authNotice, setAuthNotice] = useState('');
  const [resetToken, setResetToken] = useState<string | null>(null);
  const [inviteToken, setInviteToken] = useState<string | null>(null);
  const [dark, setDark] = useState(() => localStorage.getItem('studyrag-theme') === 'dark');

  const courseCountLabel = useMemo(() => `${courses.length} ${courses.length === 1 ? 'course' : 'courses'}`, [courses.length]);

  const fetchCourses = async () => {
    const result = await api<Course[]>('/api/courses');
    setCourses(result);
    return result;
  };

  const acceptPendingInvite = async (activeUser: User) => {
    const token = inviteToken || sessionStorage.getItem('studyrag-pending-invite');
    if (!token) return;
    try {
      const joined = await api<{ course_id: string; course_name: string; role: string }>('/api/invites/accept', { method: 'POST', body: { token } });
      sessionStorage.removeItem('studyrag-pending-invite');
      setInviteToken(null);
      setFlash(`You joined ${joined.course_name}.`);
      const updated = await fetchCourses();
      const course = updated.find((item) => item.id === joined.course_id);
      if (course) await openCourse(course.id, false);
    } catch (caught) {
      setFlash((caught as Error).message || 'This invite link is no longer available.');
      sessionStorage.removeItem('studyrag-pending-invite');
      setInviteToken(null);
    }
    void activeUser;
  };

  const openCourse = async (id: string, push = true) => {
    try {
      const detail = await api<CourseDetail>(`/api/courses/${id}`);
      setSelected(detail);
      setPrivacy(false);
      if (push) window.history.pushState({}, '', `/courses/${encodeURIComponent(id)}`);
    } catch (caught) {
      setFlash((caught as Error).message);
      setSelected(null);
      window.history.pushState({}, '', '/');
    }
  };

  useEffect(() => {
    let live = true;
    const initialize = async () => {
      const rawHash = window.location.hash.replace(/^#/, '');
      const params = new URLSearchParams(rawHash);
      const verify = params.get('verify');
      const reset = params.get('reset');
      const invite = params.get('invite');
      const oauth = params.get('oauth');
      if (verify || reset || invite || oauth) window.history.replaceState({}, '', window.location.pathname + window.location.search);
      if (oauth === 'error') setAuthNotice('Google sign-in could not be completed. Please try again.');
      if (oauth === 'cancelled') setAuthNotice('Google sign-in was cancelled.');
      if (oauth === 'success') setFlash('Signed in with Google.');
      if (reset) setResetToken(reset);
      if (invite) {
        sessionStorage.setItem('studyrag-pending-invite', invite);
        setInviteToken(invite);
      } else if (sessionStorage.getItem('studyrag-pending-invite')) {
        setInviteToken(sessionStorage.getItem('studyrag-pending-invite'));
      }
      try {
        const readiness = await fetch('/api/health/ready', { credentials: 'same-origin' });
        if (!readiness.ok) {
          const serviceError = await readiness.json().catch(() => null);
          if (live) setAuthNotice(typeof serviceError?.detail === 'string' ? serviceError.detail : 'The course database is temporarily unreachable. Please try again shortly.');
          return;
        }
        const csrf = await fetch('/api/auth/csrf', { credentials: 'same-origin' });
        if (csrf.ok) csrfToken = ((await csrf.json()) as { csrf_token: string }).csrf_token;
        if (verify) {
          try {
            const result = await api<{ message: string }>('/api/auth/verify', { method: 'POST', body: { token: verify } });
            setAuthNotice(result.message);
          } catch (caught) { setAuthNotice((caught as Error).message); }
        }
        const current = await api<User>('/api/auth/me');
        if (!live) return;
        setUser(current);
        const loaded = await fetchCourses();
        if (!live) return;
        const pathId = window.location.pathname.match(/^\/courses\/([^/]+)$/)?.[1];
        if (pathId) {
          const id = decodeURIComponent(pathId);
          if (loaded.some((item) => item.id === id)) await openCourse(id, false);
        }
        await acceptPendingInvite(current);
      } catch (caught) {
        if (live) {
          setUser(null);
          if (caught instanceof ApiError && caught.status === 503) setAuthNotice(caught.message);
        }
      } finally {
        if (live) setBooting(false);
      }
    };
    void initialize();
    const onPop = () => {
      setPrivacy(window.location.pathname === '/privacy');
      const pathId = window.location.pathname.match(/^\/courses\/([^/]+)$/)?.[1];
      if (pathId) void openCourse(decodeURIComponent(pathId), false);
      else setSelected(null);
    };
    window.addEventListener('popstate', onPop);
    return () => { live = false; window.removeEventListener('popstate', onPop); };
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = dark ? 'dark' : 'light';
    localStorage.setItem('studyrag-theme', dark ? 'dark' : 'light');
  }, [dark]);

  const authenticated = async (activeUser: User) => {
    setUser(activeUser);
    await fetchCourses();
    await acceptPendingInvite(activeUser);
  };

  const createCourse = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!newCourse.trim()) return;
    setCreating(true);
    try {
      const created = await api<Course>('/api/courses', { method: 'POST', body: { name: newCourse } });
      setNewCourse(''); setShowCreate(false); setFlash('Course workspace created.');
      await fetchCourses();
      await openCourse(created.id);
    } catch (caught) { setFlash((caught as Error).message); }
    finally { setCreating(false); }
  };

  const makeInvite = async () => {
    if (!selected) return;
    setInviteBusy(true);
    try {
      const result = await api<{ invite_url: string; expires_at: string }>(`/api/courses/${selected.id}/invites`, { method: 'POST' });
      setInviteUrl(result.invite_url);
      setFlash('Invite link created. It expires in seven days and can be used once.');
    } catch (caught) { setFlash((caught as Error).message); }
    finally { setInviteBusy(false); }
  };

  const logout = async () => {
    try { await api('/api/auth/logout', { method: 'POST' }); } catch { /* End the local view even if the network is unavailable. */ }
    setUser(null); setCourses([]); setSelected(null); setInviteUrl(''); setFlash(''); window.history.pushState({}, '', '/');
  };

  if (privacy) return <PrivacyPage onBack={() => { setPrivacy(false); window.history.pushState({}, '', '/'); }} />;
  if (booting) return <div className="boot-screen"><Brand /><span>Opening your study space…</span></div>;
  if (!user) return <AuthPage onAuthenticated={authenticated} notice={authNotice} resetToken={resetToken} onClearReset={() => setResetToken(null)} invitePending={Boolean(inviteToken || sessionStorage.getItem('studyrag-pending-invite'))} />;

  return <div className="workspace-shell">
    <aside className="sidebar">
      <div className="sidebar-brand"><Brand /></div>
      <div className="sidebar-label">YOUR WORKSPACE</div>
      <button className={`nav-item ${!selected ? 'active' : ''}`} onClick={() => { setSelected(null); window.history.pushState({}, '', '/'); }}><span className="nav-icon"><Icon name="book" /></span> All courses <span className="nav-count">{courses.length}</span></button>
      <div className="sidebar-section-heading"><span>COURSES</span><button className="icon-button add-course-small" aria-label="Create course" onClick={() => setShowCreate(true)}><Icon name="plus" size={16} /></button></div>
      <div className="course-nav-list">
        {courses.map((course) => <button className={`course-nav ${selected?.id === course.id ? 'selected' : ''}`} key={course.id} onClick={() => void openCourse(course.id)}><span className="course-dot" /> <span className="course-nav-name">{course.name}</span>{course.role === 'member' && <span className="member-marker" title="Shared course"><Icon name="users" size={13} /></span>}</button>)}
        {courses.length === 0 && <p className="sidebar-empty">Your courses will appear here.</p>}
      </div>
      <button className="add-course-link" onClick={() => setShowCreate(true)}><Icon name="plus" size={16} /> New course</button>
      <div className="sidebar-spacer" />
      <div className="sidebar-bottom">
        <button className="nav-item subtle" onClick={() => { setPrivacy(true); window.history.pushState({}, '', '/privacy'); }}><span className="nav-icon"><Icon name="shield" /></span> Privacy</button>
        <div className="user-card"><div className="avatar">{user.display_name.slice(0, 1).toUpperCase()}</div><div className="user-info"><strong>{user.display_name}</strong><span>{user.email}</span></div><button className="icon-button theme-toggle" aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'} onClick={() => setDark(!dark)}><Icon name={dark ? 'sun' : 'moon'} size={17} /></button></div>
        <button className="logout-link" onClick={() => void logout()}>Sign out</button>
      </div>
    </aside>
    <main className="main-panel">
      <header className="topbar"><div className="breadcrumb"><span>StudyRAG</span><span className="crumb-sep">/</span><strong>{selected ? selected.name : 'Courses'}</strong></div><div className="topbar-right"><span className="private-pill"><span /> PRIVATE WORKSPACE</span><button className="mobile-theme icon-button" aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'} onClick={() => setDark(!dark)}><Icon name={dark ? 'sun' : 'moon'} size={17} /></button></div></header>
      <div className="content-area">
        {flash && <div className="flash-message" role="status"><span>{flash}</span><button aria-label="Dismiss" onClick={() => setFlash('')}>×</button></div>}
        {selected ? <section className="course-view">
          <div className="course-heading-row"><div><p className="eyebrow"><span className="eyebrow-line" /> COURSE WORKSPACE <span className="role-tag">{selected.role}</span></p><h1>{selected.name}</h1><p className="course-description">A shared place for your course material and study sessions.</p></div><div className="course-actions">{selected.role === 'owner' && <button className="secondary-button" onClick={() => void makeInvite()} disabled={inviteBusy}><Icon name="users" size={17} /> {inviteBusy ? 'Creating…' : 'Share course'}</button>}</div></div>
          {inviteUrl && <div className="invite-card"><div><strong>Invite link ready</strong><p>Anyone with this link can join once. It expires after seven days.</p><code>{inviteUrl}</code></div><button className="secondary-button compact" onClick={async () => { try { await navigator.clipboard.writeText(inviteUrl); setFlash('Invite link copied.'); } catch { setFlash('Copy unavailable. Select and copy the invite link.'); } }}><Icon name="copy" size={16} /> Copy link</button></div>}
          <div className="workspace-empty"><div className="empty-emblem"><Icon name="book" size={30} /></div><p className="eyebrow">A CLEAR PAGE, READY FOR CLASS</p><h2>This course space is ready.</h2><p>Course materials and study conversations will live here. You can invite a classmate now, or return when you’re ready to add course content.</p><div className="empty-note"><span className="note-line" /> Only course members can access this workspace.</div></div>
        </section> : <section className="course-overview">
          <div className="overview-heading"><div><p className="eyebrow"><span className="eyebrow-line" /> YOUR STUDY DESK</p><h1>Make space for<br /><em>what you’re learning.</em></h1><p className="overview-sub">Keep course materials organized, shared only with the people you choose.</p></div><button className="primary-button create-button" onClick={() => setShowCreate(true)}><Icon name="plus" size={17} /> Create a course</button></div>
          <div className="overview-meta"><span>{courseCountLabel}</span><span className="meta-rule" /><span>{courses.filter((course) => course.role === 'owner').length} owned</span><span className="meta-rule" /><span>{courses.filter((course) => course.role === 'member').length} shared with you</span></div>
          {courses.length === 0 ? <div className="courses-empty"><div className="empty-graphic"><div className="empty-page page-back" /><div className="empty-page page-front"><span /><span /><span /></div><span className="empty-plus"><Icon name="plus" size={15} /></span></div><h2>Your courses begin here.</h2><p>Create a private workspace for a class. You can share it with classmates when you’re ready.</p><button className="secondary-button" onClick={() => setShowCreate(true)}><Icon name="plus" size={16} /> Create your first course</button><span className="empty-caption">NO SAMPLE COURSES · YOUR ACTIVITY ONLY</span></div> : <div className="course-grid">{courses.map((course, index) => <button key={course.id} className="course-card" onClick={() => void openCourse(course.id)}><div className="card-top"><span className={`course-monogram tone-${index % 4}`}>{course.name.trim().charAt(0).toUpperCase()}</span><span className="course-role">{course.role === 'owner' ? 'OWNER' : 'SHARED'}</span></div><h2>{course.name}</h2><div className="card-bottom"><span>Open workspace</span><Icon name="arrow" size={17} /></div></button>)}</div>}
          <div className="overview-footnote"><Icon name="shield" size={16} /><span>Your courses are private by default. Shared spaces are limited to their members.</span></div>
        </section>}
      </div>
    </main>
    {showCreate && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setShowCreate(false); }}><section className="modal" role="dialog" aria-modal="true" aria-labelledby="create-title"><button className="modal-close icon-button" aria-label="Close" onClick={() => setShowCreate(false)}>×</button><span className="modal-mark"><Icon name="book" size={21} /></span><p className="eyebrow">NEW COURSE SPACE</p><h2 id="create-title">What are you studying?</h2><p>Start with a name you’ll recognize. You can share the course later.</p><form onSubmit={(event) => void createCourse(event)}><Field label="Course name" value={newCourse} onChange={setNewCourse} placeholder="e.g. Computer Networks" /><div className="modal-actions"><button type="button" className="secondary-button" onClick={() => setShowCreate(false)}>Cancel</button><button type="submit" className="primary-button" disabled={creating || !newCourse.trim()}>{creating ? 'Creating…' : 'Create course'} <Icon name="arrow" size={16} /></button></div></form></section></div>}
  </div>;
}

export default App;
