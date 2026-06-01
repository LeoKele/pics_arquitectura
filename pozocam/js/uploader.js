// uploader.js - Lógica de S3 Multipart Upload
const API_URL = '';

// La interfaz ahora recibe también los datosGPS
window.ejecutarSubidaConUI = async function(file, datosGPS) {
    const uploadModalEl = document.getElementById('modalUpload');
    if (!uploadModalEl) return;

    const uploadModal = bootstrap.Modal.getInstance(uploadModalEl) || new bootstrap.Modal(uploadModalEl);
    uploadModal.show();

    // ACÁ ESTABA EL ERROR: Ahora usamos el ID exacto de tu HTML
    const progressBar = document.getElementById('uploadProgressBar');
    const statusText = document.getElementById('uploadStatusText');

    // Reiniciamos la barra
    progressBar.style.width = '0%';
    progressBar.innerText = '0%'; // El porcentaje lo ponemos adentro de la barrita
    statusText.innerText = 'Iniciando subida...';

    try {
        // Le pasamos los datosGPS al motor de subida
        const result = await subirVideoMultipart(file, datosGPS, (porcentaje) => {
            progressBar.style.width = `${porcentaje}%`;
            progressBar.innerText = `${porcentaje}%`;
            statusText.innerText = 'Subiendo video y GPS...';
        });

        // Éxito total
        progressBar.style.width = '100%';
        progressBar.classList.replace('bg-primary', 'bg-success');
        progressBar.innerText = '100%';
        statusText.innerText = '¡Video y telemetría subidos correctamente!';

        setTimeout(() => {
            uploadModal.hide();
            toast("Enviado al servidor exitosamente", "ok");
            S.recordedChunks = [];
            S.telemetryData = []; // Vaciamos la memoria del GPS tras subir
        }, 2000);

    } catch (error) {
        console.error("Error al subir:", error);
        progressBar.classList.replace('bg-primary', 'bg-danger');
        statusText.innerText = 'Error al subir el archivo.';
        toast("Error al subir el archivo", "err");
    }
};

// El motor pesado de subida
async function subirVideoMultipart(file, datosGPS, onProgress) {
    const CHUNK_SIZE = 5 * 1024 * 1024; // 5MB
    const totalChunks = Math.ceil(file.size / CHUNK_SIZE);
    const safeName = file.name.replace(/[^a-zA-Z0-9.]/g, '_');
    const fileName = `${Date.now()}_${safeName}`;

    try {
        const resInit = await fetch(`/api/v1/videos/upload/iniciar`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ filename: fileName, content_type: file.type })
        });
        const { upload_id, key } = await resInit.json();

        let parts = [];

        for (let i = 0; i < totalChunks; i++) {
            const partNumber = i + 1;
            const start = i * CHUNK_SIZE;
            const end = Math.min(start + CHUNK_SIZE, file.size);
            const chunk = file.slice(start, end);

            const resSign = await fetch(`/api/v1/videos/upload/firmar-parte`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ filename: key, upload_id, part_number: partNumber })
            });
            const { url } = await resSign.json();
            const urlSegura = url.replace("http://35.194.31.183:9000", "/minio");

            const uploadRes = await fetch(urlSegura, { method: 'PUT', body: chunk });
            const etag = uploadRes.headers.get("ETag");

            parts.push({ PartNumber: partNumber, ETag: etag });

            if (onProgress) onProgress(Math.round(((i + 1) / totalChunks) * 100));
        }

        // --- LA MAGIA NUEVA ---
        // Al finalizar, adjuntamos la telemetría en formato JSON crudo
        const resFinal = await fetch(`/api/v1/videos/upload/finalizar`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                filename: key,
                upload_id: upload_id,
                parts: parts,
                telemetria: datosGPS // ¡Acá mandamos el archivo JSON encubierto!
            })
        });

        if (!resFinal.ok) throw new Error("Error en la confirmación del servidor");
        return await resFinal.json();

    } catch (error) {
        console.error("Error en Multipart:", error);
        throw error;
    }
}
