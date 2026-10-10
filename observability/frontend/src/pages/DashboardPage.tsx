import { useState } from 'react'
import { signOut } from '../auth/cognito'
import { fetchObservability } from '../api/observabilityApi'
import type { ObservabilityResponse } from '../types/observability'
import { MasterConsole } from '../components/MasterConsole'

interface DashboardPageProps {
  accessToken: string
}

export function DashboardPage({ accessToken }: DashboardPageProps) {
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
    <>
      {error && <p className="error console-error">{error}</p>}
      <MasterConsole data={data} onRefresh={() => void refresh()} onSignOut={() => void signOut()} loading={loading} />
    </>
  )
}
