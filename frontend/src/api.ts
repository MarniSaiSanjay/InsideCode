export type Health = {
  status: string
  fts5: boolean
  ai_configured: boolean
  limits: Record<string, number>
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, init)
  const body = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(body.detail ?? `Request failed (${response.status})`)
  return body as T
}
