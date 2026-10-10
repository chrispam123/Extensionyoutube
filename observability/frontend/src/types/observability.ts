export type HealthStatus = 'healthy' | 'warning' | 'critical'

export interface LambdaMetrics {
  error_rate: number
  invocations: number
  errors: number
  throttles: number
  duration_p95_ms: number
}

export interface LambdaComponent {
  component: string
  function_name: string
  status: HealthStatus
  metrics: LambdaMetrics
}

export interface ObservabilityResponse {
  environment: string
  status: HealthStatus
  observed_at: string
  window_minutes?: number
  components?: LambdaComponent[]
  [section: string]: unknown
}
