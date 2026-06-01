function initGPS() {
  if (!navigator.geolocation) {
      toast("GPS no soportado", "err");
      return;
  }
  S.watchId = navigator.geolocation.watchPosition(
    pos => {
      S.gps = {
        lat: pos.coords.latitude,
        lng: pos.coords.longitude,
        accuracy: pos.coords.accuracy,
        speed: pos.coords.speed
      };
      updateGpsUI();
    },
    err => {
      document.getElementById('gpsPill').className = 'badge rounded-pill border border-secondary text-muted bg-transparent d-flex align-items-center gap-1 py-1 px-2';
      document.getElementById('gpsVal').textContent = 'Error GPS';
    },
    { enableHighAccuracy: true, maximumAge: 1000, timeout: 5000 }
  );
}

function updateGpsUI() {
  const g = S.gps;
  if (!g) return;
  const isOk = g.accuracy < 20;

  const gpsPill = document.getElementById('gpsPill');
  if (gpsPill) {
      gpsPill.className = 'badge rounded-pill border bg-transparent d-flex align-items-center gap-1 py-1 px-2 ' + (isOk ? 'border-success text-success' : 'border-warning text-warning');
  }

  const gpsTxt = document.getElementById('gpsTxt');
  if (gpsTxt) gpsTxt.textContent = isOk ? 'GPS OK' : 'GPS BAJO';

  const gpsVal = document.getElementById('gpsVal');
  if (gpsVal) gpsVal.innerHTML = `${g.lat.toFixed(6)}<br>${g.lng.toFixed(6)}`;

  const stAcc = document.getElementById('stAcc');
  if (stAcc) stAcc.textContent = `±${Math.round(g.accuracy)}m`;
}

function captureTelemetry() {
  if (!S.recording) return;
  const now = Date.now();
  const g = S.gps;
  S.frames.push({
    timestamp: new Date(now).toISOString(),
    elapsed_ms: now - S.startTime,
    lat: g ? g.lat : null,
    lng: g ? g.lng : null,
    acc: g ? g.accuracy : null,
    spd: g ? g.speed : null
  });

  const stFrames = document.getElementById('stFrames');
  if (stFrames) stFrames.textContent = S.frames.length;
}
