import { useEffect, useState } from 'react'
import type { User } from 'oidc-client-ts'
import { completeSignIn, getCurrentUser, hasRequiredGroup, removeCurrentUser } from './auth/cognito'
import { AccessDeniedPage } from './pages/AccessDeniedPage'
import { DashboardPage } from './pages/DashboardPage'
import { LoginPage } from './pages/LoginPage'

export function App() {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [accessDenied, setAccessDenied] = useState(false)

  useEffect(() => {
    const initialize = async () => {
      try {
        const currentUser = window.location.pathname === '/auth/callback'
          ? await completeSignIn()
          : await getCurrentUser()
        if (currentUser && !hasRequiredGroup(currentUser.access_token)) {
          await removeCurrentUser()
          setAccessDenied(true)
        } else {
          setUser(currentUser)
        }
        if (window.location.pathname === '/auth/callback') {
          window.history.replaceState({}, document.title, '/')
        }
      } catch (initializationError) {
        setError(initializationError instanceof Error ? initializationError.message : 'Authentication failed')
      } finally {
        setLoading(false)
      }
    }

    void initialize()
  }, [])

  if (loading) return <main className="page centered">Loading...</main>
  if (error) return <main className="page centered"><p className="error">{error}</p></main>
  if (accessDenied) return <AccessDeniedPage />
  if (!user) return <LoginPage />

  return <DashboardPage accessToken={user.access_token} />
}
