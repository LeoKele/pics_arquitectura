// ACORDATE DE ACTUALIZAR ESTA IP SI CAMBIA EN GOOGLE CLOUD
const API_URL = 'http://34.63.158.31:8000'; 

async function checkSystemHealth() {
    const globalDiv = document.getElementById('global-status');
    const globalIcon = document.getElementById('global-icon');
    const globalText = document.getElementById('global-text');

    try {
        const response = await fetch(`${API_URL}/api/v1/health`);
        
        // Si el servidor responde pero con error 500 (API viva pero algo roto) o responde 200 (OK)
        const data = await response.json();

        // 1. Pintar el Banner Global
        globalDiv.className = 'global-status';
        if (data.estado_general === 'VERDE') {
            globalDiv.classList.add('status-operational');
            globalIcon.className = 'fa-solid fa-check-circle';
            globalText.innerText = 'Todos los sistemas están operativos';
        } else if (data.estado_general === 'AMARILLO') {
            globalDiv.classList.add('status-degraded');
            globalIcon.className = 'fa-solid fa-triangle-exclamation';
            globalText.innerText = 'Rendimiento degradado en algunos servicios';
        } else {
            globalDiv.classList.add('status-outage');
            globalIcon.className = 'fa-solid fa-circle-xmark';
            globalText.innerText = 'Interrupción parcial del sistema';
        }

        // 2. Pintar los servicios individuales
        actualizarServicio('srv-api', 'OK'); // Si la API respondió, la API está OK
        actualizarServicio('srv-postgresql', data.servicios.postgresql || 'ERROR');
        actualizarServicio('srv-redis', data.servicios.redis || 'ERROR');
        actualizarServicio('srv-minio', data.servicios.minio || 'ERROR');
        actualizarServicio('srv-ollama', data.servicios.ollama || 'ERROR');

    } catch (error) {
        // Si el fetch falla (ej. pod caído, no hay internet, error CORS grave)
        globalDiv.className = 'global-status status-outage';
        globalIcon.className = 'fa-solid fa-skull-crossbones';
        globalText.innerText = 'Interrupción total del sistema (API Inaccesible)';

        const servicios = ['srv-api', 'srv-postgresql', 'srv-redis', 'srv-minio', 'srv-ollama'];
        servicios.forEach(id => actualizarServicio(id, 'ERROR'));
    }
}

function actualizarServicio(idElemento, estado) {
    const divEstado = document.querySelector(`#${idElemento} .service-state`);
    const divBarras = document.querySelector(`#${idElemento} .uptime-bars`);
    if (!divEstado || !divBarras) return;

    // Actualizar Texto
    if (estado === 'OK') {
        divEstado.className = 'service-state state-ok';
        divEstado.innerHTML = 'Operativo';
    } else {
        divEstado.className = 'service-state state-error';
        divEstado.innerHTML = 'Fuera de línea';
    }

    // Dibujar las 90 barritas (89 históricas mockeadas + 1 real de hoy)
    let barrasHTML = '';
    const totalBarras = 60; // Ponemos 60 para que entren bien en la pantalla
    
    for (let i = 0; i < totalBarras - 1; i++) {
        // Simulamos un historial perfecto (todo verde)
        barrasHTML += `<div class="uptime-bar bar-ok" title="Histórico: Operativo"></div>`;
    }

    // LA ÚLTIMA BARRA ES EL ESTADO REAL EN VIVO DE TU API
    const claseHoy = estado === 'OK' ? 'bar-ok' : 'bar-error';
    const textoHoy = estado === 'OK' ? 'Hoy: Operativo' : 'Hoy: CAÍDO';
    barrasHTML += `<div class="uptime-bar ${claseHoy}" title="${textoHoy}" style="box-shadow: 0 0 8px ${estado === 'OK' ? '#198754' : '#dc3545'};"></div>`;

    divBarras.innerHTML = barrasHTML;
}

// Arrancar al cargar la página y repetir cada 15 segundos
window.onload = () => {
    checkSystemHealth();
    setInterval(checkSystemHealth, 15000);
};