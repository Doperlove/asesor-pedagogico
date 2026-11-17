# Modelos: costos y condiciones de acceso

Precios consultados el **17 de noviembre de 2026** en dólares por millón de tokens (MTok). Pueden cambiar: verifique la página oficial antes de presupuestar.

## Supuesto de consumo por evaluación

| Componente | Tokens aprox. |
|---|---|
| Prompt del sistema + rúbrica | 2.500 |
| Informe PDF (10–15 páginas) | 12.000 |
| Código fuente (truncado a ~30.000 caracteres) | 8.000 |
| Resultados de ruff y pytest | 1.000 |
| **Entrada total** | **≈ 25.000** |
| Salida JSON (criterios, evidencias, retroalimentación) | ≈ 2.500 |

Si el modelo falla la validación, se reintenta hasta 2 veces más (el peor caso triplica el costo). La plataforma registra los tokens reales de cada evaluación en su trazabilidad.

## Comparativo

| Opción | Modelo sugerido | Entrada / salida por MTok | Costo por evaluación | 270 evaluaciones* | Condiciones de acceso |
|---|---|---|---|---|---|
| Local | Ollama `qwen2.5:7b` | $0 | $0 (electricidad) | $0 | Instalar Ollama; ~8 GB RAM o 6 GB VRAM. Los datos no salen del equipo. Más lento (30–120 s por evaluación en CPU/GPU modesta). |
| OpenAI | `gpt-5-mini` | $0,25 / $2,00 | ≈ $0,011 | ≈ $3 | Cuenta en platform.openai.com, tarjeta y saldo prepagado; `OPENAI_API_KEY`. |
| OpenAI (económico) | `gpt-5-nano` | $0,05 / $0,40 | ≈ $0,002 | ≈ $0,6 | Igual que arriba; menor calidad de razonamiento. |
| DeepSeek | `deepseek-flash` | $0,30 / $1,20 (pico) · mitad en horario valle | ≈ $0,011 | ≈ $3 | Cuenta y recarga en platform.deepseek.com. Usar `LLM_PROVIDER=openai`, `LLM_BASE_URL=https://api.deepseek.com`, `OPENAI_JSON_MODE=json_object`. Servidores en China: revisar la política de datos de la universidad. |
| Anthropic | `claude-haiku-5-5` | $0,10 / $0,50 | ≈ $0,004 | ≈ $1 | Cuenta en console.anthropic.com, créditos prepagados; `ANTHROPIC_API_KEY`. |
| Anthropic (más capaz) | `claude-sonnet-5-5` | $2 / $10 | ≈ $0,075 | ≈ $20 | Igual que arriba. |
| **Gratis** | Google Gemini `gemini-2.5-flash` (plan gratuito) | $0 | $0 | $0 (dentro de los límites diarios) | Clave en aistudio.google.com/apikey, **sin tarjeta**. Límites por minuto/día según el proyecto. Google puede usar el contenido del plan gratuito para mejorar sus productos. `LLM_PROVIDER=gemini`, `GEMINI_API_KEY`. |
| Gratis (no apto) | Groq (plan gratuito) | $0 | — | — | Unos 8.000 tokens/minuto: no alcanza para una evaluación (~25.000 tokens). |
| Demostración | `mock` (heurístico) | $0 | $0 | $0 | Sin red. No usa IA real; solo sirve para mostrar el flujo. |

\* 9 laboratorios × 30 estudiantes.

Cálculo de ejemplo con `gpt-5-mini`: 25.000 × $0,25 / 1.000.000 + 2.500 × $2,00 / 1.000.000 = $0,00625 + $0,005 ≈ **$0,011**.

## Hosting

| Servicio | Costo | Notas |
|---|---|---|
| Railway Hobby | US$5/mes (incluye US$5 de uso) | PostgreSQL y volumen se cobran por uso. Prueba gratis de 30 días con US$5 en créditos. |
| Railway Pro | US$20/mes (incluye US$20 de uso) | Para varios integrantes. |
| VPS / Proxmox propio | Costo del servidor | Permite sandbox Docker completo y Ollama local. |

## Recomendación

- **Todo gratis**: Gemini (plan gratuito) u Ollama + su propio PC con túnel de Cloudflare. Ver `DESPLIEGUE_GRATIS.md`.
- **Demostración en clase**: `mock` para mostrar el flujo sin costo y sin depender de internet, y luego una evaluación real con `gpt-5-mini` o `claude-haiku-5-5` para mostrar la calidad (menos de US$0,02 por evaluación).
- **Privacidad máxima**: Ollama local. Si la app está en Railway, conecte el PC con Ollama por Tailscale y use su IP en «URL base».

## Fuentes

- Google AI Studio — plan gratuito (BenchLM, 11-nov-2026): https://benchlm.ai/md/free-tier/google-ai-studio.md
- Groq — plan gratuito (BenchLM, 16-nov-2026): https://benchlm.ai/md/free-tier/groq.md
- Hosting gratuito para FastAPI (AgentDeals, nov-2026): https://agentdeals.dev/free-fastapi-stack
- OpenAI — precios oficiales de la API: https://developers.openai.com/api/docs/pricing.md
- DeepSeek — precios de la API (BenchLM, 29-oct-2026): https://www.benchlm.ai/deepseek/api-pricing
- Anthropic — precios de la API (BenchLM, 17-nov-2026): https://benchlm.ai/anthropic/api-pricing
- Railway — planes (Livemy, 2-nov-2026): https://livemy.app/blog/railway-pricing
