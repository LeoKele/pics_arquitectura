# Post-Mortem Técnico: Sistema de Mapeo Dinámico Vial

Este documento presenta una reflexión crítica, honesta y analítica sobre el proceso de diseño, desarrollo e implementación del **Sistema de Mapeo Dinámico Vial**. Se evalúan las decisiones técnicas clave, las dificultades superadas, los alcances y límites del sistema, y las lecciones aprendidas durante este proyecto integrador.

---

## 1. Identificación de Decisiones Clave durante el Desarrollo

A lo largo del desarrollo, se tomaron decisiones de ingeniería y modelado que definieron el rumbo de la solución:

### A. Migración de YOLOv8s a YOLO26m y Alta Resolución (1024px)
*   **Decisión:** En las etapas iniciales de modelado, se entrenaron redes YOLOv8s y YOLO26s a una resolución estándar de 640x640. Sin embargo, los baches pequeños (`D40`) localizados a mediana distancia en el horizonte resultaban invisibles o se confundían con parches oscuros. Se decidió migrar a la arquitectura **YOLO26m (Medium)** y duplicar la resolución de inferencia a **1024 píxeles** (`imgsz=1024`).
*   **Justificación:** El cambio a la versión Medium incrementó la profundidad en el extractor de características (*Backbone*), y la alta resolución preservó los píxeles de fallas pequeñas y lejanas, mejorando significativamente el `mAP50` de los baches.

### B. Adopción de la Arquitectura YOLO26 y Remoción de NMS en CPU
*   **Decisión:** Se optó por la arquitectura YOLO26 de Ultralytics en lugar de alternativas basadas en Transformers (como RT-DETR) o versiones previas de la familia YOLO.
*   **Justificación:** YOLO26 implementa dos optimizaciones cruciales para el despliegue en CPU sobre los pods de GKE:
    *   **Remoción de DFL (Distribution Focal Loss):** Simplifica la regresión de cajas, liberando recursos en CPU.
    *   **Inferencia NMS-Free (Dual-Head Design):** Su cabeza de predicción directa *One-to-One* elimina la sobrecarga computacional del algoritmo Non-Maximum Suppression (NMS) en CPU en tiempo de inferencia.
    *   Esto redujo los tiempos de cómputo en un **43% sobre procesadores tradicionales**, ideal para correr workers asíncronos en nuestro clúster cloud sin depender de GPUs dedicadas.

### C. Deduplicación Espacial Híbrida (PostGIS + ByteTrack)
*   **Decisión:** Para evitar registrar múltiples alertas de un mismo bache físico a lo largo de fotogramas continuos del video, se diseñó una lógica híbrida que combina el tracking visual **ByteTrack** en memoria caliente con validaciones espaciales en **PostGIS**.
*   **Justificación:** Si el tracking visual se corta (por vibración de la cámara o tráfico), PostGIS valida mediante la función `ST_DWithin` si ya existe un daño similar en un radio de tolerancia adaptativo por categoría (`D40: 3m`, `D20: 10m`, `calle_tierra: 30m`). De ser así, se unifican las detecciones y se actualiza el frame almacenado en MinIO solo si la nueva captura presenta una confianza de predicción mayor.

### D. Abstracción del Proveedor de LLM en Backend (Gemini / OpenAI / Ollama)
*   **Decisión:** Inicialmente, el sistema dependía estrictamente de una instancia local de **Ollama** con `llama3.2:3b`. Se implementó un selector dinámico en el backend que abstrae el cliente LLM en FastAPI a través de variables de entorno, permitiendo derivar el procesamiento a Gemini SDK (Google AI Studio) u OpenAI de manera transparente.
*   **Justificación:** Aporta estabilidad y velocidad en producción (Gemini/OpenAI responden en segundos mediante streaming), mientras que mantiene la portabilidad e independencia de costos en entornos locales a través de Ollama.

---

## 2. Análisis de Dificultades Encontradas y Cómo Fueron Abordadas

### A. Inconsistencia, Formateo y Alucinaciones en los Reportes del LLM
*   **Dificultad:** Lograr que el modelo local de 3B parámetros (`llama3.2:3b`) genere un reporte ejecutivo ordenado, formal y determinista. El modelo alucinaba calles, mezclaba términos internos de la API (como "D20", "D40" o "score de prioridad técnica") y a veces inventaba escuelas u hospitales cercanos.
*   **Resolución:** Se implementaron técnicas de **Prompt Defensivo** en `api/routers/reporte.py`. Se prohibió explícitamente el uso de códigos de desarrollo y se exigieron justificaciones basadas estrictamente en POIs reales de OpenStreetMap. Además, se fijó la temperatura de inferencia en `0.1` para limitar la variabilidad y se estructuró un contexto en JSON pre-procesado con calles y coordenadas exactas resueltas en el backend por geocodificación inversa, reduciendo a cero el margen de alucinación del modelo.

### B. Bloqueos por Directivas de Seguridad de Navegador (Mixed Content y CORS)
*   **Dificultad:** Al desplegar los frontends en Netlify (`HTTPS`) y los endpoints de la API y de MinIO en GCP bajo `HTTP`, el navegador bloqueaba las llamadas de la API de geolocalización y la subida multipart binaria de fragmentos de video por problemas de CORS y Mixed Content.
*   **Resolución:** Se configuraron reglas de redirección de proxy reverso nativas en Netlify mediante archivos `_redirects` en las carpetas públicas de los frontends, mapeando `/api/*` y `/minio/*` a las IPs correspondientes de GCP. En el frontend, el módulo `uploader.ts` reescribe las URLs absolutas devueltas por MinIO a rutas relativas para pasar por el proxy, resolviendo el bloqueo de forma limpia.


### C. Brecha de Dominio (Domain Shift) y Fracaso del Entrenamiento Inicial (Intento 1)
*   **Dificultad:** En la primera iteración del proyecto, al entrenar un modelo base de YOLOv8 pre-entrenado (de Hugging Face) únicamente sobre el dataset global **RDD2022**, el rendimiento en las calles locales fue sumamente deficiente, resultando en un `mAP50` inferior a **0.50**. RDD2022 contenía tomas aéreas de drones (`China_Drone`), vistas desde manubrios de motocicletas enfocadas directamente hacia el suelo (`China_MotorBike`) y perspectivas viales norteamericanas con lentes gran angular (`United_States`). Esto generaba un severo desacople visual (Domain Shift) con la perspectiva de la cámara montada en el parabrisas de vehículos municipales y la realidad de las calles de Moreno.
*   **Resolución:** Se analizó el dataset mediante notebooks de exploración y se realizó una limpieza drástica: se descartaron todas las subfuentes aéreas, las de motocicletas y aquellas con perspectivas incompatibles. Posteriormente, se consolidó el **Dataset Mixto** inyectando imágenes locales de Moreno recolectadas mediante la API de **Mapillary**. Esto adaptó la red a las texturas de asfalto locales, tonalidades de tierra del Conurbano y anchos de calle reales, logrando destrabar el estancamiento inicial del modelo.

### D. Conflicto de Data Augmentation y Sobreajuste por Procesamiento Externo (Intento 2)
*   **Dificultad:** En la segunda iteración, utilizando la arquitectura **YOLO26s**, se aplicaron técnicas de preprocesamiento y aumento de datos estáticos desde la herramienta externa Roboflow (redimensionamiento forzado y rotaciones severas) combinadas con los aumentos de datos dinámicos nativos del entrenamiento de YOLO (Mosaic, Mixup). Esto causó un severo sobreajuste (*overfitting*): el modelo memorizó los datos de entrenamiento y la pérdida de validación divergió a partir de la época 40, limitando el `mAP50` a un modesto **0.60** y generando múltiples falsos positivos causados por sombras de árboles y parches de humedad asfáltica.
*   **Resolución:** Se eliminó por completo el pipeline de Roboflow y el redimensionamiento artificial de las imágenes. Se optó por trabajar con **imágenes crudas (raw)** en su resolución y aspecto originales, dejando que YOLO maneje de forma exclusiva los algoritmos de aumento dinámico nativos de Ultralytics (Mosaic y Mixup). Para resolver los falsos positivos por sombras y humedad, se escaló el modelo hacia la arquitectura **YOLO26m (Medium)**, cuyas capas más profundas permitieron generalizar las texturas complejas de las calles de Moreno de forma mucho más robusta.

---

## 3. Logros Alcanzados (Cosas que Sí se Consiguieron)

*   **Pipeline de Visión Computacional Funcional en CPU:** Un procesamiento asíncrono y desacoplado mediante workers Python que leen colas de Redis y procesan videos aplicando YOLO26m, deduplicación de PostGIS y anonimización de privacidad en tiempo real sin requerir GPUs.
*   **Resiliencia en Campo (Modo Offline):** Captura estable de telemetría y video sin conexión en la calle y sincronización multipart directa desde el cliente móvil.
*   **Consola de Auditoría HITL Integrada:** Interfaz de usuario intuitiva que permite a inspectores corregir las clasificaciones de la IA y derivar automáticamente los errores a un bucket dedicado para la mejora del dataset.
*   **Informes con IA y Segmentación Vial:** Generación de resúmenes ejecutivos que incluyen conteos rápidos de fallas, nivel general de urgencia vial, chat interactivo con el asistente *PozoBot* y traducción de trayectorias en tramos de calles descriptivos (ej. *"Calle X hasta Calle Y"*) mediante consultas de reverse geocoding a OpenStreetMap.
*   **Infraestructura Nube Escalable y Observabilidad:** Despliegue listo en Google Kubernetes Engine (GKE) con auto-escalado basado en eventos mediante KEDA (escalando workers a cero réplicas si no hay tareas) y monitoreo consolidado en Grafana Loki.

---

## 4. Cosas No Alcanzadas y Limitaciones del Sistema (Autocrítica)

*   **Bajo Recall en Detección de Baches (`D40`):** El recall en baches se sitúa en un **46.9%**. La extrema similitud visual entre un bache profundo, parches de brea húmeda y sombras hace que el modelo tienda a ser "conservador" y omita detecciones dudosas. Aunque esto mantiene baja la tasa de falsas alarmas (Precision del 78% global) y permite validar el flujo completo de la plataforma sin saturarla, en un entorno de producción ideal se requeriría una mayor exhaustividad de detección.
*   **Ilusión Métrica de la Clase Calle de Tierra:** Si bien las métricas globales reportan un promedio elevado de desempeño, la clase `calle_tierra` obtuvo métricas casi perfectas (`mAP50: 99.5%`). Sin embargo, somos conscientes de que este resultado infla de manera artificial el promedio del modelo debido a dos factores: primero, a diferencia de los baches (`D40`) o grietas (`D20`), una calle de tierra ocupa la totalidad del fotograma a procesar y presenta una firma de color y textura sumamente fácil de catalogar para la red; segundo, el set de validación local solo disponía de 31 instancias de esta clase, limitando la varianza de prueba. Por lo tanto, el rendimiento real del sistema debe evaluarse aislando y observando críticamente las métricas de `D20` y `D40`.
*   **Dependencia Estricta de Precisión GPS:** Si el sensor de geolocalización del smartphone experimenta desviación (debido a mala calidad de hardware o arbolado denso), los puntos de telemetría se distorsionan, causando que PostGIS ubique daños a varias decenas de metros de su posición física real. El sistema no dispone de algoritmos de corrección de trayectorias basados en acelerómetro o giroscopio del móvil.
*   **Exposición de Seguridad en Cloud SQL:** Por simplicidad en la etapa de desarrollo y pruebas, la base de datos PostgreSQL de Cloud SQL se configuró habilitando el acceso público para la red `0.0.0.0/0`. Aunque se resguarda bajo contraseñas, esto constituye una seria vulnerabilidad que no se llegó a subsanar en la arquitectura de producción mediante VPC Peering o el uso de Cloud SQL Auth Proxy.
*   **Falta de Medición de Severidad o Profundidad:** Al trabajar con cámaras monoculares estándar 2D (smartphones), el sistema no puede inferir la profundidad del bache ni la severidad tridimensional de la grieta. Esto limita la evaluación a un conteo cuantitativo, impidiendo priorizar de forma automatizada los baches más profundos o peligrosos.
*   **Automatización Incompleta del Reentrenamiento MLOps:** Aunque se separan y almacenan los falsos positivos en un bucket dedicado en MinIO, el pipeline de reentrenamiento y actualización de pesos en producción se dejó de manera teórica en las notebooks, requiriendo intervención manual para su ejecución.
*   **Inflexibilidad del Filtrado de Horizonte (ROI Estático):** El umbral de descarte de horizonte (`y_centro < 0.50`) es una cota rígida. Movimientos bruscos de la amortiguación del vehículo o pendientes pronunciadas en calles de Moreno pueden causar que desperfectos reales queden falsamente categorizados en la mitad superior de la imagen y sean omitidos del pipeline de detección.
*   **Sensibilidad Climática e Iluminación:** Las pruebas operativas en los videos revelaron una fuerte disminución en la confianza de las detecciones durante inspecciones nocturnas con iluminación deficiente o lluvias severas, donde las anomalías viales acumulan agua y actúan como espejos reflejando luces artificiales.

---

## 5. Propuestas Concretas de Mejora y Trabajo Futuro

### A. Automatización del Pipeline de MLOps y Congelamiento de Capas
*   **Propuesta:** Implementar un disparador (trigger) que, al acumular un lote de imágenes corregidas por el auditor (HITL) en MinIO, lance un pipeline de entrenamiento en la nube. Para mitigar el olvido catastrófico y optimizar el uso de CPU/GPU en los nodos de GKE (reduciendo los tiempos de reentrenamiento), el diseño validado en la notebook `06_reentrenamiento_human_in_the_loop.ipynb` propone el **congelamiento de las primeras 10 capas (*Layer Freezing* del Backbone)** de YOLO, entrenando únicamente las capas de predicción (*Head*). Esto asegura que el modelo retenga las características visuales fundamentales ya aprendidas y solo adapte su detección a los nuevos desperfectos viales reportados.

### B. Inferencia en el Borde (Edge AI)
*   **Propuesta:** Exportar el modelo YOLO a formato ONNX / TFJS y ejecutar la inferencia de daños directamente en el dispositivo móvil del operario dentro de la app **PozoCam**. Esto evitaría transferir archivos de video pesados (ahorrando megabytes en el plan de datos municipal) y solo transmitiría al servidor las capturas aisladas de las detecciones confirmadas junto con la metadata GPS.

### C. Fortalecimiento de la Seguridad de Red
*   **Propuesta:** Cerrar la IP pública de la base de datos administrada Cloud SQL, reconfigurando los manifiestos de Kubernetes en GKE para inyectar un sidecar con el proxy seguro **Cloud SQL Auth Proxy** o implementando una red VPC privada.

### D. Políticas de Retención de Video y Enriquecimiento de Contexto en Auditoría (HITL)
*   **Propuesta:**
    *   **Ciclo de Vida de Almacenamiento:** Implementar una política de retención configurable en la base de datos y en MinIO para los
videos crudos (los cuales actualmente se eliminan del servidor inmediatamente después de procesarse), permitiendo definir un período
configurable de resguardo (ej. 7 a 30 días) antes de su purga automática.
    *   **Contexto Dinámico en Auditoría:** Modificar el frontend y el backend para que la consola de auditoría exponga un fragmento de
video recortado de pocos segundos (ej. 3 segundos antes y después del frame de detección). Esto permitirá al auditor evaluar el daño con
contexto dinámico y no solo a partir de una única imagen estática, reduciendo significativamente los falsos positivos por sombras o
reflejos.

### E. Análisis Temporal, Ciclo de Reparaciones y Deduplicación Multi-Video
*   **Propuesta:**
    *   **Línea de Tiempo Evolutiva:** Diseñar una característica que le permita al operador ver como el estado de las calles fue evolucionando a lo largo del tiempo utilizando las detecciones históricas.
    *   **Gestión del Ciclo de Reparaciones:** Habilitar un flujo de trabajo para que el personal municipal pueda marcar una calle o bache específico como "Reparado". Esto limpiará las alertas activas en el mapa y permitirá medir la calidad y durabilidad de los materiales utilizados cuando un vehículo vuelva a transitar por el área.
    *   **Deduplicación Espacial Cruzada (Multi-Video):** Extender las consultas espaciales en PostGIS para consolidar alertas redundantes generadas por diferentes trayectos o vehículos que pasaron por la misma coordenada geográfica en días distintos, unificando la vista del mapa de calor y evitando la sobreestimación cuantitativa de los desperfectos.

---

## 6. Evidencia de Aprendizaje a lo largo del Proyecto

Este proyecto consolidó aprendizajes multidisciplinarios complejos que van más allá del desarrollo de software tradicional:
1.  **MLOps y Ciclo de Vida de Modelos:** Comprensión práctica de los fenómenos que afectan a modelos en producción (*concept drift*, desbalance de clases, sesgos de background) y cómo implementar técnicas defensivas de curación de datos y HITL.
2.  **Arquitecturas Distribuidas:** Diseño de sistemas desacoplados con colas de mensajes y workers de procesamiento asíncrono pesados de forma reproducible bajo Docker y Kubernetes.
3.  **Gestión de Datos Geoespaciales:** Uso avanzado de bases de datos espaciales (PostGIS) y APIs geográficas (OpenStreetMap Nominatim/Photon/Overpass) para la priorización y ordenamiento de datos reales de urbanismo.
4.  **Ingeniería de Software:** Adaptación de frameworks web (FastAPI, Next.js, IndexedDB) para resolver problemas reales de conectividad, privacidad y seguridad de navegadores en entornos de campo.
5.  **Ingeniería de Prompts y Afinación de LLMs:** Aprendizaje sobre cómo estructurar prompts defensivos, definir restricciones de salida en modelos de lenguaje con baja cantidad de parámetros, ajustar variables de inferencia (temperatura a 0.1) e integrar APIs externas de IA como Gemini SDK mediante capas de compatibilidad estándar (OpenAI clients).
6.  **Mitigación de Brechas de Dominio (Domain Shift):** Comprensión práctica de que la calibración de datos y la eliminación de ruido geográfico/perspectiva (ej. excluir tomas aéreas de drones en dataset viales de calle) es más determinante para la precisión real de un modelo de visión computacional que la mera búsqueda de arquitecturas complejas de redes.
