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
  type: string; // IMPORT o EXPORT
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

  const triggerFilePicker = () => {
    fileInputRef.current?.click();
  };

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

  // --- PANTALLA INICIAL ---
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
    <Layout
      title="THE NOCTURNE"
      subtitle={job?.status === "DONE" ? "CONCLUDED" : "RITUAL"}
    >
      <div className="initiation-content">
        <p className="user-info">
          👤 <strong>{userEmail}</strong>
        </p>

        {/* ESTADO 1: MENÚ PRINCIPAL (Sin trabajos activos) */}
        {(!job || job.status === "FAILED") && (
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

            <div className="action-zone" style={{ marginTop: "2rem" }}>
              <p className="hero-text">Protocolo de Restauración</p>
              <div className="options-group" style={{ margin: "1rem 0" }}>
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
        )}

        {/* ESTADO 2: PROCESANDO (Común para ambos) */}
        {job &&
          (job.status === "RUNNING" ||
            job.status === "PENDING" ||
            job.status === "INITIALIZING") && (
            <div className="progress-box">
              <div className="security-badge">
                <span className="security-text">TRANSMITIENDO: {job.type}</span>
              </div>
              <h2 className="display-count">{job.doneCount}</h2>
              <p className="hero-text">ELEMENTOS PROCESADOS</p>
              <div className="loader-line"></div>
            </div>
          )}

        {/* ESTADO 3: ÉXITO (Bifurcado por Tipo) */}
        {job && job.status === "DONE" && (
          <div className="success-box">
            {job.type === "EXPORT" ? (
              <>
                <div className="security-badge success">
                  <span className="security-text">COSECHA COMPLETADA</span>
                </div>
                <h2 className="display-count">{job.doneCount}</h2>
                <p className="hero-text">CANALES EXTRAÍDOS</p>
                <button
                  className="btn-google-altar"
                  onClick={handleDownload}
                  style={{ marginTop: "1.5rem" }}
                >
                  <span className="btn-text">📥 DESCARGAR JSON</span>
                </button>
              </>
            ) : (
              <>
                <div className="security-badge success">
                  <span className="security-text">RESTAURACIÓN COMPLETADA</span>
                </div>
                <h2 className="display-count">{job.doneCount}</h2>
                <p className="hero-text">VÍNCULOS ESTABLECIDOS</p>
                <p
                  className="hero-text"
                  style={{ fontSize: "0.7rem", opacity: 0.6 }}
                >
                  Los canales han sido integrados en su nueva cuenta.
                </p>
              </>
            )}

            <button
              onClick={() => setJob(null)}
              className="btn-link"
              style={{ marginTop: "2rem" }}
            >
              VOLVER AL INICIO
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
