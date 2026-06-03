function showUploadModal(show) {
    if (uploadModal) {
        if (show) {
            uploadModal.show();
            // Remover botón de descarte si existía de un intento fallido anterior
            const prevDismiss = document.getElementById('btnDismissUploadModal');
            if (prevDismiss) prevDismiss.remove();
        } else {
            uploadModal.hide();
        }
    }
}

function updateUploadProgress(percentage, text) {
    const bar = document.getElementById('uploadProgressBar');
    if (bar) bar.style.width = `${percentage}%`;
    const textEl = document.getElementById('uploadStatusText');
    if (textEl) textEl.textContent = text;
}

function updateStepUI(stepId, state, text) {
    const el = document.getElementById(stepId);
    if (!el) return;
    if (state === "run") {
        el.innerHTML = `<i class="fa-solid fa-circle-notch fa-spin text-warning"></i> <span style="color: var(--warn);">${text}</span>`;
    } else if (state === "ok") {
        el.innerHTML = `<i class="fa-solid fa-circle-check text-success"></i> <span style="color: var(--accent);">${text}</span>`;
    } else if (state === "err") {
        el.innerHTML = `<i class="fa-solid fa-circle-xmark text-danger"></i> <span style="color: var(--danger); font-weight: bold;">${text}</span>`;
    } else if (state === "waiting") {
        el.innerHTML = `<i class="fa-regular fa-circle text-muted" style="opacity: 0.6;"></i> <span style="color: var(--muted); opacity: 0.6;">${text}</span>`;
    } else {
        el.innerHTML = `<i class="fa-regular fa-circle text-muted"></i> <span style="color: var(--muted);">${text}</span>`;
    }
}

function toggleUploadButtons(enabled) {
    const btns = document.querySelectorAll('#recBtnGrid button');
    btns.forEach(btn => {
        btn.disabled = !enabled;
        btn.style.opacity = enabled ? '1' : '0.5';
        btn.style.pointerEvents = enabled ? 'auto' : 'none';
    });
}

function toast(msg, type = "info") {
  const el = document.getElementById('toast');
  if (!el) return;
  el.textContent = msg;

  if (type === "ok") {
      el.style.borderColor = "var(--accent)";
  } else if (type === "err") {
      el.style.borderColor = "var(--danger)";
  } else {
      el.style.borderColor = "var(--border)";
  }

  el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), 3000);
}

async function resetUI() {
    const grid = document.getElementById('recBtnGrid');
    if (grid) {
        grid.className = 'row g-2';
        grid.innerHTML = `
          <div class="col-12">
            <button class="btn btn-danger w-100 fw-bold py-3 text-uppercase" id="btnAction" onclick="handleMainAction()"><i class="fa-solid fa-circle"></i> GRABAR</button>
          </div>
        `;
    }
    const timerEl = document.getElementById('timer');
    if (timerEl) timerEl.textContent = '00:00:00';
    const framesEl = document.getElementById('stFrames');
    if (framesEl) framesEl.textContent = '0';

    // Clear state
    S.frames = [];
    S.recordedChunks = [];
    S.sessionId = null;
    S.videoId = null;

    // Clear localForage
    try {
        await localforage.removeItem('pozocam_pending_video');
        await localforage.removeItem('pozocam_pending_metadata');
        await localforage.removeItem('pozocam_pending_session_id');
    } catch (err) {
        console.error("Error al limpiar localForage:", err);
    }
}

// ==========================================
// INTEGRACIÓN MULTIPART CON LA INTERFAZ
// ==========================================

async function ejecutarSubidaConUI(file) {
    // 1. Bloqueamos la interfaz y mostramos el modal de carga
    toggleUploadButtons(false);
    showUploadModal(true);

    // Asumiendo que tenés un ID 'step-upload' en tu HTML para el paso actual
    // Si tu ID es diferente, cambialo acá (ej: 'step1')
    updateStepUI('step-upload', 'run', 'Iniciando conexión segura...');
    updateUploadProgress(0, 'Calculando fragmentos...');

    try {
        // 2. Llamamos a la magia de uploader.js
        await subirVideoMultipart(file, (porcentaje) => {
            // 3. Actualizamos TU barra de progreso en tiempo real
            updateUploadProgress(porcentaje, `Subiendo a la nube: ${porcentaje}%`);

            if (porcentaje === 100) {
                updateStepUI('step-upload', 'run', 'Ensamblando video en el servidor...');
                updateUploadProgress(100, 'Procesando...');
            }
        });

        // 4. ÉXITO
        updateStepUI('step-upload', 'ok', '¡Video subido y ensamblado!');
        updateUploadProgress(100, '¡Finalizado!');
        toast('Video enviado correctamente al sistema', 'ok');

        // A los 3 segundos cerramos el modal y reseteamos la cámara
        setTimeout(() => {
            showUploadModal(false);
            resetUI();
            toggleUploadButtons(true);
        }, 3000);

    } catch (error) {
        // 5. ERROR
        console.error("Fallo detectado por la UI:", error);
        updateStepUI('step-upload', 'err', 'Error de conexión');
        updateUploadProgress(0, 'La subida ha fallado');
        toast('No se pudo subir el video. Verificá tu red.', 'err');

        // Dejamos que el usuario lea el error y cerramos a los 4 segundos
        setTimeout(() => {
            showUploadModal(false);
            toggleUploadButtons(true);
        }, 4000);
    }
}
