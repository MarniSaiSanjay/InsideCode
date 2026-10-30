import { useEffect, useRef, useState, type FormEvent } from 'react'
import {
  api,
  post,
  type Explanation,
  type Health,
  type Result,
  type SearchResponse,
  type Snapshot,
  type Source,
  type Status,
} from './api'

type Busy = '' | 'upload' | 'search'

export default function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null)
  const [search, setSearch] = useState<SearchResponse | null>(null)
  const [busy, setBusy] = useState<Busy>('')
  const [error, setError] = useState('')
  const latest = useRef(0)
  const statusSeq = useRef(0)

  // A newer status read or a successful upload makes pending status reads stale.
  const refreshStatus = () => {
    const id = ++statusSeq.current
    api<Status>('/status').then((s) => {
      if (id === statusSeq.current) setSnapshot(s.snapshot)
    }, () => {})
  }

  useEffect(() => {
    api<Health>('/health').then(setHealth, (e: Error) => setError(`Backend unavailable: ${e.message}`))
    refreshStatus()
  }, [])

  // Only the newest request may update the page; older responses are ignored.
  async function run<T>(kind: Busy, request: () => Promise<T>, apply: (value: T) => void) {
    const id = ++latest.current
    setBusy(kind)
    setError('')
    try {
      const value = await request()
      if (id === latest.current) apply(value)
    } catch (e) {
      if (id === latest.current) {
        setError((e as Error).message)
        refreshStatus()
      }
    } finally {
      if (id === latest.current) setBusy('')
    }
  }

  function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const body = new FormData(event.currentTarget)
    if (!(body.get('file') as File | null)?.size) return setError('Choose a ZIP file first.')
    run('upload', () => api<Snapshot>('/snapshots', { method: 'POST', body }), (s) => {
      statusSeq.current++
      setSnapshot(s)
      setSearch(null)
    })
  }

  function ask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const q = String(form.get('q') ?? '').trim()
    if (!snapshot || !q) return
    const expand = form.get('expand') ? 'true' : 'false'
    const params = new URLSearchParams({ snapshot_id: snapshot.snapshot_id, q, expand })
    run('search', () => api<SearchResponse>(`/search?${params}`), setSearch)
  }

  return (
    <main>
      <header>
        <h1>Brahmaniss</h1>
        <p>Find the right code in an unfamiliar Python repository, with exact source evidence.</p>
        {health && (
          <p className="muted">
            AI explanation: {health.ai_configured ? 'available' : 'not configured (search-only)'}
          </p>
        )}
      </header>

      <section aria-labelledby="upload-title">
        <h2 id="upload-title">1. Upload a repository</h2>
        <form onSubmit={upload} className="row">
          <label className="visually-hidden" htmlFor="file">Repository ZIP</label>
          <input id="file" name="file" type="file" accept=".zip,application/zip" disabled={!!busy} />
          <button disabled={!!busy}>{busy === 'upload' ? 'Indexing…' : 'Upload and index'}</button>
        </form>
        <p className="muted">
          Python files only. Code is indexed locally and never executed.
          {health && ` Limit: ${Math.round(health.limits.max_zip_bytes / 2 ** 20)} MB ZIP.`}
        </p>
        {snapshot ? <SnapshotSummary snapshot={snapshot} /> : <p>No repository indexed yet.</p>}
      </section>

      <section aria-labelledby="ask-title">
        <h2 id="ask-title">2. Ask where something lives</h2>
        <form id="ask" onSubmit={ask} className="row">
          <label className="visually-hidden" htmlFor="q">Question or symbol</label>
          <input
            id="q"
            name="q"
            maxLength={500}
            placeholder="e.g. Where is the session cookie loaded?  or  url_for"
            disabled={!snapshot || !!busy}
          />
          <button disabled={!snapshot || !!busy}>{busy === 'search' ? 'Searching…' : 'Search'}</button>
        </form>
        {health?.ai_configured && (
          <label className="muted">
            <input type="checkbox" name="expand" form="ask" /> Also ask AI for related search terms
            (sends only your question to Featherless; local results are kept)
          </label>
        )}
      </section>

      <div aria-live="polite">
        {error && <p role="alert" className="error">{error}</p>}
        {search && (
          <Results search={search} aiReady={!!health?.ai_configured} onError={refreshStatus} />
        )}
      </div>
    </main>
  )
}

function SnapshotSummary({ snapshot }: { snapshot: Snapshot }) {
  const skipped = Object.entries(snapshot.skipped)
  return (
    <p className="ready">
      Ready: <strong>{snapshot.name}</strong> — {snapshot.files} Python files, {snapshot.chunks} code
      regions indexed.
      {skipped.length > 0 && ` Skipped: ${skipped.map(([why, n]) => `${n} ${why}`).join(', ')}.`}
    </p>
  )
}

type ResultsProps = { search: SearchResponse; aiReady: boolean; onError: () => void }

function Results({ search, aiReady, onError }: ResultsProps) {
  const ai = search.ai_note ? (
    <p className="muted">{search.ai_note}</p>
  ) : (
    search.suggested_terms.length > 0 && (
      <p className="muted">AI-suggested terms also searched: {search.suggested_terms.join(', ')}</p>
    )
  )
  // A new search (different evidence) starts a fresh AI panel.
  const key = [search.snapshot_id, search.query, ...search.results.map((r) => r.id)].join('|')
  const panel = aiReady && <AIPanel key={key} search={search} />
  if (!search.results.length) {
    return (
      <>
        {ai}
        {panel}
        <p>
          No matches for “{search.query}” in our index. That does not prove it is absent from the
          repository — try a function name or different words.
        </p>
      </>
    )
  }
  return (
    <section aria-label="Evidence">
      <h2>Evidence for “{search.query}”</h2>
      {ai}
      <ol className="results">
        {search.results.map((r) => (
          <EvidenceCard
            key={`${search.snapshot_id}-${r.id}`}
            result={r}
            snapshotId={search.snapshot_id}
            onError={onError}
          />
        ))}
      </ol>
      {panel}
    </section>
  )
}

const MAX_EVIDENCE = 5

// Nothing leaves the machine until the user reviews the exact context and presses Send.
function AIPanel({ search }: { search: SearchResponse }) {
  const [context, setContext] = useState('')
  const [explanation, setExplanation] = useState<Explanation | null>(null)
  const [general, setGeneral] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const evidence = {
    snapshot_id: search.snapshot_id,
    question: search.query,
    chunk_ids: search.results.slice(0, MAX_EVIDENCE).map((r) => r.id),
  }

  async function call<T>(path: string, body: unknown, apply: (value: T) => void) {
    setBusy(true)
    setError('')
    try {
      apply(await post<T>(path, body))
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const prepare = () =>
    call<{ context: string }>('/explain/context', evidence, (r) => setContext(r.context))
  const send = () =>
    call<Explanation>('/explain', evidence, (r) => {
      setContext('')
      setExplanation(r)
    })
  const ask = () =>
    call<{ answer: string }>('/general', { question: search.query }, (r) => setGeneral(r.answer))

  return (
    <section aria-label="AI help" className="ai">
      <h2>AI help (optional)</h2>
      <p className="muted">
        Nothing is sent to Featherless until you choose. AI text can be wrong; check the cited code.
      </p>
      <div className="row">
        {evidence.chunk_ids.length > 0 && (
          <button disabled={busy} onClick={prepare}>
            Explain the top {evidence.chunk_ids.length} results…
          </button>
        )}
        <button disabled={busy} onClick={ask}>
          General programming answer (sends only the question)
        </button>
      </div>
      {context && (
        <div>
          <p>This exact text will be sent with your question:</p>
          <pre className="context" tabIndex={0}>
            {context}
          </pre>
          <div className="row">
            <button disabled={busy} onClick={send}>
              {busy ? 'Waiting for AI…' : 'Send to Featherless'}
            </button>
            <button disabled={busy} className="link" onClick={() => setContext('')}>
              Cancel
            </button>
          </div>
        </div>
      )}
      {error && <p role="alert" className="error">{error}</p>}
      {explanation && (
        <div>
          <h3>Explanation from the selected code</h3>
          {explanation.note && <p className="warn">{explanation.note}</p>}
          <ul>
            {explanation.points.map((p, i) => (
              <li key={i}>
                {p.text}{' '}
                {p.evidence.map((c) => (
                  <code key={c.id} className="cite">
                    [{c.id}] {c.path}:{c.start_line}–{c.end_line}
                    {c.is_test && ' (test)'}
                  </code>
                ))}
              </li>
            ))}
          </ul>
        </div>
      )}
      {general && (
        <div>
          <h3>General answer — not based on this repository</h3>
          <p className="general">{general}</p>
        </div>
      )}
    </section>
  )
}

type CardProps = { result: Result; snapshotId: string; onError: () => void }

function EvidenceCard({ result, snapshotId, onError }: CardProps) {
  const [open, setOpen] = useState(false)
  const [source, setSource] = useState<Source | null>(null)
  const [error, setError] = useState('')
  const lines: [number, number] = [result.start_line, result.end_line]

  function toggle() {
    setOpen(!open)
    if (!source) {
      api<Source>(`/snapshots/${snapshotId}/files/${result.file_id}`).then(setSource, (e: Error) => {
        setError(e.message)
        onError()
      })
    }
  }

  return (
    <li className="card">
      <div className="card-head">
        <code className="path">
          {result.path}:{result.start_line}–{result.end_line}
        </code>
        {result.symbol && <span className="symbol">{result.symbol}</span>}
        {result.is_test && <span className="badge">test</span>}
        <span className="muted">{result.reasons.join(' · ')}</span>
      </div>
      {open && source ? (
        <CodeLines text={source.text} first={1} highlight={lines} scroll />
      ) : (
        <CodeLines text={result.text} first={result.start_line} />
      )}
      <button className="link" aria-expanded={open} onClick={toggle}>
        {open ? 'Show snippet only' : 'Show in full file'}
      </button>
      {open && error && <p role="alert" className="error">{error}</p>}
    </li>
  )
}

function CodeLines(props: { text: string; first: number; highlight?: [number, number]; scroll?: boolean }) {
  const { text, first, highlight, scroll } = props
  const box = useRef<HTMLPreElement>(null)
  useEffect(() => {
    const pre = box.current
    const hit = pre?.querySelector<HTMLElement>('.hl')
    if (scroll && pre && hit) pre.scrollTop = hit.offsetTop - pre.clientHeight / 3
  }, [scroll])
  const lines = text.replace(/\n$/, '').split('\n')
  return (
    <pre ref={box} className={scroll ? 'code full' : 'code'} tabIndex={0}>
      {lines.map((line, i) => {
        const n = first + i
        const hit = highlight && n >= highlight[0] && n <= highlight[1]
        return (
          <span key={n} className={hit ? 'line hl' : 'line'}>
            <span className="n">{n}</span>
            {line || ' '}
          </span>
        )
      })}
    </pre>
  )
}
