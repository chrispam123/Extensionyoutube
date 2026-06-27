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
  downloadUrl?: string;
}

function App() {
  const [userEmail, setUserEmail] = useState<string | null>(null);
  const [job, setJob] = useState<JobStatus | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [options, setOptions] = useState({ channels: true, playlists: false });

  // Referencia al input de archivos oculto
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

  // --- LÓGICA DE IMPORTACIÓN (EL PUENTE) ---

  // 1. El botón dispara el selector de archivos
  const triggerFilePicker = () => {
    fileInputRef.current?.click();
  };

  // 2. Se ejecuta cuando el usuario elige el archivo
  const handleFileSelect = async (
    event: React.ChangeEvent<HTMLInputElement>,
  ) => {
    const file = event.target.files?.[0];
    if (!file) return;

    // Validación de seguridad en la frontera
    if (file.type !== "application/json" && !file.name.endsWith(".json")) {
      alert("⚠️ El archivo debe ser un JSON sagrado.");
      return;
    }

    setLoading(true);
    try {
      // Leemos el contenido del archivo como texto
      const fileContent = await file.text();

      // Validamos que sea un JSON válido antes de enviarlo
      JSON.parse(fileContent);

      // Enviamos la orden al Service Worker con la carga útil
      chrome.runtime.sendMessage({
        action: "START_JOB",
        type: "IMPORT",
        options,
        payload: fileContent, // <--- Aquí viajan los datos
      });
    } catch (e) {
      console.error("Error leyendo el archivo:", e);
      alert("❌ El archivo está corrupto o no es un JSON válido.");
      setLoading(false);
    } finally {
      // Limpiamos el input para permitir subir el mismo archivo otra vez si falla
      if (fileInputRef.current) fileInputRef.current.value = "";
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

        {(!job || job.status === "DONE" || job.status === "FAILED") && (
          <>
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

            <div className="action-zone">
              <p className="hero-text">
                Configure su protocolo de restauración
              </p>
              <div className="options-group" style={{ margin: "1.5rem 0" }}>
                <RelicToggle
                  label="Suscripciones"
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

              {/* Input de archivos oculto */}
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
                <span className="btn-text">
                  {loading ? "LEYENDO..." : "INICIAR IMPORTACIÓN"}
                </span>
                <span className="arrow-icon"></span>
              </button>
            </div>
          </>
        )}

        {job && (job.status === "RUNNING" || job.status === "PENDING") && (
          <div className="progress-box">
            <div className="security-badge">
              <span className="security-text">ESTADO: {job.status}</span>
            </div>
            <h2 className="display-count">{job.doneCount}</h2>
            <p className="hero-text">CANALES PROCESADOS</p>
          </div>
        )}

        {job && job.status === "DONE" && (
          <div className="success-box">
            <div className="security-badge success">
              <span className="security-text">RITUAL COMPLETADO</span>
            </div>
            <button
              className="btn-google-altar"
              onClick={handleDownload}
              style={{ marginTop: "1rem" }}
            >
              <span className="btn-text">📥 DESCARGAR JSON</span>
            </button>
            <button
              onClick={() => setJob(null)}
              className="btn-link"
              style={{ marginTop: "1rem" }}
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
