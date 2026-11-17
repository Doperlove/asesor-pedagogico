"""Comprobaciones objetivas del código: análisis estático (ruff + métricas) y pruebas unitarias en sandbox."""
from __future__ import annotations

import ast
import json
import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

import defusedxml.ElementTree as ET  # el XML lo genera código no confiable

from . import sandbox

RUFF_SELECT = "E,F,W,B,C90,PLE,PLW,S"  # estilo, errores, bugs, complejidad, pylint (errores/avisos), seguridad (bandit)
RUFF_IGNORE = "S101,E501"  # assert en pruebas y longitud de línea no se penalizan


def _ruff_bin() -> list[str] | None:
    if shutil.which("ruff"):
        return ["ruff"]
    try:
        import ruff  # noqa: F401

        return [sys.executable, "-m", "ruff"]
    except ImportError:
        return None


def metricas_basicas(path: Path) -> dict:
    py = [f for f in path.rglob("*.py") if f.is_file()]
    lineas = 0
    funciones = clases = docstrings = 0
    errores_sintaxis = []
    for f in py:
        try:
            src = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lineas += sum(1 for ln in src.splitlines() if ln.strip() and not ln.strip().startswith("#"))
        try:
            tree = ast.parse(src)
        except SyntaxError as exc:
            errores_sintaxis.append(f"{f.relative_to(path)}:{exc.lineno}: {exc.msg}")
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                funciones += 1
                if ast.get_docstring(node):
                    docstrings += 1
            elif isinstance(node, ast.ClassDef):
                clases += 1
    pruebas = [f for f in py if f.name.startswith("test_") or f.name.endswith("_test.py")]
    lenguajes = Counter(f.suffix.lower() for f in path.rglob("*") if f.is_file() and f.suffix)
    return {
        "archivos_python": len(py),
        "lineas_codigo": lineas,
        "funciones": funciones,
        "clases": clases,
        "funciones_documentadas_pct": round(100 * docstrings / funciones, 1) if funciones else 0.0,
        "archivos_prueba": len(pruebas),
        "tiene_readme": any(p.name.lower().startswith("readme") for p in path.iterdir()),
        "tiene_dependencias": any((path / n).exists() for n in ("requirements.txt", "pyproject.toml", "environment.yml", "package.json", "pom.xml")),
        "errores_sintaxis": errores_sintaxis,
        "extensiones": dict(lenguajes.most_common(8)),
    }


def analisis_estatico(path: Path) -> dict:
    """ruff no ejecuta el código, solo lo lee, por eso puede correr fuera del sandbox."""
    met = metricas_basicas(path)
    resultado: dict = {"metricas": met, "herramienta": "ruff", "reglas": RUFF_SELECT, "ignoradas": RUFF_IGNORE}
    if met["archivos_python"] == 0:
        resultado.update(
            disponible=False,
            motivo="No hay archivos Python; solo se reportan métricas básicas.",
            hallazgos=0, por_regla={}, muestras=[], calidad=None,
        )
        return resultado
    bin_ = _ruff_bin()
    if not bin_:
        resultado.update(disponible=False, motivo="ruff no está instalado en el servidor.", hallazgos=0, por_regla={}, muestras=[], calidad=None)
        return resultado
    proc = subprocess.run(
        [*bin_, "check", "--no-cache", "--isolated", "--select", RUFF_SELECT, "--ignore", RUFF_IGNORE, "--output-format", "json", "--exit-zero", "."],
        cwd=path, capture_output=True, text=True, timeout=120,
    )
    try:
        items = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        items = []
    por_regla = Counter(i.get("code") or "?" for i in items)
    severos = [i for i in items if (i.get("code") or "").startswith(("F", "E9", "S", "B"))]
    loc = max(met["lineas_codigo"], 1)
    densidad = len(items) / loc * 100  # hallazgos por cada 100 líneas
    # Métrica 0–100: penaliza densidad de hallazgos y más fuerte los severos y errores de sintaxis
    calidad = 100 - min(50, densidad * 2.5) - min(30, len(severos) / loc * 100 * 5) - min(40, 20 * len(met["errores_sintaxis"]))
    resultado.update(
        disponible=True,
        hallazgos=len(items),
        severos=len(severos),
        densidad_por_100_lineas=round(densidad, 2),
        por_regla=dict(por_regla.most_common(15)),
        muestras=[
            {
                "archivo": i.get("filename", "").replace(str(path) + "/", ""),
                "linea": (i.get("location") or {}).get("row"),
                "codigo": i.get("code"),
                "mensaje": i.get("message"),
            }
            for i in (severos + [x for x in items if x not in severos])[:25]
        ],
        calidad=round(max(0.0, calidad), 1),
    )
    return resultado


def rutas_de_importacion(path: Path) -> list[str]:
    """Carpetas que el estudiante probablemente usaba como directorio de trabajo al correr pytest:
    la carpeta padre de cada `tests/` y cada carpeta con código Python junto a sus pruebas."""
    rutas: set[str] = set()
    for f in path.rglob("test*.py"):
        if any(p in {"__pycache__", ".venv", "venv"} for p in f.parts):
            continue
        carpeta = f.parent
        if carpeta.name in {"tests", "test"}:
            carpeta = carpeta.parent
        rel = carpeta.relative_to(path)
        if str(rel) != ".":
            rutas.add(str(rel).replace("\\", "/"))
    return sorted(rutas)[:20]


def ejecutar_pruebas(path: Path) -> tuple[dict, dict]:
    """Corre pytest dentro del sandbox. Devuelve (resumen de pruebas, info del sandbox)."""
    met = metricas_basicas(path)
    if met["archivos_python"] == 0:
        return {"ejecutadas": False, "motivo": "No hay código Python para probar.", "tasa_exito": 0.0}, {}
    cmd = ["python", "-m", "pytest", "-q", "--tb=short", "-p", "no:cacheprovider",
           "--junitxml=_reporte_pruebas.xml", "-o", "addopts=", "."]
    res, trabajo = sandbox.ejecutar(path, cmd, rutas_python=rutas_de_importacion(path))
    try:
        reporte = trabajo / "work" / "_reporte_pruebas.xml"
        resumen: dict = {"ejecutadas": True, "comando": " ".join(cmd), "salida": res.salida[-6000:]}
        if reporte.exists():
            root = ET.parse(reporte).getroot()
            suite = root if root.tag == "testsuite" else root.find("testsuite")
            total = int(suite.get("tests", 0)) if suite is not None else 0
            fallos = int(suite.get("failures", 0)) if suite is not None else 0
            errores = int(suite.get("errors", 0)) if suite is not None else 0
            omitidas = int(suite.get("skipped", 0)) if suite is not None else 0
            casos = []
            for tc in root.iter("testcase"):
                estado = "aprobada"
                if tc.find("failure") is not None:
                    estado = "fallida"
                elif tc.find("error") is not None:
                    estado = "error"
                elif tc.find("skipped") is not None:
                    estado = "omitida"
                casos.append({"nombre": f"{tc.get('classname', '')}::{tc.get('name', '')}", "estado": estado, "tiempo_s": float(tc.get("time", 0) or 0)})
            aprobadas = total - fallos - errores - omitidas
            efectivas = total - omitidas
            resumen.update(
                total=total, aprobadas=aprobadas, fallidas=fallos, errores=errores, omitidas=omitidas,
                tasa_exito=round(100 * aprobadas / efectivas, 1) if efectivas else 0.0,
                casos=casos[:200],
            )
            if total == 0:
                resumen["motivo"] = "pytest no encontró pruebas (archivos test_*.py)."
        else:
            resumen.update(total=0, aprobadas=0, fallidas=0, errores=0, omitidas=0, tasa_exito=0.0,
                           motivo="No se generó reporte; la ejecución falló o se agotó el tiempo.")
        # Contraste: el reporte XML lo escribe un proceso que ejecuta código del estudiante; se compara con la consola
        m = re.search(r"(\d+) passed", res.salida or "")
        aprob_consola = int(m.group(1)) if m else 0
        if resumen.get("total") and aprob_consola != resumen.get("aprobadas"):
            resumen["inconsistente"] = True
            resumen["motivo"] = (f"El reporte XML ({resumen.get('aprobadas')} aprobadas) no coincide con la consola ({aprob_consola}). "
                                 "Posible manipulación: se toma el menor valor.")
            resumen["aprobadas"] = min(aprob_consola, resumen.get("aprobadas", 0))
            efectivas = resumen["total"] - resumen.get("omitidas", 0)
            resumen["tasa_exito"] = round(100 * resumen["aprobadas"] / efectivas, 1) if efectivas else 0.0
        if res.tiempo_agotado:
            resumen["motivo"] = f"Tiempo agotado ({res.limites['timeout_s']} s). Se detuvo la ejecución."
            resumen["tasa_exito"] = 0.0
        return resumen, res.as_dict() | {"salida": None}
    finally:
        shutil.rmtree(trabajo, ignore_errors=True)
