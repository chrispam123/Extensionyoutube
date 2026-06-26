// src/App.tsx
import { useState, useEffect } from "react";
import Layout from "./components/Layout";
import "./styles/Initiation.css";

// 1. CONTRATO DE DATOS: Incluimos la URL de descarga opcional
interface JobStatus {
  jobId: string;
  status: string;
  doneCount: number;
  totalItems: number;
  downloadUrl?: string; // <--- VITAL PARA LA DESCARGA
}

function App() {
  const [userEmail, setUserEmail] = useState<string | null>(null);
  const [job, setJob] = useState<JobStatus | null>(null);
  const [loading, setLoading] = useState<boolean>(false);

  useEffect(() => {
    // Carga inicial
    chrome.storage.local.get(["nocturne_user", "last_job_status"], (result) => {
      if (typeof result.nocturne_user === "string")
        setUserEmail(result.nocturne_user);
      if (result.last_job_status) setJob(result.last_job_status as JobStatus);
    });

    // Escucha de cambios (Polling del Service Worker)
    const handleStorageChange = (changes: {
      [key: string]: chrome.storage.StorageChange;
    }) => {
      if (changes.nocturne_user) {
        const val = changes.nocturne_user.newValue;
        if (typeof val === "string" || val === null) setUserEmail(val);
      }
      if (changes.last_job_status) {
        setJob(changes.last_job_status.newValue as JobStatus);
        setLoading(false);
      }
    };

    chrome.storage.onChanged.addListener(handleStorageChange);
    return () => chrome.storage.onChanged.removeListener(handleStorageChange);
  }, []);

  const login = () => {
    setLoading(true);
    chrome.runtime.sendMessage({ action: "LOGIN" });
  };

  const startExport = () => {
    setLoading(true);
    chrome.runtime.sendMessage({ action: "START_JOB", type: "EXPORT" });
  };

  // ===========================================================================
  // NUEVO: LÓGICA DE DESCARGA (PRINCIPIO DE ENTREGA)
  // ===========================================================================
  const handleDownload = () => {
    if (job?.downloadUrl) {
      chrome.downloads.download({
        url: job.downloadUrl,
        filename: `nocturne-export-${job.jobId.substring(0, 8)}.json`,
        saveAs: true,
      });
    }
  };

  const logout = () => {
    chrome.storage.local.clear(() => {
      setUserEmail(null);
      setJob(null);
    });
  };

  if (!userEmail) {
    return (
      <Layout title="THE NOCTURNE" subtitle="INITIATION">
        <div className="initiation-content">
          <p className="hero-text">Surrender to the digital void.</p>
          <button
            className="btn-google-altar"
            onClick={login}
            disabled={loading}
          >
            <span className="btn-text">
              {loading ? "INICIANDO..." : "CONECTAR CON GOOGLE"}
            </span>
          </button>
        </div>
      </Layout>
    );
  }

  return (
    <Layout title="THE NOCTURNE" subtitle="RITUAL">
      <div className="initiation-content">
        <p className="user-info">
          👤 <strong>{userEmail}</strong>
        </p>

        {/* CASO 1: NO HAY TRABAJO O FALLÓ */}
        {(!job || job.status === "FAILED") && (
          <div className="action-zone">
            <button
              className="btn-google-altar"
              onClick={startExport}
              disabled={loading}
            >
              <span className="btn-text">
                {loading ? "PREPARANDO..." : "EXPORTAR SUSCRIPCIONES"}
              </span>
            </button>
          </div>
        )}

        {/* CASO 2: TRABAJO EN PROGRESO */}
        {job && (job.status === "RUNNING" || job.status === "PENDING") && (
          <div className="progress-box">
            <div className="security-badge">
              <span className="security-text">ESTADO: {job.status}</span>
            </div>
            <h2 className="display-count">{job.doneCount}</h2>
            <p className="hero-text">CANALES PROCESADOS</p>
          </div>
        )}

        {/* =====================================================================
            CASO 3: ÉXITO FINAL (EL BLOQUE QUE FALTABA)
            ===================================================================== */}
        {job && job.status === "DONE" && (
          <div className="success-box">
            <div className="security-badge success">
              <span className="security-text">RITUAL COMPLETADO</span>
            </div>
            <h2 className="display-count">{job.doneCount}</h2>
            <p className="hero-text">CANALES COSECHADOS</p>

            <button
              className="btn-google-altar"
              onClick={handleDownload}
              style={{ marginTop: "1rem" }}
            >
              <span className="btn-text">📥 DESCARGAR JSON</span>
            </button>

            <button
              onClick={startExport}
              className="btn-link"
              style={{ marginTop: "1rem" }}
            >
              REPETIR PROCESO
            </button>
          </div>
        )}

        <button
          onClick={logout}
          className="btn-logout"
          style={{ marginTop: "2rem" }}
        >
          CERRAR SESIÓN
        </button>
      </div>
    </Layout>
  );
}

export default App;
