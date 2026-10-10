import { LoginButton } from '../components/LoginButton'

export function LoginPage() {
  return (
    <main className="login-page">
      <div className="login-frame-container">
        <div className="login-perimeter login-perimeter-top">
          <div className="login-perimeter-group">
            <span className="login-system-id">SYS_ID // 0X48-NOCTURNE</span>
            <span>|</span>
            <span>STAGE: <strong>DEVELOP</strong></span>
            <span>|</span>
            <span>CONTAINMENT: <b className="nominal-text">SEALED</b></span>
          </div>
          <div className="login-perimeter-group">
            <span>GATEWAY: <b className="cyan-text">API_GW::pugu65me5k</b></span>
            <span>|</span>
            <span>KMS: AES_256</span>
          </div>
        </div>

        <section className="login-chassis" aria-labelledby="login-title">
          <img className="chassis-image" src="/assets/chassis-frame.png" alt="" aria-hidden="true" />
          <div className="login-visor">
            <div className="login-visor-reflection" aria-hidden="true" />
            <div className="login-visor-grid" aria-hidden="true" />

            <div className="login-visor-heading">
              <span>■ NOCTURNE // SEC_AUTH</span>
              <span>SYS_BUS: <b className="nominal-text">READY</b></span>
            </div>

            <div className="login-content">
              <div className="login-copy">
                <span className="login-kicker">EVENT-DRIVEN OBSERVABILITY CORE</span>
                <h1 id="login-title">INYECCIÓN DE CREDENCIAL AL BUS</h1>
              </div>
              <LoginButton />

              <div className="login-bypass-divider" aria-hidden="true">
                <span />
                <strong>O MANUAL BYPASS TOKEN</strong>
                <span />
              </div>

              <div className="login-static-readouts" aria-label="Authentication channel status">
                <div><strong>uopechris@gmail.com</strong><span>IAM_ID</span></div>
                <div><strong>••••••••••••••••••••</strong><span>KMS_LOCK</span></div>
              </div>
            </div>

            <div className="login-status-line">
              <div><span className="amber-text">MODE: READ_ONLY</span><span>|</span><span className="nominal-text">CIRCUIT: IDLE_ARMED</span></div>
              <span className="cyan-text">CHASSIS_LOCK: [ENGAGED]</span>
            </div>
          </div>
        </section>

        <div className="login-perimeter login-perimeter-bottom">
          <span>AUTHORITY: COGNITO/OIDC</span>
          <span>|</span>
          <span>ACCESS: GROUP-GATED</span>
          <span>|</span>
          <span className="nominal-text">READ-ONLY TELEMETRY</span>
        </div>
      </div>
    </main>
  )
}
