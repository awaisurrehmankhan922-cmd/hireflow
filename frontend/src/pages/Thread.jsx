import { useState } from 'react'
import { api, fmt } from '../api'

function Draft({ m, reload }) {
  const [body, setBody] = useState(m.body)
  const act = async (fn) => { try { await fn(); reload() } catch (e) { alert(e.message) } }
  return (
    <div className="msg out draft">
      <div className="meta">AI draft · {m.classification} · confidence {Math.round((m.ai_confidence || 0) * 100)}%</div>
      <textarea rows="5" value={body} onChange={(e) => setBody(e.target.value)} />
      <div className="row">
        <button className="primary" onClick={() => act(async () => { if (body !== m.body) await api.patch(`/messages/${m.id}`, { body }); await api.post(`/messages/${m.id}/approve`) })}>Approve &amp; send</button>
        <button onClick={() => act(() => api.post(`/messages/${m.id}/discard`))}>Discard</button>
      </div>
    </div>
  )
}

export default function Thread({ applicant, reload }) {
  const [text, setText] = useState('')
  const send = async () => {
    try { await api.post(`/applicants/${applicant.id}/messages`, { body: text }); setText(''); reload() } catch (e) { alert(e.message) }
  }
  return (
    <div className="card thread">
      <h3>Conversation</h3>
      <div className="msgs">
        {applicant.messages.map((m) => m.status === 'draft' ? <Draft key={m.id} m={m} reload={reload} /> : (
          <div key={m.id} className={`msg ${m.direction === 'inbound' ? 'in' : 'out'} st-${m.status}`}>
            <div className="meta">
              {m.direction === 'inbound' ? 'Applicant' : m.author} · {fmt(m.sent_at || m.created_at)}
              {m.direction === 'outbound' && <span className={`pill m-${m.status}`}>{m.status}</span>}
              {m.classification && m.direction === 'inbound' && <span className="pill">{m.classification}</span>}
            </div>
            {m.subject && <div className="subj">{m.subject}</div>}
            <div className="body">{m.body}</div>
            {m.error && <div className="error small">{m.error}</div>}
            {m.escalated && (
              <div className="escalation">⚠ Escalated to a human: {m.escalation_reason}
                <button className="link" onClick={() => api.post(`/messages/${m.id}/resolve`).then(reload)}>Mark resolved</button>
              </div>
            )}
          </div>
        ))}
        {!applicant.messages.length && <div className="muted">No messages yet.</div>}
      </div>
      <div className="compose">
        <textarea rows="3" placeholder={applicant.opted_out_at ? 'Applicant opted out – sending disabled' : 'Write a manual reply…'} disabled={!!applicant.opted_out_at} value={text} onChange={(e) => setText(e.target.value)} />
        <button className="primary" disabled={!text.trim() || !!applicant.opted_out_at} onClick={send}>Send manual reply</button>
      </div>
    </div>
  )
}
