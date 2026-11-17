# Bitácora crítica del uso del asistente de codificación con IA

**Asistente:** Claude (Anthropic), modelo Opus 5.5, en modo agente con acceso a terminal, editor y navegador.
**Fecha de la sesión principal:** 17 de noviembre de 2026.
**Alcance:** el asistente generó el código base de la plataforma, las pruebas y la documentación a partir del enunciado del proyecto final. El equipo revisa, ajusta y es responsable del resultado.

> Las entradas 1 a 13 describen lo que ocurrió realmente durante la generación (errores detectados y cómo se corrigieron). La sección final queda para que el equipo agregue sus propias entradas y su reflexión. Esa parte es obligatoria y debe escribirla el equipo, no la IA.

## Método de trabajo

1. Leer el enunciado y convertirlo en una lista de requisitos verificables (ver `MATRIZ_CUMPLIMIENTO.md`).
2. Construir por fases: backend y rúbricas → ingesta y sandbox → evaluación con LLM → informes y frontend → pruebas y despliegue.
3. Después de cada fase, **ejecutar** el código (servidor real, llamadas a la API, capturas con Playwright) en vez de confiar en que "debería funcionar".
4. Usar las pruebas automáticas y el linter como revisores independientes del código que generó la IA.

## Entradas

| # | Qué se pidió o generó | Qué salió mal o qué se detectó | Cómo se detectó | Corrección | Lección |
|---|---|---|---|---|---|
| 1 | Evaluador heurístico (`mock`) para demos sin costo | Asignaba niveles altos sin citar evidencia; el validador semántico rechazó la salida 3 veces y la evaluación falló | El propio validador de la plataforma (regla: «nivel superior al mínimo requiere evidencia») | Si no hay evidencia, el mock baja al nivel mínimo | La validación semántica atrapa errores del generador, incluso del que escribió la misma IA. Confirma que no se debe confiar en la salida del modelo sin reglas. |
| 2 | Índice de calidad estática con ruff | Código limpio de ejemplo obtuvo 15/100: la regla S101 (`assert`) penalizaba las pruebas unitarias | Revisión manual de los hallazgos de ruff | Ignorar S101 y E501; fórmula menos agresiva | Una métrica objetiva mal calibrada es peor que no tenerla: castiga lo que se quiere promover (tener pruebas). |
| 3 | Descarga del informe integrado en PDF | Error 500 cuando el nombre del estudiante tenía tilde («Gómez»): la cabecera HTTP no admite UTF-8 | Prueba automática `test_flujo_completo` | Nombre ASCII + `filename*` (RFC 5987) | Las pruebas con datos realistas (nombres en español) encuentran errores que los datos "de juguete" no muestran. |
| 4 | Lectura del reporte XML de pytest | ruff (regla S314) avisó que el XML lo genera código no confiable (riesgo de XML bomb). Además, la IA notó que un estudiante podría **falsificar** el reporte | Linter de seguridad + análisis de amenazas | `defusedxml` y contraste con la salida de consola; si no coinciden, se toma el menor valor y se alerta | Vale la pena correr linters de seguridad sobre el código de la IA. El primer diseño confiaba en un dato que controla el evaluado. |
| 5 | Interfaz móvil | En pantallas de 390 px las columnas no se apilaban: los estilos en línea anulaban las *media queries* | Captura de pantalla con Playwright en viewport móvil | Clases CSS responsivas (`split-12`, `split-21`) | Hay que mirar el resultado en el dispositivo objetivo, no solo en escritorio. |
| 6 | Vista de una evaluación ajustada | Mostraba el nivel original del criterio con la etiqueta «ajustado», no el nivel final | Revisión visual de la captura | Mostrar el nivel ajustado y tachar el original | Detalles de UI pueden contradecir la nota publicada y minar la confianza del docente. |
| 7 | Editor de rúbricas | Las filas de competencias se desarmaban (inputs al 100 % dentro de un flex) | Captura de pantalla | Grilla de 3 columnas | — |
| 8 | Nombres y precios de modelos | El conocimiento del asistente sobre modelos y precios no estaba actualizado (proponía `gpt-4.1-mini`) | Verificación en las páginas de precios (17-nov-2026) | Valores por defecto `gpt-5-mini` y `claude-haiku-5-5`; costos documentados con fuentes | Los datos que cambian (precios, versiones) siempre se verifican; la IA no es fuente de información actual. |
| 9 | Lectura del artifact original del equipo | El asistente no pudo leer el código del prototipo desde su entorno (bloqueo de red) | Error de la herramienta | Se recorrió visualmente el prototipo en el navegador para extraer laboratorios y estructura | Conviene entregar al asistente el material fuente directamente (archivos) en vez de enlaces. |
| 10 | Vista del estudiante de una nota ajustada | Mostraba «preliminar —» y el nivel original tachado: filtraba que hubo una propuesta distinta | Recorrido completo con Playwright como estudiante | Esos datos solo se muestran al docente | Hay que revisar la interfaz con cada rol, no solo con el administrador. |
| 11 | PDF del informe integrado | Un promedio de 3,95 aparecía como «4.0» con nivel «Bueno»: parecía una contradicción | Revisión visual del PDF generado | Promedios con 2 decimales | El redondeo de presentación también afecta la confianza en el sistema. |
| 12 | Importar los trabajos reales del equipo (ZIP hechos en Windows) | Error 500: los ZIP de `Compress-Archive` marcan carpetas con `\\` y la plataforma las trataba como archivos | Carga real de Harness 3 | Reconocer ambos separadores y omitir conflictos archivo/carpeta; prueba nueva | Los datos reales del equipo encontraron un caso que los datos sintéticos no cubrían. |
| 13 | Pruebas en subcarpetas (`codigo/tests/`) | pytest no encontraba los módulos que el estudiante importaba desde `codigo/` | Verificación de Harness 2 | Detectar automáticamente las carpetas de importación; prueba nueva | Además se confirmó un error real del trabajo: al ZIP de Harness 2 le falta `agente_archivos_nube.py`. |

## Decisiones de diseño que la IA propuso y el equipo debe validar

- **El LLM no calcula la nota**: devuelve niveles; el backend aplica `Σ peso × puntaje`. Así lo exige el enunciado.
- **Criterios objetivos** (`pruebas`, `analisis_estatico`) puntuados por el backend con umbrales, sin intervención del modelo.
- **Verificación textual de citas** como medida de alucinación (indicador «evidencias verificadas»).
- **Rúbricas inmutables por versión**: la entrega queda atada a la versión con la que se subió.
- **Sandbox con degradación explícita** (docker → unshare → rlimit), indicando el modo en cada evaluación.

## Riesgos de haber usado IA para codificar

- **Comprensión**: el equipo debe poder explicar cada módulo en la sustentación. Recomendación: que cada integrante lea y explique 3–4 archivos de `app/`.
- **Seguridad**: el código pasó ruff con reglas de seguridad (bandit) y pruebas de sandbox, pero no tuvo una auditoría profesional.
- **Sesgo del evaluador**: los prompts y umbrales los propuso la IA; deben contrastarse con evaluaciones manuales del docente en algunos trabajos reales.
- **Dependencia**: si cambia la API de un proveedor, el conector puede fallar; por eso hay varios proveedores y un modo local.

## Entradas del equipo *(completar)*

| Fecha | Integrante | Herramienta | Qué se pidió | Resultado | Qué se corrigió o decidió el equipo y por qué |
|---|---|---|---|---|---|
| 17/11/2026 | Daniel Yesid Ramírez Cifuentes | Claude (Opus 5.5) | Comparar nuestro prototipo (artifact de autoevaluación) con el enunciado y listar lo que faltaba | Lista de 23 faltantes: backend, rúbrica por trabajo, nota 0–5, sandbox, autenticación, aprobación docente | El prototipo solo era una página; decidimos reconstruirlo como producto web con backend. |
| 17/11/2026 | Daniel Yesid Ramírez Cifuentes | Claude | Construir todo lo que pedía el enunciado | Plataforma FastAPI + frontend + 63 pruebas + documentación | Pedimos una alternativa 100 % gratuita (Gemini u Ollama + túnel de Cloudflare) porque Railway y las API pagas no eran viables para el curso. |
| 17/11/2026 | Daniel Yesid Ramírez Cifuentes | Claude + Desktop Commander | Instalar y publicar la plataforma en nuestro PC | Docker Desktop no arrancaba por sockets bloqueados; la IA lo diagnosticó leyendo los logs | Pedimos cambiar «Cohorte» por «Corte», que es el término que usa el curso. |
| 17/11/2026 | Equipo (D. Y. Ramírez, D. Giraldo, J. F. Parra) | Claude | Cargar nuestros 9 trabajos reales y su código | Aparecieron errores reales de nuestras entregas (ruta errada en la prueba de Harness 1, archivo faltante en Harness 2) | Los dejamos tal cual: muestran que la verificación objetiva sí detecta fallos, aunque bajen nuestra nota. |
| 17/11/2026 | Daniel Yesid Ramírez Cifuentes | Claude | Subir el repositorio a GitHub | Repositorio github.com/Doperlove/asesor-pedagogico sin `.env` ni documentos de estudiantes | Verificamos que la clave de API no quedara en el repositorio. |

**Reflexión crítica del equipo** *(borrador redactado con ayuda de la IA a partir de lo ocurrido en el proyecto; el equipo lo revisó y lo asume)*

La IA aceleró sobre todo la parte repetitiva y amplia: estructurar el backend, escribir las pruebas, documentar y desplegar. Lo que hizo valiosa la experiencia no fue que generara código, sino que lo obligamos a ejecutarse: las pruebas automáticas, el linter de seguridad y la carga de nuestros propios trabajos encontraron 13 errores que el asistente no había previsto, entre ellos un bug con los ZIP de Windows y la posibilidad de que un estudiante falsificara el reporte de pruebas. Sin esas verificaciones habríamos entregado un sistema que parecía funcionar pero fallaba con datos reales.

También aprendimos los límites: la IA no conocía los precios ni los modelos actuales (hubo que verificarlos en la web), no puede reemplazar el criterio del docente, y por eso diseñamos la plataforma para que el modelo solo proponga niveles con evidencias verificables mientras la nota la calcula el servidor y la aprueba una persona. Si lo repitiéramos, entregaríamos al asistente los archivos fuente desde el principio, en vez de enlaces, y definiríamos antes las rúbricas reales de cada laboratorio.
