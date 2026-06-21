// src/background.ts
// Motor de fondo de Nocturne y quien hace el polling

// 1. CONFIGURACIÓN (Vite inyectará estos valores en el build)
const API_URL = import.meta.env.VITE_API_URL;
const CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID;

// 2. CENTRALITA DE MENSAJES
// Escucha las órdenes que vienen del Popup (React)
// Corregido: Usamos '_' para parámetros que la API exige pero nosotros no usamos
chrome.runtime.onMessage.addListener((message, _sender, _sendResponse) => {
  if (message.action === "LOGIN") {
    handleLogin();
  } else if (message.action === "START_JOB") {
    handleStartJob(message.type);
  }
  return true;
});
// 3. LÓGICA DE LOGIN (OAuth2)
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

    // Llamada al Backend (λ-Auth)
    const res = await fetch(`${API_URL}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code })
    });

    const data = await res.json();
    if (res.ok) {
      // Guardamos en el storage para que el Popup lo vea
      await chrome.storage.local.set({
        'nocturne_token': data.token,
        'nocturne_user': data.user
      });
    }
  } catch (error) {
    console.error("Error en Background Login:", error);
  }
}

// 4. LÓGICA DE INICIO DE TRABAJO (Export/Import)
async function handleStartJob(type: string) {
  try {
    const { nocturne_token } = await chrome.storage.local.get('nocturne_token');

    const res = await fetch(`${API_URL}/jobs`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${nocturne_token}`
      },
      body: JSON.stringify({ type })
    });

    const data = await res.json();
    if (res.ok) {
      // Guardamos el Job activo y encendemos la alarma de Polling
      await chrome.storage.local.set({ 'active_job_id': data.jobId });

      // Creamos una alarma para revisar el estado cada 1 minuto
      chrome.alarms.create('poll-status', { periodInMinutes: 1 });

      // Ejecutamos el primer check inmediatamente
      checkJobStatus(data.jobId);
    }
  } catch (error) {
    console.error("Error iniciando Job:", error);
  }
}

// 5. SISTEMA DE POLLING (Alarmas)
chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name === 'poll-status') {
    const result = await chrome.storage.local.get('active_job_id');
    const active_job_id = result.active_job_id;

    // Corregido: Validación de tipo para asegurar que es un string válido
    if (typeof active_job_id === 'string') {
      checkJobStatus(active_job_id);
    } else {
      chrome.alarms.clear('poll-status');
    }
  }
});

async function checkJobStatus(jobId: string) {
  try {
    const res = await fetch(`${API_URL}/status/${jobId}`);
    const data = await res.json();

    if (res.ok) {
      await chrome.storage.local.set({ 'last_job_status': data });
      if (data.status === 'DONE' || data.status === 'FAILED') {
        chrome.alarms.clear('poll-status');
        chrome.storage.local.remove('active_job_id');

        chrome.notifications.create({
          type: 'basic',
          iconUrl: 'vite.svg',
          title: 'Nocturne Update',
          message: `El trabajo ha finalizado: ${data.status}`
        });
      }
    }
  } catch (error) {
    console.error("Error en Polling:", error);
  }
}
