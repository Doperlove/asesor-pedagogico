"""Cálculo determinista de la nota (0,0–5,0). El LLM nunca calcula la nota."""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from .rubrics import Criterio, RubricaSchema


def redondear(nota: float, decimales: int = 1) -> float:
    q = Decimal(1).scaleb(-decimales)
    return float(Decimal(str(nota)).quantize(q, rounding=ROUND_HALF_UP))


def nivel_por_metrica(criterio: Criterio, metrica: float) -> str:
    """Para criterios objetivos: el nivel más alto cuyo umbral_min ≤ métrica."""
    elegido = criterio.niveles[0].id
    for n in criterio.niveles:
        if n.umbral_min is not None and metrica >= n.umbral_min:
            elegido = n.id
    return elegido


def calcular_nota(rubrica: RubricaSchema, niveles: dict[str, str]) -> dict:
    """niveles: criterio_id -> nivel_id. Devuelve detalle y nota redondeada.

    nota = Σ (peso_i / 100) × puntaje(nivel_i)
    """
    detalle = []
    total = Decimal("0")
    for cr in rubrica.criterios:
        nivel_id = niveles.get(cr.id)
        nivel = next((n for n in cr.niveles if n.id == nivel_id), None)
        if nivel is None:
            raise ValueError(f"Falta nivel válido para el criterio {cr.id}")
        aporte = Decimal(str(cr.peso)) / Decimal(100) * Decimal(str(nivel.puntaje))
        total += aporte
        detalle.append(
            {
                "criterio_id": cr.id,
                "nivel_id": nivel.id,
                "puntaje": nivel.puntaje,
                "peso": cr.peso,
                "aporte": float(aporte),
            }
        )
    nota = min(5.0, max(0.0, float(total)))
    return {"nota": redondear(nota), "nota_sin_redondeo": float(total), "detalle": detalle}
