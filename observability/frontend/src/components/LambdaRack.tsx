import type { HealthStatus, LambdaComponent } from '../types/observability'

interface LambdaRackProps {
  components: LambdaComponent[]
}

const STATUS_LABELS: Record<HealthStatus, string> = {
  healthy: 'NOMINAL',
  warning: 'WARNING',
  critical: 'BREACH',
}

function formatDuration(value: number) {
  return `${Math.round(value)} ms`
}

export function LambdaRack({ components }: LambdaRackProps) {
  return (
    <section className="console-panel lambda-rack" aria-labelledby="lambda-rack-title">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">SUBSYSTEM // COMPUTE BAY</span>
          <h2 id="lambda-rack-title">Lambda cartridge rack</h2>
        </div>
        <span className="panel-count">{components.length.toString().padStart(2, '0')} UNITS</span>
      </div>

      <div className="lambda-grid">
        {components.map((component) => (
          <article className="lambda-cartridge" data-status={component.status} key={component.component}>
            <div className="cartridge-topline">
              <span className="cartridge-index">L-{component.component.slice(0, 3).toUpperCase()}</span>
              <span className="status-lamp" aria-label={`Status ${STATUS_LABELS[component.status]}`} />
            </div>
            <h3>{component.component}</h3>
            <p className="function-name">{component.function_name}</p>
            <div className="cartridge-status">{STATUS_LABELS[component.status]}</div>
            <dl className="metric-strip">
              <div>
                <dt>ERR</dt>
                <dd>{component.metrics.error_rate.toFixed(2)}%</dd>
              </div>
              <div>
                <dt>INV</dt>
                <dd>{component.metrics.invocations}</dd>
              </div>
              <div>
                <dt>P95</dt>
                <dd>{formatDuration(component.metrics.duration_p95_ms)}</dd>
              </div>
            </dl>
          </article>
        ))}
      </div>
    </section>
  )
}
