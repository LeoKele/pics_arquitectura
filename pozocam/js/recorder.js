function handleMainAction() {
    if (!S.recording) {
        startRec();
    } else {
        stopRec();
    }
}

async function startRec() {
  if (!S.stream) return;

  S.frames = [];
  S.recordedChunks = [];
  S.startTime = Date.now();
  S.sessionId = new Date().toISOString().replace(/[:.]/g,'-').slice(0,19);

  let options = {
    mimeType: 'video/webm;codecs=vp8',
    videoBitsPerSecond: S.bitrate
  };

  if (!MediaRecorder.isTypeSupported(options.mimeType)) {
      options = { mimeType: 'video/webm' };
  }

  try {
      S.mediaRecorder = new MediaRecorder(S.stream, options);
      S.mediaRecorder.ondataavailable = (e) => {
          if (e.data.size > 0) S.recordedChunks.push(e.data);
      };
      S.mediaRecorder.onstop = async () => {
          await saveToLocalForage();
      };
      S.mediaRecorder.start(5000);
  } catch (e) {
      toast("Error al iniciar grabadora: " + e.message);
      return;
  }

  S.recording = true;
  S.gpsIntervalId = setInterval(captureTelemetry, 500);

  const tick = () => {
      if (!S.recording) return;
      updateTimer();
      S.timerRAF = requestAnimationFrame(tick);
  };
  S.timerRAF = requestAnimationFrame(tick);

  const recPill = document.getElementById('recPill');
  if (recPill) {
      recPill.className = 'badge rounded-pill border border-danger text-danger bg-transparent d-flex align-items-center gap-1 py-1 px-2 rec-pulse';
  }

  const recDot = document.getElementById('recDot');
  if (recDot) recDot.className = 'dot blink';

  const recTxt = document.getElementById('recTxt');
  if (recTxt) recTxt.textContent = 'REC';

  const timerEl = document.getElementById('timer');
  if (timerEl) {
      timerEl.classList.add('text-danger');
  }

  const btn = document.getElementById('btnAction');
  if (btn) {
      btn.innerHTML = '<i class="fa-solid fa-stop"></i> DETENER';
      btn.className = 'btn btn-light w-100 fw-bold py-3 text-uppercase';
  }

  toast('Grabación iniciada', 'ok');
}

function stopRec() {
  S.recording = false;
  clearInterval(S.gpsIntervalId);
  cancelAnimationFrame(S.timerRAF);

  if (S.mediaRecorder && S.mediaRecorder.state !== 'inactive') {
      S.mediaRecorder.stop();
  }

  const recPill = document.getElementById('recPill');
  if (recPill) {
      recPill.className = 'badge rounded-pill border border-secondary text-muted bg-transparent d-flex align-items-center gap-1 py-1 px-2';
  }

  const recDot = document.getElementById('recDot');
  if (recDot) recDot.className = 'dot';

  const recTxt = document.getElementById('recTxt');
  if (recTxt) recTxt.textContent = 'FIN';

  const timerEl = document.getElementById('timer');
  if (timerEl) {
      timerEl.classList.remove('text-danger');
  }

  const grid = document.getElementById('recBtnGrid');
  if (grid) {
      grid.className = 'row g-2';
      grid.innerHTML = `
        <div class="col-12">
          <button class="btn btn-primary w-100 fw-bold py-3 text-uppercase" onclick="uploadToServer()"><i class="fa-solid fa-cloud-arrow-up"></i> SUBIR AL SERVIDOR</button>
        </div>
        <div class="col-6">
          <button class="btn btn-outline-info w-100 fw-bold py-2.5 text-uppercase" onclick="downloadVideo()"><i class="fa-solid fa-video"></i> VIDEO</button>
        </div>
        <div class="col-6">
          <button class="btn btn-outline-info w-100 fw-bold py-2.5 text-uppercase" onclick="downloadJSON()"><i class="fa-solid fa-file-code"></i> DATOS</button>
        </div>
        <div class="col-12">
          <button class="btn btn-outline-secondary w-100 fw-bold py-2.5 text-uppercase" onclick="resetUI()"><i class="fa-solid fa-rotate-left"></i> NUEVO</button>
        </div>
      `;
  }

  toast('Grabación finalizada');
}

function updateTimer() {
  const e = Math.floor((Date.now()-S.startTime)/1000);
  const h=String(Math.floor(e/3600)).padStart(2,'0');
  const m=String(Math.floor((e%3600)/60)).padStart(2,'0');
  const s=String(e%60).padStart(2,'0');
  const timerEl = document.getElementById('timer');
  if (timerEl) timerEl.textContent = `${h}:${m}:${s}`;
}


async function uploadToServer() {
    // 1. Verificamos que realmente haya algo grabado
    if (!S.recordedChunks || S.recordedChunks.length === 0) {
        toast("No hay video grabado para subir", "err");
        return;
    }

    // 2. Unimos los pedacitos de memoria en un archivo de video real (Blob)
    const videoBlob = new Blob(S.recordedChunks, { type: 'video/webm' });

    // 3. Le inventamos un nombre al archivo usando el ID de sesión que ya creaste en startRec()
    videoBlob.name = `pozocam_${S.sessionId}.webm`;

    // 4. ¡Disparamos la magia visual y la subida a la nube!
    ejecutarSubidaConUI(videoBlob);
}
