import { useEffect, useMemo, useRef, useState } from 'react'
import { api, post, type Explanation, type Result, type SearchResponse, type Source } from './api'
import './results.css'

type ResultsProps = { search: SearchResponse; aiReady: boolean; onError: () => void }

export default function Results({ search, aiReady, onError }: ResultsProps) {
  const ai = search.ai_note ? (
    <p className="ev-note">
      <Icon d={SPARKLE} />
      {search.ai_note}
    </p>
  ) : (
    search.suggested_terms.length > 0 && (
      <p className="ev-terms">
        <span className="muted">AI-suggested terms also searched:</span>
        {search.suggested_terms.map((t) => (
          <span key={t} className="pill accent ev-term">
            {t}
          </span>
        ))}
      </p>
    )
  )
  // A new search (different evidence) starts a fresh AI panel.
  const key = [search.snapshot_id, search.query, ...search.results.map((r) => r.id)].join('|')
  const panel = aiReady && <AIPanel key={key} search={search} />
  const count = search.results.length
  if (!count) {
    return (
      <section aria-label="Evidence" className="ev">
        {ai}
        <div className="empty ev-empty">
          <span className="ev-empty-icon">
            <Icon d={SEARCH} />
          </span>
          <p className="ev-empty-title">No matches for “{search.query}” in our index.</p>
          <p className="muted">
            That does not prove it is absent from the repository — try a function name or different
            words.
          </p>
        </div>
        {panel}
      </section>
    )
  }
  return (
    <section aria-label="Evidence" className="ev">
      <header className="ev-head">
        <h2>
          Evidence for <span className="ev-q">“{search.query}”</span>
        </h2>
        <span className="pill">
          {count} result{count === 1 ? '' : 's'}
        </span>
      </header>
      {ai}
      <ol className="ev-list">
        {search.results.map((r, i) => (
          <EvidenceCard
            key={`${search.snapshot_id}-${r.id}`}
            result={r}
            rank={i + 1}
            label={aiReady && i < MAX_EVIDENCE ? `E${i + 1}` : ''}
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

// Small inline icons (24×24 stroke paths); always decorative.
const SPARKLE = 'M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9zM19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z'
const COPY = 'M9 9h11v11H9zM5 15H4V4h11v1'
const CHECK = 'M5 12.5l4.5 4.5L19 7'
const LOCK = 'M6 11h12v9H6zM8.5 11V8a3.5 3.5 0 0 1 7 0v3'
const WARN = 'M12 3.5l9.5 16.5h-19zM12 10v4.5M12 17.5v.01'
const SEARCH = 'M4 11a7 7 0 1 0 14 0a7 7 0 1 0-14 0M21 21l-4.5-4.5'
const EXPAND = 'M8 9l4-4 4 4M8 15l4 4 4-4'
const COLLAPSE = 'M8 5l4 4 4-4M8 19l4-4 4 4'

function Icon({ d }: { d: string }) {
  return (
    <svg className="icon" viewBox="0 0 24 24" aria-hidden="true">
      <path d={d} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}


function jumpTo(chunkId: number | undefined) {
  const card = document.getElementById(`ev-${chunkId}`)
  if (!card) return
  const still = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  card.scrollIntoView({ behavior: still ? 'auto' : 'smooth', block: 'center' })
  card.focus({ preventScroll: true })
  card.classList.add('ev-flash')
  card.addEventListener('animationend', () => card.classList.remove('ev-flash'), { once: true })
}

// Nothing leaves the machine until the user reviews the exact context and presses Send.
function AIPanel({ search }: { search: SearchResponse }) {
  const [context, setContext] = useState('')
  const [explanation, setExplanation] = useState<Explanation | null>(null)
  const [general, setGeneral] = useState('')
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const evidence = {
    snapshot_id: search.snapshot_id,
    question: search.query,
    chunk_ids: search.results.slice(0, MAX_EVIDENCE).map((r) => r.id),
  }

  async function call<T>(path: string, body: unknown, apply: (value: T) => void) {
    setBusy(path === '/explain/context' ? 'Preparing preview…' : 'Waiting for AI…')
    setError('')
    try {
      apply(await post<T>(path, body))
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy('')
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
      <header className="ai-head">
        <span className="ai-icon">
          <Icon d={SPARKLE} />
        </span>
        <div>
          <h2>
            AI help <span className="ai-optional">(optional)</span>
          </h2>
          <p className="muted hint ai-privacy">
            <Icon d={LOCK} />
            Nothing is sent to Featherless until you choose. AI text can be wrong; check the cited
            code.
          </p>
        </div>
      </header>
      <div className="row ai-actions">
        {evidence.chunk_ids.length > 0 && (
          <button className="primary" disabled={!!busy} onClick={prepare}>
            Explain the top {evidence.chunk_ids.length} results…
          </button>
        )}
        <button disabled={!!busy} onClick={ask}>
          General programming answer <span className="ai-hint">(sends only the question)</span>
        </button>
      </div>
      {context && (
        <div className="ai-step">
          <p className="ai-label">
            <Icon d={WARN} />
            This exact text will be sent with your question:
          </p>
          <pre className="ai-context" tabIndex={0}>
            {context}
          </pre>
          <div className="row ai-actions">
            <button className="primary" disabled={!!busy} onClick={send}>
              Send to Featherless
            </button>
            <button disabled={!!busy} className="link" onClick={() => setContext('')}>
              Cancel
            </button>
          </div>
        </div>
      )}
      {busy && (
        <p className="ai-wait" role="status">
          <span className="spinner" aria-hidden="true" />
          {busy}
        </p>
      )}
      {error && (
        <p role="alert" className="banner error ai-error">
          {error}
        </p>
      )}
      {explanation && (
        <div className="ai-result">
          <h3>Explanation from the selected code</h3>
          {explanation.note && (
            <p className="ai-callout">
              <Icon d={WARN} />
              {explanation.note}
            </p>
          )}
          <ul className="ai-points">
            {explanation.points.map((p, i) => (
              <li key={i}>
                <p>{p.text}</p>
                <div className="ai-cites">
                  {p.evidence.map((c) => (
                    <button
                      key={c.id}
                      type="button"
                      className="ai-cite"
                      title="Jump to this evidence"
                      onClick={() => jumpTo(c.chunk_id)}
                    >
                      <b>[{c.id}]</b> {c.path}:{c.start_line}–{c.end_line}
                      {c.is_test && ' (test)'}
                    </button>
                  ))}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
      {general && (
        <div className="ai-result">
          <h3>
            <span className="pill">General answer — not based on this repository</span>
          </h3>
          <p className="ai-general">{general}</p>
        </div>
      )}
    </section>
  )
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  useEffect(() => {
    if (!copied) return
    const timer = setTimeout(() => setCopied(false), 1500)
    return () => clearTimeout(timer)
  }, [copied])
  const copy = () => navigator.clipboard?.writeText(text).then(() => setCopied(true), () => {})
  return (
    <>
      <span className="ev-copied" role="status">
        {copied && 'Copied'}
      </span>
      <button type="button" className="ev-icon-btn" aria-label={`Copy ${text}`} title="Copy path:line" onClick={copy}>
        <Icon d={copied ? CHECK : COPY} />
      </button>
    </>
  )
}

type CardProps = { result: Result; rank: number; label: string; snapshotId: string; onError: () => void }

function EvidenceCard({ result, rank, label, snapshotId, onError }: CardProps) {
  const [open, setOpen] = useState(false)
  const [source, setSource] = useState<Source | null>(null)
  const [error, setError] = useState('')
  const lines: [number, number] = [result.start_line, result.end_line]
  const slash = result.path.lastIndexOf('/') + 1

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
    <li className={rank === 1 ? 'ev-card ev-top' : 'ev-card'} id={`ev-${result.id}`} tabIndex={-1}>
      <div className="ev-card-head">
        <span className="ev-rank" aria-hidden="true">
          {rank}
        </span>
        <code className="ev-path" title={result.path}>
          <span className="ev-dir">{result.path.slice(0, slash)}</span>
          <span className="ev-file">{result.path.slice(slash)}</span>
          <span className="ev-range">
            :{result.start_line}–{result.end_line}
          </span>
        </code>
        {label && (
          <span className="ev-label" title="Label used in AI citations">
            {label}
          </span>
        )}
        <CopyButton text={`${result.path}:${result.start_line}`} />
      </div>
      <div className="ev-meta">
        {rank === 1 && <span className="pill accent ev-best">Top match</span>}
        {result.symbol && <code className="ev-tag ev-symbol">{result.symbol}</code>}
        {result.is_test && <span className="ev-tag ev-test">test</span>}
        {result.reasons.map((r) => (
          <span key={r} className="ev-tag ev-reason">
            {r}
          </span>
        ))}
      </div>
      {open && source ? (
        <CodeLines text={source.text} path={result.path} first={1} highlight={lines} scroll />
      ) : (
        <CodeLines text={result.text} path={result.path} first={result.start_line} />
      )}
      <div className="ev-foot">
        <button className="ev-btn" aria-expanded={open} onClick={toggle}>
          <Icon d={open ? COLLAPSE : EXPAND} />
          {open ? 'Show snippet only' : 'Show in full file'}
        </button>
        {open && !source && !error && <span className="muted">Loading file…</span>}
      </div>
      {open && error && (
        <p role="alert" className="banner error ev-error">
          {error}
        </p>
      )}
    </li>
  )
}

// Tiny highlighter shared by all languages: tokens are rendered as React text, never as HTML.
const KEYWORDS =
  'False|None|True|and|as|assert|async|await|break|case|catch|class|const|continue|def|defer|del|elif|else|end|enum|except|export|extends|false|final|finally|fn|for|from|func|function|go|if|impl|implements|import|in|interface|is|lambda|let|match|module|mut|new|nil|not|null|or|package|pass|private|protected|pub|public|raise|return|self|static|struct|switch|this|throw|trait|true|try|type|use|var|void|while|with|yield'
const pattern = (comment: string, single: string) =>
  new RegExp(
    String.raw`(${comment})|([rRbBuUfF]{0,2}(?:"""[\s\S]*?(?:"""|$)|'''[\s\S]*?(?:'''|$)|"(?:\\.|[^"\\\n])*"?|${single}|\x60[^\x60]*\x60?))` +
      String.raw`|(@[\w.]+)|\b(\d[\w.]*)|\b(${KEYWORDS})\b`,
    'g',
  )
// An unclosed string ends at the line end, so every match attempt succeeds and scanning stays linear.
const QUOTED = String.raw`'(?:\\.|[^'\\\n])*'?`
const RUST_CHAR = String.raw`'(?:\\.|[^'\\\n])'` // `'a` alone is a Rust lifetime, not a string
const SLASH = String.raw`//.*|/\*[\s\S]*?(?:\*/|$)`
const HASH_COMMENTS = pattern('#.*', QUOTED)
const SLASH_COMMENTS = pattern(SLASH, QUOTED)
const RUST = pattern(SLASH, RUST_CHAR)
const DEFINES = new Set(['def', 'class', 'function', 'func', 'fn', 'struct', 'interface', 'enum', 'trait', 'module'])
const TOKEN_CLASSES = ['com', 'str', 'dec', 'num', 'kw']
type Token = [kind: string, text: string]

function tokenize(text: string, path: string): Token[][] {
  const regex = /\.(py|rb)$/i.test(path) ? HASH_COMMENTS : /\.rs$/i.test(path) ? RUST : SLASH_COMMENTS
  const lines: Token[][] = [[]]
  const push = (part: string, kind = '') =>
    part.split('\n').forEach((piece, i) => {
      if (i) lines.push([])
      if (piece) lines[lines.length - 1].push([kind, piece])
    })
  // The name after def/class sits in the plain text that follows; marking it here keeps the regex linear.
  let named = false
  const plain = (gap: string) => {
    const def = named ? /^(\s+)(\w+)/.exec(gap) : null
    if (!def) return push(gap)
    push(def[1])
    push(def[2], 'fn')
    push(gap.slice(def[0].length))
  }
  let last = 0
  for (const m of text.matchAll(regex)) {
    plain(text.slice(last, m.index))
    const kind = TOKEN_CLASSES[m.slice(1).findIndex(Boolean)]
    push(m[0], kind)
    named = kind === 'kw' && DEFINES.has(m[0])
    last = m.index + m[0].length
  }
  plain(text.slice(last))
  return lines
}

type CodeProps = { text: string; path: string; first: number; highlight?: [number, number]; scroll?: boolean }

function CodeLines({ text, path, first, highlight, scroll }: CodeProps) {
  const box = useRef<HTMLPreElement>(null)
  useEffect(() => {
    const pre = box.current
    const hit = pre?.querySelector<HTMLElement>('.ev-hl')
    if (scroll && pre && hit) pre.scrollTop = hit.offsetTop - pre.clientHeight / 3
  }, [scroll])
  const lines = useMemo(() => tokenize(text.replace(/\n$/, ''), path), [text, path])
  return (
    <pre ref={box} className={scroll ? 'ev-code full' : 'ev-code'} tabIndex={0}>
      <code className="ev-code-inner">
        {lines.map((tokens, i) => {
          const n = first + i
          const hit = highlight && n >= highlight[0] && n <= highlight[1]
          return (
            <span key={n} className={hit ? 'ev-line ev-hl' : 'ev-line'}>
              <span className="ev-n">{n}</span>
              {tokens.length
                ? tokens.map(([kind, t], j) => (
                    <span key={j} className={kind && `t-${kind}`}>
                      {t}
                    </span>
                  ))
                : ' '}
            </span>
          )
        })}
      </code>
    </pre>
  )
}
