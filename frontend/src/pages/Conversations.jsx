import { useEffect, useState } from 'react'
import { api, fmt } from '../api'
import { ApplicantDetail } from './Applicants'

export default function Conversations() {
  const [rows, setRows] = useState([])
  const [attention, setAttention] = useState(true)
  const [sel, setSel] = useState(null)
  const load = () => api.get(`/conversations?attention=${attention}`).then(setRows)
  useEffect(() => { load() }, [attention])

  if (sel) return <ApplicantDetail id={sel} onBack={() => { setSel(null); load() }} />
  return (
    <section>
      <h1>Conversations</h1>
      <div className="toolbar">
        <label className="toggle"><input type="checkbox" checked={attention} onChange={(e) => setAttention(e.target.checked)} /> Only needing attention (AI drafts &amp; escalations)</label>
      </div>
      <div className="list">
        {rows.map((r) => (
          <div key={r.applicant.id} className="card convo" onClick={() => setSel(r.applicant.id)}>
            <div className="row between">
              <b>{r.applicant.full_name || r.applicant.email}</b>
              <span className="muted small">{fmt(r.last_message.created_at)}</span>
            </div>
            <div className="preview">{r.last_message.direction === 'inbound' ? '← ' : '→ '}{r.last_message.body.slice(0, 160)}</div>
            <div>
              {r.drafts > 0 && <span className="pill">{r.drafts} draft{r.drafts > 1 && 's'} to review</span>}
              {r.escalated && <span className="pill warn">escalated</span>}
              {r.applicant.human_takeover && <span className="pill">human takeover</span>}
            </div>
          </div>
        ))}
        {!rows.length && <div className="muted">Nothing waiting. 🎉</div>}
      </div>
    </section>
  )
}
