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
      {actionLabel && <button className="hub-station-button" onClick={onOpen} disabled={!onOpen}>{actionLabel}</button>}
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
  const apiHealth = !api ? 'unknown' : has5xx || api.status === 'critical' ? 'critical' : api.status === 'healthy' ? 'healthy' : 'warning'
  const apiScreen = !api ? ['SIN DATOS'] : apiHealth === 'critical' ? ['ERROR 5XX', 'REVISAR API'] : apiHealth === 'healthy' ? ['NOMINAL', 'NO 5XX'] : ['AVISO', 'REVISAR MÉTRICAS']
  const eventHealth = !eventbridge ? 'unknown' : eventbridge.metrics.failed_invocations > 0 || !eventbridge.target_configured || eventbridge.state.toUpperCase() !== 'ENABLED' || eventbridge.status === 'critical' ? 'critical' : eventbridge.status === 'healthy' ? 'healthy' : 'warning'
  const eventScreen = !eventbridge ? ['SIN DATOS'] : eventHealth === 'critical' ? ['ERROR', 'REVISAR REGLA'] : eventHealth === 'healthy' ? ['RULE ENABLED', 'TARGET OK'] : ['AVISO', 'REVISAR REGLA']
  const display = (value: string | number | null | undefined, suffix = '') => value === null || value === undefined ? 'NO OBSERVADO' : `${value}${suffix}`

  return (
    <>
      <div className="hub-detail-toolbar"><span>ESTACIÓN 01 // TELEMETRÍA DE ADMISIÓN</span><button className="hub-station-button" onClick={onBack}>◀ RETORNAR AL HUB CENTRAL</button></div>
      <main className="hub-ingress-detail">
        <section className="hub-ingress-detail-head"><span className="hub-kicker">EVENT-DRIVEN OBSERVABILITY CORE</span><h2>API GATEWAY + EVENTBRIDGE // BUS DE ADMISIÓN</h2><p>LECTURA DEL SNAPSHOT REAL // SIN ACCIONES OPERATIVAS</p></section>
        <div className="hub-ingress-detail-grid">
          <section className="hub-detail-instrument">
            <div className="hub-detail-instrument-stage">
              <div className="hub-detail-label"><span className="cyan-text">COLECTOR 01 // API GATEWAY</span><span>ID: {api?.api_id ?? 'NO OBSERVADO'}</span></div>
              <div className="hub-instrument-row api">
                <div className="hub-lcd">
                  <span>P95: <b>{display(api?.metrics.latency_p95_ms, 'ms')}</b></span><span>4XX: <b>{display(api?.metrics.errors_4xx)}</b></span><span>5XX: <b className={has5xx ? 'danger-text' : ''}>{display(errors5xx)}</b></span><span>RATE: <b className={has5xx ? 'danger-text' : ''}>{display(errorRate, '%')}</b></span>
                </div>
                <InstrumentPreview image="/assets/api-gateway-gauge.png" label="API Gateway gauge">
                  <div className="hub-gauge-overlay"><strong>{display(requests)}</strong><span>REQ / WINDOW</span></div>
                  <span className={`hub-health-led hub-api-led-left ${apiHealth === 'healthy' ? 'healthy' : 'off'}`} aria-hidden="true" />
                  <span className={`hub-health-led hub-api-led-right ${apiHealth === 'critical' ? 'critical' : 'off'}`} aria-hidden="true" />
                  <div className={`hub-status-screen ${apiHealth}`} aria-label="Estado de API Gateway">{apiScreen.map((line) => <span key={line}>{line}</span>)}</div>
                </InstrumentPreview>
              </div>
            </div>
            <div className="hub-detail-status"><span>ESTADO: <b className={api?.status ?? 'warning'}>{api ? statusLabel[api.status] : 'NO OBSERVADO'}</b></span><span>STAGE: {api?.stage ?? '—'}</span></div>
          </section>
          <div className="hub-detail-divider">INTAKE<br />&amp; SYNC</div>
          <section className="hub-detail-instrument">
            <div className="hub-detail-instrument-stage">
              <div className="hub-detail-label"><span className="amber-text">OSCILADOR 02 // EVENTBRIDGE</span><span>{eventbridge?.rule_name ?? 'NO OBSERVADO'}</span></div>
              <div className="hub-instrument-row eventbridge">
                <InstrumentPreview image="/assets/eventbridge-clock.png" label="EventBridge clock">
                  <div className="hub-clock-overlay"><span>INVOCACIONES</span><strong>{display(invocations)}</strong></div>
                  <span className={`hub-health-led hub-event-led-first ${eventHealth === 'healthy' ? 'healthy' : 'off'}`} aria-hidden="true" />
                  <span className={`hub-health-led hub-event-led-second ${eventHealth === 'critical' ? 'critical' : 'off'}`} aria-hidden="true" />
                  <span className="hub-health-led hub-event-led-right-top off" aria-hidden="true" />
                  <span className="hub-health-led hub-event-led-right-bottom off" aria-hidden="true" />
                  <div className={`hub-status-screen ${eventHealth}`} aria-label="Estado de EventBridge">{eventScreen.map((line) => <span key={line}>{line}</span>)}</div>
                </InstrumentPreview>
                <div className="hub-lcd">
                  <span>STATE: <b>{eventbridge?.state ?? 'NO OBSERVADO'}</b></span><span>FAILURES: <b className={failedInvocations ? 'danger-text' : ''}>{display(failedInvocations)}</b></span><span>TARGET: <b>{eventbridge?.target_function ?? 'NO OBSERVADO'}</b></span>
                </div>
              </div>
            </div>
            <div className="hub-detail-status"><span>TARGET_CFG: <b className={eventbridge?.target_configured ? 'healthy' : 'warning'}>{eventbridge ? (eventbridge.target_configured ? 'TRUE' : 'FALSE') : 'NO OBSERVADO'}</b></span><span>RULE: {eventbridge?.schedule_expression ?? '—'}</span></div>
          </section>
        </div>
        <section className="hub-snapshot-strip"><div><span className="amber-text">SIMULADOR DE ENTRADA Y DISPARO:</span><small>LECTURA REAL DEL SNAPSHOT, SIN DISPARAR SERVICIOS</small></div><div className="hub-snapshot-states"><span className={!hasHttpActivity && !has5xx ? 'active' : ''}>[01] REPOSO {!hasHttpActivity && !has5xx ? 'NOMINAL' : 'NO APLICABLE'}</span><span className={hasHttpActivity ? 'active' : ''}>[02] INYECCIÓN HTTP {hasHttpActivity ? 'DETECTADA' : 'SIN EVENTOS'}</span><span className={hasCronActivity ? 'active' : ''}>[03] PULSO DE CRON {hasCronActivity ? 'DETECTADO' : 'SIN EVENTOS'}</span><span className={has5xx ? 'critical' : ''}>[04] ALERTA 5XX {has5xx ? 'DETECTADA' : 'SIN ALERTA'}</span></div></section>
      </main>
    </>
  )
}

const lambdaTopology: Record<string, { channel: string; role: string }> = {
  auth: { channel: 'API_GW / DYNAMODB', role: 'Valida la sesión de la extensión y registra el perfil autenticado en DynamoDB.' },
  upload: { channel: 'API_GW / S3 / SQS WORK', role: 'Crea el Job PENDING, genera la URL prefirmada de S3 y encola el claim-check.' },
  dispatcher: { channel: 'S3 / SQS INGESTION / SQS WORK', role: 'Consume el evento de S3, identifica el trabajo y encola un mensaje ligero en SQS Work.' },
  worker: { channel: 'SQS WORK / S3 / DYNAMODB', role: 'Consume el claim-check, procesa la lista y actualiza el trabajo y la exportación.' },
  status: { channel: 'API_GW / DYNAMODB / S3', role: 'Consulta el trabajo del usuario y prepara la URL prefirmada de la exportación.' },
  resumer: { channel: 'EVENTBRIDGE / DYNAMODB / SQS WORK', role: 'Detecta trabajos PAUSED_QUOTA y los reactiva publicando un mensaje en SQS Work.' },
}

function getLambdaTopology(component: LambdaComponent) {
  return lambdaTopology[component.component.toLowerCase()] ?? { channel: 'NO OBSERVADO', role: 'Topología todavía no catalogada para este componente.' }
}

function LambdaTelemetry({ component, onBack }: { component: LambdaComponent; onBack: () => void }) {
  const topology = getLambdaTopology(component)
  return (
    <main className="lambda-detail-page lambda-telemetry-page">
      <div className="lambda-detail-toolbar"><span>NIVEL 3 // RAW_TELEMETRY // TELEMETRY_BUS</span><button className="hub-station-button" onClick={onBack}>[X] RETORNAR AL CARTUCHO</button></div>
      <header className="lambda-telemetry-header"><div><span className="hub-kicker">● {component.status === 'healthy' ? 'HEALTHY' : statusLabel[component.status]}</span><h2>MOD_{component.component.toUpperCase()} // [{component.function_name}]</h2></div><span>VENTANA: 5 MINUTOS DESLIZANTE</span></header>
      <div className="lambda-telemetry-status"><span>STATUS: <b className={component.status}>● {statusLabel[component.status]}</b></span><span>STAGE: <b>DEVELOP</b></span></div>
      <div className="lambda-telemetry-grid"><section><h3>01. EJECUCIÓN &amp; LATENCIA</h3><p>Invocaciones (Ejecuciones): <b>{component.metrics.invocations}</b></p><p>Duration P95 (Respuesta): <b className="cyan-text">{Math.round(component.metrics.duration_p95_ms)} ms</b></p></section><section><h3>02. ERRORES &amp; RESTRICCIONES</h3><p>Errors (Recuento Fallos): <b>{component.metrics.errors}</b></p><p>Error Rate (Porcentaje): <b className={component.metrics.error_rate > 0 ? 'danger-text' : 'healthy'}>{component.metrics.error_rate.toFixed(1)} %</b></p><p>Throttles (Estrangulamientos): <b>{component.metrics.throttles}</b></p></section></div>
      <section className="lambda-topology-panel"><h3>TOPOLOGÍA EN NOCTURNE EDA:</h3><p>➔ CANAL / BUS: <b>{topology.channel}</b></p><p>➔ ROL: {topology.role}</p></section>
      <section className="lambda-log-placeholder"><span>LOG STREAM // CLOUDWATCH</span><b>NO CONSULTADO EN ESTE MVP</b><small>La telemetría actual expone métricas agregadas; los logs reales requieren una consulta backend específica.</small></section>
      <footer className="lambda-detail-footer"><span>CORE_RACK_SLOT: <b>{component.component.toUpperCase()}</b></span><span className="healthy">BUS_INTEGRITY: READ_ONLY</span></footer>
    </main>
  )
}

function LambdaDetail({ component, onBack }: { component: LambdaComponent; onBack: () => void }) {
  const topology = getLambdaTopology(component)
  const [deepTelemetry, setDeepTelemetry] = useState(false)
  if (deepTelemetry) return <LambdaTelemetry component={component} onBack={() => setDeepTelemetry(false)} />
  return (
    <main className="lambda-detail-page">
      <div className="lambda-detail-toolbar"><button className="hub-station-button" onClick={onBack}>◀ RETORNAR AL RACK DE 6</button><span>SLOT: BAY // [{component.component.toUpperCase()}]</span></div>
      <div className="lambda-cartridge-detail">
        <img src="/assets/lambda-cartridge.jpg" alt={`Cartucho Lambda ${component.component}`} />
        <div className="lambda-cartridge-detail-label"><span className="hub-led" /> MOD_{component.component.toUpperCase()}</div>
        <div className="lambda-cartridge-detail-metrics"><div><span>{component.function_name}</span><b className={component.status}>{statusLabel[component.status]}</b></div><div className="hub-mini-metrics"><span>INV {component.metrics.invocations}</span><span>P95 {Math.round(component.metrics.duration_p95_ms)}ms</span><span>ERR {component.metrics.errors}</span></div><div><span>BUS: {topology.channel.split(' / ')[0]}</span><span className="amber-text">EXPAND ➔</span></div></div>
      </div>
      <section className="lambda-topology-summary"><h3>TOPOLOGÍA EN NOCTURNE EDA:</h3><p>➔ CANAL / BUS: <b>{topology.channel}</b></p><p>➔ ROL: {topology.role}</p></section>
      <button className="lambda-expand-button" onClick={() => setDeepTelemetry(true)}>➔ ABRIR DESGLOSE TÉCNICO COMPLETO (NIVEL 3)</button>
    </main>
  )
}

function LambdaStation({ components, onOpen }: { components: LambdaComponent[]; onOpen: (component: LambdaComponent) => void }) {
  return (
    <section className="hub-station hub-station-wide">
      <StationHeading title="ESTACIÓN 02 // BASTIDOR DE CÓMPUTO (6 MÓDULOS SERVERLESS)" subtitle="[AUTH, UPLOAD, DISPATCHER, WORKER, STATUS, RESUMER]" actionLabel="" accent="#ffb800" />
      <div className="hub-cartridge-grid">
        {components.map((component, index) => (
          <article className="hub-cartridge" data-status={component.status} key={component.component} role="button" tabIndex={0} onClick={() => onOpen(component)} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') onOpen(component) }}>
            <img src="/assets/lambda-cartridge.jpg" alt="" aria-hidden="true" />
            <div className="hub-cartridge-plasma" aria-hidden="true" />
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

function QueueDetail({ queues, onBack }: { queues: QueueSummary[]; onBack: () => void }) {
  const ingestion = queues.find((queue) => queue.queue === 'ingestion')
  const work = queues.find((queue) => queue.queue === 'work')
  const dlqCount = queues.filter((queue) => queue.type === 'dlq').reduce((total, queue) => total + queue.metrics.visible, 0)
  const queueName = (queue: QueueSummary | undefined) => queue?.queue_name ?? 'NO OBSERVADO'
  const queueState = (queue: QueueSummary | undefined) => queue ? statusLabel[queue.status] : 'NO OBSERVADO'
  const queueHealth = (queue: QueueSummary | undefined) => queue?.status === 'healthy' ? 'healthy' : queue?.status === 'critical' ? 'critical' : 'warning'
  return (
    <main className="sqs-detail-page">
      <header className="sqs-detail-header"><div><span className="hub-kicker">NOCTURNE // ASYNCHRONOUS PIPELINE MONITOR</span><h1>TOPOLOGÍA FÍSICA DE COLAS // FLUJO DE TRANSPORTE REAL</h1></div><span>PATRÓN: <b className="amber-text">CLAIM-CHECK + S3 BYPASS</b></span><span>ESTADO: <b className={dlqCount > 0 ? 'critical' : 'healthy'}>● {dlqCount > 0 ? 'REVISAR DLQ' : 'CIRCUITO OPERATIVO'}</b></span><button className="hub-station-button" onClick={onBack}>◀ RETORNAR AL HUB CENTRAL</button></header>
      <div className="sqs-flow-grid">
        <section className="sqs-flow-column"><div className="sqs-flow-label"><b>▼ 1. PUNTO DE ENTRADA (INFLOW):</b><span>S3 EVENT</span><strong>S3 Bucket [uploads/userId/jobId.json]</strong><small>La extensión sube el archivo; S3 dispara el evento automático.</small></div><QueueDetailVessel queue={ingestion} label="SQS INGESTION" /><div className="sqs-flow-label bottom"><b>▲ 2. DESTINO DE CONSUMO (OUTFLOW):</b><span>MOD_DISPATCHER</span><strong>Lambda Dispatcher [{queueName(ingestion)}]</strong><small>Consume el evento de S3, crea el Job y transfiere el ticket ligero a SQS Work.</small></div></section>
        <div className="sqs-claim-check"><b>CONEXIÓN DE<br />TRANSFERENCIA</b><strong>CLAIM-CHECK TICKET</strong><code>{'{ jobId, userId }'}</code><small>No viaja el JSON pesado; el Dispatcher solo inyecta la llave de referencia hacia SQS Work.</small><span>➜ ➜ ➜</span></div>
        <section className="sqs-flow-column"><div className="sqs-flow-label"><b>▼ 1. PUNTOS DE INYECCIÓN (INFLOW):</b><span>DUAL_SOURCE</span><strong>A) Lambda Upload (Export) o<br />B) Lambda Dispatcher (Import)</strong><small>Ambos depositan el ticket en la cola de trabajo.</small></div><QueueDetailVessel queue={work} label="SQS WORK" /><div className="sqs-flow-label bottom"><b>▲ 2. DESTINO DE CONSUMO (OUTFLOW):</b><span>MOD_WORKER</span><strong>Lambda Worker [{queueName(work)}]</strong><small>Consume el mensaje, obtiene el JSON desde S3 y actualiza DynamoDB/S3.</small></div></section>
      </div>
      <div className="sqs-detail-footer"><span>ESTADO INGESTION: <b className={queueHealth(ingestion)}>{queueState(ingestion)}</b></span><span>ESTADO WORK: <b className={queueHealth(work)}>{queueState(work)}</b></span><span>DLQ VISIBLES: <b className={dlqCount > 0 ? 'critical' : 'healthy'}>{dlqCount}</b></span></div>
    </main>
  )
}

function QueueDetailVessel({ queue, label }: { queue: QueueSummary | undefined; label: string }) {
  return <div className="sqs-detail-vessel"><div className="sqs-detail-vessel-image"><img src="/assets/sqs-containment-vessel.png" alt={label} /><span>VIS: {queue?.metrics.visible ?? 0}</span><small>IN-FLIGHT: {queue?.metrics.not_visible ?? 0}</small></div><div className="sqs-detail-vessel-metrics"><span>QUEUE: <b>{queue?.queue_name ?? 'NO OBSERVADO'}</b></span><span>OLDEST: <b>{queue?.metrics.oldest_age_seconds ?? 0}s</b></span><span>STATUS: <b className={queue?.status ?? 'warning'}>{queue ? statusLabel[queue.status] : 'NO OBSERVADO'}</b></span></div></div>
}

function QueueStation({ queues, onOpen }: { queues: QueueSummary[]; onOpen: () => void }) {
  const ingestion = queues.find((queue) => queue.queue === 'ingestion')
  const work = queues.find((queue) => queue.queue === 'work')
  const dlqCount = queues.filter((queue) => queue.type === 'dlq').reduce((total, queue) => total + queue.metrics.visible, 0)
  return (
    <section className="hub-station hub-half-station">
      <StationHeading title="ESTACIÓN 03 // VASOS DE CONTENCIÓN SQS & DLQ" subtitle="Circuito de ingesta ➔ Transferencia Claim-Check ➔ Circuito de trabajo" actionLabel="➔ ABRIR CON LEYENDAS Y FLUJO COMPLETO" accent="#00f0ff" onOpen={onOpen} />
      <div className="hub-vessel-row">
        {[['01: INGESTION SQS', ingestion, 'S3 ➔ DISPATCHER'], ['02: WORK SQS', work, 'UPLOAD/DISPATCH ➔ WORKER']].map(([label, queue, flow]) => {
          const item = queue as QueueSummary | undefined
          return <div className="hub-vessel" key={label as string}>
            <b>{label as string}</b>
            <div className="hub-vessel-image"><img src="/assets/sqs-containment-vessel.png" alt="" aria-hidden="true" /><div className="hub-vessel-liquid" aria-hidden="true" /><span>VIS: {item?.metrics.visible ?? 0}</span><small>DLQ: {dlqCount}</small></div>
            <span>{flow as string}</span>
          </div>
        })}
      </div>
      <div className={`hub-station-footer ${dlqCount > 0 ? 'critical' : 'healthy'}`}>● {dlqCount > 0 ? `${dlqCount} BRECHA DLQ` : 'DLQ SIN RESIDUOS'}</div>
    </section>
  )
}

function JobsStation({ jobs, onOpen }: { jobs: JobsSummary | null; onOpen: () => void }) {
  const counts = jobs?.metrics.counts_by_status ?? {}
  const statuses = [['INIT', 'INITIALIZING'], ['PEND', 'PENDING'], ['RUN', 'RUNNING'], ['DONE', 'DONE'], ['FAIL', 'FAILED'], ['QUOTA', 'PAUSED_QUOTA']] as const
  return (
    <section className="hub-station hub-half-station">
      <StationHeading title="ESTACIÓN 04 // REGISTRO DE TRABAJOS & LOTES" subtitle="Tabla de trabajos DynamoDB + Exportaciones S3" actionLabel="" accent="#00ff66" />
      <div className="hub-terminal is-clickable" role="button" tabIndex={0} onClick={onOpen} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') onOpen() }} aria-label="Abrir auditoría completa de lotes DynamoDB y exportaciones S3">
        <div className="hub-terminal-header"><b>REGISTRO DE EJECUCIÓN DEL PIPELINE</b><span>MÁS ANTIGUO: {jobs?.metrics.oldest_age_seconds_by_status.DONE ?? 0}s</span></div>
        <div className="hub-vfd-grid">{statuses.map(([label, key]) => <div className={key === 'DONE' ? 'done' : key === 'FAILED' ? 'failed' : ''} key={key}><span>{label}</span><strong>{counts[key] ?? 0}</strong></div>)}</div>
        <div className="hub-terminal-footer"><span>EXPORTACIONES VERIFICADAS: <b>{jobs?.metrics.done_exports_checked ?? 0} / {jobs?.metrics.done_exports_missing ?? 0} FALTANTES</b></span></div>
      </div>
      <div className="hub-station-footer healthy">● {counts.DONE ?? 0} COMPLETADOS ({jobs?.metrics.stale_running ?? 0} ATASCADOS)</div>
    </section>
  )
}

function JobsDetail({ jobs, onBack }: { jobs: JobsSummary | null; onBack: () => void }) {
  const counts = jobs?.metrics.counts_by_status ?? {}
  const metrics = jobs?.metrics
  const stalePending = metrics?.stale_pending_or_initializing ?? null
  const staleRunning = metrics?.stale_running ?? null
  const checked = metrics?.done_exports_checked ?? null
  const missing = metrics?.done_exports_missing ?? null
  const oldestDone = metrics?.oldest_age_seconds_by_status.DONE ?? null
  const statuses = [
    ['INITIALIZING', 'Subiendo a S3'],
    ['PENDING', 'En cola SQS Work'],
    ['RUNNING', 'Procesando en Worker'],
    ['DONE', 'Finalizados con éxito'],
    ['FAILED', 'Errores irrecuperables'],
    ['PAUSED_QUOTA', 'En espera de Resumer'],
  ] as const
  const consistent = jobs?.status === 'healthy' && stalePending === 0 && staleRunning === 0 && missing === 0
  const auditState = jobs ? (consistent ? 'CONSISTENTE' : 'REVISAR') : 'NO OBSERVADO'
  const healthText = jobs ? `${statusLabel[jobs.status]} (${consistent ? 'ALL CONSISTENT' : 'REVISAR MÉTRICAS'})` : 'NO OBSERVADO'
  const display = (value: number | null) => value === null ? 'NO OBSERVADO' : value

  return (
    <main className="jobs-detail-page">
      <header className="jobs-detail-header">
        <div><span className="hub-kicker">DEEP_AUDIT // PRODUCTION_LEDGER</span><h1>REGISTRO DE LOTES DYNAMODB &amp; EXPORTACIONES S3</h1></div>
        <button className="hub-station-button" onClick={onBack}>[X] CERRAR AUDITORÍA</button>
      </header>
      <div className="jobs-detail-status"><span>REGISTRY_HEALTH: <b className={jobs?.status ?? 'warning'}>● {healthText}</b></span><span>TABLE: <b>NO OBSERVADO</b></span><span>STORAGE: <b>S3 // EXPORTACIONES</b></span></div>
      <section className="jobs-state-section"><h2>01. DESGLOSE COMPLETO POR ESTADOS (COUNTS_BY_STATUS)</h2><div className="jobs-state-grid">{statuses.map(([key, description]) => <article className={`jobs-state-card ${key === 'DONE' ? 'done' : key === 'FAILED' ? 'failed' : ''}`} key={key}><span>{key}</span><strong>{counts[key] ?? 0}</strong><small>{description}</small></article>)}</div></section>
      <div className="jobs-audit-grid">
        <section className="jobs-audit-panel"><h2>02. TRABAJOS ESTANCADOS (STALE CHECK)</h2><p><span>Stale Pending / Initializing:</span><b className={stalePending === 0 ? 'healthy' : 'critical'}>{display(stalePending)} {stalePending === 0 ? '(NORMAL)' : '(REVISAR)'}</b></p><p><span>Stale Running (Trabajos Colgados):</span><b className={staleRunning === 0 ? 'healthy' : 'critical'}>{display(staleRunning)} {staleRunning === 0 ? '(NORMAL)' : '(REVISAR)'}</b></p></section>
        <section className="jobs-audit-panel"><h2>03. AUDITORÍA DE ARCHIVOS EXPORTADOS (S3)</h2><p><span>Done Exports Checked:</span><b>{display(checked)} {checked !== null ? 'VERIFICADOS' : ''}</b></p><p><span>Done Exports Missing (Faltantes):</span><b className={missing === 0 ? 'healthy' : 'critical'}>{display(missing)} {missing !== null ? (missing === 0 ? '(DISPONIBLES)' : '(REVISAR)') : ''}</b></p></section>
      </div>
      <div className="jobs-oldest"><span>OLDEST AGE (DONE): <b>{oldestDone === null ? 'NO OBSERVADO' : `${oldestDone} SEGUNDOS`}</b></span><b className={consistent ? 'healthy' : 'warning'}>LIFECYCLE: {auditState}</b></div>
      <footer className="jobs-detail-footer"><span>LEDGER_HASH: NO OBSERVADO</span><span className={consistent ? 'healthy' : 'warning'}>AUDIT_VERIFICATION: {auditState}</span></footer>
    </main>
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
  const [selectedLambda, setSelectedLambda] = useState<LambdaComponent | null>(null)
  const [sqsOpen, setSqsOpen] = useState(false)
  const [jobsOpen, setJobsOpen] = useState(false)
  const api = data ? getApiGateway(data) : null
  const eventbridge = data ? getEventBridge(data) : null

  if (station === 'ingress' && data) {
    return <main className="hub-page"><IngressDetail api={api} eventbridge={eventbridge} onBack={() => setStation('hub')} /></main>
  }

  if (selectedLambda) {
    return <main className="hub-page"><LambdaDetail component={selectedLambda} onBack={() => setSelectedLambda(null)} /></main>
  }

  if (sqsOpen && data) {
    return <main className="hub-page"><QueueDetail queues={getQueues(data)} onBack={() => setSqsOpen(false)} /></main>
  }

  if (jobsOpen && data) {
    return <main className="hub-page"><JobsDetail jobs={getJobs(data)} onBack={() => setJobsOpen(false)} /></main>
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
        <LambdaStation components={data.components ?? []} onOpen={setSelectedLambda} />
        <div className="hub-bottom-grid"><QueueStation queues={getQueues(data)} onOpen={() => setSqsOpen(true)} /><JobsStation jobs={getJobs(data)} onOpen={() => setJobsOpen(true)} /></div>
      </>}
    </main>
  )
}
