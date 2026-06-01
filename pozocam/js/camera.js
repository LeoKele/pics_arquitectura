async function initCamera() {
  if (S.stream) {
      S.stream.getTracks().forEach(t => t.stop());
  }

  try {
    let constraints = { audio: false };

    if (S.resolution === 'full') {
        constraints.video = {
            deviceId: S.deviceId ? { exact: S.deviceId } : undefined,
            facingMode: S.deviceId ? undefined : { ideal: 'environment' },
            width: { ideal: 4096 },
            height: { ideal: 2160 }
        };
    } else {
        const [w, h] = S.resolution.split('x').map(Number);
        constraints.video = {
            deviceId: S.deviceId ? { exact: S.deviceId } : undefined,
            facingMode: S.deviceId ? undefined : { ideal: 'environment' },
            width: { exact: w },
            height: { exact: h }
        };
    }

    try {
        S.stream = await navigator.mediaDevices.getUserMedia(constraints);
    } catch (err) {
        console.warn("Retrying with flexible constraints...", err);
        // Fallback if 'exact' fails
        delete constraints.video.width.exact;
        delete constraints.video.height.exact;
        S.stream = await navigator.mediaDevices.getUserMedia(constraints);
    }

    const videoTrack = S.stream.getVideoTracks()[0];
    const settings = videoTrack.getSettings();

    const resEl = document.getElementById('stRes');
    if (resEl) resEl.textContent = `${settings.width}x${settings.height}`;

    const camVideo = document.getElementById('camVideo');
    if (camVideo) camVideo.srcObject = S.stream;

    // Sync UI selects
    const selRes = document.getElementById('selRes');
    if (selRes) selRes.value = S.resolution;

    const selBitrate = document.getElementById('selBitrate');
    if (selBitrate) selBitrate.value = S.bitrate;

    const txtApiUrl = document.getElementById('txtApiUrl');
    if (txtApiUrl) txtApiUrl.value = S.apiUrl;

    // Re-enumerate to get labels if we didn't have them
    refreshDeviceList();

  } catch (e) {
      toast('Error cámara: ' + e.message);
      console.error(e);
  }
}

async function refreshDeviceList() {
    try {
        const devices = await navigator.mediaDevices.enumerateDevices();
        const videoDevices = devices.filter(d => d.kind === 'videoinput');
        const sel = document.getElementById('selCamera');
        if (!sel) return;

        sel.innerHTML = videoDevices.map(d =>
            `<option value="${d.deviceId}" ${S.deviceId === d.deviceId ? 'selected' : ''}>${d.label || 'Cámara ' + d.deviceId.slice(0,5)}</option>`
        ).join('');

        // If no deviceId saved, pick the first one
        if (!S.deviceId && videoDevices.length > 0) {
            S.deviceId = videoDevices[0].deviceId;
        }
    } catch (e) {
        toast("Error al listar cámaras");
    }
}
