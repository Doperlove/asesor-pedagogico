"""Conector de modelos: formato de las peticiones y manejo de límites del plan gratuito (sin red real)."""
import json

import httpx
import pytest

from app.llm import providers as pv


class FakeResp:
    def __init__(self, status: int, body: dict, headers: dict | None = None):
        self.status_code = status
        self._body = body
        self.headers = headers or {}
        self.text = json.dumps(body)

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=self)


def _cfg(prov: str) -> pv.ConfigModelo:
    d = pv.DEFAULTS[prov]
    return pv.ConfigModelo(proveedor=prov, modelo=d["model"], base_url=d["base_url"])


def _ok(contenido: dict) -> FakeResp:
    return FakeResp(200, {"choices": [{"message": {"content": json.dumps(contenido)}}], "usage": {"prompt_tokens": 10, "completion_tokens": 5}})


def test_gemini_formato_de_peticion(monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "gemini_api_key", "clave-falsa")
    vistos = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        vistos.update(url=url, payload=json, headers=headers)
        return _ok({"ok": True})

    monkeypatch.setattr(httpx, "post", fake_post)
    r = pv.crear_proveedor(_cfg("gemini")).generar("sis", [{"role": "user", "content": "hola"}], {"type": "object"}, "probar")
    assert r.datos == {"ok": True}
    assert vistos["url"] == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    assert vistos["headers"]["Authorization"] == "Bearer clave-falsa"
    assert "seed" not in vistos["payload"]
    assert vistos["payload"]["response_format"] == {"type": "json_object"}
    assert vistos["payload"]["temperature"] == 0.0


def test_gemini_sin_clave(monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "gemini_api_key", None)
    with pytest.raises(pv.LLMError, match="GEMINI_API_KEY"):
        pv.crear_proveedor(_cfg("gemini")).generar("s", [{"role": "user", "content": "x"}], {}, "probar")


def test_reintenta_ante_limite_429(monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "gemini_api_key", "k")
    respuestas = iter([FakeResp(429, {"error": "quota"}, {"retry-after": "1"}), _ok({"ok": True})])
    monkeypatch.setattr(httpx, "post", lambda *a, **k: next(respuestas))
    esperas = []
    monkeypatch.setattr(pv.time, "sleep", esperas.append)
    r = pv.crear_proveedor(_cfg("gemini")).generar("s", [{"role": "user", "content": "x"}], {}, "probar")
    assert r.datos == {"ok": True} and esperas == [1.0]


def test_429_persistente_da_mensaje_claro(monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "gemini_api_key", "k")
    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResp(429, {"error": "quota"}))
    monkeypatch.setattr(pv.time, "sleep", lambda s: None)
    with pytest.raises(pv.LLMError, match="plan gratuito"):
        pv.crear_proveedor(_cfg("gemini")).generar("s", [{"role": "user", "content": "x"}], {}, "probar")


def test_ollama_envia_json_schema(monkeypatch):
    vistos = {}

    def fake_post(url, json=None, timeout=None, **k):
        vistos.update(url=url, payload=json)
        return FakeResp(200, {"message": {"content": '{"ok": true}'}, "prompt_eval_count": 3, "eval_count": 2})

    monkeypatch.setattr(httpx, "post", fake_post)
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}}
    r = pv.crear_proveedor(_cfg("ollama")).generar("s", [{"role": "user", "content": "x"}], schema, "probar")
    assert r.datos == {"ok": True}
    assert vistos["payload"]["format"] == schema
    assert vistos["payload"]["options"]["temperature"] == 0.0 and vistos["payload"]["options"]["seed"] == 42


def test_json_envuelto_en_markdown():
    assert pv._extraer_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert pv._extraer_json('Claro, aquí está: {"a": 2} saludos') == {"a": 2}
