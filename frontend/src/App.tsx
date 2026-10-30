import { useEffect, useRef, useState, type DragEvent, type FormEvent } from 'react'
import { api, type Health, type SearchResponse, type Snapshot, type Status } from './api'
import Results from './Results'

type Busy = '' | 'upload' | 'search'

const EXAMPLES = [
  'Where is configuration loaded?',
  'Where are errors handled?',
  'Where is the database initialised?',
  'How is the app started?',
]

export default function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null)
  const [search, setSearch] = useState<SearchResponse | null>(null)
  const [busy, setBusy] = useState<Busy>('')
  const [error, setError] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [dragging, setDragging] = useState(false)
  const latest = useRef(0)
  const statusSeq = useRef(0)
  const fileInput = useRef<HTMLInputElement>(null)
  const askForm = useRef<HTMLFormElement>(null)
  const query = useRef<HTMLInputElement>(null)

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

  function drop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault()
    setDragging(false)
    const input = fileInput.current
    if (!input || busy || !event.dataTransfer.files.length) return
    // Keep only the first file, so the upload matches the file name shown.
    const one = new DataTransfer()
    one.items.add(event.dataTransfer.files[0])
    input.files = one.files
    setFile(one.files[0])
  }

  function askExample(text: string) {
    if (!query.current) return
    query.current.value = text
    askForm.current?.requestSubmit()
  }

  const limitMb = health && Math.round(health.limits.max_zip_bytes / 2 ** 20)

  return (
    <>
      <header className="topbar">
        <div className="topbar-inner">
          <div className="brand">
            <Logo />
            <span className="brand-name">Brahmaniss</span>
            <span className="tagline">Evidence-first code discovery</span>
          </div>
          <div className="pills">
            <span className="pill ok" title="Your code is indexed on this machine">
              <span className="dot" aria-hidden="true" />
              Local index
            </span>
            {health && (
              <span
                className={health.ai_configured ? 'pill accent' : 'pill'}
                title={health.ai_configured ? 'AI explanations available on request' : 'Search-only mode'}
              >
                <span className="dot" aria-hidden="true" />
                AI: {health.ai_configured ? 'on' : 'off'}
              </span>
            )}
          </div>
        </div>
      </header>

      <main>
        <div className="hero">
          <h1>Find where things live in an unfamiliar codebase.</h1>
          <p>
            Ask a question and get ranked code snippets with exact paths and line numbers. Evidence
            first. AI explanations only when you ask.
          </p>
          <ul className="trust">
            <li><Check /> Indexed locally</li>
            <li><Check /> Never executed</li>
            <li><Check /> Cites exact lines</li>
          </ul>
        </div>

        <div className="steps">
          <section className="panel" aria-labelledby="upload-title">
            <div className="panel-head">
              <span className="step" aria-hidden="true">1</span>
              <h2 id="upload-title">Upload a repository</h2>
            </div>
            <form onSubmit={upload} className="upload">
              <label
                htmlFor="file"
                className={`dropzone${dragging ? ' dragging' : ''}${busy ? ' disabled' : ''}`}
                onDragOver={(e) => {
                  e.preventDefault()
                  if (!busy) setDragging(true)
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={drop}
              >
                <input
                  ref={fileInput}
                  id="file"
                  name="file"
                  type="file"
                  accept=".zip,application/zip"
                  className="visually-hidden"
                  disabled={!!busy}
                  onChange={(e) => setFile(e.currentTarget.files?.[0] ?? null)}
                />
                <UploadIcon />
                {file ? (
                  <>
                    <span className="drop-title">{file.name}</span>
                    <span className="muted">{formatSize(file.size)} · click to choose another</span>
                  </>
                ) : (
                  <>
                    <span className="drop-title">Drop a repository ZIP here</span>
                    <span className="muted">or click to choose a file</span>
                  </>
                )}
              </label>
              <button className="primary" disabled={!!busy}>
                {busy === 'upload' ? <><Spinner /> Indexing…</> : 'Upload and index'}
              </button>
            </form>
            <p className="muted hint">
              {health ? `${health.languages.join(', ')}. ` : ''}
              Code is indexed locally and never executed.
              {limitMb ? ` Max ${limitMb} MB ZIP.` : ''}
            </p>
            {snapshot ? (
              <SnapshotSummary snapshot={snapshot} />
            ) : (
              <div className="empty">
                <strong>No repository indexed yet</strong>
                <span className="muted">Upload a ZIP to start asking questions.</span>
              </div>
            )}
          </section>

          <section className="panel" aria-labelledby="ask-title">
            <div className="panel-head">
              <span className="step" aria-hidden="true">2</span>
              <h2 id="ask-title">Ask where something lives</h2>
            </div>
            <form id="ask" ref={askForm} onSubmit={ask} className="searchbar">
              <label className="visually-hidden" htmlFor="q">Question or symbol</label>
              <div className="search-field">
                <SearchIcon />
                <input
                  ref={query}
                  id="q"
                  name="q"
                  maxLength={500}
                  autoComplete="off"
                  placeholder="e.g. Where is the session cookie loaded?  or  url_for"
                  disabled={!snapshot || !!busy}
                />
              </div>
              <button className="primary" disabled={!snapshot || !!busy}>
                {busy === 'search' ? <><Spinner /> Searching…</> : 'Search'}
              </button>
            </form>
            {snapshot ? (
              <div className="examples" aria-label="Example questions" role="group">
                {EXAMPLES.map((text) => (
                  <button
                    key={text}
                    type="button"
                    className="example"
                    disabled={!!busy}
                    onClick={() => askExample(text)}
                  >
                    {text}
                  </button>
                ))}
              </div>
            ) : (
              <p className="muted hint">Index a repository first to enable search.</p>
            )}
            {health?.ai_configured && (
              <label className="switch">
                <input type="checkbox" name="expand" form="ask" />
                <span className="switch-track" aria-hidden="true" />
                <span>
                  Also ask AI for related search terms
                  <span className="muted switch-note">
                    Sends only your question to Featherless; local results are kept.
                  </span>
                </span>
              </label>
            )}
          </section>
        </div>

        <div aria-live="polite" className="output">
          {error && (
            <p role="alert" className="error banner">
              <AlertIcon />
              <span>{error}</span>
            </p>
          )}
          {search && (
            <Results search={search} aiReady={!!health?.ai_configured} onError={refreshStatus} />
          )}
        </div>
      </main>
    </>
  )
}

function SnapshotSummary({ snapshot }: { snapshot: Snapshot }) {
  const skipped = Object.entries(snapshot.skipped)
  return (
    <div className="summary">
      <p className="summary-title">
        <Check /> Ready to search
      </p>
      <ul className="stats">
        <li className="stat repo" title={snapshot.name}>{snapshot.name}</li>
        <li className="stat"><strong>{snapshot.files}</strong> source files</li>
        <li className="stat"><strong>{snapshot.chunks}</strong> code regions</li>
        {skipped.map(([why, n]) => (
          <li key={why} className="stat skipped"><strong>{n}</strong> skipped: {why}</li>
        ))}
      </ul>
    </div>
  )
}

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 2 ** 20) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 2 ** 20).toFixed(1)} MB`
}

function Icon({ d, className = 'icon' }: { d: string; className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={d} />
    </svg>
  )
}

const Check = () => <Icon d="M20 6 9 17l-5-5" />
const SearchIcon = () => <Icon d="m21 21-4.3-4.3M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14z" />
const UploadIcon = () => <Icon className="icon drop-icon" d="M12 15V3m0 0-4 4m4-4 4 4M4 15v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4" />
const AlertIcon = () => <Icon d="M12 8v4m0 4h.01M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z" />
const Spinner = () => <span className="spinner" aria-hidden="true" />

function Logo() {
  return (
    <svg className="logo" viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="8" fill="var(--accent)" />
      <path d="M11 10 7 16l4 6M21 10l4 6-4 6" fill="none" stroke="var(--surface)" strokeWidth="2.4"
        strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="16" cy="16" r="2.4" fill="var(--surface)" />
    </svg>
  )
}
