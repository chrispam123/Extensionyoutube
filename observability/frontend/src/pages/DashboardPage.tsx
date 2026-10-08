import { useState } from 'react'
import { signOut } from '../auth/cognito'
import { fetchObservability } from '../api/observabilityApi'
import type { ObservabilityResponse } from '../types/observability'
import { StatusSummary } from '../components/StatusSummary'

interface DashboardPageProps {
  accessToken: string
  email?: string
}

export function DashboardPage({ accessToken, email }: DashboardPageProps) {
  const [data, setData] = useState<ObservabilityResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const refresh = async () => {
    setLoading(true)
    setError(null)
    try {
      setData(await fetchObservability(accessToken))
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unknown request error')
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="page">
      <header className="toolbar">
        <div>
          <h1>Nocturne Observability</h1>
          {email && <small>{email}</small>}
        </div>
        <button onClick={() => void signOut()}>Sign out</button>
      </header>

      <button onClick={() => void refresh()} disabled={loading}>
        {loading ? 'Loading...' : 'Refresh status'}
      </button>

      {error && <p className="error">{error}</p>}
      {data && (
        <>
          <StatusSummary environment={data.environment} status={data.status} observedAt={data.observed_at} />
          <pre>{JSON.stringify(data, null, 2)}</pre>
        </>
      )}
    </main>
  )
}
