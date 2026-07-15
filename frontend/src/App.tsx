// src/App.tsx
import { useState, useEffect, useRef } from "react";
import Layout from "./components/Layout";
import RelicToggle from "./components/RelicToggle";
import hourglassLoader from "./assets/hourglass-loader.svg";
import "./styles/Initiation.css";

interface JobStatus {
  jobId: string;
  status: string;
  doneCount: number;
  failedCount: number;
  totalItems: number;
  type: string;
  currentPlaylist?: number;
  currentVideo?: number;
  downloadUrl?: string;
}

function App() {
  const [userEmail, setUserEmail] = useState<string | null>(null);
  const [job, setJob] = useState<JobStatus | null>(null);
  const [loading, setLoading] = useState<boolean>(false);

  // 1. CONFIGURACIÓN GLOBAL: Rige tanto para Cosecha como para Restauración
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
        if (typeof val === "string" || val === null) {
          setUserEmail(val);
          setLoading(false);
        }
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
    chrome.runtime.sendMessage({ action: "LOGIN" }, (res) => {
      if (!res?.success) setLoading(false);
    });
  };

  // 2. EXPORTACIÓN CORREGIDA: Ahora envía las opciones
  const startExport = () => {
    setLoading(true);
    chrome.runtime.sendMessage({
      action: "START_JOB",
      type: "EXPORT",
      options, // <--- AHORA SÍ SE ENVÍAN
    });
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
    // Preservar el estado del job para recuperarlo al re-login
    chrome.storage.local.get(["last_job_status"], (result) => {
      const snapshot = result.last_job_status;
      chrome.storage.local.clear(() => {
        if (snapshot) chrome.storage.local.set({ last_job_status: snapshot });
        setUserEmail(null);
        setJob(null);
      });
    });
  };

  if (!userEmail) {
    return (
      <Layout title="THE NOCTURNE" subtitle="INITIATION">
        <div className="initiation-content">
          <p className="hero-text">
            Exportación e Importación de tus gemas digitales
          </p>
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

  // --- PANTALLA DE ÉXITO ---
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
                <span className="cross-motif cross-inverted"></span>
                <span className="btn-text">DESCARGA TUS GEMAS</span>
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

  // --- PANTALLA DE PROGRESO ---
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
            <p className="hero-text">VÍNCULOS ESTABLECIDOS</p>
            <img
              src={hourglassLoader}
              alt="Procesando"
              className="hourglass-loader"
            />
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

  // --- MENÚ PRINCIPAL (IDLE) ---
  return (
    <Layout title="THE NOCTURNE" subtitle="RITUAL">
      <div className="initiation-content">
        <p className="user-info">
          👤 <strong>{userEmail}</strong>
        </p>

        {/* 3. ZONA GLOBAL DE CONFIGURACIÓN (Mantenida arriba) */}
        <div
          className="global-options"
          style={{
            borderBottom: "1px solid var(--color-ghost)",
            paddingBottom: "1.5rem",
          }}
        >
          <p
            className="hero-text"
            style={{ fontSize: "0.8rem", marginBottom: "1rem" }}
          >
            Configuración del Ritual
          </p>
          <div className="options-group">
            <RelicToggle
              label="Canales"
              active={options.channels}
              onChange={() =>
                setOptions({ ...options, channels: !options.channels })
              }
            />
            <RelicToggle
              label="Playlists"
              active={options.playlists}
              onChange={() =>
                setOptions({ ...options, playlists: !options.playlists })
              }
            />
          </div>
        </div>

        <div className="action-zone-container" style={{ marginTop: "1.5rem" }}>
          <div className="action-zone">
            <button
              className="btn-google-altar"
              onClick={startExport}
              disabled={loading || (!options.channels && !options.playlists)}
            >
              <span className="btn-text">COSECHAR (EXPORTAR)</span>
            </button>
          </div>

          <div className="action-zone" style={{ marginTop: "2rem" }}>
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
              disabled={loading || (!options.channels && !options.playlists)}
            >
              <span className="btn-text">RESTAURAR (IMPORTAR)</span>
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
