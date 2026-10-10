import { useState, type ReactNode } from 'react'
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
  data: ObservabilityResponse | null
  onRefresh: () => void
  onSignOut: () => void
  loading: boolean
}

const statusLabel: Record<HealthStatus, string> = {
  healthy: 'SALUDABLE',
  warning: 'AVISO',
  critical: 'BRECHA',
}

const getApiGateway = (data: ObservabilityResponse) => data.api_gateway ?? null
const getEventBridge = (data: ObservabilityResponse) => data.eventbridge ?? null
const getQueues = (data: ObservabilityResponse) => data.queues ?? []
const getJobs = (data: ObservabilityResponse) => data.jobs ?? null

function StationHeading({ title, subtitle, actionLabel, accent, onOpen }: { title: string; subtitle: string; actionLabel: string; accent: string; onOpen?: () => void }) {
  return (
    <div className="hub-station-heading">
      <div>
        <span className="hub-station-title" style={{ color: accent }}>{title}</span>
        <div className="hub-station-subtitle">{subtitle}</div>
      </div>
      <button className="hub-station-button" onClick={onOpen} disabled={!onOpen}>{actionLabel}</button>
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

function IngressStation({ api, eventbridge, onOpen }: { api: ApiGatewaySummary | null; eventbridge: EventBridgeSummary | null; onOpen: () => void }) {
  const apiStatus = api?.status ?? 'warning'
  const eventStatus = eventbridge?.status ?? 'warning'
  return (
    <section className="hub-station hub-station-wide">
      <StationHeading title="ESTACIÓN 01 // ADMISIÓN HTTP & OSCILADOR TEMPORIZADOR" subtitle="[API GATEWAY + EVENTBRIDGE]" actionLabel="➔ ABRIR ESTACIÓN COMPLETA (AGUJA + RADAR DEDICADOS)" accent="#00f0ff" onOpen={onOpen} />
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
            <b className="cyan-text">API GATEWAY // {api?.api_id ?? 'NO OBSERVADO'}</b>
            <span>ETAPA: {api?.stage ?? '—'} | LATENCIA: {api?.metrics.latency_p95_ms ?? 0} ms</span>
            <HealthLine status={apiStatus}>ESTADO</HealthLine>
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
            <b className="amber-text">EVENTBRIDGE // {eventbridge?.rule_name ?? 'NO OBSERVADO'}</b>
            <span>FRECUENCIA: {eventbridge?.schedule_expression ?? '—'} | OBJETIVO: {eventbridge?.target_function ?? '—'}</span>
            <HealthLine status={eventStatus}>ESTADO</HealthLine>
          </div>
        </div>
      </div>
    </section>
  )
}

function IngressDetail({ api, eventbridge, onBack }: { api: ApiGatewaySummary | null; eventbridge: EventBridgeSummary | null; onBack: () => void }) {
  const requests = api?.metrics.requests ?? null
  const errors5xx = api?.metrics.errors_5xx ?? null
  const errorRate = api?.metrics.error_rate_5xx ?? null
  const invocations = eventbridge?.metrics.invocations ?? null
  const failedInvocations = eventbridge?.metrics.failed_invocations ?? null
  const hasHttpActivity = requests !== null && requests > 0
  const hasCronActivity = invocations !== null && invocations > 0
  const has5xx = (errors5xx !== null && errors5xx > 0) || (errorRate !== null && errorRate > 0)
  const display = (value: string | number | null | undefined, suffix = '') => value === null || value === undefined ? 'NO OBSERVADO' : `${value}${suffix}`

  return (
    <>
      <div className="hub-detail-toolbar"><span>ESTACIÓN 01 // TELEMETRÍA DE ADMISIÓN</span><button className="hub-station-button" onClick={onBack}>◀ RETORNAR AL HUB CENTRAL</button></div>
      <main className="hub-ingress-detail">
        <section className="hub-ingress-detail-head"><span className="hub-kicker">EVENT-DRIVEN OBSERVABILITY CORE</span><h2>API GATEWAY + EVENTBRIDGE // BUS DE ADMISIÓN</h2><p>LECTURA DEL SNAPSHOT REAL // SIN ACCIONES OPERATIVAS</p></section>
        <div className="hub-ingress-detail-grid">
          <section className="hub-detail-instrument">
            <div className="hub-detail-label"><span className="cyan-text">COLECTOR 01 // API GATEWAY</span><span>ID: {api?.api_id ?? 'NO OBSERVADO'}</span></div>
            <InstrumentPreview image="/assets/api-gateway-gauge.png" label="API Gateway gauge">
              <div className="hub-gauge-overlay"><strong>{display(requests)}</strong><span>REQ / WINDOW</span></div>
              <div className="hub-lcd"><span>P95: <b>{display(api?.metrics.latency_p95_ms, 'ms')}</b></span><span>4XX: <b>{display(api?.metrics.errors_4xx)}</b></span><span>5XX: <b className={has5xx ? 'danger-text' : ''}>{display(errors5xx)}</b></span><span>RATE: <b className={has5xx ? 'danger-text' : ''}>{display(errorRate, '%')}</b></span></div>
            </InstrumentPreview>
            <div className="hub-detail-status"><span>ESTADO: <b className={api?.status ?? 'warning'}>{api ? statusLabel[api.status] : 'NO OBSERVADO'}</b></span><span>STAGE: {api?.stage ?? '—'}</span></div>
          </section>
          <div className="hub-detail-divider">INTAKE<br />&amp; SYNC</div>
          <section className="hub-detail-instrument">
            <div className="hub-detail-label"><span className="amber-text">OSCILADOR 02 // EVENTBRIDGE</span><span>{eventbridge?.rule_name ?? 'NO OBSERVADO'}</span></div>
            <InstrumentPreview image="/assets/eventbridge-clock.png" label="EventBridge clock">
              <div className="hub-clock-overlay"><span>INVOCACIONES</span><strong>{display(invocations)}</strong></div>
              <div className="hub-lcd"><span>STATE: <b>{eventbridge?.state ?? 'NO OBSERVADO'}</b></span><span>FAILURES: <b className={failedInvocations ? 'danger-text' : ''}>{display(failedInvocations)}</b></span><span>TARGET: <b>{eventbridge?.target_function ?? 'NO OBSERVADO'}</b></span></div>
            </InstrumentPreview>
            <div className="hub-detail-status"><span>TARGET_CFG: <b className={eventbridge?.target_configured ? 'healthy' : 'warning'}>{eventbridge ? (eventbridge.target_configured ? 'TRUE' : 'FALSE') : 'NO OBSERVADO'}</b></span><span>RULE: {eventbridge?.schedule_expression ?? '—'}</span></div>
          </section>
        </div>
        <section className="hub-snapshot-strip"><div><span className="amber-text">SIMULADOR DE ENTRADA Y DISPARO:</span><small>LECTURA REAL DEL SNAPSHOT, SIN DISPARAR SERVICIOS</small></div><div className="hub-snapshot-states"><span className={!hasHttpActivity && !has5xx ? 'active' : ''}>[01] REPOSO {!hasHttpActivity && !has5xx ? 'NOMINAL' : 'NO APLICABLE'}</span><span className={hasHttpActivity ? 'active' : ''}>[02] INYECCIÓN HTTP {hasHttpActivity ? 'DETECTADA' : 'SIN EVENTOS'}</span><span className={hasCronActivity ? 'active' : ''}>[03] PULSO DE CRON {hasCronActivity ? 'DETECTADO' : 'SIN EVENTOS'}</span><span className={has5xx ? 'critical' : ''}>[04] ALERTA 5XX {has5xx ? 'DETECTADA' : 'SIN ALERTA'}</span></div></section>
      </main>
    </>
  )
}

function LambdaStation({ components }: { components: LambdaComponent[] }) {
  return (
    <section className="hub-station hub-station-wide">
      <StationHeading title="ESTACIÓN 02 // BASTIDOR DE CÓMPUTO (6 MÓDULOS SERVERLESS)" subtitle="[AUTH, UPLOAD, DISPATCHER, WORKER, STATUS, RESUMER]" actionLabel="➔ ABRIR ESTACIÓN DE LAMBDAS (ZOOM PROGRESIVO DE 3 NIVELES)" accent="#ffb800" />
      <div className="hub-cartridge-grid">
        {components.map((component, index) => (
          <article className="hub-cartridge" data-status={component.status} key={component.component}>
            <img src="/assets/lambda-cartridge.jpg" alt="" aria-hidden="true" />
            <div className="hub-cartridge-label">MOD_{String(index + 1).padStart(2, '0')} // {component.component.toUpperCase()}</div>
            <div className="hub-cartridge-lcd">
              <div><span>{component.function_name}</span><b>● {component.status === 'healthy' ? 'OK' : statusLabel[component.status]}</b></div>
              <div className="hub-mini-metrics"><span>INV {component.metrics.invocations}</span><span>P95 {Math.round(component.metrics.duration_p95_ms)}ms</span><span>ERR {component.metrics.errors}</span></div>
              <div className="hub-cartridge-footer"><span>ZOOM LISTO</span><span>➔</span></div>
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
      <StationHeading title="ESTACIÓN 03 // VASOS DE CONTENCIÓN SQS & DLQ" subtitle="Circuito de ingesta ➔ Transferencia Claim-Check ➔ Circuito de trabajo" actionLabel="➔ ABRIR CON LEYENDAS Y FLUJO COMPLETO" accent="#00f0ff" />
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
      <div className={`hub-station-footer ${dlqCount > 0 ? 'critical' : 'healthy'}`}>● {dlqCount > 0 ? `${dlqCount} BRECHA DLQ` : 'DLQ SIN RESIDUOS'}</div>
    </section>
  )
}

function JobsStation({ jobs }: { jobs: JobsSummary | null }) {
  const counts = jobs?.metrics.counts_by_status ?? {}
  const statuses = [['INIT', 'INITIALIZING'], ['PEND', 'PENDING'], ['RUN', 'RUNNING'], ['DONE', 'DONE'], ['FAIL', 'FAILED'], ['QUOTA', 'PAUSED_QUOTA']] as const
  return (
    <section className="hub-station hub-half-station">
      <StationHeading title="ESTACIÓN 04 // REGISTRO DE TRABAJOS & LOTES" subtitle="Tabla de trabajos DynamoDB + Exportaciones S3" actionLabel="➔ ABRIR AUDITORÍA COMPLETA S3" accent="#00ff66" />
      <div className="hub-terminal">
        <div className="hub-terminal-header"><b>REGISTRO DE EJECUCIÓN DEL PIPELINE</b><span>MÁS ANTIGUO: {jobs?.metrics.oldest_age_seconds_by_status.DONE ?? 0}s</span></div>
        <div className="hub-vfd-grid">{statuses.map(([label, key]) => <div className={key === 'DONE' ? 'done' : key === 'FAILED' ? 'failed' : ''} key={key}><span>{label}</span><strong>{counts[key] ?? 0}</strong></div>)}</div>
        <div className="hub-terminal-footer"><span>EXPORTACIONES VERIFICADAS: <b>{jobs?.metrics.done_exports_checked ?? 0} / {jobs?.metrics.done_exports_missing ?? 0} FALTANTES</b></span><span>ABRIR AUDITORÍA ➔</span></div>
      </div>
      <div className="hub-station-footer healthy">● {counts.DONE ?? 0} COMPLETADOS ({jobs?.metrics.stale_running ?? 0} ATASCADOS)</div>
    </section>
  )
}

function TelemetryActuator({ loading, active, onRefresh }: { loading: boolean; active: boolean; onRefresh: () => void }) {
  return (
    <section className={`hub-actuator-shell ${loading ? 'probing' : active ? 'nominal' : 'standby'}`} aria-label="Actuador maestro de telemetría">
      <div className="hub-telemetry-banner" role="status">
        {loading
          ? '● INITIATING PROBE // SYNCING WITH AWS...'
          : active
            ? '● TELEMETRY STREAM ACTIVE | TODOS LOS COMPONENTES ENERGIZADOS'
            : '▲ [!] NO TELEMETRY STREAM | PULSA EL ACTUADOR PARA ENERGIZAR EL BUS'}
      </div>
      <div className="hub-actuator">
        <img src="/assets/actuador.jpg" alt="Actuador maestro de telemetría" />
        <span className="hub-actuator-led" aria-hidden="true" />
        <button className="hub-actuator-button" type="button" onClick={onRefresh} disabled={loading} aria-label="Refresh status">
          <span className="sr-only">Refresh status</span>
        </button>
        <div className="hub-actuator-subtext">
          {loading ? '● INITIATING PROBE // SYNCING WITH AWS...' : active ? '[PROBE COMPLETED // BUS NOMINAL]' : '[CLICK TO PROBE AWS BACKEND]'}
        </div>
      </div>
    </section>
  )
}

export function MasterConsole({ data, onRefresh, onSignOut, loading }: MasterConsoleProps) {
  const [station, setStation] = useState<'hub' | 'ingress'>('hub')
  const api = data ? getApiGateway(data) : null
  const eventbridge = data ? getEventBridge(data) : null

  if (station === 'ingress' && data) {
    return <main className="hub-page"><IngressDetail api={api} eventbridge={eventbridge} onBack={() => setStation('hub')} /></main>
  }

  return (
    <main className="hub-page">
      <header className="hub-header">
        <div className="hub-title-block"><span className="hub-led" /><div><span className="hub-kicker">NOCTURNE OBSERVABILIDAD // MOTOR EDA SERVERLESS AWS</span><h1>HUB CENTRAL DE OPERACIONES // NAVEGACIÓN ENTRE ESTACIONES DE MANDO</h1></div></div>
        <div className="hub-global-meta"><span>ENTORNO: <b>{data?.environment.toUpperCase() ?? 'DEVELOP'}</b></span><span>NÚCLEO: <b className={`hub-core-status ${data?.status ?? 'warning'}`}>● {data ? statusLabel[data.status] : 'SIN TELEMETRÍA'}</b></span><button className="hub-exit-button" onClick={onSignOut}>[SALIR // BLOQUEAR CHASIS]</button></div>
      </header>
      <TelemetryActuator loading={loading} active={data !== null} onRefresh={onRefresh} />
      {data && <>
        <div className="hub-last-read">ÚLTIMA TELEMETRÍA: {new Date(data.observed_at).toISOString()} // VENTANA: {data.window_minutes ?? 5} MIN</div>
        <IngressStation api={api} eventbridge={eventbridge} onOpen={() => setStation('ingress')} />
        <LambdaStation components={data.components ?? []} />
        <div className="hub-bottom-grid"><QueueStation queues={getQueues(data)} /><JobsStation jobs={getJobs(data)} /></div>
      </>}
    </main>
  )
}
