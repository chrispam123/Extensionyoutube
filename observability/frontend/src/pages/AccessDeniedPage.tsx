import { signOutAndChooseAccount } from '../auth/cognito'

export function AccessDeniedPage() {
  return (
    <main className="page centered">
      <h1>Nocturne Observability</h1>
      <p className="error">This Google account is not authorized to access the panel.</p>
      <button onClick={() => void signOutAndChooseAccount()}>Choose another Google account</button>
    </main>
  )
}
