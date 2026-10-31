export type Health = {
  status: string
  fts5: boolean
  ai_configured: boolean
  limits: Record<string, number>
  languages: string[]
}

export type Snapshot = {
  snapshot_id: string
  name: string
  files: number
  chunks: number
  definitions: number
  languages: string[]
}

export type Status = { importing: boolean; snapshot: Snapshot | null }

export type Result = {
  id: number
  file_id: number
  path: string
  kind: string
  symbol: string | null
  start_line: number
  end_line: number
  text: string
  is_test: boolean
  reasons: string[]
}

export type SearchResponse = {
  snapshot_id: string
  query: string
  scope: string | null
  suggested_terms: string[]
  ai_note: string | null
  results: Result[]
}

export type ArchStep = { symbol: string; kind: string; path: string; line: number; module: string }

/** A step of a key flow: its doc summary, last line, and the line where it calls the next step. */
export type FlowStep = ArchStep & { end: number; doc: string | null; calls_at: number | null }

export type ArchModule = {
  id: string
  label: string
  files: number
  definitions: number
  language: string
  entry: string[]
  hub: boolean
  stack: string[]
  key: ArchStep[]
}

export type ArchEdge = { source: string; target: string; imports: number; calls: number }

export type StackRole = { role: string; labels: string[] }

export type Architecture = {
  modules: ArchModule[]
  edges: ArchEdge[]
  groups: { title: string; stack: StackRole[]; rows: string[][] }[]
  stack: StackRole[]
  flows: FlowStep[][]
}

export type Source = { id: number; path: string; text: string; is_test: boolean }

export type Citation = {
  id: string
  chunk_id: number
  path: string
  start_line: number
  end_line: number
  is_test: boolean
}

export type Explanation = {
  sufficient: boolean
  note: string | null
  points: { text: string; evidence: Citation[] }[]
}

export function post<T>(path: string, body: unknown): Promise<T> {
  const headers = { 'Content-Type': 'application/json' }
  return api<T>(path, { method: 'POST', headers, body: JSON.stringify(body) })
}

function failure(status: number, body: { detail?: unknown } | null): Error {
  return new Error(typeof body?.detail === 'string' ? body.detail : `Request failed (${status})`)
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, init)
  const body = await response.json().catch(() => ({}))
  if (!response.ok) throw failure(response.status, body)
  return body as T
}

// XHR rather than fetch so we know when the ZIP is sent and the server starts indexing.
export function uploadSnapshot(body: FormData, onSent: () => void): Promise<Snapshot> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', '/api/snapshots')
    xhr.responseType = 'json'
    xhr.upload.onload = onSent
    xhr.onload = () =>
      xhr.status >= 200 && xhr.status < 300 ? resolve(xhr.response) : reject(failure(xhr.status, xhr.response))
    xhr.onerror = () => reject(new Error('Upload failed: network error'))
    xhr.send(body)
  })
}
