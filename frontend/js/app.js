const API_URL = 'http://34.63.158.31:8000';
const NOMBRE_BUCKET = "detecciones";
let videoSeleccionadoActualmente = null;
const MARGEN_EXTRA = 4;
let intervaloHealth = null;
let intervaloDatos = null;

// Inicialización del Mapa
const map = L.map('map').setView([-34.6441, -58.7894], 14);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '© OpenStreetMap contributors', maxZoom: 19 }).addTo(map);

const iconoBache = L.divIcon({
  className: '',
  html: `<div style="width: 16px; height: 16px; background: #ff3d3d; border: 2px solid white; border-radius: 50%; box-shadow: 0 0 8px rgba(255,61,61,0.9);"></div>`,
  iconSize: [16, 16],
  iconAnchor: [8, 8],
});

let marcadores = L.layerGroup().addTo(map);
let trayectorias = L.layerGroup().addTo(map);

// Lógica de Login
window.onload = () => {
  const rolGuardado = localStorage.getItem('pics_rol');
  if (rolGuardado) {
    iniciarDashboard(rolGuardado);
  } else {
    document.getElementById('login-screen').style.display = 'flex';
    document.getElementById('dashboard-content').style.display = 'none';
  }
};

async function procesarLogin() {
  const user = document.getElementById('login-user').value.trim().toLowerCase();
  const pass = document.getElementById('login-pass').value.trim();

  try {
    const response = await fetch(`${API_URL}/api/v1/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: user, password: pass })
    });

    if (!response.ok) {
        throw new Error("Credenciales inválidas");
    }

    const data = await response.json();
    
    localStorage.setItem('pics_token', data.access_token);
    localStorage.setItem('pics_rol', data.rol);
    
    document.getElementById('login-error').style.display = 'none';
    iniciarDashboard(data.rol);

  } catch (error) {
    document.getElementById('login-error').style.display = 'block';
  }
}

function cerrarSesion() {
  localStorage.removeItem('pics_rol');
  clearInterval(intervaloHealth);
  clearInterval(intervaloDatos);
  location.reload();
}

function iniciarDashboard(rol) {
  document.getElementById('login-screen').style.display = 'none';
  document.getElementById('dashboard-content').style.display = 'flex';
  document.getElementById('nombre-rol-header').innerText = rol === 'admin' ? 'Administrador' : 'Operador Municipal';

  setTimeout(() => { map.invalidateSize(); }, 300);

  if (rol === 'admin') {
    document.getElementById('admin-health-container').style.display = 'inline-block';
    document.getElementById('btn-grafana').style.display = 'flex';
    chequearHealth();
    intervaloHealth = setInterval(chequearHealth, 10000);
  }

  cargarDatos();
  intervaloDatos = setInterval(cargarDatos, 15000);
}

function abrirLogsGrafana() {
  const IP_GRAFANA = "34.172.225.250";
  const estadoGrafana = {
      datasource: "Loki",
      queries: [{ refId: "A", expr: '{app="api-fastapi"}' }],
      range: { from: "now-1h", to: "now" }
  };
  const parametroURL = encodeURIComponent(JSON.stringify(estadoGrafana));
  window.open(`http://${IP_GRAFANA}:3000/explore?orgId=1&left=${parametroURL}`, '_blank');
}

async function chequearHealth() {
  try {
    const res = await fetch(`${API_URL}/api/v1/health`);
    const data = await res.json();
    const dot = document.getElementById('health-dot');
    const text = document.getElementById('health-text');

    dot.className = 'health-dot';
    
    if (data.estado_general === 'VERDE') { 
        dot.classList.add('dot-verde'); 
        text.innerText = 'Sistemas OK'; 
    }
    else if (data.estado_general === 'AMARILLO') { 
        dot.classList.add('dot-amarillo'); 
        text.innerText = 'Advertencia'; 
    }
    else { 
        dot.classList.add('dot-rojo'); 
        text.innerText = 'Error Crítico'; 
    }
    
  } catch (e) {
    const dot = document.getElementById('health-dot');
    const text = document.getElementById('health-text');
    if(dot) dot.className = 'health-dot dot-rojo'; 
    if(text) text.innerText = 'API Apagada';
  }
}

window.dibujarBbox = function(imgElement) {
  let xMin = parseFloat(imgElement.getAttribute('data-xmin')); let yMin = parseFloat(imgElement.getAttribute('data-ymin'));
  let xMax = parseFloat(imgElement.getAttribute('data-xmax')); let yMax = parseFloat(imgElement.getAttribute('data-ymax'));
  if (isNaN(xMin) || isNaN(yMin)) return;
  const armarCaja = () => {
    const originalW = imgElement.naturalWidth; const originalH = imgElement.naturalHeight;
    if (!originalW || !originalH) { setTimeout(armarCaja, 50); return; }
    if (xMax <= 2 && yMax <= 2) { xMin = xMin * originalW; xMax = xMax * originalW; yMin = yMin * originalH; yMax = yMax * originalH; }
    let leftPct = (xMin / originalW) * 100; let topPct = (yMin / originalH) * 100;
    let widthPct = ((xMax - xMin) / originalW) * 100; let heightPct = ((yMax - yMin) / originalH) * 100;
    leftPct = Math.max(0, leftPct - MARGEN_EXTRA); topPct = Math.max(0, topPct - MARGEN_EXTRA);
    widthPct = Math.min(100 - leftPct, widthPct + (MARGEN_EXTRA * 2)); heightPct = Math.min(100 - topPct, heightPct + (MARGEN_EXTRA * 2));
    const bboxOverlay = imgElement.nextElementSibling;
    if (bboxOverlay && bboxOverlay.classList.contains('bbox-overlay')) {
      bboxOverlay.style.left = leftPct + '%'; bboxOverlay.style.top = topPct + '%';
      bboxOverlay.style.width = widthPct + '%'; bboxOverlay.style.height = heightPct + '%';
      bboxOverlay.style.display = 'block'; bboxOverlay.style.zIndex = '10';
    }
  };
  armarCaja();
};

function seleccionarVideoGeneral(vidId) {
  videoSeleccionadoActualmente = vidId;
  document.getElementById('video-screen').innerHTML = `
    <div style="color:var(--color-primario); font-weight:bold; font-size:1.2rem;"><i class="fa-solid fa-film"></i> VIDEO #${vidId} ACTIVADO</div>
    <div style="font-size:0.8rem; color:#aaa; margin-top:8px;">Seleccioná un pin en el mapa para ver la foto de la falla.</div>
  `;
  activarControlesChat(vidId);
}

function activarControlesChat(vidId) {
  document.getElementById('chat-input').disabled = false;
  document.getElementById('chat-input').placeholder = `Preguntale a Llama sobre el video #${vidId}...`;
  document.getElementById('btn-enviar-chat').disabled = false;
  document.getElementById('btn-consultar-reporte-ia').disabled = false;
  document.getElementById('btn-generar-reporte-ia').disabled = false;
}

function cerrarModalReporte() { document.getElementById('modal-reporte').style.display = 'none'; }

async function abrirModalReporte(metodoAccion) {
  if (!videoSeleccionadoActualmente) return;
  const modal = document.getElementById('modal-reporte'); const body = document.getElementById('modal-reporte-body');
  modal.style.display = 'flex';
  if (metodoAccion === 'POST') {
      body.innerHTML = `
          <div class="ia-progress-container">
              <div id="barra-ia" class="ia-progress-bar"></div>
          </div>
          <div class="reporte-texto" id="texto-stream" style="padding-top: 20px;">
              <em style="color:#888;"><i class="fa-solid fa-plug fa-fade"></i> Analizando datos geográficos e inicializando el modelo IA...</em>
          </div>
      `;
  } else {
      body.innerHTML = `<div style="text-align:center; padding: 40px;"><div style="color:var(--color-primario); font-size: 2rem; margin-bottom: 16px;"><i class="fa-solid fa-circle-notch fa-spin"></i></div><div style="color:#aaa; font-size: 1.1rem;">Buscando el reporte guardado...</div></div>`;
  }


  try {
    let urlReporte = ''; let opcionesFetch = {};
    if (metodoAccion === 'POST') {
        urlReporte = `${API_URL}/api/v1/reportes/generar`;
        opcionesFetch = { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ video_id: videoSeleccionadoActualmente }) };
    } else {
        urlReporte = `${API_URL}/api/v1/reporte/${videoSeleccionadoActualmente}`;
        opcionesFetch = { method: 'GET', headers: { 'Content-Type': 'application/json' } };
    }
    const response = await fetch(urlReporte, opcionesFetch);

    if (response.status === 404 && metodoAccion === 'GET') {
        body.innerHTML = `<div style="text-align:center; padding: 30px;"><div style="color:#ffb86c; font-size: 2rem; margin-bottom: 16px;"><i class="fa-solid fa-folder-open"></i></div><strong style="color:#e0e0e0; font-size: 1.1rem;">No hay ningún reporte guardado.</strong><br><span style="color:#aaa; display:block; margin-top:8px;">Usá el botón "Generar Nuevo Reporte" para que la IA lo redacte.</span></div>`;
        return;
    }
    if (!response.ok) throw new Error("Error en el servidor.");

    // LÓGICA DE MÁQUINA DE ESCRIBIR (STREAMING) PARA POST
    if (metodoAccion === 'POST') {
        // Inyectamos la barra animada y el espacio para el texto
        body.innerHTML = `
            <div class="ia-progress-container">
                <div id="barra-ia" class="ia-progress-bar"></div>
            </div>
            <div class="reporte-texto" id="texto-stream">
                <em style="color:#888;"><i class="fa-solid fa-circle-notch fa-spin"></i> Analizando contexto con Llama 3.2...</em>
            </div>
        `;

        const reader = response.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let textoAcumulado = "";

        while (true) {
            const { done, value } = await reader.read();
            if (done) break; // Terminó de escribir

            // Si es la primera palabra, borramos el "Analizando contexto..."
            if (textoAcumulado === "") {
                document.getElementById('texto-stream').innerHTML = "";
            }

            textoAcumulado += decoder.decode(value, { stream: true });

            // Lo mostramos con un cursor parpadeante al final
            document.getElementById('texto-stream').innerHTML = marked.parse(textoAcumulado) + '<span style="color:var(--color-primario);"> █</span>';

            // Auto-scroll hacia abajo
            body.scrollTop = body.scrollHeight;
        }

        // --- LA IA TERMINÓ ---
        // Limpiamos el cursor cuadradito al final
        document.getElementById('texto-stream').innerHTML = marked.parse(textoAcumulado);

        // Frenamos la barra y la pintamos de verde
        const barra = document.getElementById('barra-ia');
        if (barra) {
            barra.className = 'ia-progress-done';
        }
    }
    // LÓGICA NORMAL
    else {
        const data = await response.json();
        const textoCrudo = data.contenido || data.reporte || data.texto || data.respuesta || JSON.stringify(data);
        body.innerHTML = `<div class="reporte-texto">${marked.parse(textoCrudo)}</div>`;
    }
  } catch (err) { body.innerHTML = `<div style="text-align:center; padding: 30px;"><div style="color:var(--color-peligro); font-size: 2rem; margin-bottom: 16px;"><i class="fa-solid fa-triangle-exclamation"></i></div><strong style="color:var(--color-peligro); font-size: 1.1rem;">Error de conexión con la IA</strong><br><span style="color:#aaa; display:block; margin-top:8px;">Verificá los logs del servidor con Grafana.</span></div>`; }
}

function exportarFichaPDF() {
  const elemento = document.getElementById('ficha-para-exportar');
  const opt = { margin: 10, filename: `Ficha_Bache_${videoSeleccionadoActualmente}.pdf`, image: { type: 'jpeg', quality: 0.98 }, html2canvas: { scale: 2, useCORS: true }, jsPDF: { unit: 'mm', format: 'a4', orientation: 'landscape' } };
  elemento.style.background = "#000000"; elemento.style.padding = "20px";
  html2pdf().set(opt).from(elemento).save().then(() => { elemento.style.padding = "0px"; elemento.style.background = "transparent"; });
}

async function auditarDeteccion(deteccionId, nuevoEstado) {
  const accionTexto = nuevoEstado === 'falso_positivo' ? 'descartar esta detección (Falso Positivo)' : 'marcar esta detección como Verificada';
  if(!confirm(`¿Estás seguro de que querés ${accionTexto}?`)) return;

  try {
    const response = await fetch(`${API_URL}/api/v1/detecciones/${deteccionId}?nuevo_estado=${nuevoEstado}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' }
    });

    if (!response.ok) throw new Error("Fallo en la API al auditar la detección.");

    if (nuevoEstado === 'falso_positivo') {
      document.getElementById('video-screen').innerHTML = `
        <div style="padding: 20px; text-align: center; color: #888; width: 100%;">
          <i class="fa-solid fa-trash-can" style="font-size: 3rem; color: #dc3545; margin-bottom: 15px;"></i>
          <p>Detección descartada exitosamente.</p>
          <p style="font-size: 0.8rem; margin-top: 5px;">Se ha enviado al bucket de reentrenamiento para mejorar la IA.</p>
        </div>
      `;
    } else {
      document.getElementById('video-screen').innerHTML = `
        <div style="padding: 20px; text-align: center; color: #888; width: 100%;">
          <i class="fa-solid fa-check-circle" style="font-size: 3rem; color: #198754; margin-bottom: 15px;"></i>
          <p>Bache verificado correctamente.</p>
        </div>
      `;
    }

    cargarDatos();

  } catch (err) {
    console.error(err);
    alert("Ocurrió un error al auditar la detección. Revisá los logs en Grafana.");
  }
}

async function cargarDatos() {
  try {
    const resDetec = await fetch(`${API_URL}/api/v1/detecciones?v=${new Date().getTime()}`);
    if (!resDetec.ok) throw new Error(`Error HTTP`);
    const detecciones = await resDetec.json();
    document.getElementById('total-detecciones').textContent = detecciones.length;

    const videosMap = new Map();
    marcadores.clearLayers();

    detecciones.forEach(d => {
      if (d.video_id) videosMap.set(d.video_id, d.video_id);
      if (!d.geometria || !d.geometria.coordinates || d.geometria.coordinates.length < 2) return;
      const lon = d.geometria.coordinates[0]; const lat = d.geometria.coordinates[1];

      const marker = L.marker([lat, lon], { icon: iconoBache });

      const confianza = d.confianza ? (d.confianza * 100).toFixed(0) : 'N/A';
      const clase = d.tipo_dano ? d.tipo_dano.toUpperCase() : 'FALLA';
      const urlImagen = `http://35.194.31.183:9000/${NOMBRE_BUCKET}/${d.frame_minio_path}`;

      let bboxData = d.bbox; if (typeof bboxData === 'string') { try { bboxData = JSON.parse(bboxData); } catch (e) { bboxData = null; } }
      let bXmin, bYmin, bXmax, bYmax; let hasBbox = false;
      if (bboxData) {
        bXmin = bboxData.x_min ?? bboxData.xmin ?? bboxData.x1; bYmin = bboxData.y_min ?? bboxData.ymin ?? bboxData.y1;
        bXmax = bboxData.x_max ?? bboxData.xmax ?? bboxData.x2; bYmax = bboxData.y_max ?? bboxData.ymax ?? bboxData.y2;
        if (bXmin !== undefined && bXmin !== null) hasBbox = true;
      }
      let dataAttributes = hasBbox ? `data-xmin="${bXmin}" data-ymin="${bYmin}" data-xmax="${bXmax}" data-ymax="${bYmax}"` : "";
      let onloadScript = hasBbox ? `onload="window.dibujarBbox(this)"` : "";

      let badgeEstado = d.estado_auditoria === 'verificado'
          ? '<span style="background:#198754; color:#fff; padding:3px 8px; border-radius:12px; font-size:0.6rem; margin-left:6px; vertical-align: middle;"><i class="fa-solid fa-check"></i> OK</span>'
          : '';

      let fechaFormateada = 'Reporte Reciente';
      if (d.fecha) {
          try {
              const partes = d.fecha.split('T')[0].split('-');
              fechaFormateada = `${partes[2]}/${partes[1]}/${partes[0]}`;
          } catch(e) {
              fechaFormateada = new Date(d.fecha).toLocaleDateString('es-AR');
          }
      }

      marker.bindPopup(`
        <div style="color: #fff; font-size: 0.85rem; width: 180px;">
          <strong><i class="fa-solid fa-road-circle-exclamation" style="color:var(--color-primario);"></i> ${clase}</strong> ${badgeEstado}<br>
          Confianza: ${confianza}%<br>
          <div style="margin-top: 8px; border-radius: 6px; overflow: hidden; border: 1px solid var(--color-primario); background: #000; text-align: center;">
             <div style="position: relative; display: inline-block; line-height: 0;">
               <img src="${urlImagen}" crossorigin="anonymous" style="width: 100%; height: auto; display: block;" ${dataAttributes} ${onloadScript} onerror="this.style.display='none';">
               <div class="bbox-overlay" style="position: absolute; border: 1px solid #ff3d3d; background: rgba(255, 61, 61, 0.3); display: none; pointer-events: none;"></div>
             </div>
          </div>
        </div>
      `);

      marker.on('click', async () => {
        videoSeleccionadoActualmente = d.video_id;

        let seccionAuditoriaHTML = '';
        if (d.estado_auditoria === 'verificado') {
            seccionAuditoriaHTML = `
              <div style="margin-top: 20px; padding: 12px; background: rgba(25, 135, 84, 0.15); border: 1px solid #198754; border-radius: 8px; color: #20c997; text-align: center; font-weight: bold; width: 100%; font-size: 0.95rem;">
                <i class="fa-solid fa-shield-check"></i> Falla Verificada por Auditoría
              </div>
            `;
        } else {
            seccionAuditoriaHTML = `
              <div style="display: flex; gap: 10px; margin-top: 20px; width: 100%;">
                <button onclick="auditarDeteccion(${d.id}, 'verificado')" class="btn-auditoria btn-verificado" title="Confirmar que es un bache real"><i class="fa-solid fa-check-double"></i> Verificar Falla</button>
                <button onclick="auditarDeteccion(${d.id}, 'falso_positivo')" class="btn-auditoria btn-falso" title="Descartar y enviar a reentrenamiento"><i class="fa-solid fa-trash-can"></i> Falso Positivo</button>
              </div>
            `;
        }

        document.getElementById('video-screen').style.padding = "0";
        document.getElementById('video-screen').innerHTML = `
          <div id="ficha-para-exportar" style="width: 100%; height: 100%; text-align:left; display: flex; flex-direction: column;">
            <div style="border-bottom: 1px solid #333; padding-bottom: 10px; margin-bottom: 15px;">
              <h2 style="color: var(--color-primario); font-size: 1.2rem;"><i class="fa-solid fa-file-shield"></i> Ficha de Inspección Técnica</h2>
              <span style="color:#aaa; font-size:0.8rem;">Municipalidad de Moreno - Video ID: ${d.video_id}</span>
            </div>
            <div style="position: relative; display: inline-block; line-height: 0; text-align: center;">
              <img id="img-panel-derecho" src="${urlImagen}" crossorigin="anonymous" style="max-height: 250px; max-width: 100%; width: auto; height: auto; border-radius: 8px; display: inline-block;" ${dataAttributes} onerror="this.style.display='none'">
              <div class="bbox-overlay" style="position: absolute; border: 2px solid #ff3d3d; background: rgba(255, 61, 61, 0.2); display: none; cursor: crosshair;">
                 <span style="position:absolute; top:-22px; left:-2px; background:#ff3d3d; color:#fff; font-size:0.7rem; padding:2px 8px; font-weight:bold; border-radius:4px 4px 0 0; white-space: nowrap; line-height: 1.5;">${clase}</span>
              </div>
            </div>
            <div style="margin-top: 20px; font-size: 0.95rem; color: #e0e0e0; line-height: 1.8; background: #121212; padding: 15px; border-radius: 8px; border: 1px solid #222;">
              <strong><i class="fa-solid fa-tag" style="color:#888;"></i> Falla Detectada:</strong> <span style="color:#ff3d3d; font-weight:bold;">${clase}</span><br>
              <strong><i class="fa-solid fa-percent" style="color:#888;"></i> Confianza IA:</strong> ${confianza}%<br>
              <strong><i class="fa-solid fa-location-dot" style="color:#888;"></i> Calle / Ubicación:</strong> <span id="ficha-calle">Consultando GPS...</span><br>
              <strong><i class="fa-solid fa-calendar-days" style="color:#888;"></i> Fecha de Registro:</strong> ${fechaFormateada}<br>
            </div>
          </div>

          ${seccionAuditoriaHTML}

          <button onclick="exportarFichaPDF()" class="btn-ficha-pdf"><i class="fa-solid fa-file-pdf"></i> Exportar Ficha en PDF</button>
        `;
        try {
           const resGeo = await fetch(`https://nominatim.openstreetmap.org/reverse?format=json&lat=${lat}&lon=${lon}`);
           const geoData = await resGeo.json();
           document.getElementById('ficha-calle').innerText = (geoData.address.road || geoData.display_name.split(',')[0]);
        } catch(err) { document.getElementById('ficha-calle').innerText = `Lat: ${lat.toFixed(4)}, Lng: ${lon.toFixed(4)}`; }

        if (hasBbox) {
          const imgPanel = document.getElementById('img-panel-derecho');
          if (imgPanel) { if (imgPanel.complete) window.dibujarBbox(imgPanel); else imgPanel.onload = () => window.dibujarBbox(imgPanel); }
        }
        activarControlesChat(d.video_id);
      });
      marcadores.addLayer(marker);
    });

    document.getElementById('total-inspecciones').textContent = videosMap.size;
    const listaLateral = document.getElementById('lista-inspecciones');
    const colaProcesamiento = document.getElementById('cola-procesamiento');
    listaLateral.innerHTML = ''; colaProcesamiento.innerHTML = '';

    if (videosMap.size === 0) {
      listaLateral.innerHTML = '<p style="color:#666; font-size:0.8rem">Sin registros.</p>';
      colaProcesamiento.innerHTML = '<p style="color:#666; font-size:0.8rem">Sistema en espera.</p>';
    } else {
      videosMap.forEach(vidId => {
        const divLateral = document.createElement('div');
        divLateral.className = 'inspeccion-item';
        divLateral.innerHTML = `<div><strong><i class="fa-solid fa-film"></i> Video #${vidId}</strong></div><span class="status-badge" id="badge-video-${vidId}"><i class="fa-solid fa-circle-notch fa-spin"></i></span>`;
        divLateral.onclick = () => seleccionarVideoGeneral(vidId);
        listaLateral.appendChild(divLateral);

        const divCola = document.createElement('div');
        divCola.style = "background: var(--fondo-secundario); padding: 10px; border-radius: 6px; border: 1px solid var(--bordes); display: flex; justify-content: space-between; font-size: 0.85rem;";
        divCola.innerHTML = `<div><strong>Video #${vidId}</strong></div><div id="estado-cola-${vidId}" style="color: #aaa; font-weight: bold;"><i class="fa-solid fa-circle-notch fa-spin"></i> Consultando...</div>`;
        colaProcesamiento.appendChild(divCola);

        fetch(`${API_URL}/api/v1/videos/${vidId}`)
          .then(res => res.json())
          .then(data => {
              const est = data.estado ? data.estado.toUpperCase() : 'DESCONOCIDO';
              const elCola = document.getElementById(`estado-cola-${vidId}`);
              const elBadge = document.getElementById(`badge-video-${vidId}`);

              elBadge.innerText = est;

              if (est === 'PROCESADO' || est === 'FINALIZADO') {
                  elCola.style.color = 'var(--color-primario)';
                  elCola.innerHTML = `<i class="fa-solid fa-check-double"></i> ${est}`;
                  elBadge.style.background = '#003366';
                  elBadge.style.color = '#66ccff';
              } else if (est === 'PENDIENTE') {
                  elCola.style.color = '#ffcc00';
                  elCola.innerHTML = `<i class="fa-solid fa-clock"></i> EN COLA`;
                  elBadge.style.background = '#665000';
                  elBadge.style.color = '#ffcc00';
              } else {
                  elCola.style.color = '#3dff7a';
                  elCola.innerHTML = `<i class="fa-solid fa-gears fa-spin"></i> ${est}`;
                  elBadge.style.background = '#004d1a';
                  elBadge.style.color = '#3dff7a';
              }
          })
          .catch(() => {
              const elCola = document.getElementById(`estado-cola-${vidId}`);
              if (elCola) elCola.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> ERROR`;
          });
      });
    }
  } catch (err) { console.error('Error conectando a la API de detecciones:', err); }

  try {
    const resTrayectos = await fetch(`${API_URL}/api/v1/trayectorias?v=${new Date().getTime()}`);
    if (resTrayectos.ok) {
      const trayectoriasReales = await resTrayectos.json();
      trayectorias.clearLayers();

      Object.keys(trayectoriasReales).forEach(vidId => {
        const puntosDeRuta = trayectoriasReales[vidId];

        if (puntosDeRuta.length > 1) {
          const lineaPunteada = L.polyline(puntosDeRuta, {
            color: '#00aaff',
            weight: 4,
            opacity: 0.7,
            dashArray: '10, 10',
            lineJoin: 'round'
          });
          trayectorias.addLayer(lineaPunteada);
        }
      });
    }
  } catch (errTrayectos) {
    console.warn("No se pudo cargar la telemetría del recorrido:", errTrayectos);
  }
}

async function enviarMensaje() {
  // Si no hay video seleccionado, le mandamos "0" al backend para activar el MODO GLOBAL
  const videoContexto = videoSeleccionadoActualmente || 0;

  const input = document.getElementById('chat-input');
  const chatBox = document.getElementById('chat-box');
  const mensaje = input.value.trim();

  if (!mensaje) return;

  const userBubble = document.createElement('div');
  userBubble.className = 'chat-bubble chat-user';
  userBubble.textContent = mensaje;
  chatBox.appendChild(userBubble);

  input.value = '';
  chatBox.scrollTop = chatBox.scrollHeight;

  const aiBubble = document.createElement('div');
  aiBubble.className = 'chat-bubble chat-ai';
  aiBubble.innerHTML = '<em><i class="fa-solid fa-circle-notch fa-spin"></i> Analizando el mapa de Moreno...</em>';
  chatBox.appendChild(aiBubble);
  chatBox.scrollTop = chatBox.scrollHeight;

  try {
    // Acá inyectamos el ID (0 si es global, o el número de video si seleccionó uno)
    const url = `${API_URL}/api/v1/video/${videoContexto}/preguntar`;

    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pregunta: mensaje })
    });

    if (!response.ok) throw new Error("Error en IA.");

    const data = await response.json();
    const textoChatCrudo = data.respuesta || data.mensaje || JSON.stringify(data);

    aiBubble.innerHTML = marked.parse(textoChatCrudo);
  } catch (err) {
    aiBubble.innerHTML = `⚠️ <strong>Error.</strong> Verifica la conexión con el contenedor de la API.`;
  }

  chatBox.scrollTop = chatBox.scrollHeight;
}
