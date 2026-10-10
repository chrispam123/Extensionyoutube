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

export interface ApiGatewaySummary {
  api_id: string
  stage: string
  status: HealthStatus
  metrics: {
    requests: number
    errors_5xx: number
    errors_4xx: number
    error_rate_5xx: number
    latency_p95_ms: number
  }
}

export interface EventBridgeSummary {
  rule_name: string
  state: string
  schedule_expression: string
  target_function: string
  target_configured: boolean
  status: HealthStatus
  metrics: {
    window_minutes: number
    invocations: number
    failed_invocations: number
  }
}

export interface QueueSummary {
  queue: string
  queue_name: string
  type: 'primary' | 'dlq'
  status: HealthStatus
  metrics: {
    visible: number
    not_visible: number
    oldest_age_seconds: number
  }
}

export interface JobsSummary {
  status: HealthStatus
  metrics: {
    counts_by_status: Record<string, number>
    stale_pending_or_initializing: number
    stale_running: number
    done_exports_checked: number
    done_exports_missing: number
    oldest_age_seconds_by_status: Record<string, number>
  }
}

export interface ObservabilityResponse {
  environment: string
  status: HealthStatus
  observed_at: string
  window_minutes?: number
  components?: LambdaComponent[]
  api_gateway?: ApiGatewaySummary | null
  eventbridge?: EventBridgeSummary | null
  queues?: QueueSummary[]
  jobs?: JobsSummary
  [section: string]: unknown
}
