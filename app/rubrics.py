"""Rúbrica parametrizada: esquema, validación de coherencia y versionado.

Formato (JSON):
{
  "nombre": "Rúbrica Lab 3",
  "competencias": [{"id": "RA1", "nombre": "...", "descripcion": "..."}],
  "criterios": [
    {
      "id": "CR1", "competencia_id": "RA1", "nombre": "...", "descripcion": "...",
      "peso": 30,                       # en %, la suma debe dar 100
      "fuente": "llm",                  # llm | pruebas | analisis_estatico
      "niveles": [
        {"id": "N1", "nombre": "Insuficiente", "puntaje": 1.0, "descriptor": "...", "umbral_min": null},
        ...
      ]
    }
  ]
}

`puntaje` está en la escala 0,0–5,0. La nota = Σ (peso/100 × puntaje del nivel elegido).
Para criterios objetivos (pruebas / analisis_estatico) cada nivel declara `umbral_min`
(0–100) y el backend elige el nivel según la métrica medida, sin intervención del LLM.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

FUENTES = ("llm", "pruebas", "analisis_estatico")
_ID_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,30}$")


class Nivel(BaseModel):
    id: str
    nombre: str
    puntaje: float
    descriptor: str = ""
    umbral_min: float | None = None


class Criterio(BaseModel):
    id: str
    competencia_id: str
    nombre: str
    descripcion: str = ""
    peso: float
    fuente: Literal["llm", "pruebas", "analisis_estatico"] = "llm"
    niveles: list[Nivel] = Field(default_factory=list)


class Competencia(BaseModel):
    id: str
    nombre: str
    descripcion: str = ""


class RubricaSchema(BaseModel):
    nombre: str
    descripcion: str = ""
    competencias: list[Competencia] = Field(default_factory=list)
    criterios: list[Criterio] = Field(default_factory=list)


class ResultadoValidacion(BaseModel):
    valida: bool
    errores: list[str]
    advertencias: list[str]
    rubrica: RubricaSchema | None = None


def validar_rubrica(data: dict | str, catalogo_competencias: set[str] | None = None) -> ResultadoValidacion:
    """Valida estructura y coherencia. Devuelve todos los errores encontrados, no solo el primero."""
    errores: list[str] = []
    adv: list[str] = []

    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError as exc:
            return ResultadoValidacion(valida=False, errores=[f"JSON inválido: {exc.msg} (línea {exc.lineno})"], advertencias=[])

    try:
        rub = RubricaSchema.model_validate(data)
    except ValidationError as exc:
        for err in exc.errors():
            loc = " → ".join(str(p) for p in err["loc"])
            errores.append(f"Campo {loc}: {err['msg']}")
        return ResultadoValidacion(valida=False, errores=errores, advertencias=[])

    if not rub.nombre.strip():
        errores.append("La rúbrica no tiene nombre.")
    if not rub.competencias:
        errores.append("Debe declarar al menos una competencia.")
    if not rub.criterios:
        errores.append("Debe declarar al menos un criterio.")

    comp_ids = [c.id for c in rub.competencias]
    for cid in comp_ids:
        if not _ID_RE.match(cid):
            errores.append(f"Id de competencia inválido: '{cid}' (use letras, números, guion o punto).")
    for dup in {c for c in comp_ids if comp_ids.count(c) > 1}:
        errores.append(f"Competencia duplicada: {dup}.")
    for c in rub.competencias:
        if not c.nombre.strip():
            errores.append(f"La competencia {c.id} no tiene nombre.")
        if catalogo_competencias is not None and c.id not in catalogo_competencias:
            adv.append(f"La competencia {c.id} no está en el catálogo del curso; no se consolidará con otros laboratorios.")

    crit_ids = [c.id for c in rub.criterios]
    for dup in {c for c in crit_ids if crit_ids.count(c) > 1}:
        errores.append(f"Criterio duplicado: {dup}.")

    total = 0.0
    usadas: set[str] = set()
    for cr in rub.criterios:
        etiqueta = f"Criterio {cr.id} ({cr.nombre or 'sin nombre'})"
        if not _ID_RE.match(cr.id):
            errores.append(f"Id de criterio inválido: '{cr.id}'.")
        if not cr.nombre.strip():
            errores.append(f"{etiqueta}: falta el nombre.")
        if cr.competencia_id not in comp_ids:
            errores.append(f"{etiqueta}: la competencia '{cr.competencia_id}' no existe en la rúbrica.")
        usadas.add(cr.competencia_id)
        if cr.peso <= 0:
            errores.append(f"{etiqueta}: el peso debe ser mayor que 0 (tiene {cr.peso}).")
        total += cr.peso

        if len(cr.niveles) < 2:
            errores.append(f"{etiqueta}: necesita al menos 2 niveles de desempeño.")
            continue
        niv_ids = [n.id for n in cr.niveles]
        for dup in {n for n in niv_ids if niv_ids.count(n) > 1}:
            errores.append(f"{etiqueta}: nivel duplicado {dup}.")
        puntajes = [n.puntaje for n in cr.niveles]
        for n in cr.niveles:
            if not 0.0 <= n.puntaje <= 5.0:
                errores.append(f"{etiqueta}: el nivel {n.id} tiene puntaje {n.puntaje}, fuera de 0,0–5,0.")
            if not n.descriptor.strip():
                errores.append(f"{etiqueta}: el nivel {n.id} no tiene descriptor de desempeño.")
            if not n.nombre.strip():
                errores.append(f"{etiqueta}: el nivel {n.id} no tiene nombre.")
        if len(set(puntajes)) != len(puntajes):
            errores.append(f"{etiqueta}: dos niveles tienen el mismo puntaje; los niveles deben distinguirse.")
        if puntajes != sorted(puntajes):
            errores.append(f"{etiqueta}: los niveles deben ir de menor a mayor puntaje.")
        if max(puntajes) < 5.0:
            adv.append(f"{etiqueta}: el nivel más alto vale {max(puntajes)}; con este criterio no se puede llegar a 5,0.")
        descs = [n.descriptor.strip().lower() for n in cr.niveles if n.descriptor.strip()]
        if len(set(descs)) != len(descs):
            errores.append(f"{etiqueta}: hay descriptores idénticos en niveles distintos.")

        if cr.fuente != "llm":
            umbrales = [n.umbral_min for n in cr.niveles]
            if any(u is None for u in umbrales):
                errores.append(f"{etiqueta}: los criterios objetivos ({cr.fuente}) requieren 'umbral_min' (0–100) en cada nivel.")
            else:
                if any(not 0 <= u <= 100 for u in umbrales):  # type: ignore[operator]
                    errores.append(f"{etiqueta}: 'umbral_min' debe estar entre 0 y 100.")
                if umbrales != sorted(umbrales):  # type: ignore[type-var]
                    errores.append(f"{etiqueta}: los umbrales deben crecer con el puntaje.")
                if umbrales[0] != 0:
                    errores.append(f"{etiqueta}: el nivel más bajo debe tener umbral_min = 0 para cubrir cualquier resultado.")

    if rub.criterios and abs(total - 100.0) > 0.01:
        errores.append(f"Los pesos suman {round(total, 2)} %; deben sumar exactamente 100 %.")
    for c in comp_ids:
        if c not in usadas:
            adv.append(f"La competencia {c} no tiene criterios asociados.")

    return ResultadoValidacion(valida=not errores, errores=errores, advertencias=adv, rubrica=rub)


def rubrica_sha256(contenido: dict) -> str:
    canon = json.dumps(contenido, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def rubrica_json_schema() -> dict:
    return RubricaSchema.model_json_schema()
