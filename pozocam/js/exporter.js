function downloadVideo() {
    if (S.recordedChunks.length === 0) return;
    const blob = new Blob(S.recordedChunks, { type: 'video/webm' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `pozocam_${S.sessionId}.webm`;
    a.click();
    URL.revokeObjectURL(url);
}

function downloadJSON() {
    if (S.frames.length === 0) return;
    const data = JSON.stringify({
        session_id: S.sessionId,
        device: navigator.userAgent,
        total_points: S.frames.length,
        data: S.frames
    }, null, 2);
    const blob = new Blob([data], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `pozocam_${S.sessionId}.json`;
    a.click();
    URL.revokeObjectURL(url);
}
