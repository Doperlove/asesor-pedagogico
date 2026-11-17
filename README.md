# Asesor Pedagógico Inteligente

Plataforma web desplegable para **evaluar, retroalimentar y fortalecer competencias en IA**. Recibe los trabajos de las cohortes 1 y 2 con su rúbrica, verifica evidencias, propone valoraciones con IA y construye un diagnóstico integral del aprendizaje. Proyecto final de Inteligencia Artificial, Universidad de Manizales.

> **Principio de diseño:** no basta con que un LLM asigne una nota. El modelo solo propone niveles con citas, el sistema **verifica** cada cita contra el material, **mide** el código con pruebas y análisis estático en un sandbox, **calcula** la nota en el servidor y el **docente aprueba** antes de publicar.

## Funcionalidades

- **Portafolio** por cohorte y laboratorio: informe PDF legible, código (ZIP o GitHub con commit fijado) y anexos opcionales.
- **Rúbrica parametrizada** por laboratorio (competencias, criterios, descriptores y pesos que suman 100 %), con editor visual, JSON o importación desde PDF/DOCX. Las rúbricas incoherentes se rechazan con la lista de errores y quedan como borrador para corregir. Las versiones son inmutables.
- **Evaluación por trabajo**: aprendizajes demostrados, puntaje por criterio con evidencias verificadas, fortalezas, vacíos, retroalimentación, recomendaciones y actividades. Nota preliminar de 0,0 a 5,0.
- **Verificación objetiva**: ruff (estilo, errores, complejidad, seguridad) y pytest en un sandbox sin red con límites de tiempo y memoria.
- **Revisión docente**: aprobar, o ajustar niveles con justificación obligatoria. El estudiante solo ve notas publicadas.
- **Informe integrado** por estudiante, cohorte y laboratorio: notas, competencias, progresión, brechas y plan de fortalecimiento, descargable en PDF.
- **Conector de modelos**: Ollama (local, gratis), Google Gemini (plan gratuito), APIs compatibles con OpenAI (OpenAI, DeepSeek…), Anthropic, y un evaluador de demostración sin costo.
- **Trazabilidad**: modelo, parámetros, hashes de entrada y prompt, versión de rúbrica y de esquema, resultados de pruebas, intentos, tokens y auditoría de acciones.

## Inicio rápido

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export DEMO_PASSWORD='una-clave-de-demo' SECRET_KEY="$(python -c 'import secrets;print(secrets.token_urlsafe(48))')"
uvicorn app.main:app --reload
```

Abra http://localhost:8000.

| Rol | Correo | Contraseña |
|---|---|---|
| Docente | docente@demo.edu.co | valor de `DEMO_PASSWORD` (por defecto `Demo-2026-Asesor`) |
| Estudiante | ana.gomez@demo.edu.co · luis.perez@demo.edu.co | igual |

La primera vez se crean los 9 laboratorios con sus rúbricas y un historial de ejemplo. En producción cambie `DEMO_PASSWORD` o use `SEED_DEMO=false`.

## Despliegue

- **Gratis** (su PC + túnel de Cloudflare + Gemini u Ollama): ver [docs/DESPLIEGUE_GRATIS.md](docs/DESPLIEGUE_GRATIS.md).
- **Railway** (URL pública con HTTPS): ver [manual técnico §7.2](docs/MANUAL_TECNICO.md#72-railway-url-pública).
- **Servidor propio con Docker** (sandbox con aislamiento completo): `docker build -t asesor-sandbox ./sandbox && docker compose up -d`.

## Pruebas

```bash
pytest -q                       # 61 pruebas: rúbricas, nota, esquema LLM, evidencias, sandbox, seguridad, flujo completo
ruff check app tests scripts
```

## Documentación

| Documento | Contenido |
|---|---|
| [docs/MANUAL_TECNICO.md](docs/MANUAL_TECNICO.md) | Arquitectura, modelo de datos, flujo de evaluación, seguridad, sandbox, despliegue, API |
| [docs/DESPLIEGUE_GRATIS.md](docs/DESPLIEGUE_GRATIS.md) | Cómo publicar la plataforma y usar IA sin pagar nada |
| [docs/COSTOS_Y_ACCESO.md](docs/COSTOS_Y_ACCESO.md) | Costos por evaluación y condiciones de acceso de cada proveedor |
| [docs/BITACORA_IA.md](docs/BITACORA_IA.md) | Bitácora crítica del uso del asistente de codificación con IA |
| [docs/GUION_DEMO.md](docs/GUION_DEMO.md) | Guion minuto a minuto de la demostración obligatoria |
| [docs/MATRIZ_CUMPLIMIENTO.md](docs/MATRIZ_CUMPLIMIENTO.md) | Cada requisito del enunciado → implementación → prueba |

## Estructura

```
app/
  main.py          aplicación FastAPI, cabeceras de seguridad
  api.py           endpoints REST
  models.py        modelo de datos (SQLAlchemy)
  security.py      JWT, bcrypt, roles, límite de intentos, auditoría
  rubrics.py       esquema y validación de rúbricas
  grading.py       cálculo de la nota (backend)
  ingest.py        PDF, ZIP, GitHub
  code_check.py    ruff + pytest
  sandbox.py       ejecución aislada
  evidence.py      verificación de citas y detección de inyección
  evaluation.py    orquestación y revisión docente
  reports.py       informes integrados y PDF
  llm/             esquemas, prompts y proveedores
static/            interfaz web (HTML/CSS/JS sin dependencias)
tests/             pruebas automáticas
sandbox/           imagen Docker del sandbox
sample_data/       archivos para la demostración
docs/              documentación
```
