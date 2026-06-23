// src/background.ts
// Motor de fondo de Nocturne - Arquitectura de Persistencia

// 1. CONFIGURACIÓN (Inyectada por Vite/GitHub Actions)
const API_URL = import.meta.env.VITE_API_URL;
const CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID;

// 2. ESCUCHA DE COMANDOS DESDE EL POPUP (REACT)
chrome.runtime.onMessage.addListener((message, _sender, _sendResponse) => {
  if (message.action === "LOGIN") {
    handleLogin();
  } else if (message.action === "START_JOB") {
    handleStartJob(message.type);
  }
  return true; // Mantiene el canal abierto para respuestas asíncronas
});

// 3. LÓGICA DE LOGIN (Intercambio de tokens con Google y AWS)
async function handleLogin() {
  try {
    const redirectUri = `https://${chrome.runtime.id}.chromiumapp.org/`;
    const authUrl = `https://accounts.google.com/o/oauth2/v2/auth?` +
      `client_id=${CLIENT_ID}&` +
      `response_type=code&` +
      `redirect_uri=${encodeURIComponent(redirectUri)}&` +
      `scope=${encodeURIComponent('openid email https://www.googleapis.com/auth/youtube.readonly')}&` +
      `access_type=offline&prompt=consent`;

    const responseUrl = await chrome.identity.launchWebAuthFlow({
      url: authUrl,
      interactive: true
    });

    if (!responseUrl) return;

    const url = new URL(responseUrl);
    const code = url.searchParams.get('code');

    const res = await fetch(`${API_URL}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code })
    });

    const data = await res.json();
    if (res.ok) {
      // Guardamos el JWT de Nocturne para futuras peticiones
      await chrome.storage.local.set({
        'nocturne_token': data.token,
        'nocturne_user': data.user
      });
    }
  } catch (error) {
    console.error("Error en Login:", error);
  }
}

// 4. LÓGICA DE INICIO DE TRABAJO (Exportación/Importación)
async function handleStartJob(type: string) {
  try {
    // Recuperamos el token para identificarnos ante la Lambda de Upload
    const { nocturne_token } = await chrome.storage.local.get('nocturne_token');

    const res = await fetch(`${API_URL}/jobs`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${nocturne_token}` // <--- Identidad enviada
      },
      body: JSON.stringify({ type })
    });

    const data = await res.json();
    if (res.ok) {
      await chrome.storage.local.set({ 'active_job_id': data.jobId });
      // Iniciamos la alarma de polling (cada 1 minuto)
      chrome.alarms.create('poll-status', { periodInMinutes: 1 });
      checkJobStatus(data.jobId);
    }
  } catch (error) {
    console.error("Error iniciando Job:", error);
  }
}

// 5. SISTEMA DE ALARMAS (Polling en segundo plano)
chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name === 'poll-status') {
    const result = await chrome.storage.local.get('active_job_id');
    const active_job_id = result.active_job_id;

    if (typeof active_job_id === 'string') {
      checkJobStatus(active_job_id);
    } else {
      chrome.alarms.clear('poll-status');
    }
  }
});

// 6. CONSULTA DE ESTADO (La función que fallaba)
async function checkJobStatus(jobId: string) {
  try {
    // --- CORRECCIÓN CRÍTICA ---
    // Recuperamos el token del almacenamiento local
    const { nocturne_token } = await chrome.storage.local.get('nocturne_token');

    // Realizamos la petición incluyendo el Header de Authorization
    const res = await fetch(`${API_URL}/status/${jobId}`, {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${nocturne_token}` // <--- AHORA SÍ ENVIAMOS EL PASAPORTE
      }
    });

    const data = await res.json();

    if (res.ok) {
      // Actualizamos el estado para que el Popup de React lo pinte
      await chrome.storage.local.set({ 'last_job_status': data });

      if (data.status === 'DONE' || data.status === 'FAILED') {
        chrome.alarms.clear('poll-status');
        chrome.storage.local.remove('active_job_id');

        // Notificación visual al sistema operativo
        chrome.notifications.create({
          type: 'basic',
          iconUrl: 'vite.svg',
          title: 'Nocturne Update',
          message: `El proceso ha finalizado: ${data.status}`
        });
      }
    }
  } catch (error) {
    console.error("Error en Polling de Status:", error);
  }
}
