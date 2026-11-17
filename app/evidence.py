"""Verificación de evidencias: comprueba que cada cita del LLM exista realmente en el informe,
el código o la salida de pruebas, y corrige su ubicación (página o archivo:línea)."""
from __future__ import annotations

import re
import unicodedata

PATRONES_INYECCION = [
    r"ignora(r)? (todas )?(las )?instrucciones",
    r"ignore (all |the )?(previous |prior )?instructions",
    r"asigna(me)? (una )?(nota|calificacion) (de )?5",
    r"give (me |this )?(a |the )?(maximum|full|perfect) (score|grade)",
    r"eres un evaluador que siempre",
    r"system prompt",
    r"califica(lo)? con 5",
]


def normalizar(texto: str) -> str:
    t = unicodedata.normalize("NFKC", texto).lower()
    t = "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")
    t = re.sub(r"[“”«»\"'`´]", "", t)
    t = re.sub(r"[^\w\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _trigramas(palabras: list[str]) -> set[tuple[str, ...]]:
    return {tuple(palabras[i:i + 3]) for i in range(max(0, len(palabras) - 2))}


class Verificador:
    def __init__(self, paginas: list[str], codigo: dict[str, list[str]], salida_pruebas: str = "") -> None:
        self.paginas = [(i + 1, normalizar(p)) for i, p in enumerate(paginas)]
        self.codigo = codigo
        self.codigo_norm = {f: [normalizar(ln) for ln in lineas] for f, lineas in codigo.items()}
        self.pruebas = normalizar(salida_pruebas)
        self._tri_paginas = [(n, _trigramas(t.split())) for n, t in self.paginas]

    def _buscar_informe(self, cita: str) -> tuple[str, str | None]:
        for n, texto in self.paginas:
            if cita in texto:
                return "exacta", f"p. {n}"
        palabras = cita.split()
        tri = _trigramas(palabras)
        if len(tri) >= 3:
            mejor, pag = 0.0, None
            for n, tp in self._tri_paginas:
                cobertura = len(tri & tp) / len(tri)
                if cobertura > mejor:
                    mejor, pag = cobertura, n
            if mejor >= 0.8:
                return "aproximada", f"p. {pag}"
        return "no_encontrada", None

    def _buscar_codigo(self, cita: str) -> tuple[str, str | None]:
        cita_lineas = [ln for ln in (normalizar(x) for x in cita.splitlines()) if ln]
        if not cita_lineas:
            return "no_encontrada", None
        primera = cita_lineas[0]
        mejor: tuple[float, str | None] = (0.0, None)
        for archivo, lineas in self.codigo_norm.items():
            for i, ln in enumerate(lineas):
                if primera not in ln:
                    continue
                if len(cita_lineas) == 1:
                    return "exacta", f"{archivo}:{i + 1}"
                ventana = lineas[i:i + len(cita_lineas) * 3 + 5]
                pos, hallados = 0, 1
                for c in cita_lineas[1:]:
                    for k in range(pos + 1, len(ventana)):
                        if c in ventana[k]:
                            pos, hallados = k, hallados + 1
                            break
                cobertura = hallados / len(cita_lineas)
                if cobertura == 1.0:
                    return "exacta", f"{archivo}:{i + 1}"
                if cobertura > mejor[0]:
                    mejor = (cobertura, f"{archivo}:{i + 1}")
        if mejor[0] >= 0.7:
            return "aproximada", mejor[1]
        # La cita puede venir sin saltos de línea: buscar en el texto unido
        unida = " ".join(cita_lineas)
        for archivo, lineas in self.codigo_norm.items():
            acumulado, inicios = 0, []
            for ln in lineas:
                inicios.append(acumulado)
                acumulado += len(ln) + 1
            texto = " ".join(lineas)
            idx = texto.find(unida)
            if idx >= 0:
                linea = max(k for k, ini in enumerate(inicios) if ini <= idx) + 1
                return "aproximada", f"{archivo}:{linea}"
        return "no_encontrada", None

    def verificar(self, fuente: str, cita: str) -> dict:
        n = normalizar(cita)
        if len(n) < 8:
            return {"estado": "no_encontrada", "ubicacion_verificada": None, "motivo": "Cita demasiado corta para verificarse."}
        orden = {"informe": ["informe", "codigo"], "codigo": ["codigo", "informe"], "pruebas": ["pruebas", "codigo"]}.get(fuente, ["informe", "codigo"])
        for f in orden:
            if f == "informe":
                estado, ubic = self._buscar_informe(n)
            elif f == "codigo":
                estado, ubic = self._buscar_codigo(cita)
            else:
                estado, ubic = ("exacta", "salida de pruebas") if n in self.pruebas else ("no_encontrada", None)
            if estado != "no_encontrada":
                return {"estado": estado, "ubicacion_verificada": ubic, "fuente_verificada": f}
        return {"estado": "no_encontrada", "ubicacion_verificada": None, "motivo": "La cita no aparece en el material entregado."}


def detectar_inyeccion(*textos: str) -> list[str]:
    hallazgos = []
    for t in textos:
        tn = normalizar(t)
        for p in PATRONES_INYECCION:
            m = re.search(p, tn)
            if m:
                hallazgos.append(m.group(0))
    return sorted(set(hallazgos))
