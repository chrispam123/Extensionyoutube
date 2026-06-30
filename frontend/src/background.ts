// src/background.ts
// Motor de fondo de Nocturne - Arquitectura de Persistencia

// 1. CONFIGURACIÓN (Inyectada por Vite/GitHub Actions)
const API_URL = import.meta.env.VITE_API_URL;
const CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID;

// 2. ESCUCHA DE COMANDOS DESDE EL POPUP (REACT)
chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  switch (message.action) {
    case "LOGIN":
      handleLogin(sendResponse);
      return true;

    case "START_JOB":
      // [NUEVO]: Ahora pasamos también las opciones y la carga útil (archivo)
      handleStartJob(
        message.type,
        message.options,
        message.payload,
        sendResponse,
      );
      return true;

    case "GET_USER":
      chrome.storage.local.get(["nocturne_user"], (result) => {
        sendResponse({ nocturne_user: result.nocturne_user });
      });
      return true;
  }
});

// 3. LÓGICA DE LOGIN (OAuth2)
async function handleLogin(sendResponse: (response: object) => void) {
  try {
    const redirectUri = `https://${chrome.runtime.id}.chromiumapp.org/`;
    const authUrl =
      `https://accounts.google.com/o/oauth2/v2/auth?` +
      `client_id=${CLIENT_ID}&` +
      `response_type=code&` +
      `redirect_uri=${encodeURIComponent(redirectUri)}&` +
      // CAMBIO: Usamos force-ssl para permitir suscripciones (escritura)nvalidación de Sesión. Al cambiar el scope, los tokens antiguos en DynamoDB ya no sirven para importar.
      // Debes cerrar sesión en la extensión y volver a entrar para generar un token con el nuevo scope
      `scope=${encodeURIComponent("openid email https://www.googleapis.com/auth/youtube.force-ssl")}&` +
      `access_type=offline&prompt=consent`;

    const responseUrl = await chrome.identity.launchWebAuthFlow({
      url: authUrl,
      interactive: true,
    });

    if (!responseUrl) {
      sendResponse({ success: false, error: "Cancelado" });
      return;
    }

    const url = new URL(responseUrl);
    const code = url.searchParams.get("code");

    const res = await fetch(`${API_URL}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code }),
    });

    const data = await res.json();
    if (res.ok) {
      await chrome.storage.local.set({
        nocturne_token: data.token,
        nocturne_user: data.user,
      });
      sendResponse({ success: true, user: data.user });
    } else {
      sendResponse({
        success: false,
        error: data.error || "Error del servidor",
      });
    }
  } catch (error) {
    console.error("Error en Login:", error);
    sendResponse({ success: false, error: "Error de red" });
  }
}

// 4. LÓGICA DE INICIO DE TRABAJO (Doble Salto para Importación)
async function handleStartJob(
  type: string,
  options: object,
  payload: string | null,
  sendResponse: (response: object) => void,
) {
  try {
    const { nocturne_token } = await chrome.storage.local.get("nocturne_token");

    // PASO 1: Registrar el Job en AWS y obtener URL si es IMPORT
    const res = await fetch(`${API_URL}/jobs`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${nocturne_token}`,
      },
      body: JSON.stringify({ type, options }),
    });

    const data = await res.json();

    if (!res.ok) {
      sendResponse({ success: false, error: data.error });
      return;
    }

    // PASO 2: Si es IMPORT, subimos el archivo directamente a S3(para q haga el trabajo pesado) no pasa por apigateway
    // Manejo de payload: El contenido del archivo viaja del Popup al Service Worker y de ahí a S3. Es un flujo de memoria eficiente porque el archivo JSON
    // de suscripciones no suele pesar más de unos pocos megabytes.
    if (type === "IMPORT" && data.uploadUrl && payload) {
      console.log("📦 Iniciando subida directa a S3...");
      const s3Res = await fetch(data.uploadUrl, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: payload, // El contenido del JSON que leyó el Popup
      });

      if (!s3Res.ok) {
        throw new Error("Fallo al subir el archivo al búnker S3");
      }
      console.log("✅ Archivo entregado a S3 con éxito.");
    }

    // PASO 3: Activar el Polling de estado
    await chrome.storage.local.set({ active_job_id: data.jobId });
    chrome.alarms.create("poll-status", { periodInMinutes: 1 });
    checkJobStatus(data.jobId);

    sendResponse({ success: true, jobId: data.jobId });
  } catch (error) {
    console.error("Error iniciando Job:", error);
    sendResponse({ success: false, error: "Error en la transmisión" });
  }
}

// 5. SISTEMA DE ALARMAS (Polling)
chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name === "poll-status") {
    const result = await chrome.storage.local.get("active_job_id");
    const active_job_id = result.active_job_id;
    if (typeof active_job_id === "string") {
      checkJobStatus(active_job_id);
    } else {
      chrome.alarms.clear("poll-status");
    }
  }
});

// 6. CONSULTA DE ESTADO
async function checkJobStatus(jobId: string) {
  try {
    const { nocturne_token } = await chrome.storage.local.get("nocturne_token");
    const res = await fetch(`${API_URL}/status/${jobId}`, {
      method: "GET",
      headers: { Authorization: `Bearer ${nocturne_token}` },
    });

    const data = await res.json();
    if (res.ok) {
      await chrome.storage.local.set({ last_job_status: data });
      if (data.status === "DONE" || data.status === "FAILED") {
        chrome.alarms.clear("poll-status");
        chrome.storage.local.remove("active_job_id");
        chrome.notifications.create({
          type: "basic",
          iconUrl: "vite.svg",
          title: "Nocturne Update",
          message: `El proceso ha finalizado: ${data.status}`,
        });
      }
    }
  } catch (error) {
    console.error("Error en Polling:", error);
  }
}
