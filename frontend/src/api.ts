export type Health = {
  status: string
  fts5: boolean
  ai_configured: boolean
  limits: Record<string, number>
}

export type Snapshot = {
  snapshot_id: string
  name: string
  files: number
  chunks: number
  skipped: Record<string, number>
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
  suggested_terms: string[]
  ai_note: string | null
  results: Result[]
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

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, init)
  const body = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = typeof body.detail === 'string' ? body.detail : undefined
    throw new Error(detail ?? `Request failed (${response.status})`)
  }
  return body as T
}
