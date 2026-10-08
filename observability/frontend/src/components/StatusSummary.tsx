import type { HealthStatus } from '../types/observability'

interface StatusSummaryProps {
  environment: string
  status: HealthStatus
  observedAt: string
}

export function StatusSummary({ environment, status, observedAt }: StatusSummaryProps) {
  return (
    <section className="summary">
      <span>Environment: {environment}</span>
      <strong data-status={status}>Status: {status}</strong>
      <small>Observed: {observedAt}</small>
    </section>
  )
}
