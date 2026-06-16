import { useState } from 'react'
import './App.css'

function App() {
  const [status, setStatus] = useState<string>('Esperando...')
  const API_URL = import.meta.env.VITE_API_URL;

  const testConnection = async () => {
    setStatus('Consultando...');
    try {
      // Intentamos consultar un jobId que no existe para ver el 404
      // Pero esta vez desde el origen correcto (la extensión)
      const response = await fetch(`${API_URL}/status/test-id-123`);
      const data = await response.json();

      if (response.status === 404) {
        setStatus('✅ Conexión Exitosa: El Backend respondió 404 (Correcto)');
      } else {
        setStatus(`🤔 Respuesta inesperada: ${response.status}`);
      }
      console.log('Datos recibidos:', data);
    } catch (error) {
      console.error(error);
      setStatus('❌ Error de CORS o Red. Revisa la consola.');
    }
  }

  return (
    <div className="App">
      <h1>Nocturne QA Sensor</h1>
      <div className="card">
        <button onClick={testConnection}>
          Probar Conexión con AWS
        </button>
        <p>Estado: {status}</p>
        <small>URL: {API_URL}</small>
      </div>
    </div>
  )
}

export default App
