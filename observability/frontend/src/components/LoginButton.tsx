import { signIn } from '../auth/cognito'

export function LoginButton() {
  return <button onClick={() => void signIn()}>Sign in with Google</button>
}
