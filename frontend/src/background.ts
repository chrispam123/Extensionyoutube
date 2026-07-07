// src/background.ts
// Motor de fondo de Nocturne - Arquitectura de Persistencia y Resiliencia

// 0. CONFIGURACIÓN DEL SIDE PANEL (Apertura al hacer clic en el icono)
chrome.sidePanel
  .setPanelBehavior({ openPanelOnActionClick: true })
  .catch((error) => console.error("Error configurando SidePanel:", error));

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
      // Guardamos la sesión
      await chrome.storage.local.set({
        nocturne_token: data.token,
        nocturne_user: data.user,
      });

      // [NUEVO]: Sincronización inmediata tras el login
      // Intentamos ver si el usuario dejó algún trabajo a medias en la nube
      await syncActiveJob();

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

// [NUEVO]: Función de Sincronización (El Apretón de Manos)
async function syncActiveJob() {
  console.log("🔍 Sincronizando estado con la nube...");
  // Llamamos a handleStartJob con tipo SYNC_CHECK.
  // - Si hay un job activo → 409 → se activa el polling
  // - Si no hay nada → 200 → no se hace nada
  await handleStartJob("SYNC_CHECK", {}, null, () => {});
}

// 4. LÓGICA DE INICIO DE TRABAJO (Con manejo de 409 Conflict)
async function handleStartJob(
  type: string,
  options: object,
  payload: string | null,
  sendResponse: (response: object) => void,
) {
  try {
    const { nocturne_token } = await chrome.storage.local.get("nocturne_token");
    if (!nocturne_token) return;

    const res = await fetch(`${API_URL}/jobs`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${nocturne_token}`,
      },
      body: JSON.stringify({ type, options }),
    });

    const data = await res.json();

    // SYNC_CHECK sin trabajo activo: 200, no hay nada que hacer
    if (type === "SYNC_CHECK" && res.status === 200) {
      sendResponse({ success: true, active: false });
      return;
    }

    // [MODIFICADO]: Tratamos el 201 (Creado) y el 409 (Ya existe) como éxitos de flujo
    if (res.ok || res.status === 409) {
      const jobId = data.jobId;

      if (res.status === 409) {
        console.log(`♻️ Recuperando Job existente: ${jobId}`);
      }

      // Si es un IMPORT nuevo (201), subimos el archivo
      if (
        res.status === 201 &&
        type === "IMPORT" &&
        data.uploadUrl &&
        payload
      ) {
        await fetch(data.uploadUrl, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: payload,
        });
      }

      // Anclamos el ID en el storage y activamos el Polling
      await chrome.storage.local.set({ active_job_id: jobId });
      chrome.alarms.create("poll-status", { periodInMinutes: 1 });

      // Primer check inmediato para actualizar la UI de React
      checkJobStatus(jobId);

      sendResponse({ success: true, jobId: jobId });
    } else {
      sendResponse({ success: false, error: data.error });
    }
  } catch (error) {
    console.error("Error iniciando/sincronizando Job:", error);
    sendResponse({ success: false, error: "Error de comunicación" });
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
    if (!nocturne_token) return;

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
          title: "Nocturne Ritual",
          message: `El proceso ha finalizado: ${data.status}`,
        });
      }
    }
  } catch (error) {
    console.error("Error en Polling:", error);
  }
}
