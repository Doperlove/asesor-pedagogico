# Guion de la demostración obligatoria (8–10 minutos)

**Flujo exigido:** cargar trabajo y rúbrica → verificar evidencias → puntuar criterios → calcular nota → retroalimentar → aprobar → emitir informe integrado.

## Antes de presentar

- [ ] La URL pública responde: `https://SU-DOMINIO/api/salud` → `{"ok": true}`.
- [ ] Tener a mano los archivos de `sample_data/`:
  - `rubrica_invalida_para_demo.json` (para mostrar el rechazo)
  - `informe_harness2_agente.pdf` + `codigo_harness2_agente.zip` (trabajo normal)
  - `informe_con_inyeccion.pdf` (opcional: alerta de seguridad)
- [ ] Decidir el modelo: `mock` (sin internet) o uno real (`gpt-5-mini`, `claude-haiku-5-5`, Ollama). Probarlo antes en «Modelo y sandbox → Probar conexión».
- [ ] Mejor aún, usar un **trabajo real** de ustedes (PDF + ZIP) en el laboratorio correspondiente.
- [ ] Dos pestañas: una como **docente** y otra en ventana privada como **estudiante** (ana.gomez@demo.edu.co).

## Paso a paso

| Min | Paso | Qué hacer | Qué decir |
|---|---|---|---|
| 0:00 | Contexto | Panel docente: cohortes 1 y 2 con sus laboratorios | «Cada laboratorio tiene su propia rúbrica versionada. El portafolio organiza las dos cohortes.» |
| 0:45 | **Rúbrica** | Laboratorio *Harness 2* → *Editar* → *Importar archivo* → `rubrica_invalida_para_demo.json` | «La plataforma rechaza rúbricas incoherentes: pesos que suman 115 %, un descriptor vacío, una competencia que no existe y un criterio automático sin umbrales.» |
| 1:30 | Corrección | Corregir en el editor visual (peso 25, completar el descriptor, competencia RA3, umbral 0) → *Validar* → *Guardar versión* | «El docente corrige y se crea la versión 2, inmutable. Las entregas anteriores conservan su versión.» |
| 2:15 | **Cargar trabajo** | *Cargar trabajo* → Harness 2, estudiante Ana → PDF + ZIP | «Si el PDF es escaneado, se rechaza porque no se podrían verificar las citas. El código queda con su hash; si viene de GitHub, se fija el commit.» |
| 3:00 | **Verificar evidencias** | *Verificar código* | «ruff analiza sin ejecutar. pytest corre en un sandbox sin red, con límite de tiempo y memoria: 4 de 4 pruebas. Aquí se ve el modo de aislamiento.» |
| 4:00 | **Puntuar criterios** | *Evaluar con IA* | «El modelo devuelve JSON validado con Pydantic: un nivel por criterio y citas textuales. Los criterios de pruebas y calidad los puntúa el backend con umbrales, no el modelo.» |
| 5:00 | **Evidencias** | Mostrar las marcas ✓ y la ubicación (p. 2, `agente/bucle.py:7`) y el indicador «evidencias verificadas» | «Cada cita se busca en el PDF y en el código. Si el modelo inventa una, aparece en rojo y genera una alerta.» |
| 5:45 | **Calcular nota** | Señalar «Cálculo en el backend: 25 %×5,0 + …» | «La nota de 0 a 5 la calcula el servidor con la fórmula Σ peso × puntaje. El modelo nunca escribe una nota.» |
| 6:15 | **Retroalimentar** | Aprendizajes, fortalezas, vacíos, recomendaciones con el «cómo», actividades | — |
| 6:45 | Confianza | Pestaña estudiante: el trabajo aparece «en revisión», sin nota | «El estudiante no ve nada hasta que el docente apruebe.» |
| 7:00 | **Aprobar** | Cambiar un nivel → la nota se recalcula → escribir la justificación → *Publicar con ajustes* | «Ajustar exige justificación. Queda auditado: quién, cuándo, de qué nota a qué nota.» |
| 7:45 | Estudiante | Recargar: ve la nota final y el comentario | — |
| 8:00 | **Informe integrado** | *Informes* → Ana → promedio, progresión entre cohortes, competencias RA1–RA4, plan de fortalecimiento → *Descargar PDF* | «Consolida los laboratorios de ambas cohortes: brechas y plan priorizado.» |
| 8:45 | Trazabilidad | Abrir *Trazabilidad técnica* (modelo, hashes, esquema, intentos, tokens) y *Auditoría* | «Por esto la evaluación merece confianza: es reproducible, verificable y supervisada.» |
| 9:15 | Extra (opcional) | Evaluar `informe_con_inyeccion.pdf` → alerta roja | «Si el informe intenta manipular al evaluador, se detecta y se avisa al docente.» |

## Preguntas probables

- **¿Y si el modelo alucina?** Las citas se verifican contra el material, el porcentaje se muestra y las no encontradas generan alertas. Además, el docente aprueba.
- **¿Es reproducible?** Temperatura 0, semilla fija, prompt y esquema versionados, hash de entrada. Al reevaluar se comparan los niveles.
- **¿Por qué no deja que el LLM ponga la nota?** Porque el texto libre no es auditable. El backend aplica una fórmula fija y comprobable.
- **¿Cómo se protege el servidor del código del estudiante?** Con el sandbox sin red y con límites (sección 6 del manual) y con el análisis estático, que no ejecuta nada.
- **¿Cuánto cuesta?** Ver `COSTOS_Y_ACCESO.md`: cerca de US$0,01 por evaluación con `gpt-5-mini`, o $0 con Ollama.
