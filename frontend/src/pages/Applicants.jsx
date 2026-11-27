import { useEffect, useState } from 'react'
import { api, fmt } from '../api'
import Thread from './Thread'

const STATUSES = ['new', 'in_review', 'contacted', 'shortlisted', 'closed']

export default function Applicants() {
  const [rows, setRows] = useState([])
  const [q, setQ] = useState('')
  const [status, setStatus] = useState('')
  const [cls, setCls] = useState('')
  const [sel, setSel] = useState(null)

  const load = () => api.get(`/applicants?q=${encodeURIComponent(q)}&status=${status}&classification=${cls}`).then(setRows)
  useEffect(() => { load() }, [q, status, cls])

  if (sel) return <ApplicantDetail id={sel} onBack={() => { setSel(null); load() }} />

  return (
    <section>
      <h1>Applicants</h1>
      <div className="toolbar">
        <input placeholder="Search name or email…" value={q} onChange={(e) => setQ(e.target.value)} />
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All statuses</option>{STATUSES.map((s) => <option key={s}>{s}</option>)}
        </select>
        <select value={cls} onChange={(e) => setCls(e.target.value)}>
          <option value="">All AI classes</option>{['qualified', 'needs_info', 'incomplete', 'spam'].map((s) => <option key={s}>{s}</option>)}
        </select>
      </div>
      <table>
        <thead><tr><th>Name</th><th>Position</th><th>Status</th><th>AI class</th><th>Flags</th><th>Received</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} onClick={() => setSel(r.id)}>
              <td><b>{r.full_name || '—'}</b><div className="muted small">{r.email}</div></td>
              <td>{r.position}</td>
              <td><span className={`pill s-${r.status}`}>{r.status}</span></td>
              <td>{r.classification && <span className={`pill c-${r.classification}`}>{r.classification}</span>}</td>
              <td className="flags">
                {r.needs_attention && <span className="pill warn">attention</span>}
                {r.opted_out_at && <span className="pill bad">opted out</span>}
                {r.automation_paused && <span className="pill">paused</span>}
                {r.human_takeover && <span className="pill">human</span>}
                {r.applications_count > 1 && <span className="pill">{r.applications_count} apps</span>}
              </td>
              <td className="small">{fmt(r.created_at)}</td>
            </tr>
          ))}
          {!rows.length && <tr><td colSpan="6" className="muted">No applicants yet.</td></tr>}
        </tbody>
      </table>
    </section>
  )
}

export function ApplicantDetail({ id, onBack }) {
  const [a, setA] = useState(null)
  const [notes, setNotes] = useState('')
  const load = () => api.get(`/applicants/${id}`).then((d) => { setA(d); setNotes(d.notes) })
  useEffect(() => { load() }, [id])
  if (!a) return null
  const patch = (b) => api.patch(`/applicants/${id}`, b).then(load).catch((e) => alert(e.message))

  return (
    <section>
      <button className="link" onClick={onBack}>← Back</button>
      <div className="detail-head">
        <div>
          <h1>{a.full_name || a.email}</h1>
          <div className="muted">{a.email} · {a.phone} {a.email_verified && '· ✓ email verified'}</div>
        </div>
        <select value={a.status} onChange={(e) => patch({ status: e.target.value })}>
          {STATUSES.map((s) => <option key={s}>{s}</option>)}
        </select>
      </div>
      <div className="grid2">
        <div>
          <div className="card">
            <h3>Controls</h3>
            <label className="toggle"><input type="checkbox" checked={a.automation_paused} onChange={(e) => patch({ automation_paused: e.target.checked })} /> Pause automation for this applicant</label>
            <label className="toggle"><input type="checkbox" checked={a.human_takeover} onChange={(e) => patch({ human_takeover: e.target.checked })} /> Human takeover (AI stops replying)</label>
            <label className="toggle"><input type="checkbox" checked={a.consent_email} disabled={!!a.opted_out_at} onChange={(e) => patch({ consent_email: e.target.checked })} /> Email permission {a.opted_out_at && <span className="pill bad">opted out {fmt(a.opted_out_at)}</span>}</label>
          </div>
          <div className="card">
            <h3>Applications</h3>
            {a.applications.map((x) => (
              <div key={x.id} className="app-item">
                <div><b>{x.position}</b> <span className="muted small">#{x.id} · {fmt(x.received_at)}</span></div>
                <div>
                  <span className={`pill p-${x.processing_status}`}>{x.processing_status}</span>
                  {x.classification && <span className={`pill c-${x.classification}`}>{x.classification} {x.ai_confidence != null && `· ${Math.round(x.ai_confidence * 100)}%`}</span>}
                  {x.is_duplicate && <span className="pill warn">duplicate of #{x.duplicate_of_id}</span>}
                </div>
                {x.ai_summary && <p className="summary">{x.ai_summary}</p>}
                <details><summary className="small">Submitted fields</summary><pre>{JSON.stringify(x.payload, null, 2)}</pre></details>
              </div>
            ))}
          </div>
          <div className="card">
            <h3>Internal notes</h3>
            <textarea rows="4" value={notes} onChange={(e) => setNotes(e.target.value)} />
            <button onClick={() => patch({ notes })}>Save notes</button>
          </div>
        </div>
        <Thread applicant={a} reload={load} />
      </div>
    </section>
  )
}
