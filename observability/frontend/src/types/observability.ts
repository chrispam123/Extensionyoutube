export type HealthStatus = 'healthy' | 'warning' | 'critical'

export interface ObservabilityResponse {
  environment: string
  status: HealthStatus
  observed_at: string
  [section: string]: unknown
}
