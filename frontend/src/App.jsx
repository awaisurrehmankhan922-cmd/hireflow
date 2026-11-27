import { useEffect, useState } from 'react'
import { api } from './api'
import Applicants from './pages/Applicants'
import Conversations from './pages/Conversations'
import Automation from './pages/Automation'
import Settings from './pages/Settings'
import AIConsole from './pages/AIConsole'

const TABS = [
  ['applicants', 'Applicants', Applicants],
  ['conversations', 'Conversations', Conversations],
  ['automation', 'Automation', Automation],
  ['settings', 'Settings', Settings],
  ['ai', 'AI Interface', AIConsole],
]

function Login({ onLogin }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [err, setErr] = useState('')
  const submit = async (e) => {
    e.preventDefault()
    try {
      await api.post('/auth/login', { email, password })
      onLogin()
    } catch (x) { setErr(x.message) }
  }
  return (
    <div className="login">
      <form onSubmit={submit} className="card">
        <div className="brand big">HireFlow<span>AI</span></div>
        <p className="muted">Recruitment &amp; communications console</p>
        <input placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} />
        <input placeholder="Password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
        {err && <div className="error">{err}</div>}
        <button className="primary">Sign in</button>
      </form>
    </div>
  )
}

export default function App() {
  const [me, setMe] = useState(undefined)
  const [tab, setTab] = useState(location.hash.slice(1) || 'applicants')
  const [navKey, setNavKey] = useState(0)
  const [stats, setStats] = useState(null)
  const [health, setHealth] = useState(null)

  const load = () => api.get('/auth/me').then(setMe).catch(() => setMe(null))
  useEffect(() => { load(); const h = () => setMe(null); window.addEventListener('hf:logout', h); return () => window.removeEventListener('hf:logout', h) }, [])
  useEffect(() => {
    if (!me) return
    const tick = () => { api.get('/stats').then(setStats).catch(() => {}); api.get('/health').then(setHealth).catch(() => {}) }
    tick(); const t = setInterval(tick, 15000); return () => clearInterval(t)
  }, [me, tab])
  useEffect(() => { location.hash = tab }, [tab])

  if (me === undefined) return null
  if (!me) return <Login onLogin={load} />
  const Page = TABS.find((t) => t[0] === tab)?.[2] || Applicants

  return (
    <div className="shell">
      <aside>
        <div className="brand">HireFlow<span>AI</span></div>
        <nav>
          {TABS.map(([id, label]) => (
            <button key={id} className={tab === id ? 'active' : ''} onClick={() => { setTab(id); setNavKey((k) => k + 1) }}>
              {label}
              {id === 'conversations' && stats && stats.drafts + stats.escalated > 0 && <em>{stats.drafts + stats.escalated}</em>}
            </button>
          ))}
        </nav>
        <div className="status">
          <div><i className={health?.database ? 'ok' : 'bad'} /> Database</div>
          <div><i className={health?.llm ? 'ok' : 'bad'} /> AI ({health?.llm_provider || '…'})</div>
          <div className="muted small">{me.email}</div>
          <button className="link" onClick={() => api.post('/auth/logout').then(() => setMe(null))}>Sign out</button>
        </div>
      </aside>
      <main>
        {stats && tab !== 'ai' && (
          <div className="kpis">
            <div><b>{stats.applicants}</b>Applicants</div>
            <div><b>{stats.pending_ai}</b>Waiting for AI</div>
            <div><b>{stats.needs_review}</b>Needs review</div>
            <div><b>{stats.drafts}</b>Drafts to approve</div>
            <div><b>{stats.escalated}</b>Escalated</div>
            <div className={stats.failed_deliveries ? 'warn' : ''}><b>{stats.failed_deliveries}</b>Failed sends</div>
          </div>
        )}
        <Page key={`${tab}-${navKey}`} />
      </main>
    </div>
  )
}
