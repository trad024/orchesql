'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import {
  ArrowUp,
  Check,
  Clock3,
  Copy,
  Database,
  Info,
  Menu,
  PanelLeft,
  Plus,
  Settings2,
  Sparkles,
  X,
} from 'lucide-react'

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

type QueryResults = {
  columns: string[]
  rows: unknown[][]
  row_count: number
  truncated: boolean
}

type QueryResponse = {
  session_id: string
  status: string
  sql?: string | null
  explanation?: string | null
  results?: QueryResults | null
  error?: string | null
  clarification?: { question: string; options: string[] } | null
}

const PIPELINE_STEPS = [
  'Understanding question',
  'Finding relevant tables',
  'Writing SQL',
  'Running query',
  'Formatting results',
]

function formatSql(sql: string): string[] {
  const pattern = /\b(SELECT|FROM|WHERE|GROUP BY|ORDER BY|LEFT JOIN|INNER JOIN|JOIN|HAVING|LIMIT|AND|OR)\b/gi
  const spaced = sql.replace(pattern, (m) => `\n${m.toUpperCase()}`)
  return spaced.split('\n').map((l) => l.trim()).filter(Boolean)
}

function isChartable(results: QueryResults): boolean {
  if (results.columns.length < 2 || results.rows.length < 2) return false
  return results.rows.every((row) => typeof row[row.length - 1] === 'number' && Number.isFinite(row[row.length - 1] as number))
}

function MiniChart({ results }: { results: QueryResults }) {
  const values = results.rows.map((row) => Number(row[row.length - 1]))
  const labels = results.rows.map((row) => String(row[0]))
  const min = Math.min(...values, 0)
  const max = Math.max(...values)
  const range = max - min || 1
  const left = 28
  const right = 492
  const top = 30
  const bottom = 174
  const step = (right - left) / Math.max(values.length - 1, 1)

  const points = values
    .map((v, i) => `${left + i * step},${bottom - ((v - min) / range) * (bottom - top)}`)
    .join(' ')
  const area = `${left},${bottom} ${points} ${right},${bottom}`

  return (
    <div className="chart-wrap" aria-label={`Line chart from ${min} to ${max}`}>
      <svg viewBox="0 0 520 210" role="img" className="chart-svg" preserveAspectRatio="none">
        <defs>
          <linearGradient id="chartFill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="var(--green)" stopOpacity=".18" />
            <stop offset="100%" stopColor="var(--green)" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[30, 75, 120, 165].map((y) => (
          <line key={y} x1="28" x2="492" y1={y} y2={y} className="grid-line" />
        ))}
        <polygon points={area} fill="url(#chartFill)" />
        <polyline points={points} fill="none" stroke="var(--green)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
        {points.split(' ').map((point, i) => {
          const [cx, cy] = point.split(',')
          return <circle key={point} cx={cx} cy={cy} r="3.5" fill="var(--panel)" stroke="var(--green)" strokeWidth="2" data-i={i} />
        })}
        {labels.map((label, i) => (
          <text key={label + i} x={left + i * step} y={202} className="axis-label" textAnchor="middle">
            {label.length > 8 ? `${label.slice(0, 8)}…` : label}
          </text>
        ))}
      </svg>
    </div>
  )
}

function Pipeline({ active }: { active: number }) {
  return (
    <div className="pipeline" aria-label="Query pipeline">
      <div className="pipeline-head">
        <span>PIPELINE</span>
        <span className="pipeline-state">{active >= PIPELINE_STEPS.length ? 'COMPLETE' : 'RUNNING'}</span>
      </div>
      {PIPELINE_STEPS.map((step, index) => (
        <div className={`pipeline-step ${index < active ? 'complete' : index === active ? 'current' : ''}`} key={step}>
          <span className="step-icon">
            {index < active ? <Check size={12} /> : index === active ? <span className="pulse-dot" /> : <span className="empty-dot" />}
          </span>
          <span>{step}</span>
          {index === active && <span className="step-note">working</span>}
        </div>
      ))}
    </div>
  )
}

function ResultCard({
  results,
  explanation,
  latencyMs,
  onSql,
  hasSql,
}: {
  results: QueryResults
  explanation?: string | null
  latencyMs: number
  onSql: () => void
  hasSql: boolean
}) {
  const chartable = isChartable(results)
  return (
    <section className="result-card">
      <div className="result-head">
        <div>
          <div className="eyebrow">RESULT</div>
          <h2>{results.row_count} row{results.row_count === 1 ? '' : 's'}</h2>
        </div>
        <div className="result-actions">
          {hasSql && (
            <button className="sql-chip" onClick={onSql}>
              &lt;/&gt; SQL
            </button>
          )}
        </div>
      </div>
      {explanation && (
        <div className="result-summary">
          <span>{explanation}</span>
        </div>
      )}
      {chartable && <MiniChart results={results} />}
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              {results.columns.map((col) => (
                <th key={col}>{col}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {results.rows.map((row, i) => (
              <tr key={i}>
                {row.map((cell, j) => (
                  <td key={j}>{cell === null ? '—' : String(cell)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="result-foot">
        <span>
          <Clock3 size={13} /> {latencyMs}ms
        </span>
        {results.truncated && (
          <span>
            <Database size={13} /> truncated
          </span>
        )}
      </div>
    </section>
  )
}

function SqlInspector({ sql, onClose }: { sql: string; onClose: () => void }) {
  const lines = formatSql(sql)
  return (
    <aside className="sql-inspector" aria-label="SQL inspector">
      <div className="inspector-head">
        <div>
          <span className="eyebrow">INSPECTOR</span>
          <h3>Generated SQL</h3>
        </div>
        <button className="icon-button" onClick={onClose} aria-label="Close SQL inspector">
          <X size={16} />
        </button>
      </div>
      <div className="code-block">
        {lines.map((line, i) => (
          <div key={`${line}-${i}`}>
            <span className="line-number">{String(i + 1).padStart(2, '0')}</span>
            <code>{line}</code>
          </div>
        ))}
      </div>
      <button className="copy-sql" onClick={() => navigator.clipboard.writeText(sql)}>
        <Copy size={14} /> Copy SQL
      </button>
    </aside>
  )
}

export default function Page() {
  const [question, setQuestion] = useState('')
  const [submittedQuestion, setSubmittedQuestion] = useState('')
  const [submitted, setSubmitted] = useState(false)
  const [pipeline, setPipeline] = useState(0)
  const [inspector, setInspector] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [response, setResponse] = useState<QueryResponse | null>(null)
  const [latencyMs, setLatencyMs] = useState(0)
  const [connected, setConnected] = useState<boolean | null>(null)
  const timerRef = useRef<number | null>(null)

  useEffect(() => {
    fetch(`${API_URL}/health`)
      .then((r) => setConnected(r.ok))
      .catch(() => setConnected(false))
  }, [])

  const canSubmit = question.trim().length > 0
  const status = useMemo(() => (submitted ? 'READY' : 'IDLE'), [submitted])

  function startPipeline() {
    setPipeline(0)
    let step = 0
    timerRef.current = window.setInterval(() => {
      step += 1
      setPipeline(Math.min(step, PIPELINE_STEPS.length - 1))
    }, 420)
  }

  function stopPipeline() {
    if (timerRef.current) window.clearInterval(timerRef.current)
    setPipeline(PIPELINE_STEPS.length)
  }

  async function submit() {
    if (!canSubmit) return
    const q = question
    setSubmittedQuestion(q)
    setSubmitted(true)
    setResponse(null)
    setInspector(false)
    startPipeline()
    const start = performance.now()
    try {
      const res = await fetch(`${API_URL}/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q }),
      })
      const data: QueryResponse = await res.json()
      setLatencyMs(Math.round(performance.now() - start))
      setSessionId(data.session_id)
      setResponse(data)
    } catch {
      setLatencyMs(Math.round(performance.now() - start))
      setResponse({ session_id: '', status: 'failed', error: 'Could not reach the OrcheSQL API.' })
    } finally {
      stopPipeline()
    }
  }

  async function clarify(answer: string) {
    if (!sessionId) return
    startPipeline()
    const start = performance.now()
    try {
      const res = await fetch(`${API_URL}/query/${sessionId}/clarify`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ answer }),
      })
      const data: QueryResponse = await res.json()
      setLatencyMs(Math.round(performance.now() - start))
      setResponse(data)
    } catch {
      setLatencyMs(Math.round(performance.now() - start))
      setResponse({ session_id: sessionId, status: 'failed', error: 'Could not reach the OrcheSQL API.' })
    } finally {
      stopPipeline()
    }
  }

  function newChat() {
    setQuestion('')
    setSubmitted(false)
    setSubmittedQuestion('')
    setPipeline(0)
    setInspector(false)
    setResponse(null)
    setSessionId(null)
  }

  const isRunning = submitted && !response
  const isClarifying = response?.status === 'needs_clarification'
  const isDone = response?.status === 'done'
  const isFailed = response?.status === 'failed' || !!response?.error

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark">
            <Sparkles size={15} />
          </div>
          <span>Helm</span>
          <span className="version">v0.1</span>
        </div>
        <div className="top-actions">
          <span className="status">
            <span className="status-dot" /> {status}
          </span>
          <button className="icon-button" aria-label="Settings">
            <Settings2 size={16} />
          </button>
          <button className="avatar" aria-label="Account">
            YOU
          </button>
        </div>
        <button className="mobile-menu icon-button" onClick={() => setSidebarOpen(!sidebarOpen)} aria-label="Toggle navigation">
          <Menu size={18} />
        </button>
      </header>
      <div className="workspace">
        <aside className={`history-sidebar ${sidebarOpen ? 'open' : ''}`}>
          <div className="sidebar-top">
            <span className="eyebrow">WORKSPACE</span>
            <button className="icon-button" aria-label="Collapse sidebar">
              <PanelLeft size={15} />
            </button>
          </div>
          <button className="new-chat" onClick={newChat}>
            <Plus size={15} /> New conversation
          </button>
          <div className="sidebar-bottom">
            <div className="connection">
              <span className="status-dot" style={connected === false ? { background: '#e5484d', boxShadow: 'none' } : undefined} />
              <span>OrcheSQL</span>
              <span className="connected">{connected === null ? 'checking…' : connected ? 'connected' : 'offline'}</span>
            </div>
            <button className="settings-link">
              <Info size={14} /> {API_URL}
            </button>
          </div>
        </aside>
        <section className="conversation">
          <div className="conversation-inner">
            <div className="context-row">
              <span className="context-chip">
                <Database size={13} /> OrcheSQL
              </span>
              <span className="context-chip">read-only</span>
            </div>
            <div className="thread">
              {submitted && (
                <div className="user-message">
                  <span className="message-label">YOU</span>
                  <p>{submittedQuestion}</p>
                </div>
              )}
              {submitted && (
                <div className="assistant-message">
                  <div className="assistant-avatar">
                    <Sparkles size={14} />
                  </div>
                  <div className="assistant-body">
                    <div className="message-label">
                      HELM <span className="muted">just now</span>
                    </div>
                    {isRunning && <Pipeline active={pipeline} />}
                    {isFailed && <p style={{ color: '#e5484d' }}>{response?.error ?? 'Something went wrong.'}</p>}
                    {isClarifying && response?.clarification && (
                      <div className="pipeline" style={{ maxWidth: 550 }}>
                        <p style={{ margin: '0 0 12px', color: 'var(--foreground)' }}>{response.clarification.question}</p>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                          {response.clarification.options.map((opt) => (
                            <button key={opt} className="sql-chip" onClick={() => clarify(opt)}>
                              {opt}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                    {isDone && response?.results && (
                      <ResultCard
                        results={response.results}
                        explanation={response.explanation}
                        latencyMs={latencyMs}
                        hasSql={!!response.sql}
                        onSql={() => setInspector(true)}
                      />
                    )}
                  </div>
                </div>
              )}
            </div>
            <div className="composer-wrap">
              <div className="composer">
                <textarea
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing && e.keyCode !== 229) {
                      e.preventDefault()
                      submit()
                    }
                  }}
                  placeholder="Ask anything about your data..."
                  rows={1}
                  aria-label="Ask Helm"
                />
                <button className="send-button" onClick={submit} disabled={!canSubmit} aria-label="Send question">
                  <ArrowUp size={17} />
                </button>
              </div>
              <div className="composer-hint">
                <span>
                  Enter to run <span className="key">⇧ Enter</span> for new line
                </span>
                <span>Helm can make mistakes. Check important results.</span>
              </div>
            </div>
          </div>
        </section>
        {inspector && response?.sql && <SqlInspector sql={response.sql} onClose={() => setInspector(false)} />}
      </div>
    </main>
  )
}
