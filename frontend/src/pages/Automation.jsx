import { useEffect, useState } from 'react'
import { api } from '../api'

export default function Automation() {
  const [s, setS] = useState(null)
  const load = () => api.get('/automation').then(setS)
  useEffect(() => { load() }, [])
  if (!s) return null
  const setting = (k, v) => api.put('/settings', { [k]: v }).then(load)

  return (
    <section>
      <h1>Automation</h1>
      <div className={`card killswitch ${s.automation_paused ? 'paused' : ''}`}>
        <div>
          <h3>{s.automation_paused ? 'All automated communication is PAUSED' : 'Automation is running'}</h3>
          <p className="muted">Global stop for acknowledgments, AI replies and follow-ups. Takes effect immediately. Manual replies still work; opt-outs are always enforced.</p>
        </div>
        <button className={s.automation_paused ? 'primary' : 'danger'} onClick={() => api.post('/automation/pause', { paused: !s.automation_paused }).then(load)}>
          {s.automation_paused ? 'Resume automation' : 'Pause everything'}
        </button>
      </div>
      <div className="grid3">
        <div className="card"><h3>Auto-acknowledge</h3><label className="toggle"><input type="checkbox" checked={s.auto_acknowledge} onChange={(e) => setting('auto_acknowledge', e.target.checked)} /> Send acknowledgment on new applications</label></div>
        <div className="card"><h3>AI replies</h3><label className="toggle"><input type="checkbox" checked={s.auto_send_ai_replies} onChange={(e) => setting('auto_send_ai_replies', e.target.checked)} /> Auto-send confident AI replies</label><p className="muted small">Off = every AI reply waits for human approval.</p></div>
        <div className="card"><h3>Permissions</h3><p><b>{s.opted_out}</b> opted out · <b>{s.paused_applicants}</b> individually paused</p></div>
      </div>
      <h2>Follow-up workflows</h2>
      {s.rules.map((r) => <Rule key={r.id} rule={r} reload={load} />)}
      <button onClick={() => api.post('/automation/rules', { name: 'New follow-up', trigger_status: 'in_review', wait_hours: 72, template: 'Hi {first_name}, …\n\nReply UNSUBSCRIBE to stop these emails.', max_sends: 1, is_active: false }).then(load)}>+ Add workflow</button>
    </section>
  )
}

function Rule({ rule, reload }) {
  const [r, setR] = useState(rule)
  const f = (k) => (e) => setR({ ...r, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.type === 'number' ? +e.target.value : e.target.value })
  return (
    <div className="card rule">
      <div className="row">
        <input value={r.name} onChange={f('name')} />
        <label className="toggle"><input type="checkbox" checked={r.is_active} onChange={f('is_active')} /> Active</label>
      </div>
      <div className="row small">
        When status is <select value={r.trigger_status} onChange={f('trigger_status')}>{['new', 'in_review', 'contacted', 'shortlisted'].map((x) => <option key={x}>{x}</option>)}</select>
        and no reply for <input type="number" value={r.wait_hours} onChange={f('wait_hours')} style={{ width: 70 }} /> hours, send at most
        <input type="number" value={r.max_sends} onChange={f('max_sends')} style={{ width: 50 }} /> time(s):
      </div>
      <textarea rows="4" value={r.template} onChange={f('template')} />
      <button onClick={() => api.put(`/automation/rules/${r.id}`, r).then(reload)}>Save</button>
    </div>
  )
}
