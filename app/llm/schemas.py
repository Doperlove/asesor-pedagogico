"""Esquemas de salida del LLM (Pydantic → JSON Schema). El LLM solo elige niveles y cita
evidencias; nunca devuelve una nota numérica."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "eval-1.2"


class Evidencia(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fuente: Literal["informe", "codigo", "pruebas"]
    cita: str = Field(min_length=8, max_length=600, description="Fragmento copiado textualmente del material entregado.")
    ubicacion: str = Field(default="", max_length=120, description="Página del informe o archivo:línea.")


class CriterioEvaluado(BaseModel):
    model_config = ConfigDict(extra="forbid")
    criterio_id: str
    nivel_id: str = Field(description="Id de uno de los niveles definidos para este criterio.")
    justificacion: str = Field(min_length=20, max_length=1500)
    evidencias: list[Evidencia] = Field(default_factory=list, max_length=5)


class Recomendacion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    accion: str = Field(min_length=5, max_length=400)
    como: str = Field(min_length=5, max_length=600)


class Actividad(BaseModel):
    model_config = ConfigDict(extra="forbid")
    titulo: str = Field(min_length=3, max_length=160)
    descripcion: str = Field(min_length=10, max_length=600)
    competencia_id: str


class SalidaEvaluacion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    criterios: list[CriterioEvaluado]
    aprendizajes_demostrados: list[str] = Field(min_length=1, max_length=8)
    fortalezas: list[str] = Field(min_length=1, max_length=8)
    vacios: list[str] = Field(default_factory=list, max_length=8)
    retroalimentacion: str = Field(min_length=40, max_length=2500)
    recomendaciones: list[Recomendacion] = Field(min_length=1, max_length=6)
    actividades_fortalecimiento: list[Actividad] = Field(default_factory=list, max_length=6)


class SalidaRubrica(BaseModel):
    """Para extraer una rúbrica desde un documento del docente."""

    model_config = ConfigDict(extra="allow")
    nombre: str
    descripcion: str = ""
    competencias: list[dict]
    criterios: list[dict]


def schema_evaluacion() -> dict:
    return SalidaEvaluacion.model_json_schema()


def _inline_refs(schema: dict) -> dict:
    """Algunos proveedores no aceptan $defs/$ref; se expanden en línea."""
    defs = schema.get("$defs", {})

    def walk(node):
        if isinstance(node, dict):
            if "$ref" in node:
                name = node["$ref"].split("/")[-1]
                return walk(dict(defs[name]))
            return {k: walk(v) for k, v in node.items() if k != "$defs"}
        if isinstance(node, list):
            return [walk(x) for x in node]
        return node

    return walk(schema)


def schema_plano(model: type[BaseModel]) -> dict:
    return _inline_refs(model.model_json_schema())
