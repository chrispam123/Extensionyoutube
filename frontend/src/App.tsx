import { useState, useEffect } from 'react'
import './App.css'

function App() {
  const [userEmail, setUserEmail] = useState<string | null>(null)
  const [loading, setLoading] = useState<boolean>(false)

  const API_URL = import.meta.env.VITE_API_URL
  const CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID;

  // 1. Recuperar sesión al abrir la extensión
  useEffect(() => {
    // Corregido: Añadimos tipo al parámetro 'result' para evitar TS7006 (implicit any)
    chrome.storage.local.get(['nocturne_token', 'nocturne_user'], (result: { [key: string]: any }) => {
      if (result.nocturne_token && result.nocturne_user) {
        setUserEmail(result.nocturne_user)
      }
    });
  }, [])

  const loginWithGoogle = async () => {
    setLoading(true)
    try {
      // Corregido: Eliminada la variable 'manifest' (Ruff/TS6133: declared but never read)
      const redirectUri = `https://${chrome.runtime.id}.chromiumapp.org/`

      const authUrl = `https://accounts.google.com/o/oauth2/v2/auth?` +
        `client_id=${CLIENT_ID}&` +
        `response_type=code&` +
        `redirect_uri=${encodeURIComponent(redirectUri)}&` +
        `scope=${encodeURIComponent('openid email https://www.googleapis.com/auth/youtube.readonly')}&` +
        `access_type=offline&` +
        `prompt=consent`

      // B. Abrir Popup de Google
      const responseUrl = await chrome.identity.launchWebAuthFlow({
        url: authUrl,
        interactive: true
      })

      // Corregido: Validación de seguridad por si el usuario cierra el popup sin loguearse
      if (!responseUrl) {
        setLoading(false)
        return
      }

      const url = new URL(responseUrl)
      const code = url.searchParams.get('code')

      if (!code) throw new Error("No se recibió el código de autorización")

      // D. Enviar código a nuestro Backend (λ-Auth)
      const backendResponse = await fetch(`${API_URL}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code })
      })

      const data = await backendResponse.json()

      if (backendResponse.ok) {
        await chrome.storage.local.set({
          'nocturne_token': data.token,
          'nocturne_user': data.user
        })
        setUserEmail(data.user)
      } else {
        alert("Error en el backend: " + data.error)
      }

    } catch (error) {
      console.error("Fallo en login:", error)
    } finally {
      setLoading(false)
    }
  }

  const logout = () => {
    chrome.storage.local.clear(() => {
      setUserEmail(null)
    })
  }

  return (
    <div className="App">
      <h1>Nocturne Identity</h1>
      <div className="card">
        {userEmail ? (
          <>
            <p>Bienvenido: <strong>{userEmail}</strong></p>
            <button onClick={logout}>Cerrar Sesión</button>
          </>
        ) : (
          <button onClick={loginWithGoogle} disabled={loading}>
            {loading ? 'Conectando...' : 'Conectar con Google'}
          </button>
        )}
      </div>
    </div>
  )
}

export default App
