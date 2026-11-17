# Despliegue 100 % gratis

Combinación recomendada, sin tarjeta de crédito:

| Pieza | Opción gratis | Limitación |
|---|---|---|
| **Modelo de IA** | **Google Gemini** (plan gratuito de Google AI Studio, modelo `gemini-2.5-flash`) **u Ollama** local (`qwen2.5:7b`) | Gemini gratis: límites por minuto y por día, y Google puede usar los datos del plan gratuito para mejorar sus productos. Ollama: requiere un PC con unos 8 GB de RAM libres y es más lento. |
| **Servidor + URL pública** | Su propio PC + **túnel de Cloudflare** (`docker-compose.gratis.yml`) o **Tailscale Funnel** | La URL funciona mientras el PC esté encendido. |
| **Base de datos** | SQLite dentro del volumen de Docker | Suficiente para un curso; para más usuarios, PostgreSQL. |

## Paso 1 — Elegir el modelo gratis

### Opción A: Google Gemini (más fácil, mejor calidad)

1. Entre a https://aistudio.google.com/apikey con una cuenta de Google y pulse **Create API key**. No pide tarjeta.
2. En `.env` ponga:
   ```
   LLM_PROVIDER=gemini
   GEMINI_API_KEY=su-clave
   ```
3. O, ya dentro de la plataforma: **Modelo y sandbox → Proveedor: Google Gemini → Guardar → Probar conexión**.

Si aparece «Se alcanzó el límite del plan gratuito (429)», la plataforma ya reintentó sola. Espere un minuto y vuelva a evaluar.

**Privacidad:** como Google puede usar el contenido del plan gratuito, para la demo use los trabajos de ustedes mismos o los archivos de `sample_data/`. No suba trabajos de otros estudiantes sin su permiso. Para datos reales de estudiantes, use Ollama.

### Opción B: Ollama (100 % local y privado)

1. Instale Ollama desde https://ollama.com/download.
2. En una terminal: `ollama pull qwen2.5:7b` (descarga unos 4,7 GB).
3. En `.env`:
   ```
   LLM_PROVIDER=ollama
   LLM_MODEL=qwen2.5:7b
   LLM_BASE_URL=http://host.docker.internal:11434
   ```
   Si corre la app sin Docker, use `http://localhost:11434`.

Cada evaluación puede tardar de 1 a 3 minutos en un PC sin GPU dedicada.

> **Groq gratis no sirve aquí:** su plan gratuito permite unos 8.000 tokens por minuto y una evaluación envía unos 25.000.

## Paso 2 — Publicar la plataforma gratis desde su PC

Requisitos: **Docker Desktop** instalado (Windows/Mac) o Docker en Linux. En Windows use Docker (o WSL2), no Python directo: el sandbox necesita funciones de Linux.

```bash
cp .env.example .env          # en Windows: copy .env.example .env
# edite .env: SECRET_KEY, DEMO_PASSWORD y el modelo del paso 1
docker compose -f docker-compose.gratis.yml up -d --build
docker compose -f docker-compose.gratis.yml logs tunel
```

En el log aparece una línea como:

```
Your quick Tunnel has been created! Visit it at: https://algo-aleatorio.trycloudflare.com
```

**Esa es la URL operativa** que pide el proyecto. Ábrala desde el celular para comprobar que funciona fuera de su red.

- La URL cambia cada vez que se reinicia el túnel; anótela el día de la sustentación.
- Para detener: `docker compose -f docker-compose.gratis.yml down` (los datos quedan en el volumen).

### Alternativa con URL fija: Tailscale Funnel

Si ya usan Tailscale (plan personal gratuito):

```bash
docker compose -f docker-compose.gratis.yml up -d --build app   # sin el túnel de Cloudflare
tailscale funnel 8000
```

La URL queda fija, del tipo `https://nombre-del-pc.su-tailnet.ts.net`.

## Sandbox en esta modalidad

Dentro del contenedor el sandbox queda en modo `rlimit`: aislamiento parcial, con límites de tiempo, memoria y archivos, sin secretos en el entorno y con la red bloqueada en Python. La plataforma lo indica en cada evaluación. Para la demo con trabajos propios es suficiente. Para aislamiento completo ver el manual técnico §6.

## Otras opciones gratis (y por qué quedan en segundo lugar)

| Opción | Qué ofrece | Problema |
|---|---|---|
| Railway (plan de prueba) | US$5 de crédito durante 30 días, sin tarjeta | Gratis solo el primer mes; después el crédito de US$1/mes no alcanza para tenerla siempre encendida. Sirve si la sustentación cae dentro de esos 30 días. |
| Render (plan gratuito) | Contenedor gratis | Se duerme a los 15 minutos (la primera carga tarda cerca de 1 minuto) y el disco es efímero: los PDF y ZIP subidos se pierden al reiniciar. Requiere una base externa (Neon gratis). |
| Koyeb / Fly.io | — | Ya no tienen plan gratis para cuentas nuevas. |
