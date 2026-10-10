import { LoginButton } from '../components/LoginButton'

export function LoginPage() {
  return (
    <main className="login-page">
      <div className="login-perimeter login-perimeter-top">
        <span className="login-system-id">SYS_ID // 0X48-NOCTURNE</span>
        <span>STAGE: <strong>DEVELOP</strong></span>
        <span>CONTAINMENT: <b className="nominal-text">SEALED</b></span>
        <span className="login-gateway">GATEWAY: <b>OBSERVABILITY</b></span>
        <span>KMS: AES_256</span>
      </div>

      <section className="login-chassis" aria-labelledby="login-title">
        <div className="login-visor">
          <div className="login-visor-heading">
            <span>■ NOCTURNE // SEC_AUTH</span>
            <span>SYS_BUS: <b className="nominal-text">READY</b></span>
          </div>

          <div className="login-content">
            <span className="login-kicker">EVENT-DRIVEN OBSERVABILITY CORE</span>
            <h1 id="login-title">INYECCIÓN DE CREDENCIAL AL BUS</h1>
            <LoginButton />
            <div className="login-readout" aria-label="Authentication mode">
              <span>AUTH_CHANNEL</span>
              <strong>GOOGLE OAUTH2 // COGNITO</strong>
            </div>
          </div>

          <div className="login-status-line">
            <span>MODE: READ_ONLY</span>
            <span>CIRCUIT: IDLE_ARMED</span>
            <span className="nominal-text">CHASSIS_LOCK: [ENGAGED]</span>
          </div>
        </div>
      </section>

      <div className="login-perimeter login-perimeter-bottom">
        <span>AUTHORITY: COGNITO/OIDC</span>
        <span>ACCESS: GROUP-GATED</span>
        <span className="nominal-text">READ-ONLY TELEMETRY</span>
      </div>
    </main>
  )
}
