import { useEffect, useState } from 'react'
import { api, fmt } from '../api'

export default function Settings() {
  const [s, setS] = useState(null)
  const [kb, setKb] = useState([])
  const [admins, setAdmins] = useState([])
  const [audit, setAudit] = useState([])
  const load = () => {
    api.get('/settings').then(setS); api.get('/knowledge').then(setKb)
    api.get('/admins').then(setAdmins); api.get('/audit?limit=25').then(setAudit)
  }
  useEffect(() => { load() }, [])
  if (!s) return null
  const rt = s.runtime
  const save = (patch) => api.put('/settings', patch).then(load)

  return (
    <section>
      <h1>Settings</h1>
      <div className="grid2">
        <div className="card">
          <h3>AI configuration</h3>
          <p className="muted small">Provider: <b>{s.llm.provider}</b> · model <b>{s.llm.model}</b> (set in server .env)</p>
          <label>Company name<input defaultValue={rt.company_name} onBlur={(e) => save({ company_name: e.target.value })} /></label>
          <label>Escalate below confidence ({rt.confidence_threshold})
            <input type="range" min="0.3" max="0.95" step="0.05" defaultValue={rt.confidence_threshold} onMouseUp={(e) => save({ confidence_threshold: +e.target.value })} /></label>
          <label>Extra instructions for the assistant<textarea rows="3" defaultValue={rt.system_prompt_extra} onBlur={(e) => save({ system_prompt_extra: e.target.value })} /></label>
          <label>Acknowledgment subject<input defaultValue={rt.ack_subject} onBlur={(e) => save({ ack_subject: e.target.value })} /></label>
          <label>Acknowledgment template <span className="muted small">{'{first_name} {position} {company}'}</span><textarea rows="6" defaultValue={rt.ack_template} onBlur={(e) => save({ ack_template: e.target.value })} /></label>
        </div>
        <div>
          <div className="card">
            <h3>Knowledge base</h3>
            <p className="muted small">The AI may only answer from these articles.</p>
            {kb.map((a) => <Article key={a.id} a={a} reload={load} />)}
            <button onClick={() => api.post('/knowledge', { title: 'New article', content: '', tags: '' }).then(load)}>+ Add article</button>
          </div>
          <div className="card">
            <h3>Administrators</h3>
            {admins.map((u) => <div key={u.id} className="row between"><span>{u.email}</span><span className="muted small">{u.is_active ? 'active' : 'disabled'}</span></div>)}
            <NewAdmin reload={load} />
          </div>
        </div>
      </div>
      <div className="card">
        <h3>Audit log</h3>
        <table className="compact"><tbody>
          {audit.map((x) => <tr key={x.id}><td className="small">{fmt(x.created_at)}</td><td>{x.actor}</td><td><code>{x.action}</code></td><td className="small muted">{x.entity} {x.entity_id}</td></tr>)}
        </tbody></table>
      </div>
    </section>
  )
}

function Article({ a, reload }) {
  const [v, setV] = useState(a)
  return (
    <details className="kb">
      <summary>{v.title}{!v.is_active && ' (inactive)'}</summary>
      <input value={v.title} onChange={(e) => setV({ ...v, title: e.target.value })} />
      <textarea rows="4" value={v.content} onChange={(e) => setV({ ...v, content: e.target.value })} />
      <input placeholder="tags" value={v.tags} onChange={(e) => setV({ ...v, tags: e.target.value })} />
      <label className="toggle"><input type="checkbox" checked={v.is_active} onChange={(e) => setV({ ...v, is_active: e.target.checked })} /> Active</label>
      <button onClick={() => api.put(`/knowledge/${a.id}`, v).then(reload)}>Save</button>
    </details>
  )
}

function NewAdmin({ reload }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  return (
    <div className="row">
      <input placeholder="new admin email" value={email} onChange={(e) => setEmail(e.target.value)} />
      <input placeholder="password (10+)" type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
      <button onClick={() => api.post('/admins', { email, password }).then(() => { setEmail(''); setPassword(''); reload() }).catch((e) => alert(e.message))}>Add</button>
    </div>
  )
}
