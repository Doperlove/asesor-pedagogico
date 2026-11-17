# Matriz de cumplimiento frente al enunciado

| Requisito del enunciado | Cómo se cumple | Dónde (código) | Prueba / evidencia |
|---|---|---|---|
| **1. Portafolio por cohortes y laboratorios** | Cohortes 1 y 2 con sus laboratorios en el panel docente y en «Mis trabajos» del estudiante | `models.Cohorte/Laboratorio`, `GET /api/cohortes`, `static/app.js` (panel) | Demo paso 0:00 |
| Informe PDF de texto legible | Se verifica la firma `%PDF`, se extrae el texto por página y se rechaza si tiene menos de 300 caracteres útiles | `ingest.procesar_pdf` | `test_pdf_sin_texto_se_rechaza` |
| Código fuente (GitHub o ZIP) | ZIP con protección zip-slip o GitHub con commit fijado | `ingest.extraer_zip`, `ingest.descargar_github` | `test_zip_slip...`, `test_validacion_url_github` |
| Rúbrica específica por entrega y versión conservada | Rúbrica por laboratorio con versiones inmutables; `Entrega.rubrica_id` se congela al cargar | `models.Rubrica`, `api.crear_entrega` | `test_flujo_completo` (rubrica_version) |
| Videos y presentaciones opcionales | Enlace o archivo anexo opcional | `Entrega.extra_url/extra_path` | Formulario «Anexos opcionales» |
| **2. Rúbrica parametrizada** (competencias, criterios, descriptores, pesos 100 %) | Esquema Pydantic + editor visual + JSON + importación PDF/DOCX | `rubrics.py`, `/rubrica/:lab` en la UI | `test_rubrica_valida` |
| Rechazar rúbricas incompletas o incoherentes | Más de 20 reglas de coherencia; HTTP 422 con todos los errores | `rubrics.validar_rubrica` | `test_rubricas_incoherentes_se_rechazan` (8 casos) |
| Permitir que el docente las corrija | Borrador guardado con sus errores; el editor lo abre y muestra los errores | `api._guardar_rubrica`, editor | `test_rubrica_incoherente_rechazada_y_corregible` |
| **3. Evaluación de cada trabajo**: aprendizajes, evidencias, puntaje por criterio | Esquema `SalidaEvaluacion` con aprendizajes, criterios, evidencias, fortalezas, vacíos, retroalimentación, recomendaciones y actividades | `llm/schemas.py`, `evaluation.evaluar` | `test_flujo_completo` |
| Nota preliminar 0,0–5,0 con revisión docente | La evaluación queda en estado `preliminar`, invisible para el estudiante | `Evaluacion.estado` | `test_flujo_completo` (el estudiante no ve la preliminar) |
| **4. Informe integrado** por laboratorio, cohorte y estudiante | Tres vistas: notas, competencias, progresión, brechas, plan | `reports.py`, `/informe/...` en la UI | `test_flujo_completo` |
| Consultar y descargar el informe | Vista web + PDF con ReportLab | `GET /api/informes/estudiante/{id}/pdf` | Prueba: la respuesta empieza por `%PDF` |
| **Evaluación reproducible**: JSON Schema/Pydantic (evidencia, criterio, nivel) | JSON Schema enviado al proveedor + validación Pydantic + reglas semánticas + reintentos | `llm/schemas.py`, `evaluation.validar_salida` | `test_salida_valida`, `test_nivel_inexistente...` |
| Conversión niveles y pesos → nota en el backend, nunca el LLM | `extra="forbid"` impide un campo de nota; `grading.calcular_nota` con Decimal | `grading.py` | `test_el_llm_no_puede_devolver_una_nota`, `test_formula_de_la_nota` |
| **Verificación de código**: revisión conceptual + análisis estático + pruebas unitarias | Criterios LLM (conceptual) + ruff + pytest; criterios automáticos con umbrales | `code_check.py`, `grading.nivel_por_metrica` | `test_nivel_objetivo_por_metrica` |
| Sandbox aislado, límites de tiempo y recursos, sin red por defecto | docker / unshare / rlimit; timeout que mata el grupo de procesos; entorno vacío | `sandbox.py`, `sandbox/Dockerfile` | `test_sandbox_corta_bucles_infinitos`, `test_sandbox_sin_red`, `test_sandbox_no_expone_secretos` |
| **IA local o API remota con conector configurable** | Ollama, Gemini (plan gratuito), OpenAI-compatible (OpenAI, DeepSeek…), Anthropic y mock; seleccionable en la UI | `llm/providers.py`, `/config` | «Probar conexión» |
| Documentar costos y condiciones de acceso | Tabla comparativa con fuentes y estimación por evaluación | `docs/COSTOS_Y_ACCESO.md` | — |
| Asistente de codificación con IA + bitácora crítica | Bitácora con 11 incidentes reales y espacio para el equipo | `docs/BITACORA_IA.md` | — |
| **Servidor web con URL operativa** | Dockerfile + `railway.json` + `docker-compose.yml`; guía de despliegue | `Dockerfile`, manual §7 | *El equipo debe desplegar y anotar la URL* |
| Autenticación | JWT en cookie httpOnly, roles, límite de intentos, bcrypt | `security.py` | `test_requiere_autenticacion`, `test_login_incorrecto`, `test_estudiante_no_accede...` |
| Almacenamiento seguro | Archivos con nombres UUID fuera de `/static`, servidos con autorización; secretos en el entorno | `ingest.nueva_carpeta`, `api.descargar_informe` | Prueba de otro estudiante → 404 |
| **Registrar modelo, evidencias, versión de rúbrica, resultados de pruebas** | `Evaluacion` guarda proveedor, modelo, parámetros, hashes, rúbrica, verificación y respuesta; tabla de auditoría | `models.Evaluacion`, `models.Auditoria` | «Trazabilidad técnica» y «Auditoría» en la UI |
| Proteger información estudiantil | Aislamiento por estudiante, CSP, cookies seguras, entorno del sandbox sin secretos | `security.can_see_student`, `main.cabeceras_seguridad` | `test_flujo_completo` (Luis → 404) |
| Docente aprueba o ajusta antes de publicar | Revisión con ajuste por criterio, justificación obligatoria y nota recalculada | `evaluation.revisar` | `test_flujo_completo` (422 sin justificación) |
| **Entregables**: URL + repositorio + manual + bitácora + pruebas | `README.md`, `docs/`, `tests/` (61 pruebas), CI | — | `pytest -q` |
| Demostración obligatoria | Guion minuto a minuto con archivos de muestra | `docs/GUION_DEMO.md`, `sample_data/` | — |

## Criterios de la rúbrica del proyecto

| Criterio (peso) | Evidencia que la plataforma aporta |
|---|---|
| 1. Ingeniería de software y codificación asistida (20 %) | Arquitectura modular, tipado, 61 pruebas, CI, ruff con reglas de seguridad, bitácora crítica |
| 2. Producto web desplegado (20 %) | Docker/Railway, autenticación, portafolio con rúbrica versionada por trabajo |
| 3. Evaluación individual rigurosa (25 %) | Evidencias verificadas, pruebas en sandbox, niveles por criterio, cálculo 0–5 en el backend, retroalimentación accionable |
| 4. Informe integrado y fortalecimiento (15 %) | Ambas cohortes, competencias RA1–RA4, progresión, brechas, plan priorizado, PDF |
| 5. Confianza y validación (20 %) | Seguridad, auditoría, reproducibilidad (hashes, temperatura 0, comparación), detección de inyección, aprobación docente |
