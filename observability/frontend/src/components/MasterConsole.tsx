import type { ReactNode } from 'react'
import type {
  ApiGatewaySummary,
  EventBridgeSummary,
  HealthStatus,
  JobsSummary,
  LambdaComponent,
  ObservabilityResponse,
  QueueSummary,
} from '../types/observability'

interface MasterConsoleProps {
  data: ObservabilityResponse
  onRefresh: () => void
  onSignOut: () => void
  loading: boolean
}

const statusLabel: Record<HealthStatus, string> = {
  healthy: 'HEALTHY',
  warning: 'WARNING',
  critical: 'BREACH',
}

const getApiGateway = (data: ObservabilityResponse) => data.api_gateway ?? null
const getEventBridge = (data: ObservabilityResponse) => data.eventbridge ?? null
const getQueues = (data: ObservabilityResponse) => data.queues ?? []
const getJobs = (data: ObservabilityResponse) => data.jobs ?? null

function StationHeading({ title, subtitle, accent }: { title: string; subtitle: string; accent: string }) {
  return (
    <div className="hub-station-heading">
      <div>
        <span className="hub-station-title" style={{ color: accent }}>{title}</span>
        <div className="hub-station-subtitle">{subtitle}</div>
      </div>
      <button className="hub-station-button" disabled>OPEN STATION ➔</button>
    </div>
  )
}

function HealthLine({ status, children }: { status: HealthStatus; children: string }) {
  return <div className={`hub-health-line ${status}`}>● {children} ({statusLabel[status]})</div>
}

function InstrumentPreview({ image, label, children }: { image: string; label: string; children: ReactNode }) {
  return (
    <div className="hub-instrument-unit">
      <div className="hub-instrument">
        <img src={image} alt={label} />
        {children}
      </div>
    </div>
  )
}

function IngressStation({ api, eventbridge }: { api: ApiGatewaySummary | null; eventbridge: EventBridgeSummary | null }) {
  const apiStatus = api?.status ?? 'warning'
  const eventStatus = eventbridge?.status ?? 'warning'
  return (
    <section className="hub-station hub-station-wide">
      <StationHeading title="STATION 01 // HTTP INGRESS & TIMER OSCILLATOR" subtitle="[API GATEWAY + EVENTBRIDGE]" accent="#00f0ff" />
      <div className="hub-ingress-grid">
        <div className="hub-preview-with-copy">
          <InstrumentPreview image="/assets/api-gateway-gauge.png" label="API Gateway gauge">
            <div className="hub-gauge-overlay">
              <strong>{api?.metrics.requests ?? 0}</strong><span>REQ / WINDOW</span>
            </div>
            <div className="hub-lcd">
              <span>P95: <b>{api?.metrics.latency_p95_ms ?? 0}ms</b></span>
              <span>5XX: <b>{api?.metrics.error_rate_5xx ?? 0}%</b></span>
            </div>
          </InstrumentPreview>
          <div className="hub-instrument-copy">
            <b className="cyan-text">API GATEWAY // {api?.api_id ?? 'NOT OBSERVED'}</b>
            <span>STAGE: {api?.stage ?? '—'} | LATENCY: {api?.metrics.latency_p95_ms ?? 0} ms</span>
            <HealthLine status={apiStatus}>STATUS</HealthLine>
          </div>
        </div>

        <div className="hub-instrument-divider" />

        <div className="hub-preview-with-copy">
          <InstrumentPreview image="/assets/eventbridge-clock.png" label="EventBridge clock">
            <div className="hub-clock-overlay">
              <span>NEXT PULSE</span><strong>{eventbridge?.metrics.invocations ?? 0}</strong>
            </div>
          </InstrumentPreview>
          <div className="hub-instrument-copy">
            <b className="amber-text">EVENTBRIDGE // {eventbridge?.rule_name ?? 'NOT OBSERVED'}</b>
            <span>RATE: {eventbridge?.schedule_expression ?? '—'} | TARGET: {eventbridge?.target_function ?? '—'}</span>
            <HealthLine status={eventStatus}>STATUS</HealthLine>
          </div>
        </div>
      </div>
    </section>
  )
}

function LambdaStation({ components }: { components: LambdaComponent[] }) {
  return (
    <section className="hub-station hub-station-wide">
      <StationHeading title="STATION 02 // COMPUTE RACK (6 SERVERLESS MODULES)" subtitle="[AUTH, UPLOAD, DISPATCHER, WORKER, STATUS, RESUMER]" accent="#ffb800" />
      <div className="hub-cartridge-grid">
        {components.map((component, index) => (
          <article className="hub-cartridge" data-status={component.status} key={component.component}>
            <img src="/assets/lambda-cartridge.jpg" alt="" aria-hidden="true" />
            <div className="hub-cartridge-label">MOD_{String(index + 1).padStart(2, '0')} // {component.component.toUpperCase()}</div>
            <div className="hub-cartridge-lcd">
              <div><span>{component.function_name}</span><b>● {component.status === 'healthy' ? 'OK' : statusLabel[component.status]}</b></div>
              <div className="hub-mini-metrics"><span>INV {component.metrics.invocations}</span><span>P95 {Math.round(component.metrics.duration_p95_ms)}ms</span><span>ERR {component.metrics.errors}</span></div>
              <div className="hub-cartridge-footer"><span>ZOOM READY</span><span>➔</span></div>
            </div>
          </article>
        ))}
      </div>
    </section>
  )
}

function QueueStation({ queues }: { queues: QueueSummary[] }) {
  const ingestion = queues.find((queue) => queue.queue === 'ingestion')
  const work = queues.find((queue) => queue.queue === 'work')
  const dlqCount = queues.filter((queue) => queue.type === 'dlq').reduce((total, queue) => total + queue.metrics.visible, 0)
  return (
    <section className="hub-station hub-half-station">
      <StationHeading title="STATION 03 // SQS & DLQ CONTAINMENT" subtitle="Ingestion ➔ Claim-Check ➔ Work Circuit" accent="#00f0ff" />
      <div className="hub-vessel-row">
        {[['01: INGESTION SQS', ingestion, 'S3 ➔ DISPATCHER'], ['02: WORK SQS', work, 'UPLOAD/DISPATCH ➔ WORKER']].map(([label, queue, flow]) => {
          const item = queue as QueueSummary | undefined
          return <div className="hub-vessel" key={label as string}>
            <b>{label as string}</b>
            <div className="hub-vessel-image"><img src="/assets/sqs-containment-vessel.png" alt="" aria-hidden="true" /><span>VIS: {item?.metrics.visible ?? 0}</span><small>DLQ: {dlqCount}</small></div>
            <span>{flow as string}</span>
          </div>
        })}
      </div>
      <div className={`hub-station-footer ${dlqCount > 0 ? 'critical' : 'healthy'}`}>● {dlqCount > 0 ? `${dlqCount} DLQ BREACH` : 'DLQ ZERO RESIDUES'}</div>
    </section>
  )
}

function JobsStation({ jobs }: { jobs: JobsSummary | null }) {
  const counts = jobs?.metrics.counts_by_status ?? {}
  const statuses = [['INIT', 'INITIALIZING'], ['PEND', 'PENDING'], ['RUN', 'RUNNING'], ['DONE', 'DONE'], ['FAIL', 'FAILED'], ['QUOTA', 'PAUSED_QUOTA']] as const
  return (
    <section className="hub-station hub-half-station">
      <StationHeading title="STATION 04 // JOBS & BATCH REGISTER" subtitle="DynamoDB Jobs Table + S3 Exports" accent="#00ff66" />
      <div className="hub-terminal">
        <div className="hub-terminal-header"><b>PIPELINE EXECUTION REGISTER</b><span>OLDEST: {jobs?.metrics.oldest_age_seconds_by_status.DONE ?? 0}s</span></div>
        <div className="hub-vfd-grid">{statuses.map(([label, key]) => <div className={key === 'DONE' ? 'done' : key === 'FAILED' ? 'failed' : ''} key={key}><span>{label}</span><strong>{counts[key] ?? 0}</strong></div>)}</div>
        <div className="hub-terminal-footer"><span>VERIFIED EXPORTS: <b>{jobs?.metrics.done_exports_checked ?? 0} / {jobs?.metrics.done_exports_missing ?? 0} MISSING</b></span><span>CLICK TO AUDIT ➔</span></div>
      </div>
      <div className="hub-station-footer healthy">● {counts.DONE ?? 0} COMPLETED ({jobs?.metrics.stale_running ?? 0} STALE)</div>
    </section>
  )
}

export function MasterConsole({ data, onRefresh, onSignOut, loading }: MasterConsoleProps) {
  return (
    <main className="hub-page">
      <header className="hub-header">
        <div className="hub-title-block"><span className="hub-led" /><div><span className="hub-kicker">NOCTURNE OBSERVABILITY // AWS SERVERLESS EDA ENGINE</span><h1>CENTRAL OPERATIONS HUB // NAVIGATION BETWEEN COMMAND STATIONS</h1></div></div>
        <div className="hub-global-meta"><span>ENV: <b>{data.environment.toUpperCase()}</b></span><span>CORE: <b className={`hub-core-status ${data.status}`}>● {statusLabel[data.status]}</b></span><button onClick={onRefresh} disabled={loading}>{loading ? 'READING...' : 'REFRESH STATUS'}</button><button className="hub-exit-button" onClick={onSignOut}>[EXIT // LOCK CHASSIS]</button></div>
      </header>
      <div className="hub-last-read">LAST TELEMETRY: {new Date(data.observed_at).toISOString()} // WINDOW: {data.window_minutes ?? 5} MIN</div>
      <IngressStation api={getApiGateway(data)} eventbridge={getEventBridge(data)} />
      <LambdaStation components={data.components ?? []} />
      <div className="hub-bottom-grid"><QueueStation queues={getQueues(data)} /><JobsStation jobs={getJobs(data)} /></div>
    </main>
  )
}
