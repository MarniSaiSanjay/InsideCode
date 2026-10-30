import { useEffect, useState } from 'react'
import { api, type Health } from './api'

export default function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api<Health>('/health').then(setHealth, (e: Error) => setError(e.message))
  }, [])

  return (
    <main>
      <h1>Brahmaniss</h1>
      <p>Find the right code in an unfamiliar Python repository.</p>
      {error && <p role="alert">Backend unavailable: {error}</p>}
      {health && (
        <p>
          Backend {health.status} · FTS5 {health.fts5 ? 'ready' : 'missing'} · AI{' '}
          {health.ai_configured ? 'configured' : 'not configured (search-only)'}
        </p>
      )}
    </main>
  )
}
