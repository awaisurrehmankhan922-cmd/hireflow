import { useEffect, useState } from 'react'
import { api } from '../api'

// Open WebUI is served by nginx at /ai/ behind the same login (auth_request -> /api/auth/verify),
// so it is embedded rather than rebuilding a chat UI. The guarded-reply tester below exercises
// the *production* reply engine (knowledge base + escalation rules), which Open WebUI does not.
export default function AIConsole() {
  const [url, setUrl] = useState('/ai/')
  const [msg, setMsg] = useState('Hi, I applied last week. When will I hear back?')
  const [out, setOut] = useState(null)
  const [busy, setBusy] = useState(false)
  const [mode, setMode] = useState('webui')
  useEffect(() => { api.get('/settings').then((s) => setUrl(s.open_webui_url)) }, [])

  const test = async () => {
    setBusy(true)
    try { setOut(await api.post('/ai/test', { message: msg })) } catch (e) { setOut({ error: e.message }) }
    setBusy(false)
  }

  return (
    <section className="ai">
      <div className="row between">
        <h1>AI Interface</h1>
        <div className="seg">
          <button className={mode === 'webui' ? 'active' : ''} onClick={() => setMode('webui')}>Open WebUI</button>
          <button className={mode === 'tester' ? 'active' : ''} onClick={() => setMode('tester')}>Reply engine tester</button>
        </div>
      </div>
      {mode === 'webui' ? (
        <>
          <iframe title="Open WebUI" src={url} className="webui" />
          <p className="muted small">Open WebUI talks directly to the local Ollama service. If it is down, the recruitment platform keeps working. <a href={url} target="_blank">Open in new tab ↗</a></p>
        </>
      ) : (
        <div className="grid2">
          <div className="card">
            <h3>Simulate an applicant message</h3>
            <textarea rows="6" value={msg} onChange={(e) => setMsg(e.target.value)} />
            <button className="primary" disabled={busy} onClick={test}>{busy ? 'Thinking…' : 'Run through reply engine'}</button>
            <p className="muted small">Dry run: nothing is saved or sent. Try “Can you sponsor my visa?” to see escalation.</p>
          </div>
          <div className="card">
            <h3>Result</h3>
            {out?.error && <div className="error">{out.error}</div>}
            {out && !out.error && (
              <>
                <p>{out.needs_human ? <span className="pill warn">Escalate to human</span> : <span className="pill c-qualified">OK to send</span>} <span className="pill">{out.intent}</span> <span className="pill">confidence {Math.round(out.confidence * 100)}%</span></p>
                {out.reason && <p className="muted">Reason: {out.reason}</p>}
                {out.reply && <div className="msg out"><div className="body">{out.reply}</div></div>}
              </>
            )}
          </div>
        </div>
      )}
    </section>
  )
}
