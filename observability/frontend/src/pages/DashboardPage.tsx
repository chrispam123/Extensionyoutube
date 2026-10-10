import { useState } from 'react'
import { signOut } from '../auth/cognito'
import { fetchObservability } from '../api/observabilityApi'
import type { ObservabilityResponse } from '../types/observability'
import { StatusSummary } from '../components/StatusSummary'
import { LambdaRack } from '../components/LambdaRack'

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
    <main className="page console-shell">
      <header className="toolbar console-header">
        <div>
          <span className="eyebrow">NOCTURNE // MASTER OPERATIONS HUB</span>
          <h1>Observability console</h1>
          {email && <small>{email}</small>}
        </div>
        <div className="header-actions">
          <span className="environment-chip">{data?.environment ?? 'DEVELOP'}</span>
          <button className="console-button secondary" onClick={() => void signOut()}>Sign out</button>
        </div>
      </header>

      <section className="control-deck">
        <div>
          <span className="eyebrow">READ-ONLY TELEMETRY</span>
          <p>On-demand snapshot of the Nocturne systems.</p>
        </div>
        <button className="console-button" onClick={() => void refresh()} disabled={loading}>
          {loading ? 'Reading telemetry...' : 'Refresh status'}
        </button>
      </section>

      {error && <p className="error console-error">{error}</p>}
      {data && (
        <>
          <StatusSummary environment={data.environment} status={data.status} observedAt={data.observed_at} />
          {data.components && <LambdaRack components={data.components} />}
          <details className="raw-telemetry">
            <summary>Open raw telemetry payload</summary>
            <pre>{JSON.stringify(data, null, 2)}</pre>
          </details>
        </>
      )}
    </main>
  )
}
