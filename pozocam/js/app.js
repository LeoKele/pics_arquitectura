document.addEventListener('DOMContentLoaded', async () => {
  initCamera();
  initGPS();
  await checkPendingUpload();

  // Inicializar modal de subida de Bootstrap
  const modalUploadEl = document.getElementById('modalUpload');
  if (modalUploadEl) {
      uploadModal = new bootstrap.Modal(modalUploadEl, {
          backdrop: 'static',
          keyboard: false
      });
  }

  // Cargar lista de cámaras cuando se abre el modal de configuración de Bootstrap
  const settingsEl = document.getElementById('modalSettings');
  if (settingsEl) {
      settingsEl.addEventListener('shown.bs.modal', refreshDeviceList);
  }
});


async function uploadToServer() {
    if (!S.recordedChunks || S.recordedChunks.length === 0) {
        toast("No hay video grabado para subir", "err");
        return;
    }

    // 1. Armamos el archivo de video
    const videoBlob = new Blob(S.recordedChunks, { type: 'video/webm' });
    videoBlob.name = `pozocam_${S.sessionId}.webm`;

    // 2. Agarramos el historial de coordenadas (nuestro futuro JSON)
    const datosGPS = S.telemetryData || [];

    // 3. Le pasamos el video Y los datos a la interfaz
    if (typeof ejecutarSubidaConUI === "function") {
        ejecutarSubidaConUI(videoBlob, datosGPS);
    } else {
        console.error("No se encontró ejecutarSubidaConUI. Revisá ui.js/uploader.js");
        toast("Error de interfaz. Ver consola.", "err");
    }
}
