const S = {
  recording: false,
  startTime: null,
  frames: [],
  gps: null,
  watchId: null,
  timerRAF: null,
  gpsIntervalId: null,
  mediaRecorder: null,
  recordedChunks: [],
  stream: null,
  sessionId: null,

  // Settings
  deviceId: localStorage.getItem('pozocam_deviceId') || null,
  resolution: localStorage.getItem('pozocam_res') || '1920x1080',
  bitrate: parseInt(localStorage.getItem('pozocam_bitrate')) || 7500000,
  apiUrl: localStorage.getItem('pozocam_apiUrl') || 'http://localhost:8000',
  videoId: null
};

let uploadModal = null;

function applySettings() {
    S.deviceId = document.getElementById('selCamera').value;
    S.resolution = document.getElementById('selRes').value;
    S.bitrate = parseInt(document.getElementById('selBitrate').value);
    S.apiUrl = document.getElementById('txtApiUrl').value.trim() || 'http://localhost:8000';

    localStorage.setItem('pozocam_deviceId', S.deviceId);
    localStorage.setItem('pozocam_res', S.resolution);
    localStorage.setItem('pozocam_bitrate', S.bitrate);
    localStorage.setItem('pozocam_apiUrl', S.apiUrl);

    if (!S.recording) {
        initCamera();
    }
}
