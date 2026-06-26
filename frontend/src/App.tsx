// src/App.tsx
import { useState, useEffect } from "react";
import Layout from "./components/Layout";
import "./styles/Initiation.css"; // Reutilizamos estilos base

// 1. CONTRATO DE DATOS: Definimos qué es un Job para TypeScript
interface JobStatus {
  jobId: string;
  status: string;
  doneCount: number;
  totalItems: number;
  downloadUrl?: string;
}

function App() {
  const [userEmail, setUserEmail] = useState<string | null>(null);
  const [job, setJob] = useState<JobStatus | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  //Si defines job dentro de un if, no estará disponible fuera.
  // 2. EFECTO DE VIGILANCIA: Sincronización con el Service Worker
  useEffect(() => {
    // A. Carga inicial: ¿Quién soy y qué estoy haciendo?
    chrome.storage.local.get(["nocturne_user", "last_job_status"], (res) => {
      if (typeof res.nocturne_user === "string") {
        setUserEmail(res.nocturne_user);
      }
      if (res.last_job_status) {
        setJob(res.last_job_status as JobStatus);
      }
    });

    // B. Escucha activa: Si el Background actualiza el storage, React reacciona
    const handleStorageChange = (changes: {
      [key: string]: chrome.storage.StorageChange;
    }) => {
      if (changes.nocturne_user) {
        const val = changes.nocturne_user.newValue;
        if (typeof val === "string" || val === null) {
          setUserEmail(val);
        }
      }
      if (changes.last_job_status) {
        setJob(changes.last_job_status.newValue as JobStatus);
        setLoading(false); // Detenemos estados de carga si llega un update
      }
    };

    chrome.storage.onChanged.addListener(handleStorageChange);
    return () => chrome.storage.onChanged.removeListener(handleStorageChange);
  }, []);

  // 3. COMANDOS AL MOTOR (Background)
  const login = () => {
    setLoading(true);
    chrome.runtime.sendMessage({ action: "LOGIN" });
  };

  const startExport = () => {
    setLoading(true);
    chrome.runtime.sendMessage({ action: "START_JOB", type: "EXPORT" });
  };

  const logout = () => {
    chrome.storage.local.clear(() => {
      setUserEmail(null);
      setJob(null);
    });
  };

  // --- RENDERIZADO: PANTALLA DE INICIACIÓN ---
  if (!userEmail) {
    return (
      <Layout title="THE NOCTURNE" subtitle="INITIATION">
        <div className="initiation-content">
          <p className="hero-text">
            Surrender to the digital void. <br />
            Your journey into the atmospheric abyss begins with a single
            connection.
          </p>
          <div className="security-badge">
            <span className="shield-icon">🛡️</span>
            <span className="security-text">
              VAULT SECURITY PROTOCOL ACTIVE
            </span>
          </div>
          <button
            className="btn-google-altar"
            onClick={login}
            disabled={loading}
          >
            <span className="google-icon">G</span>
            <span className="btn-text">
              {loading ? "INICIANDO..." : "CONECTAR CON GOOGLE"}
            </span>
            <span className="arrow-icon"></span>
          </button>
        </div>
      </Layout>
    );
  }

  // --- RENDERIZADO: PANTALLA DE RITUAL (DASHBOARD) ---
  return (
    <Layout title="THE NOCTURNE" subtitle="RITUAL">
      <div className="initiation-content">
        <p className="user-info">
          👤 <strong>{userEmail}</strong>
        </p>

        {/* LÓGICA DINÁMICA SEGÚN EL ESTADO DEL TRABAJO */}
        {!job || job.status === "DONE" || job.status === "FAILED" ? (
          <div className="action-zone">
            <p className="hero-text">Seleccione su protocolo de transmisión</p>
            <button
              className="btn-google-altar"
              onClick={startExport}
              disabled={loading}
            >
              <span className="btn-text">
                {loading ? "PREPARANDO..." : "EXPORTAR SUSCRIPCIONES"}
              </span>
              <span className="arrow-icon"></span>
            </button>
          </div>
        ) : (
          <div className="progress-box">
            <div className="security-badge">
              <span className="security-text">ESTADO: {job.status}</span>
            </div>
            <h2 className="display-count">{job.doneCount}</h2>
            <p className="hero-text">CANALES PROCESADOS</p>
            <div className="loader-line"></div>
          </div>
        )}

        <button onClick={logout} className="btn-logout">
          CERRAR SESIÓN
        </button>
      </div>
    </Layout>
  );
}

export default App;
