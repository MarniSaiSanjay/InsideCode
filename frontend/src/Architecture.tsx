import { useEffect, useId, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { api, type ArchEdge, type ArchModule, type ArchStep, type Architecture as Overview, type FlowStep } from './api'
import './architecture.css'

type Props = {
  snapshotId: string
  scope: string | null
  onScope: (module: string) => void
  onSymbol: (symbol: string, module: string) => void
}

type Box = {
  left: number
  right: number
  top: number
  bottom: number
  x: number
}
type Line = { edge: ArchEdge; back?: ArchEdge; d: string }

const ROW_GAP = 56
const LANE = 8 // space between parallel arrows
const CLEAR = 26 // space between a box and the nearest arrow lane, leaving a straight run into the arrowhead

const fileName = (path: string) => path.slice(path.lastIndexOf('/') + 1)
const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`

/** Architecture of the indexed repository: module map with dependency arrows, and key call flows. */
export default function Architecture({ snapshotId, scope, onScope, onSymbol }: Props) {
  const [data, setData] = useState<Overview | null>(null)
  const [failed, setFailed] = useState('')
  const [open, setOpen] = useState(true)
  const [view, setView] = useState<'map' | 'flows'>('map')
  const [hovered, setHovered] = useState<string | null>(null)

  // The parent keys this component by snapshot, so each repository starts fresh.
  useEffect(() => {
    let live = true
    api<Overview>(`/snapshots/${snapshotId}/architecture`).then(
      (d) => live && setData(d),
      (e: Error) => live && setFailed(e.message),
    )
    return () => {
      live = false
    }
  }, [snapshotId])

  const modules = new Map(data?.modules.map((m) => [m.id, m]))
  const neighbours = new Set(
    data?.edges.flatMap((e) => (e.source === hovered ? [e.target] : e.target === hovered ? [e.source] : [])),
  )

  return (
    <section className="arch" aria-labelledby="arch-title">
      <div className="arch-head">
        <button
          type="button"
          className="arch-toggle"
          aria-expanded={open}
          aria-controls="arch-body"
          onClick={() => setOpen(!open)}
        >
          <svg className="icon arch-chevron" viewBox="0 0 24 24" aria-hidden="true">
            <path d="m6 9 6 6 6-6" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </svg>
          <span id="arch-title">Architecture</span>
        </button>
        {data && (
          <span className="arch-meta">
            {plural(data.modules.length, 'module')} · {plural(data.edges.length, 'link')} · from real imports &amp;
            calls
          </span>
        )}
        {open && !!data?.flows.length && (
          <div className="arch-tabs" role="group" aria-label="Architecture view">
            <button type="button" aria-pressed={view === 'map'} onClick={() => setView('map')}>
              Module map
            </button>
            <button type="button" aria-pressed={view === 'flows'} onClick={() => setView('flows')}>
              Key flows <span className="arch-count">{data.flows.length}</span>
            </button>
          </div>
        )}
      </div>

      {open && (
        <div id="arch-body" className="arch-body">
          {failed && <p className="arch-note">Architecture unavailable: {failed}</p>}
          {!data && !failed && <p className="arch-note">Mapping modules…</p>}
          {data && !data.modules.length && <p className="arch-note">No source files to map.</p>}
          {!!data?.stack.length && (
            <ul className="arch-stack" aria-label="Detected stack">
              {data.stack.map((s) => (
                <li key={s.role} className={`arch-role role-${s.role.toLowerCase()}`}>
                  <b>{s.role}</b> {s.labels.join(' · ')}
                </li>
              ))}
            </ul>
          )}

          {data && view === 'map' && (
            <>
              {data.groups.map((group) => (
                <GroupMap
                  key={group.rows.flat().join()}
                  title={data.groups.length > 1 ? group.title : ''}
                  rows={group.rows}
                  edges={data.edges}
                  hovered={hovered}
                  renderModule={(id) => {
                    const m = modules.get(id)
                    if (!m) return null
                    const state = id === hovered || neighbours.has(id) ? 'linked' : hovered ? 'faded' : ''
                    return (
                      <ModuleBox
                        module={m}
                        state={`${state} ${scope === id ? 'active' : ''}`}
                        onHover={setHovered}
                        onScope={onScope}
                        onSymbol={onSymbol}
                      />
                    )
                  }}
                />
              ))}
              {!!data.modules.length && (
                <p className="arch-hint">
                  Arrows point from a module to the code it imports or calls. Click a module to search only inside it,
                  or a function to find it.
                </p>
              )}
            </>
          )}

          {data && view === 'flows' && <Flows flows={data.flows} modules={modules} onSymbol={onSymbol} />}
        </div>
      )}
    </section>
  )
}

function ModuleBox({
  module: m,
  state,
  onHover,
  onScope,
  onSymbol,
}: {
  module: ArchModule
  state: string
  onHover: (id: string | null) => void
  onScope: (module: string) => void
  onSymbol: (symbol: string, module: string) => void
}) {
  return (
    <div
      className={`arch-module ${state}`}
      data-module={m.id}
      onMouseEnter={() => onHover(m.id)}
      onMouseLeave={() => onHover(null)}
      onFocus={() => onHover(m.id)}
      onBlur={() => onHover(null)}
    >
      <button type="button" className="arch-module-main" title={`Search only in ${m.id}`} onClick={() => onScope(m.id)}>
        <strong>{m.label}</strong>
        <code>{m.id}</code>
      </button>
      <span className="arch-module-meta">
        {plural(m.files, 'file')} · {m.language || 'other'}
      </span>
      {(m.entry.length > 0 || m.hub || m.stack.length > 0) && (
        <span className="arch-badges">
          {m.entry.length > 0 && (
            <span className="arch-badge entry" title={`Entry point: ${m.entry.join(', ')}`}>
              Entry
            </span>
          )}
          {m.hub && (
            <span className="arch-badge hub" title="Used by the most other modules">
              Hub
            </span>
          )}
          {m.stack.map((label) => (
            <span key={label} className="arch-badge">
              {label}
            </span>
          ))}
        </span>
      )}
      {m.key.length > 0 && (
        <ul className="arch-key" aria-label={`Key code in ${m.label}`}>
          {m.key.map((k) => (
            <li key={`${k.path}:${k.symbol}`}>
              <button type="button" title={`${k.path}:${k.line}`} onClick={() => onSymbol(k.symbol, m.id)}>
                <span className={`arch-kind ${k.kind}`} aria-hidden="true">
                  {k.kind === 'class' ? 'C' : 'ƒ'}
                </span>
                {k.symbol}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

/** Rows of module boxes with SVG arrows measured from their rendered positions (edges of other groups are skipped). */
function GroupMap({
  title,
  rows,
  edges,
  hovered,
  renderModule,
  lit = (e) => e.source === hovered || e.target === hovered,
  describe = (e) =>
    `${e.source} → ${e.target}: ${[e.imports && plural(e.imports, 'import'), e.calls && plural(e.calls, 'call')].filter(Boolean).join(', ')}`,
}: {
  title: string
  rows: string[][]
  edges: ArchEdge[]
  hovered: string | null
  renderModule: (id: string) => ReactNode
  lit?: (edge: ArchEdge) => boolean
  describe?: (edge: ArchEdge) => string
}) {
  const frame = useRef<HTMLDivElement>(null)
  const [{ lines, gap }, setLayout] = useState<{ lines: Line[]; gap: number }>({ lines: [], gap: ROW_GAP })
  const arrow = useId()

  useLayoutEffect(() => {
    const el = frame.current
    if (!el) return
    const observer = new ResizeObserver(() => setLayout(route(el, edges)))
    observer.observe(el)
    return () => observer.disconnect()
  }, [edges])

  return (
    <div className="arch-group">
      {title && <h3 className="arch-group-title">{title}</h3>}
      <div className="arch-map" ref={frame} style={{ rowGap: gap }}>
        <svg className={`arch-lines ${hovered ? 'dim' : ''}`} aria-hidden="true">
          <defs>
            {['', 'on'].map((state) => (
              <marker
                key={state}
                id={arrow + state}
                className={state}
                viewBox="0 0 10 10"
                refX="9"
                refY="5"
                markerUnits="userSpaceOnUse"
                markerWidth="12"
                markerHeight="12"
                orient="auto-start-reverse"
              >
                <path d="M0 0.5 10 5 0 9.5 2.5 5z" />
              </marker>
            ))}
          </defs>
          {lines.map(({ edge, back, d }) => {
            const on = lit(edge)
            const head = `url(#${CSS.escape(arrow + (on ? 'on' : ''))})`
            return (
              <path
                key={`${edge.source}>${edge.target}`}
                d={d}
                markerEnd={head}
                markerStart={back && head}
                className={on ? 'on' : ''}
                strokeWidth={Math.min(
                  1.2 + Math.log2(edge.imports + edge.calls + (back ? back.imports + back.calls : 0)),
                  3.5,
                )}
              >
                <title>{[edge, back].map((e) => e && `${describe(e)}\n`)}</title>
              </path>
            )
          })}
        </svg>
        {rows.map((row) => (
          <div key={row.join()} className="arch-row">
            {row.map((id) => (
              <div key={id} className="arch-cell">
                {renderModule(id)}
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}

/**
 * Arrows between boxes, returned with the row gap they need. Rows link with rounded elbows, each on its own lane in
 * the gap above the lower box, ordered so they do not cross; neighbours in a row link straight across, and farther
 * boxes in a row link with brackets below it.
 */
function route(frame: HTMLElement, edges: ArchEdge[]): { lines: Line[]; gap: number } {
  const base = frame.getBoundingClientRect()
  const boxes = new Map<string, Box>()
  for (const node of frame.querySelectorAll<HTMLElement>('[data-module]')) {
    const r = node.getBoundingClientRect()
    const box = {
      left: r.left - base.left,
      right: r.right - base.left,
      top: r.top - base.top,
      bottom: r.bottom - base.top,
    }
    boxes.set(node.dataset.module!, { ...box, x: (box.left + box.right) / 2 })
  }
  const all = [...boxes.values()]
  // Links both ways between two modules share one double-headed arrow.
  const byKey = new Map(edges.map((e) => [`${e.source}>${e.target}`, e]))
  const placed = edges.flatMap((edge) => {
    const a = boxes.get(edge.source)
    const b = boxes.get(edge.target)
    const back = byKey.get(`${edge.target}>${edge.source}`)
    if (!a || !b || (back && edge.source > edge.target)) return []
    const side = b.top >= a.bottom - 1 ? 'down' : b.bottom <= a.top + 1 ? 'up' : 'same'
    const [l, r] = a.x < b.x ? [a, b] : [b, a]
    const between = all.some((c) => c.x > l.x && c.x < r.x && c.top < l.bottom && c.bottom > l.top)
    const key = `${edge.source}>${edge.target}`
    return [{ key, edge, back, a, b, side: side === 'same' && !between ? 'beside' : side }]
  })

  // Spread the ends meeting one side of a box, ordered by where the other end lies.
  const offsets = new Map<string, number>()
  const ends = new Map<string, { key: string; x: number; width: number }[]>()
  const addEnd = (side: string, key: string, x: number, width: number) =>
    ends.set(side, [...(ends.get(side) ?? []), { key, x, width }])
  for (const { key, edge, a, b, side } of placed) {
    if (side === 'beside') continue
    addEnd(`${edge.source}:${side === 'up' ? 'top' : 'bottom'}`, `${key}:out`, b.x, a.right - a.left)
    addEnd(`${edge.target}:${side === 'down' ? 'top' : 'bottom'}`, `${key}:in`, a.x, b.right - b.left)
  }
  for (const list of ends.values()) {
    list.sort((p, q) => p.x - q.x)
    const step = list.length > 1 ? Math.min(26, (list[0].width * 0.7) / (list.length - 1)) : 0
    list.forEach((p, i) => offsets.set(p.key, (i - (list.length - 1) / 2) * step))
  }
  const xs = new Map(
    placed.map(({ key, a, b }) => [
      key,
      [a.x + (offsets.get(`${key}:out`) ?? 0), b.x + (offsets.get(`${key}:in`) ?? 0)] as const,
    ]),
  )

  // A lane sits one step past every lane it overlaps. Elbows are counted up from the lower row, taking first the
  // ones whose turn is nearest that row's box (so no turn crosses another's drop); brackets down from their row.
  const lanes = new Map<string, number>()
  const stack = (list: { key: string; from: number; to: number }[]) => {
    const done: { from: number; to: number; lane: number }[] = []
    for (const { key, from, to } of list) {
      const lane = Math.max(-1, ...done.filter((d) => d.from < to + LANE && from < d.to + LANE).map((d) => d.lane)) + 1
      done.push({ from, to, lane })
      lanes.set(key, lane)
    }
    return done.length ? Math.max(...done.map((d) => d.lane)) + 1 : 0
  }
  const groups = (side: (s: string) => boolean, at: (p: (typeof placed)[number]) => number) => {
    const found = new Map<number, typeof placed>()
    for (const p of placed.filter((p) => side(p.side)))
      found.set(Math.round(at(p)), [...(found.get(Math.round(at(p))) ?? []), p])
    return found
  }
  let elbows = 0
  for (const list of groups(
    (s) => s === 'down' || s === 'up',
    (p) => (p.side === 'down' ? p.b.top : p.a.top),
  ).values()) {
    const turns = list.flatMap(({ key, side }) => {
      const [x1, x2] = xs.get(key)!
      const [upper, lower] = side === 'down' ? [x1, x2] : [x2, x1]
      return Math.abs(lower - upper) < 1 ? [] : [{ key, upper, lower, from: Math.min(x1, x2), to: Math.max(x1, x2) }]
    })
    // heading left, the turn farthest right is nearest the lower row; heading right, the one farthest left
    const left = turns.filter((t) => t.lower < t.upper).sort((p, q) => q.upper - p.upper)
    const right = turns.filter((t) => t.lower > t.upper).sort((p, q) => p.upper - q.upper)
    elbows = Math.max(elbows, stack([...left, ...right]))
  }
  const lastRow = Math.round(Math.max(...all.map((b) => b.bottom)))
  let brackets = 0
  for (const [row, list] of groups(
    (s) => s === 'same',
    (p) => Math.max(p.a.bottom, p.b.bottom),
  )) {
    const loops = list.map(({ key, a, b }) => ({ key, from: Math.min(a.x, b.x), to: Math.max(a.x, b.x) }))
    const count = stack(loops.sort((p, q) => p.to - p.from - (q.to - q.from)))
    if (row < lastRow) brackets = Math.max(brackets, count)
  }
  const gap = Math.max(ROW_GAP, 2 * CLEAR + Math.max(0, elbows - 1) * LANE + (brackets && CLEAR + brackets * LANE))

  const tip = 3 // keep arrow tips just off the box border
  const elbow = (x1: number, y1: number, x2: number, y: number, y2: number) => {
    if (Math.abs(x2 - x1) < 1) return `M${x1} ${y1} V${y2}`
    const r = Math.min(8, Math.abs(x2 - x1) / 2, Math.abs(y - y1), Math.abs(y2 - y))
    const [dx, dy1, dy2] = [Math.sign(x2 - x1), Math.sign(y - y1), Math.sign(y2 - y)]
    return (
      `M${x1} ${y1} V${y - dy1 * r} Q${x1} ${y} ${x1 + dx * r} ${y} ` +
      `H${x2 - dx * r} Q${x2} ${y} ${x2} ${y + dy2 * r} V${y2}`
    )
  }
  const lines = placed.map(({ key, edge, back, a, b, side }) => {
    const [x1, x2] = xs.get(key)!
    const lane = lanes.get(key) ?? 0
    if (side === 'beside') {
      const y = (Math.max(a.top, b.top) + Math.min(a.bottom, b.bottom)) / 2
      const [s, t] = a.x < b.x ? [a.right + tip, b.left - tip] : [a.left - tip, b.right + tip]
      return { edge, back, d: `M${s} ${y} H${t}` }
    }
    if (side === 'same') {
      const y = Math.max(a.bottom, b.bottom) + CLEAR + lane * LANE
      return { edge, back, d: elbow(x1, a.bottom + tip, x2, y, b.bottom + tip) }
    }
    const lower = side === 'down' ? b.top : a.top
    const y = lower - CLEAR - lane * LANE
    const [y1, y2] = side === 'down' ? [a.bottom + tip, b.top - tip] : [a.top - tip, b.bottom + tip]
    return { edge, back, d: elbow(x1, y1, x2, y, y2) }
  })
  return { lines, gap }
}

/** A call between two flow steps: the line it is made on, and the flows (by index) that take it. */
type FlowEdge = ArchEdge & { line: number | null; flows: number[] }

/** The key flows merged into one call graph: steps shared by several flows appear once, callers above callees. */
function Flows({
  flows,
  modules,
  onSymbol,
}: {
  flows: FlowStep[][]
  modules: Map<string, ArchModule>
  onSymbol: (symbol: string, module: string) => void
}) {
  // A hovered step, or a hovered flow (by index) to trace its whole path.
  const [hovered, setHovered] = useState<string | number | null>(null)
  const graph = useMemo(() => {
    const id = (s: ArchStep) => `${s.path}:${s.symbol}`
    const steps = new Map<string, FlowStep>()
    const depth = new Map<string, number>()
    const inFlows = new Map<string, number[]>()
    const counts = new Map<string, FlowEdge>()
    flows.forEach((flow, f) =>
      flow.forEach((s, i) => {
        steps.set(id(s), s)
        depth.set(id(s), Math.max(depth.get(id(s)) ?? 0, i))
        inFlows.set(id(s), [...(inFlows.get(id(s)) ?? []), f])
        if (i === 0) return
        const from = flow[i - 1]
        const key = `${id(from)}>${id(s)}`
        const edge = counts.get(key) ?? { source: id(from), target: id(s), imports: 0, calls: 0, line: null, flows: [] }
        counts.set(key, { ...edge, calls: edge.calls + 1, line: from.calls_at, flows: [...edge.flows, f] })
      }),
    )
    const edges = [...counts.values()]
    // Pull callers down to sit just above their nearest callee, so arrows rarely skip a row.
    for (const node of [...depth.keys()].sort((a, b) => depth.get(b)! - depth.get(a)!)) {
      const below = edges.filter((e) => e.source === node).map((e) => depth.get(e.target)!)
      if (below.length) depth.set(node, Math.max(depth.get(node)!, Math.min(...below) - 1))
    }
    const rows: string[][] = []
    for (const [node, d] of depth) (rows[d] ??= []).push(node)
    const files = new Set(flows.flat().map((s) => s.path)).size
    const manyModules = new Set(flows.flat().map((s) => s.module)).size > 1
    return { steps, edges, rows: rows.filter(Boolean), inFlows, files, manyModules }
  }, [flows])

  const isLit = (e: ArchEdge) =>
    typeof hovered === 'number' ? (e as FlowEdge).flows.includes(hovered) : e.source === hovered || e.target === hovered
  const litNodes = new Set(graph.edges.filter(isLit).flatMap((e) => [e.source, e.target]))
  const hover = (value: string | number | null) => ({
    onMouseEnter: () => setHovered(value),
    onMouseLeave: () => setHovered(null),
    onFocus: () => setHovered(value),
    onBlur: () => setHovered(null),
  })

  return (
    <>
      <ol className="flow-legend">
        {flows.map((flow, f) => (
          <li key={f}>
            <button
              type="button"
              className={hovered === f ? 'on' : ''}
              title={flow.map((s) => s.symbol).join(' → ')}
              {...hover(f)}
            >
              <span className={`flow-tag flow-${f}`}>{f + 1}</span>
              <span>
                {flow[0].symbol} → {flow.at(-1)!.symbol}
              </span>
              <small>{plural(flow.length, 'step')}</small>
            </button>
          </li>
        ))}
      </ol>
      <GroupMap
        title=""
        rows={graph.rows}
        edges={graph.edges}
        hovered={hovered === null ? null : String(hovered)}
        lit={isLit}
        describe={(e) => {
          const edge = e as FlowEdge
          const from = graph.steps.get(e.source)!
          return `${from.symbol} calls ${graph.steps.get(e.target)!.symbol} at ${fileName(from.path)}:${edge.line} · flow ${edge.flows.map((f) => f + 1).join(', ')}`
        }}
        renderModule={(node) => {
          const s = graph.steps.get(node)!
          const doc = s.kind === 'module' ? 'Top-level code that runs when the file loads' : s.doc
          const state = node === hovered || litNodes.has(node) ? 'linked' : hovered !== null ? 'faded' : ''
          return (
            <div className={`arch-module arch-step ${state}`} data-module={node} {...hover(node)}>
              <button
                type="button"
                className="arch-module-main"
                title={`${doc ? `${doc}\n\n` : ''}Find ${s.symbol} (${s.path}:${s.line})`}
                onClick={() => onSymbol(s.symbol, s.module)}
              >
                <span className="arch-step-head">
                  <span className={`arch-kind ${s.kind}`} aria-hidden="true">
                    {s.kind === 'class' ? 'C' : s.kind === 'module' ? '▤' : 'ƒ'}
                  </span>
                  <code className="arch-step-symbol">{s.symbol}</code>
                  {graph.inFlows.get(node)!.map((f) => (
                    <span key={f} className={`flow-tag flow-${f}`} title={`In flow ${f + 1}`}>
                      {f + 1}
                    </span>
                  ))}
                </span>
                {doc && <span className="arch-step-doc">{doc}</span>}
                <span className="arch-module-meta">
                  {fileName(s.path)}:{s.line}–{s.end} · {plural(s.end - s.line + 1, 'line')}
                  {graph.manyModules && ` · ${modules.get(s.module)?.label ?? s.module}`}
                </span>
              </button>
            </div>
          )
        }}
      />
      <p className="arch-hint">
        {plural(graph.steps.size, 'step')} across {plural(graph.files, 'file')}. Arrows point to the function called
        (hover one for its line). Hover a flow to trace it; click a step to find it.
      </p>
    </>
  )
}
