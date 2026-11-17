"""Conector configurable de modelos: local (Ollama) o API remota (OpenAI-compatible / Anthropic).

Todos devuelven JSON que luego se valida con Pydantic. El proveedor `mock` es un evaluador
heurístico determinista (sin IA) para pruebas automáticas y demostraciones sin red.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field

import httpx

from ..config import get_settings
from ..evidence import normalizar

DEFAULTS = {
    "mock": {"model": "heuristico-v1", "base_url": ""},
    "ollama": {"model": "qwen2.5:7b", "base_url": "http://localhost:11434"},
    "openai": {"model": "gpt-5-mini", "base_url": "https://api.openai.com/v1"},
    "anthropic": {"model": "claude-haiku-5-5", "base_url": "https://api.anthropic.com"},
    "gemini": {"model": "gemini-2.5-flash", "base_url": "https://generativelanguage.googleapis.com/v1beta/openai"},
}


class LLMError(RuntimeError):
    pass


@dataclass
class ConfigModelo:
    proveedor: str
    modelo: str
    base_url: str
    temperatura: float = 0.0
    seed: int = 42
    timeout_s: int = 180

    def publico(self) -> dict:
        return {"proveedor": self.proveedor, "modelo": self.modelo, "base_url": self.base_url,
                "temperatura": self.temperatura, "seed": self.seed}


@dataclass
class RespuestaLLM:
    datos: dict
    uso: dict = field(default_factory=dict)
    duracion_ms: int = 0


def _extraer_json(texto: str) -> dict:
    texto = texto.strip()
    texto = re.sub(r"^```(?:json)?\s*|\s*```$", "", texto)
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        ini, fin = texto.find("{"), texto.rfind("}")
        if ini >= 0 and fin > ini:
            try:
                return json.loads(texto[ini:fin + 1])
            except json.JSONDecodeError:
                pass
    raise LLMError("El modelo no devolvió JSON válido.")


class Proveedor:
    def __init__(self, cfg: ConfigModelo) -> None:
        self.cfg = cfg

    def generar(self, sistema: str, mensajes: list[dict], schema: dict, nombre: str, contexto: dict | None = None) -> RespuestaLLM:
        t0 = time.monotonic()
        datos, uso = self._llamar(sistema, mensajes, schema, nombre, contexto or {})
        return RespuestaLLM(datos=datos, uso=uso, duracion_ms=int((time.monotonic() - t0) * 1000))

    def _llamar(self, sistema, mensajes, schema, nombre, contexto):  # pragma: no cover - interfaz
        raise NotImplementedError


class OllamaProveedor(Proveedor):
    def _llamar(self, sistema, mensajes, schema, nombre, contexto):
        payload = {
            "model": self.cfg.modelo,
            "messages": [{"role": "system", "content": sistema}, *mensajes],
            "stream": False,
            "format": schema,  # salida estructurada con JSON Schema (Ollama ≥ 0.5)
            "options": {"temperature": self.cfg.temperatura, "seed": self.cfg.seed, "num_ctx": 32768},
        }
        try:
            r = httpx.post(f"{self.cfg.base_url.rstrip('/')}/api/chat", json=payload, timeout=self.cfg.timeout_s)
            r.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMError(f"Ollama no respondió en {self.cfg.base_url}: {exc}") from exc
        data = r.json()
        uso = {"entrada": data.get("prompt_eval_count"), "salida": data.get("eval_count")}
        return _extraer_json(data["message"]["content"]), uso


def _post_con_reintentos(url: str, payload: dict, headers: dict, timeout: int, intentos: int = 4) -> httpx.Response:
    """POST con reintento ante 429/503 (límites de los planes gratuitos), respetando Retry-After."""
    espera = 5.0
    for i in range(intentos):
        try:
            r = httpx.post(url, json=payload, headers=headers, timeout=timeout)
        except httpx.HTTPError as exc:
            raise LLMError(f"No se pudo contactar la API: {exc}") from exc
        if r.status_code in (429, 503) and i < intentos - 1:
            try:
                espera = min(60.0, float(r.headers.get("retry-after", espera)))
            except ValueError:
                pass
            time.sleep(espera)
            espera = min(60.0, espera * 2)
            continue
        if r.status_code >= 400:
            msg = r.text[:300]
            if r.status_code == 429:
                msg = "Se alcanzó el límite del plan gratuito (429). Espere un minuto o cambie de modelo. " + msg
            raise LLMError(f"La API respondió {r.status_code}: {msg}")
        return r
    raise LLMError("La API no respondió tras varios intentos.")


class OpenAIProveedor(Proveedor):
    """Sirve para OpenAI y cualquier API compatible (DeepSeek, Groq, OpenRouter, LM Studio...)."""

    enviar_seed = True

    def _clave(self) -> str | None:
        return get_settings().openai_api_key

    def _modo_json(self) -> str:
        return get_settings().openai_json_mode

    def _llamar(self, sistema, mensajes, schema, nombre, contexto):
        clave = self._clave()
        if not clave and "localhost" not in self.cfg.base_url and "127.0.0.1" not in self.cfg.base_url:
            raise LLMError(f"Falta la clave de API ({self.variable_clave}) en las variables de entorno del servidor.")
        if self._modo_json() == "json_object":
            fmt: dict = {"type": "json_object"}
            sistema = sistema + "\n\nEsquema JSON que debes cumplir:\n" + json.dumps(schema, ensure_ascii=False)
        else:
            fmt = {"type": "json_schema", "json_schema": {"name": nombre, "schema": schema, "strict": False}}
        payload = {
            "model": self.cfg.modelo,
            "messages": [{"role": "system", "content": sistema}, *mensajes],
            "temperature": self.cfg.temperatura,
            "response_format": fmt,
        }
        if self.enviar_seed:
            payload["seed"] = self.cfg.seed
        headers = {"Authorization": f"Bearer {clave or 'local'}"}
        r = _post_con_reintentos(f"{self.cfg.base_url.rstrip('/')}/chat/completions", payload, headers, self.cfg.timeout_s)
        data = r.json()
        u = data.get("usage") or {}
        return _extraer_json(data["choices"][0]["message"]["content"]), {"entrada": u.get("prompt_tokens"), "salida": u.get("completion_tokens")}

    variable_clave = "OPENAI_API_KEY"


class GeminiProveedor(OpenAIProveedor):
    """Google Gemini por su endpoint compatible con OpenAI. Tiene plan gratuito sin tarjeta (Google AI Studio)."""

    enviar_seed = False
    variable_clave = "GEMINI_API_KEY"

    def _clave(self) -> str | None:
        return get_settings().gemini_api_key

    def _modo_json(self) -> str:
        return get_settings().gemini_json_mode


class AnthropicProveedor(Proveedor):
    """Usa tool use forzado: el modelo debe llenar los argumentos de la herramienta según el esquema."""

    def _llamar(self, sistema, mensajes, schema, nombre, contexto):
        s = get_settings()
        if not s.anthropic_api_key:
            raise LLMError("Falta ANTHROPIC_API_KEY en las variables de entorno del servidor.")
        payload = {
            "model": self.cfg.modelo,
            "max_tokens": 8000,
            "temperature": self.cfg.temperatura,
            "system": sistema,
            "messages": mensajes,
            "tools": [{"name": nombre, "description": "Registra el resultado estructurado.", "input_schema": schema}],
            "tool_choice": {"type": "tool", "name": nombre},
        }
        headers = {"x-api-key": s.anthropic_api_key, "anthropic-version": "2023-06-01"}
        r = _post_con_reintentos(f"{self.cfg.base_url.rstrip('/')}/v1/messages", payload, headers, self.cfg.timeout_s)
        data = r.json()
        bloque = next((b for b in data.get("content", []) if b.get("type") == "tool_use"), None)
        if not bloque:
            raise LLMError("El modelo no devolvió la herramienta estructurada.")
        u = data.get("usage") or {}
        return bloque["input"], {"entrada": u.get("input_tokens"), "salida": u.get("output_tokens")}


# ------------------------------------------------------------------ Evaluador heurístico (mock)
_STOP = set("para como con sobre entre desde donde cuando cual cuales este esta estos estas que del las los una unos unas por sus muy mas más ser son fue tiene tienen hace hacer debe deben cada todo toda todos todas otro otra parte trabajo estudiante nivel criterio forma manera clara claro bien".split())


def _palabras_clave(texto: str) -> list[str]:
    return [w for w in dict.fromkeys(normalizar(texto).split()) if len(w) > 4 and w not in _STOP]


def _oraciones(paginas: list[str]) -> list[tuple[int, str]]:
    out = []
    for n, p in enumerate(paginas, start=1):
        for o in re.split(r"(?<=[.!?])\s+|\n{2,}", p):
            o = " ".join(o.split())
            if 40 <= len(o) <= 400 and not o.lower().startswith(("informe:", "referencias")):
                out.append((n, o))
    return out


class MockProveedor(Proveedor):
    """Determinista: misma entrada → misma salida. Elige niveles por cobertura de conceptos
    de la rúbrica en el informe y el código, y cita oraciones reales del material."""

    def _llamar(self, sistema, mensajes, schema, nombre, contexto):
        if nombre != "registrar_evaluacion":
            raise LLMError("El proveedor 'mock' solo evalúa trabajos; para extraer rúbricas desde documentos configure un modelo real o use JSON/formulario.")
        rub = contexto["rubrica"]
        oraciones = _oraciones(contexto.get("paginas", []))
        codigo: dict[str, list[str]] = contexto.get("codigo", {})
        texto_total = normalizar(" ".join(contexto.get("paginas", [])) + " " + " ".join(" ".join(v) for v in codigo.values()))
        palabras_total = set(texto_total.split())
        criterios, fortalezas, vacios, actividades = [], [], [], []
        for cr in rub["criterios"]:
            if cr.get("fuente", "llm") != "llm":
                continue
            kws = _palabras_clave(cr["nombre"] + " " + cr.get("descripcion", "") + " " + " ".join(n["descriptor"] for n in cr["niveles"]))
            presentes = [k for k in kws if k in palabras_total or any(p.startswith(k[:6]) for p in palabras_total if len(k) > 6)]
            cobertura = min(1.0, len(presentes) / max(4, 0.35 * len(kws))) if kws else 0.0
            niveles = cr["niveles"]
            nivel = niveles[round(cobertura * (len(niveles) - 1))]
            puntuadas = sorted(
                ((sum(1 for k in presentes if k in normalizar(o)), -n, o, n) for n, o in oraciones),
                reverse=True,
            )
            evidencias = [{"fuente": "informe", "cita": o[:300], "ubicacion": f"p. {n}"} for c, _, o, n in puntuadas[:2] if c > 0]
            if codigo and re.search(r"codig|implement|prueba|funci|program|agente|script", normalizar(cr["nombre"] + cr.get("descripcion", ""))):
                for archivo, lineas in sorted(codigo.items()):
                    linea = next((i for i, ln in enumerate(lineas) if ln.strip().startswith(("def ", "class "))), None)
                    if linea is not None:
                        evidencias.append({"fuente": "codigo", "cita": lineas[linea].strip(), "ubicacion": f"{archivo}:{linea + 1}"})
                        break
            if not evidencias:
                nivel = niveles[0]
            just = (
                f"Se encontraron {len(presentes)} de {len(kws)} conceptos clave del criterio en el material "
                f"({', '.join(presentes[:5]) or 'ninguno'}). Esto corresponde al descriptor del nivel «{nivel['nombre']}»."
            )
            criterios.append({"criterio_id": cr["id"], "nivel_id": nivel["id"], "justificacion": just, "evidencias": evidencias[:3]})
            if cobertura >= 0.66:
                fortalezas.append(f"{cr['nombre']}: el trabajo aborda la mayoría de los aspectos esperados.")
            else:
                faltan = [k for k in kws if k not in presentes][:4]
                vacios.append(f"{cr['nombre']}: faltan o están poco desarrollados aspectos como {', '.join(faltan) or 'los descritos en la rúbrica'}.")
                actividades.append({
                    "titulo": f"Refuerzo: {cr['nombre']}"[:150],
                    "descripcion": f"Revise el descriptor del nivel superior y agregue evidencia explícita sobre {', '.join(faltan[:3]) or 'este criterio'} en el informe y el código.",
                    "competencia_id": cr["competencia_id"],
                })
        pr = contexto.get("pruebas") or {}
        if pr.get("ejecutadas") and pr.get("total"):
            (fortalezas if pr.get("tasa_exito", 0) >= 80 else vacios).append(
                f"Pruebas unitarias: {pr.get('aprobadas')} de {pr.get('total')} aprobadas ({pr.get('tasa_exito')} %)."
            )
        if not fortalezas:
            fortalezas.append("El trabajo fue entregado completo (informe y código) y es legible.")
        return {
            "criterios": criterios,
            "aprendizajes_demostrados": [f"Aplicación de: {c['nombre']}" for c in rub["criterios"] if c.get("fuente", "llm") == "llm"][:5],
            "fortalezas": fortalezas[:6],
            "vacios": vacios[:6],
            "retroalimentacion": (
                "Esta valoración la generó el evaluador heurístico de demostración (sin IA), que mide la presencia de los conceptos de la rúbrica "
                "en tu informe y tu código y cita fragmentos reales como evidencia. "
                + ("Tus puntos más sólidos: " + "; ".join(f.split(':')[0] for f in fortalezas[:3]) + ". " if fortalezas else "")
                + ("Prioriza mejorar: " + "; ".join(v.split(':')[0] for v in vacios[:3]) + "." if vacios else "")
            ),
            "recomendaciones": [
                {"accion": v.split(":")[0] + ": profundizar", "como": "Agrega una sección con evidencia (resultados, capturas, fragmentos de código) que demuestre este punto según el nivel superior de la rúbrica."}
                for v in vacios[:4]
            ] or [{"accion": "Mantener la calidad de la documentación", "como": "Conserva la trazabilidad entre lo que afirmas en el informe y lo que hace el código."}],
            "actividades_fortalecimiento": actividades[:5],
        }, {"entrada": len(mensajes[0]["content"]) // 4, "salida": 0}


PROVEEDORES = {"mock": MockProveedor, "ollama": OllamaProveedor, "gemini": GeminiProveedor, "openai": OpenAIProveedor, "anthropic": AnthropicProveedor}


def crear_proveedor(cfg: ConfigModelo) -> Proveedor:
    cls = PROVEEDORES.get(cfg.proveedor)
    if not cls:
        raise LLMError(f"Proveedor desconocido: {cfg.proveedor}")
    return cls(cfg)
