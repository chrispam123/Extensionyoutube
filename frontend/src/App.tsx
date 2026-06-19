import { useState, useEffect } from 'react'
import './App.css'

function App() {
  const [userEmail, setUserEmail] = useState<string | null>(null)
  const [loading, setLoading] = useState<boolean>(false)

  const API_URL = import.meta.env.VITE_API_URL
  const CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID;


  // 1. Efecto para recuperar la sesión al abrir la extensión
  useEffect(() => {
    chrome.storage.local.get(['nocturne_token', 'nocturne_user'], (result) => {
      if (result.nocturne_token && result.nocturne_user) {
        setUserEmail(result.nocturne_user)
      }
    })
  }, [])

  const loginWithGoogle = async () => {
    setLoading(true)
    try {
      // A. Construir URL de Google OAuth
      const manifest = chrome.runtime.getManifest()
      const redirectUri = `https://${chrome.runtime.id}.chromiumapp.org/`
      const authUrl = `https://accounts.google.com/o/oauth2/v2/auth?` +
        `client_id=${CLIENT_ID}&` +
        `response_type=code&` +
        `redirect_uri=${encodeURIComponent(redirectUri)}&` +
        `scope=${encodeURIComponent('openid email https://www.googleapis.com/auth/youtube.readonly')}&` +
        `access_type=offline&` +  //access_type=offline: CRÍTICO. Sin este parámetro, Google nunca enviará el refresh_token
        `prompt=consent` // Forzamos consent para asegurar el refresh_token en pruebas

      // B. Abrir Popup de Google
      const responseUrl = await chrome.identity.launchWebAuthFlow({
        url: authUrl,
        interactive: true
      })

      // C. Extraer el código de la URL de respuesta
      const url = new URL(responseUrl!)
      const code = url.searchParams.get('code')

      // D. Enviar código a nuestro Backend (λ-Auth)
      const backendResponse = await fetch(`${API_URL}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code })
      })

      const data = await backendResponse.json()

      if (backendResponse.ok) {
        // E. Guardar sesión profesionalmente
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
