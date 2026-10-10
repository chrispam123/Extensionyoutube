import { signIn } from '../auth/cognito'

export function LoginButton() {
  return (
    <button className="login-google-button" onClick={() => void signIn()}>
      <span aria-hidden="true">◉</span> INICIAR CON GOOGLE // OAUTH2 <b>→ [EXEC]</b>
    </button>
  )
}
