import { useState, useEffect } from "react";
import Layout from "./components/Layout";
import "./styles/Initiation.css";

function App() {
  const [userEmail, setUserEmail] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(false);

  useEffect(() => {
    // PRINCIPIO DE TYPE NARROWING:
    // Si en la realidad física esto es un string, hazlo. Si no, ignóralo.
    chrome.runtime.sendMessage({ action: "GET_USER" }, (res) => {
      if (typeof res?.nocturne_user === "string") {
        setUserEmail(res.nocturne_user);
      }
    });
  }, []);

  const login = () => {
    setLoading(true);
    chrome.runtime.sendMessage({ action: "LOGIN" });
  };

  // Si no hay usuario, mostramos la pantalla de INICIACIÓN
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

          <footer className="initiation-footer">
            <p>
              AL PROCEDER, RECONOCES LOS TÉRMINOS DEL PACTO DIGITAL Y NUESTRA
              POLÍTICA DE SOMBRAS.
            </p>
            <div className="footer-links">
              <span>PRIVACIDAD</span>
              <span>TÉRMINOS</span>
            </div>
          </footer>
        </div>
      </Layout>
    );
  }

  // Pantalla de usuario logueado (la haremos en el siguiente bloque)
  return (
    <Layout title="THE NOCTURNE" subtitle="RITUAL">
      <p>Bienvenido, {userEmail}</p>
    </Layout>
  );
}

export default App;
