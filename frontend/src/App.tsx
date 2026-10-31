import { useEffect, useRef, useState, type DragEvent, type FormEvent } from 'react'
import { flushSync } from 'react-dom'
import { api, uploadSnapshot, type Health, type SearchResponse, type Snapshot, type Status } from './api'
import Architecture from './Architecture'
import Results from './Results'

type Busy = '' | 'upload' | 'search'
type Theme = 'light' | 'dark'

const darkQuery = matchMedia('(prefers-color-scheme: dark)')

function savedTheme(): string | null {
  try {
    return localStorage.getItem('theme')
  } catch {
    return null
  }
}

const EXAMPLES = [
  'Where is configuration loaded?',
  'Where are errors handled?',
  'Where is the database initialised?',
  'How is the app started?',
]

// Flask (BSD-3-Clause) at a pinned commit; its licence ships inside the ZIP.
const SAMPLE = { url: '/samples/flask.zip', file: 'flask.zip' }

// Each upload step's label once done, and while in progress.
const STEPS = [
  ['ZIP selected', 'ZIP selected'],
  ['Uploaded', 'Uploading…'],
  ['Parsed & indexed', 'Indexing…'],
  ['Ready to search', 'Ready to search'],
]

const HOW = [
  ['Upload a ZIP', 'Code is parsed into functions and classes on this machine.'],
  ['Ask in plain English', 'Search runs on the local index.'],
  ['See exact evidence', 'Ranked snippets with file paths and line numbers.'],
]

export default function App() {
  const [health, setHealth] = useState<Health | null>(null)
  // Every visit starts on the upload page, even if the server still holds an earlier index.
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null)
  const [search, setSearch] = useState<SearchResponse | null>(null)
  // Architecture module the search is limited to.
  const [scope, setScope] = useState<string | null>(null)
  const [busy, setBusy] = useState<Busy>('')
  const [error, setError] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [dragging, setDragging] = useState(false)
  const [replacing, setReplacing] = useState(false)
  // Number of upload STEPS completed for the chosen file, and whether the next one failed.
  const [stepsDone, setStepsDone] = useState(0)
  const [stepFailed, setStepFailed] = useState(false)
  const latest = useRef(0)
  const statusSeq = useRef(0)
  const fileInput = useRef<HTMLInputElement>(null)
  // Any newer file choice (or Start over) cancels a sample that is still downloading.
  const choiceSeq = useRef(0)
  const askForm = useRef<HTMLFormElement>(null)
  const query = useRef<HTMLInputElement>(null)
  // index.html sets the initial theme before first paint.
  const [theme, setTheme] = useState<Theme>(() =>
    document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light',
  )
  // Remembered separately so a choice holds for the visit even if storage is blocked.
  const themeChosen = useRef(savedTheme() !== null)

  useEffect(() => {
    document.documentElement.dataset.theme = theme
  }, [theme])

  // Follow the system setting until the user picks a theme.
  useEffect(() => {
    const follow = () => {
      if (!themeChosen.current) setTheme(darkQuery.matches ? 'dark' : 'light')
    }
    darkQuery.addEventListener('change', follow)
    return () => darkQuery.removeEventListener('change', follow)
  }, [])

  function toggleTheme() {
    const next = theme === 'dark' ? 'light' : 'dark'
    themeChosen.current = true
    setTheme(next)
    try {
      localStorage.setItem('theme', next)
    } catch {
      // Storage may be blocked; the choice then lasts for this visit only.
    }
  }

  // Re-syncs the repo opened in this visit after an error; never opens one by itself.
  // A newer status read or a successful upload makes pending status reads stale.
  const refreshStatus = () => {
    const id = ++statusSeq.current
    api<Status>('/status').then((s) => {
      if (id === statusSeq.current) setSnapshot((current) => current && s.snapshot)
    }, () => {})
  }

  useEffect(() => {
    api<Health>('/health').then(setHealth, (e: Error) => setError(`Backend unavailable: ${e.message}`))
  }, [])

  // "/" focuses the search box unless the user is already typing somewhere.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const input = query.current
      if (e.key !== '/' || e.metaKey || e.ctrlKey || e.altKey || !input || input.disabled) return
      const target = e.target
      if (target instanceof HTMLElement && (target.isContentEditable || target.closest('input, textarea, select'))) return
      e.preventDefault()
      input.focus()
      input.select()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  // A freshly indexed repo hands focus to search, the obvious next step.
  const snapshotId = snapshot?.snapshot_id
  useEffect(() => {
    if (snapshotId) query.current?.focus({ preventScroll: true })
  }, [snapshotId])

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
    if (!file?.size) return setError('Choose a ZIP file first.')
    send(file)
  }

  // Uploads the chosen file itself (not the form input), so drops and the sample need no input tricks.
  function send(zip: File) {
    const body = new FormData()
    body.append('file', zip)
    setStepsDone(1)
    setStepFailed(false)
    const request = () =>
      uploadSnapshot(body, () => setStepsDone(2)).catch((e: unknown) => {
        setStepFailed(true)
        throw e
      })
    run('upload', request, (s) => {
      statusSeq.current++
      setSnapshot(s)
      setSearch(null)
      setScope(null)
      setStepsDone(STEPS.length)
      setReplacing(false)
    })
  }

  function choose(next: File | null) {
    choiceSeq.current++
    setFile(next)
    setStepsDone(next ? 1 : 0)
    setStepFailed(false)
  }

  // The bundled sample goes through the normal upload, so every step is real.
  async function trySample() {
    const id = ++choiceSeq.current
    setError('')
    try {
      const response = await fetch(SAMPLE.url)
      if (!response.ok) throw new Error(`Sample unavailable (${response.status})`)
      const zip = new File([await response.blob()], SAMPLE.file, { type: 'application/zip' })
      if (id !== choiceSeq.current) return
      choose(zip)
      send(zip)
    } catch (e) {
      if (id === choiceSeq.current) setError((e as Error).message)
    }
  }

  function startOver() {
    latest.current++
    statusSeq.current++
    setBusy('')
    setError('')
    setSnapshot(null)
    setSearch(null)
    setScope(null)
    setReplacing(false)
    choose(null)
  }

  function ask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const q = String(form.get('q') ?? '').trim()
    if (!snapshot || !q) return
    const expand = form.get('expand') ? 'true' : 'false'
    const params = new URLSearchParams({ snapshot_id: snapshot.snapshot_id, q, expand })
    if (scope) params.set('scope', scope)
    run('search', () => api<SearchResponse>(`/search?${params}`), setSearch)
  }

  function drop(event: DragEvent<HTMLElement>) {
    event.preventDefault()
    event.stopPropagation()
    setDragging(false)
    if (busy || !event.dataTransfer.files.length) return
    choose(event.dataTransfer.files[0])
  }

  // Rendered synchronously first, so the submitted search already uses the new scope.
  function searchIn(next: string | null, text?: string) {
    flushSync(() => setScope(next))
    if (!query.current) return
    if (text !== undefined) query.current.value = text
    askForm.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    query.current.focus({ preventScroll: true })
    if (query.current.value.trim() && !busy) askForm.current?.requestSubmit()
  }

  function askExample(text: string) {
    if (!query.current) return
    query.current.value = text
    askForm.current?.requestSubmit()
  }

  const limitMb = health && Math.round(health.limits.max_zip_bytes / 2 ** 20)

  // Shown under the dropzone on the welcome stage.
  const runner = file && (
    <ol className="runner" aria-label="Upload progress" aria-live="polite">
      {STEPS.map(([label, working], i) => {
        const state =
          i < stepsDone ? 'done' : i > stepsDone ? 'todo' : stepFailed ? 'failed' : busy === 'upload' ? 'active' : 'todo'
        return (
          <li key={label} className={state} aria-current={state === 'active' ? 'step' : undefined}>
            <span className="runner-dot">
              {state === 'done' ? <Check /> : state === 'active' ? <Spinner /> : state === 'failed' ? '!' : i + 1}
            </span>
            <span className="runner-label">
              {state === 'active' ? working : label}
              <span className="visually-hidden">{state === 'todo' ? ' (pending)' : ` (${state})`}</span>
            </span>
          </li>
        )
      })}
    </ol>
  )

  // Rendered by both stages; only one copy is ever mounted.
  const uploadForm = (
    <form onSubmit={upload} className="upload">
      <label
        htmlFor="file"
        className={`dropzone${dragging ? ' dragging' : ''}${file ? ' has-file' : ''}${busy ? ' disabled' : ''}${busy === 'upload' ? ' uploading' : ''}`}
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
          type="file"
          accept=".zip,application/zip"
          className="visually-hidden"
          disabled={!!busy}
          // Cleared on open so picking the same file again (e.g. after a drop) still registers.
          onClick={(e) => (e.currentTarget.value = '')}
          onChange={(e) => choose(e.currentTarget.files?.[0] ?? null)}
        />
        <span className="drop-icon">
          {file ? <ZipIcon /> : <UploadIcon />}
        </span>
        {busy === 'upload' ? (
          <>
            <span className="drop-title">{stepsDone < 2 ? 'Uploading' : 'Indexing'} {file?.name ?? 'repository'}…</span>
            <span className="muted">
              {stepsDone < 2 ? 'Sending the ZIP to the local server' : 'Parsing files into searchable code regions'}
            </span>
          </>
        ) : file ? (
          <>
            <span className="drop-title">{file.name}</span>
            <span className="muted">{formatSize(file.size)} · click to choose another</span>
          </>
        ) : (
          <>
            <span className="drop-title">Drop a repository ZIP here</span>
            <span className="muted">or click to browse your files</span>
          </>
        )}
        {busy === 'upload' && <span className="progress" aria-hidden="true" />}
      </label>
      {!snapshot && runner}
      <div className="upload-actions">
        <p className="muted hint">
          Indexed locally, never executed.
          {limitMb && busy !== 'upload' ? ` Max ${limitMb} MB ZIP.` : ''}
          {!file && (
            <>
              {' '}
              <span className="nowrap">
                No ZIP handy?{' '}
                <button type="button" className="link" onClick={trySample}>
                  Try the Flask sample
                </button>
              </span>
            </>
          )}
        </p>
        <button className="primary" disabled={!!busy || !file}>
          {busy === 'upload' ? (
            <><Spinner /> {stepsDone < 2 ? 'Uploading…' : 'Indexing…'}</>
          ) : (
            <>Upload and index <ArrowIcon /></>
          )}
        </button>
      </div>
    </form>
  )

  const languages = health && (
    <ul className="langs" aria-label="Supported languages">
      {health.languages.map((lang) => <li key={lang}>{lang}</li>)}
    </ul>
  )

  const errorBanner = error && (
    <p role="alert" className="error banner">
      <AlertIcon />
      <span>{error}</span>
    </p>
  )

  return (
    <>
      <header className="topbar">
        <div className="topbar-inner">
          <div className="brand">
            <Logo />
            <span className="brand-name">InsideCode</span>
          </div>
          <div className="toolbar">
            <span className="tb-status local" title="Your code is indexed on this machine">
              <LockIcon />
              <span className="tb-label">Local index</span>
            </span>
            {health && (
              <span
                className={`tb-status${health.ai_configured ? ' ai-on' : ''}`}
                title={health.ai_configured ? 'AI explanations available on request' : 'Search-only mode'}
              >
                <SparkIcon />
                AI {health.ai_configured ? 'on' : 'off'}
              </span>
            )}
            <span className="toolbar-sep" aria-hidden="true" />
            <button
              type="button"
              className="tool theme-toggle"
              onClick={toggleTheme}
              aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
              title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
            >
              <SunIcon />
              <MoonIcon />
            </button>
          </div>
        </div>
      </header>

      <main>
        {!snapshot && (
          <div className="stage welcome">
            <div className="hero">
              <p className="eyebrow">
                <ShieldIcon /> Evidence-first code discovery
              </p>
              <h1>
                Find where things live in an <span className="gradient-text">unfamiliar codebase.</span>
              </h1>
              <p>
                Drop in a repository and ask questions in plain English. Every answer is exact code
                with its path and line numbers. AI explanations only when you ask.
              </p>
            </div>

            <section className="upload-card" aria-labelledby="upload-title">
              <h2 id="upload-title" className="visually-hidden">Upload a repository</h2>
              {uploadForm}
              {languages}
            </section>
            {errorBanner}

            <ul className="trust">
              <li><Check /> Indexed locally</li>
              <li><Check /> Never executed</li>
              <li><Check /> Cites exact lines</li>
            </ul>

            <ol className="how" aria-label="How it works">
              {HOW.map(([title, text], i) => (
                <li key={title}>
                  <span className="how-n" aria-hidden="true">{i + 1}</span>
                  <strong>{title}</strong>
                  <span className="muted">{text}</span>
                </li>
              ))}
            </ol>
          </div>
        )}

        {snapshot && (
          <div
            className="stage workspace"
            onDragEnter={(e) => {
              if (!busy && e.dataTransfer.types.includes('Files')) setReplacing(true)
            }}
            // Files dropped anywhere in the workspace go to the upload panel opened above.
            onDragOver={(e) => {
              if (e.dataTransfer.types.includes('Files')) e.preventDefault()
            }}
            onDrop={drop}
          >
            <section className="repo-card" aria-label="Indexed repository">
              <div className="repo-bar">
                <span className="repo-icon"><RepoIcon /></span>
                <div className="repo-meta">
                  <span className="repo-status"><span className="dot" aria-hidden="true" /> Indexed · ready to search</span>
                  <strong className="repo-name" title={snapshot.name}>{snapshot.name}</strong>
                </div>
                <ul className="repo-stats">
                  <li><LayersIcon /><span><strong>{snapshot.files}</strong> source files</span></li>
                  <li><CodeIcon /><span><strong>{snapshot.chunks}</strong> code regions</span></li>
                  <li><BracesIcon /><span><strong>{snapshot.definitions}</strong> functions &amp; classes</span></li>
                  <li title={snapshot.languages.join(', ')}>
                    <GlobeIcon />
                    <span><strong>{snapshot.languages.length}</strong> {snapshot.languages.length === 1 ? 'language' : 'languages'}<small>{snapshot.languages.join(' · ')}</small></span>
                  </li>
                </ul>
                <div className="repo-actions">
                  <button type="button" disabled={busy === 'upload'} onClick={startOver}>
                    <ResetIcon /> Start over
                  </button>
                  <button
                    type="button"
                    aria-expanded={replacing}
                    aria-controls="replace"
                    disabled={busy === 'upload'}
                    onClick={() => {
                      // Mount the panel synchronously so the picker opens within this click.
                      flushSync(() => {
                        setReplacing(!replacing)
                        choose(null)
                      })
                      if (!replacing) fileInput.current?.click()
                    }}
                  >
                    {replacing ? 'Cancel' : <><UploadIcon /> Upload another repo</>}
                  </button>
                </div>
              </div>

              {replacing && (
                <section id="replace" className="replace" aria-labelledby="replace-title">
                  <h2 id="replace-title" className="visually-hidden">Upload another repository</h2>
                  {uploadForm}
                </section>
              )}
            </section>

            <Architecture
              key={snapshot.snapshot_id}
              snapshotId={snapshot.snapshot_id}
              scope={scope}
              onScope={(module) => searchIn(module)}
              onSymbol={(symbol, module) => searchIn(module, symbol)}
            />

            <section className="ask" aria-labelledby="ask-title">
              <h1 id="ask-title">
                What are you <span className="gradient-text">looking for?</span>
              </h1>
              <p className="muted ask-sub">
                Ask in plain English or type a symbol. Every result cites exact lines.
              </p>
              <div className="palette">
                {scope && (
                  <div className="scope-chip">
                    Searching only in <code>{scope}</code>
                    <button
                      type="button"
                      className="scope-clear"
                      aria-label="Search the whole repository"
                      title="Search the whole repository"
                      onClick={() => searchIn(null)}
                    >
                      ×
                    </button>
                  </div>
                )}
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
                      aria-keyshortcuts="/"
                      disabled={!!busy}
                    />
                    <kbd className="kbd" aria-hidden="true" title="Press / to focus">/</kbd>
                  </div>
                  <button className="primary" disabled={!!busy}>
                    {busy === 'search' ? <><Spinner /> Searching…</> : 'Search'}
                  </button>
                </form>
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
              </div>
            </section>

            <div aria-live="polite" aria-busy={busy === 'search'} className="output">
              {errorBanner}
              {search ? (
                <Results search={search} aiReady={!!health?.ai_configured} onError={refreshStatus} />
              ) : (
                busy === 'search' && <Skeleton />
              )}
            </div>
          </div>
        )}
      </main>
    </>
  )
}

function Skeleton() {
  return (
    <div className="skeleton" aria-hidden="true">
      {[0, 1].map((i) => (
        <div key={i} className="skeleton-card">
          <span className="skeleton-bar w-40" />
          <span className="skeleton-bar w-25" />
          <span className="skeleton-block" />
        </div>
      ))}
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

const ResetIcon = () => <Icon d="M3 12a9 9 0 1 0 3-6.7L3 8M3 3v5h5" />
const LockIcon = () => <Icon d="M7 11V7a5 5 0 0 1 10 0v4M5 11h14v10H5z" />
const SparkIcon = () => <Icon d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9zM19 16l.7 1.8 1.8.7-1.8.7L19 21l-.7-1.8-1.8-.7 1.8-.7z" />
const Check = () => <Icon d="M20 6 9 17l-5-5" />
const SearchIcon = () => <Icon d="m21 21-4.3-4.3M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14z" />
const UploadIcon = () => <Icon d="M12 15V3m0 0-4 4m4-4 4 4M4 15v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4" />
const ShieldIcon = () => <Icon d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10zm-3-10 2 2 4-4" />
const RepoIcon = () => <Icon d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20V3H6.5A2.5 2.5 0 0 0 4 5.5v14zm0 0A2.5 2.5 0 0 0 6.5 22H20v-5" />
const ZipIcon = () => <Icon d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zm0 0v6h6M10 9h1m-1 4h1m-1 4h1" />
const LayersIcon = () => <Icon d="M12 2 2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" />
const CodeIcon = () => <Icon d="m16 18 6-6-6-6M8 6l-6 6 6 6" />
const BracesIcon = () => <Icon d="M8 3H7a2 2 0 0 0-2 2v5a2 2 0 0 1-2 2 2 2 0 0 1 2 2v5a2 2 0 0 0 2 2h1m8-18h1a2 2 0 0 1 2 2v5a2 2 0 0 0 2 2 2 2 0 0 0-2 2v5a2 2 0 0 1-2 2h-1" />
const GlobeIcon = () => <Icon d="M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
const ArrowIcon = () => <Icon d="M5 12h14m-6-6 6 6-6 6" />
const AlertIcon = () => <Icon d="M12 8v4m0 4h.01M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z" />
const SunIcon = () => (
  <Icon className="icon sun" d="M12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM12 2v2m0 16v2M4.93 4.93l1.41 1.41m11.32 11.32 1.41 1.41M2 12h2m16 0h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" />
)
const MoonIcon = () => <Icon className="icon moon" d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9z" />
const Spinner = () => <span className="spinner" aria-hidden="true" />

function Logo() {
  return (
    <svg className="logo" viewBox="0 0 32 32" aria-hidden="true">
      <defs>
        <linearGradient id="logo-fill" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" style={{ stopColor: 'var(--grad-from)' }} />
          <stop offset="1" style={{ stopColor: 'var(--grad-to)' }} />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="9" fill="url(#logo-fill)" />
      <g fill="none" stroke="#fff" strokeLinecap="round">
        <path d="M8 10h9M8 22h6" strokeWidth="2" opacity="0.5" />
        <path d="M8 16h7" strokeWidth="2.6" />
        <circle cx="20" cy="16" r="5" strokeWidth="2.2" />
        <path d="m23.6 19.6 3 3" strokeWidth="2.6" />
      </g>
      <circle cx="20" cy="16" r="1.8" fill="#fff" />
    </svg>
  )
}
