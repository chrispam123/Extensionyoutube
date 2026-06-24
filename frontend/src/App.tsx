// src/App.tsx
import { useState, useEffect } from "react";
import "./App.css";

// Actualizamos la interfaz para incluir la URL de descarga
interface JobStatus {
  jobId: string;
  status: string;
  doneCount: number;
  totalItems: number;
  downloadUrl?: string; // Opcional, solo vendrá cuando el estado sea DONE
}

function App() {
  const [userEmail, setUserEmail] = useState<string | null>(null);
  const [job, setJob] = useState<JobStatus | null>(null);
  const [loading, setLoading] = useState<boolean>(false);

  // 1. SINCRONIZACIÓN: Escuchar cambios en el almacenamiento de la extensión
  useEffect(() => {
    // Carga inicial
    chrome.storage.local.get(
      ["nocturne_user", "last_job_status"],
      (result: { [key: string]: any }) => {
        if (result.nocturne_user) setUserEmail(result.nocturne_user);
        if (result.last_job_status) setJob(result.last_job_status as JobStatus);
      },
    );

    // Reaccionar a actualizaciones del Service Worker (Polling)
    const handleStorageChange = (changes: {
      [key: string]: chrome.storage.StorageChange;
    }) => {
      if (changes.nocturne_user) setUserEmail(changes.nocturne_user.newValue);
      if (changes.last_job_status) {
        setJob(changes.last_job_status.newValue as JobStatus);
        setLoading(false);
      }
    };

    chrome.storage.onChanged.addListener(handleStorageChange);
    return () => chrome.storage.onChanged.removeListener(handleStorageChange);
  }, []);

  // 2. COMANDOS AL MOTOR (Service Worker)
  const login = () => {
    setLoading(true);
    chrome.runtime.sendMessage({ action: "LOGIN" });
  };

  const startExport = () => {
    setLoading(true);
    chrome.runtime.sendMessage({ action: "START_JOB", type: "EXPORT" });
  };

  // 3. LÓGICA DE DESCARGA PROFESIONAL
  const handleDownload = () => {
    if (job?.downloadUrl) {
      chrome.downloads.download({
        url: job.downloadUrl,
        filename: `nocturne-export-${job.jobId.substring(0, 8)}.json`,
        saveAs: true, // Abre el diálogo de "Guardar como"
      });
    }
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
              {loading ? "Abriendo Google..." : "Conectar con Google"}
            </button>
          </div>
        ) : (
          <div className="user-section">
            <p className="user-info">
              👤 <strong>{userEmail}</strong>// src/App.tsx
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

            </p>

            {/* BIFURCACIÓN DE INTERFAZ SEGÚN ESTADO */}
            {(!job || job.status === "FAILED") && (
              <button
                onClick={startExport}
                disabled={loading}
                className="btn-primary"
              >
                {loading ? "Iniciando..." : "🚀 Exportar Suscripciones"}
              </button>
            )}

            {job && job.status === "RUNNING" && (
              <div className="progress-container">
                <div className="status-badge">PROCESANDO</div>
                <p className="progress-text">
                  Canales encontrados: {job.doneCount}
                </p>
                <div className="loader"></div>
              </div>
            )}

            {job && job.status === "DONE" && (
              <div className="success-container">
                <div className="status-badge success">¡LISTO!</div>
                <p>Se han exportado {job.doneCount} canales.</p>
                <button onClick={handleDownload} className="btn-download">
                  📥 Descargar JSON
                </button>
                <button onClick={startExport} className="btn-retry">
                  Repetir
                </button>
              </div>
            )}

            <div className="footer-actions">
              <button onClick={logout} className="btn-link">
                Cerrar Sesión
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
