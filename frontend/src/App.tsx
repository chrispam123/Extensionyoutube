// src/App.tsx
import { useState, useEffect } from 'react'
import './App.css'

// Definimos el contrato de datos para el Job para mantener la integridad de tipos
interface JobStatus {
  jobId: string;
  status: string;
  doneCount: number;
  totalItems: number;
}

function App() {
  const [userEmail, setUserEmail] = useState<string | null>(null)
  const [job, setJob] = useState<JobStatus | null>(null)
  const [loading, setLoading] = useState<boolean>(false)

  // 1. EFECTO DE SINCRONIZACIÓN: El Popup es un espejo del Storage
  useEffect(() => {
    // Carga inicial al abrir el popup
    chrome.storage.local.get(['nocturne_user', 'last_job_status'], (result: { [key: string]: any }) => {
      if (result.nocturne_user) setUserEmail(result.nocturne_user);
      if (result.last_job_status) setJob(result.last_job_status as JobStatus);
    });

    // Escucha en tiempo real: Si el Service Worker actualiza algo, React lo pinta
    const handleStorageChange = (changes: { [key: string]: chrome.storage.StorageChange }) => {
      if (changes.nocturne_user) {
        setUserEmail(changes.nocturne_user.newValue as string);
        setLoading(false); // Detenemos el loading si el usuario ya aparece
      }
      if (changes.last_job_status) {
        setJob(changes.last_job_status.newValue as JobStatus);
      }
    };

    chrome.storage.onChanged.addListener(handleStorageChange);
    return () => chrome.storage.onChanged.removeListener(handleStorageChange);
  }, [])

  // 2. COMANDOS AL MOTOR (Delegación total al Service Worker)
  const login = () => {
    setLoading(true);
    chrome.runtime.sendMessage({ action: "LOGIN" });
  };

  const startExport = () => {
    chrome.runtime.sendMessage({ action: "START_JOB", type: "EXPORT" });
  };

  const logout = () => {
    chrome.storage.local.clear(() => {
      setUserEmail(null);
      setJob(null);
    });
  };

  return (
    <div className="App">
      <h1>Nocturne Dashboard</h1>

      <div className="card">
        {!userEmail ? (
          <div className="login-section">
            <button onClick={login} disabled={loading} className="btn-login">
              {loading ? 'Abriendo Google...' : 'Conectar con Google'}
            </button>
            <p className="hint">Necesitamos permiso para leer tus suscripciones.</p>
          </div>
        ) : (
          <div className="user-section">
            <p className="user-info">👤 <strong>{userEmail}</strong></p>

            {/* LÓGICA DE ESTADO: El botón solo sale si no hay trabajo activo */}
            {!job || job.status === 'DONE' || job.status === 'FAILED' ? (
              <button onClick={startExport} className="btn-primary">
                🚀 Exportar Suscripciones
              </button>
            ) : (
              <div className="progress-container">
                <div className="status-badge">{job.status}</div>
                <p className="progress-text">Canales procesados: {job.doneCount}</p>
                <div className="progress-bar-simulated"></div>
              </div>
            )}

            <div className="footer-actions">
              <button onClick={logout} className="btn-link">Cerrar Sesión</button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default App
