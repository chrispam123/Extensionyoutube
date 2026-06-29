// src/App.tsx
import { useState, useEffect, useRef } from "react";
import Layout from "./components/Layout";
import RelicToggle from "./components/RelicToggle";
import "./styles/Initiation.css";

interface JobStatus {
  jobId: string;
  status: string;
  doneCount: number;
  totalItems: number;
  type: string;
  downloadUrl?: string;
}

function App() {
  const [userEmail, setUserEmail] = useState<string | null>(null);
  const [job, setJob] = useState<JobStatus | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [options, setOptions] = useState({ channels: true, playlists: false });
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    chrome.storage.local.get(["nocturne_user", "last_job_status"], (result) => {
      if (typeof result.nocturne_user === "string")
        setUserEmail(result.nocturne_user);
      if (result.last_job_status) setJob(result.last_job_status as JobStatus);
    });

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

  const triggerFilePicker = () => fileInputRef.current?.click();

  const handleFileSelect = async (
    event: React.ChangeEvent<HTMLInputElement>,
  ) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setLoading(true);
    try {
      const fileContent = await file.text();
      JSON.parse(fileContent);
      chrome.runtime.sendMessage({
        action: "START_JOB",
        type: "IMPORT",
        options,
        payload: fileContent,
      });
    } catch (e) {
      alert("Archivo inválido");
      setLoading(false);
    }
  };

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

  // --- 1. PANTALLA DE INICIACIÓN (LOGIN) ---
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
              {loading ? "ABRIENDO PUERTA..." : "CONECTAR CON GOOGLE"}
            </span>
          </button>
        </div>
      </Layout>
    );
  }

  // --- 2. PANTALLA DE ÉXITO (CONCLUDED) ---
  // Prioridad alta: Si el trabajo terminó, mostramos esto y nada más.
  if (job && job.status === "DONE") {
    return (
      <Layout title="THE NOCTURNE" subtitle="CONCLUDED">
        <div className="initiation-content">
          <p className="user-info">
            👤 <strong>{userEmail}</strong>
          </p>
          <div className="success-box">
            <div className="security-badge success">
              <span className="security-text">
                {job.type === "EXPORT"
                  ? "COSECHA COMPLETADA"
                  : "RESTAURACIÓN COMPLETADA"}
              </span>
            </div>
            <h2 className="display-count">{job.doneCount}</h2>
            <p className="hero-text">ELEMENTOS PROCESADOS</p>

            {job.type === "EXPORT" && job.downloadUrl && (
              <button
                className="btn-google-altar"
                onClick={handleDownload}
                style={{ marginTop: "1.5rem" }}
              >
                <span className="btn-text">📥 DESCARGAR JSON</span>
              </button>
            )}

            <button
              onClick={() => setJob(null)}
              className="btn-link"
              style={{ marginTop: "2rem" }}
            >
              VOLVER AL INICIO
            </button>
          </div>
          <button onClick={logout} className="btn-logout">
            CERRAR SESIÓN
          </button>
        </div>
      </Layout>
    );
  }

  // --- 3. PANTALLA DE PROGRESO (RUNNING / PENDING) ---
  if (
    job &&
    (job.status === "RUNNING" ||
      job.status === "PENDING" ||
      job.status === "INITIALIZING" ||
      job.status === "PAUSED_QUOTA")
  ) {
    return (
      <Layout title="THE NOCTURNE" subtitle="TRANSMITTING">
        <div className="initiation-content">
          <p className="user-info">
            👤 <strong>{userEmail}</strong>
          </p>
          <div className="progress-box">
            <div className="security-badge">
              <span className="security-text">ESTADO: {job.status}</span>
            </div>
            <h2 className="display-count">{job.doneCount}</h2>
            <p className="hero-text">CANALES PROCESADOS</p>
            <div className="loader-line"></div>
          </div>
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

  // --- 4. PANTALLA DE MENÚ PRINCIPAL (IDLE) ---
  // Si llegamos aquí es porque userEmail existe y job es null o FAILED
  return (
    <Layout title="THE NOCTURNE" subtitle="RITUAL">
      <div className="initiation-content">
        <p className="user-info">
          👤 <strong>{userEmail}</strong>
        </p>

        <div className="action-zone-container">
          <div className="action-zone">
            <button
              className="btn-google-altar"
              onClick={startExport}
              disabled={loading}
            >
              <span className="btn-text">EXPORTAR SUSCRIPCIONES</span>
            </button>
          </div>

          <div className="action-zone" style={{ marginTop: "2.5rem" }}>
            <p className="hero-text">Protocolo de Restauración</p>
            <div className="options-group" style={{ margin: "1.2rem 0" }}>
              <RelicToggle
                label="Canales"
                active={options.channels}
                onChange={() =>
                  setOptions({ ...options, channels: !options.channels })
                }
              />
            </div>
            <input
              type="file"
              ref={fileInputRef}
              style={{ display: "none" }}
              accept=".json"
              onChange={handleFileSelect}
            />
            <button
              className="btn-google-altar"
              onClick={triggerFilePicker}
              disabled={loading}
            >
              <span className="btn-text">INICIAR IMPORTACIÓN</span>
              <span className="arrow-icon"></span>
            </button>
          </div>
        </div>

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
