"""Contenido de demostración: rúbricas por laboratorio, informes y código de ejemplo."""
from __future__ import annotations

import io
import zipfile

COMPETENCIAS = [
    ("RA1", "Analizar fundamentos y modelos de IA", "Explica conceptos, familias de modelos y criterios de selección."),
    ("RA2", "Diseñar interacciones verificables", "Diseña prompts, esquemas y validaciones que hacen verificable la salida de un modelo."),
    ("RA3", "Integrar IA en el ciclo del software", "Incorpora modelos y asistentes de IA en el desarrollo, las pruebas y el despliegue."),
    ("RA4", "Construir con una fábrica aumentada", "Construye productos con agentes, herramientas y supervisión humana."),
]

NIVELES = [("N1", "Insuficiente", 1.5), ("N2", "Básico", 3.0), ("N3", "Competente", 4.0), ("N4", "Destacado", 5.0)]


def criterio(cid: str, comp: str, nombre: str, peso: float, desc: str, descriptores: list[str], fuente: str = "llm", umbrales=None) -> dict:
    niveles = []
    for i, (nid, nnom, punt) in enumerate(NIVELES):
        n = {"id": nid, "nombre": nnom, "puntaje": punt, "descriptor": descriptores[i]}
        if fuente != "llm":
            n["umbral_min"] = umbrales[i]
        niveles.append(n)
    return {"id": cid, "competencia_id": comp, "nombre": nombre, "descripcion": desc, "peso": peso, "fuente": fuente, "niveles": niveles}


def comps(*ids: str) -> list[dict]:
    return [{"id": c, "nombre": n, "descripcion": d} for c, n, d in COMPETENCIAS if c in ids]


CRIT_PRUEBAS = lambda cid, comp, peso: criterio(  # noqa: E731
    cid, comp, "Pruebas unitarias del código", peso, "Medición automática: porcentaje de pruebas aprobadas en el sandbox.",
    ["Menos del 50 % de las pruebas pasan o no hay pruebas.", "Entre 50 % y 79 % de las pruebas pasan.",
     "Entre 80 % y 99 % de las pruebas pasan.", "El 100 % de las pruebas pasan."],
    fuente="pruebas", umbrales=[0, 50, 80, 100])

CRIT_ESTATICO = lambda cid, comp, peso: criterio(  # noqa: E731
    cid, comp, "Calidad estática del código", peso, "Medición automática con ruff: densidad de hallazgos de estilo, errores y seguridad.",
    ["Índice de calidad menor a 60: muchos errores o problemas de seguridad.", "Índice entre 60 y 79: hallazgos frecuentes.",
     "Índice entre 80 y 89: pocos hallazgos menores.", "Índice de 90 o más: código limpio."],
    fuente="analisis_estatico", umbrales=[0, 60, 80, 90])


def rubrica_harness(lab: str, foco: str) -> dict:
    return {
        "nombre": f"Rúbrica {lab}",
        "descripcion": f"Evalúa el laboratorio de harness: {foco}.",
        "competencias": comps("RA2", "RA3", "RA4"),
        "criterios": [
            criterio("CR1", "RA4", "Diseño del agente y del harness", 25,
                     "Arquitectura del agente: bucle de control, herramientas, memoria y supervisión humana.",
                     ["No describe la arquitectura del agente ni sus herramientas.",
                      "Describe el agente de forma general sin explicar el bucle de control ni las herramientas.",
                      "Explica el bucle de control, las herramientas y cómo se valida cada paso.",
                      "Justifica el diseño del agente, el bucle de control, las herramientas y la supervisión humana con evidencias y alternativas."]),
            criterio("CR2", "RA2", "Verificación de salidas del modelo", 20,
                     "Uso de esquemas, validaciones y comparación esperado vs obtenido.",
                     ["No verifica las salidas del modelo.", "Verifica manualmente algunos casos sin criterio explícito.",
                      "Valida las salidas con esquema o reglas y compara esperado contra obtenido.",
                      "Valida con esquema, reglas e integridad (hash) y documenta casos de fallo y su manejo."]),
            criterio("CR3", "RA3", "Documentación técnica y reflexión", 20,
                     "Informe claro con resultados, limitaciones y uso responsable de IA.",
                     ["Informe incompleto o sin resultados.", "Informe con resultados pero sin análisis ni limitaciones.",
                      "Informe claro con resultados, análisis y limitaciones.",
                      "Informe claro con resultados, análisis crítico, limitaciones, costos y uso responsable de la IA."]),
            CRIT_PRUEBAS("CR4", "RA3", 20),
            CRIT_ESTATICO("CR5", "RA3", 15),
        ],
    }


def rubrica_teorica(lab: str, tema: str, comp_principal: str = "RA1") -> dict:
    return {
        "nombre": f"Rúbrica {lab}",
        "descripcion": f"Trabajo de análisis: {tema}.",
        "competencias": comps(comp_principal, "RA3"),
        "criterios": [
            criterio("CR1", comp_principal, "Dominio de conceptos", 35, f"Precisión conceptual sobre {tema}.",
                     ["Conceptos ausentes o con errores graves.", "Conceptos correctos pero superficiales.",
                      "Conceptos correctos, relacionados entre sí y con ejemplos.", "Conceptos profundos, comparados críticamente y con fuentes académicas."]),
            criterio("CR2", comp_principal, "Análisis y argumentación", 30, "Calidad del análisis, comparación y criterio propio.",
                     ["Describe sin analizar.", "Analiza con argumentos débiles o sin evidencias.",
                      "Analiza con argumentos y evidencias del caso.", "Analiza críticamente, contrasta alternativas y concluye con criterio propio."]),
            criterio("CR3", "RA3", "Evidencia y fuentes", 20, "Uso de fuentes verificables y referencias.",
                     ["Sin fuentes.", "Fuentes escasas o no académicas.", "Fuentes pertinentes citadas en el texto.",
                      "Fuentes académicas pertinentes, citadas en APA y contrastadas."]),
            criterio("CR4", "RA3", "Claridad y presentación", 15, "Estructura, redacción y presentación.",
                     ["Desorganizado y difícil de leer.", "Estructura básica con problemas de redacción.",
                      "Bien estructurado y redactado.", "Excelente estructura, redacción precisa y apoyos visuales útiles."]),
        ],
    }


LABORATORIOS = [
    # (cohorte, nombre, descripcion, requiere_codigo, rubrica)
    (1, "Historia de la IA", "Video y documento sobre la evolución de la IA.", False, rubrica_teorica("Historia de la IA", "la evolución histórica de la IA")),
    (1, "Manizales resiliente: blueprint CUMANDAY", "Blueprint de solución con IA para un reto urbano.", False, rubrica_teorica("Blueprint CUMANDAY", "el diseño de una solución con IA para la ciudad", "RA4")),
    (1, "Ingeniero aumentado y modelos de código", "Comparación de asistentes y modelos de código.", True, rubrica_harness("Ingeniero aumentado", "uso de modelos de código en el ciclo de desarrollo")),
    (1, "Primer parcial: fundamentos de IA", "Cartografía de modelos, modelos locales y vibe coding.", True, rubrica_harness("Primer parcial", "modelos locales, vibe coding y series de tiempo")),
    (2, "Coloquio: observatorio de proyectos de IA", "Informe de observación de proyectos del coloquio.", False, rubrica_teorica("Coloquio", "el análisis crítico de proyectos de IA")),
    (2, "Harness 1: organizador con Python tradicional", "Línea base sin IA.", True, rubrica_harness("Harness 1", "organizador de archivos con Python tradicional")),
    (2, "Harness 2: agente con LLM en la nube", "Agente con modelo remoto.", True, rubrica_harness("Harness 2", "agente con LLM en la nube")),
    (2, "Harness 3: modelo local con Ollama", "Agente con modelo local.", True, rubrica_harness("Harness 3", "agente con modelo local en Ollama")),
    (2, "Harness 4: agente con DeepSeek Harness", "Agente completo con harness.", True, rubrica_harness("Harness 4", "agente completo con DeepSeek Harness")),
]


# ---------------------------------------------------------------- informes de ejemplo
INFORMES = {
    "Historia de la IA": [
        "Introducción. Este trabajo presenta la evolución histórica de la inteligencia artificial desde la lógica formal hasta los modelos de lenguaje actuales.",
        "En 1950 Alan Turing propuso el test de Turing como criterio para evaluar si una máquina puede exhibir comportamiento inteligente. En 1956 la conferencia de Dartmouth dio nombre al campo.",
        "Los sistemas expertos de los años ochenta codificaban conocimiento en reglas. Su limitación principal fue el costo de mantener la base de conocimiento.",
        "El aprendizaje profundo resurgió en 2012 cuando una red neuronal convolucional ganó ImageNet. En 2017 la arquitectura transformer permitió los grandes modelos de lenguaje.",
        "Conclusión. La historia de la IA alterna periodos de entusiasmo e inviernos; comprender los conceptos de cada etapa ayuda a evaluar críticamente las promesas actuales.",
        "Referencias: Russell, S. y Norvig, P. (2021). Artificial Intelligence: A Modern Approach. Pearson.",
    ],
    "Coloquio: observatorio de proyectos de IA": [
        "Introducción. Se observaron cuatro proyectos presentados en el coloquio y se clasificaron sus afirmaciones como confirmadas, declaradas, inferidas o no determinadas.",
        "Proyecto 1 usa OCR y un modelo local qwen2.5 para procesar documentos contables. Se confirmó la demostración en vivo y se infiere que no hay validación del esquema de salida.",
        "Proyecto 2 aplica aprendizaje supervisado para evaluar espacio público. El análisis compara su enfoque con alternativas de clasificación y discute el sesgo de los datos.",
        "Proyecto 4 no tiene un componente real de IA; el análisis crítico separa lo confirmado de lo declarado por los autores.",
        "Se contrastan los proyectos con fuentes académicas citadas en APA, por ejemplo Hevner et al. (2004) sobre Design Science Research.",
        "Conclusión. La principal brecha observada es la falta de evidencia verificable de las salidas de los modelos.",
    ],
    "Harness 1: organizador con Python tradicional": [
        "Introducción. Este laboratorio construye la línea base del harness: un organizador de archivos con Python tradicional, sin modelo de lenguaje.",
        "Diseño. El programa recorre una carpeta, clasifica cada archivo por extensión y lo mueve a una subcarpeta. El bucle de control es determinista y cada paso registra un log.",
        "Verificación. Se compara el resultado esperado contra el obtenido con pruebas unitarias y se valida la integridad de cada archivo con un hash SHA-256 antes y después de moverlo.",
        "Resultados. Las pruebas unitarias cubren clasificación, conflictos de nombres y carpetas vacías. Todas las pruebas pasan.",
        "Limitaciones. La clasificación solo usa la extensión; no entiende el contenido. Esto motiva los siguientes laboratorios con agentes y LLM.",
        "Uso responsable de IA. Se usó un asistente de codificación para generar pruebas iniciales que se revisaron manualmente.",
    ],
    "Harness 2: agente con LLM en la nube": [
        "Introducción. Se construye un agente que usa un LLM en la nube para clasificar archivos según su contenido.",
        "Diseño del agente. El bucle de control sigue el patrón ReAct: el modelo propone una acción, el harness la valida contra un esquema JSON y una persona aprueba los movimientos.",
        "Herramientas. El agente dispone de las herramientas listar_archivos, leer_resumen y mover_archivo. La memoria guarda las decisiones previas.",
        "Verificación de salidas. Cada respuesta del modelo se valida con Pydantic; si no cumple el esquema se reintenta. Se compara esperado contra obtenido en un conjunto de prueba.",
        "Costos y limitaciones. El costo por ejecución depende de los tokens; se documentan latencia, errores del modelo y riesgos de privacidad al enviar contenido a la nube.",
    ],
}


def texto_informe(lab: str) -> list[str]:
    return INFORMES.get(lab, [
        f"Introducción. Este informe presenta el trabajo realizado en el laboratorio {lab}.",
        "Desarrollo. Se describen los conceptos aplicados, las decisiones de diseño y los resultados obtenidos con evidencias.",
        "Resultados. Se presentan tablas y análisis de los resultados frente a lo esperado.",
        "Conclusiones. Se discuten limitaciones y trabajo futuro.",
    ])


def generar_pdf(titulo: str, autor: str, parrafos: list[str]) -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, title=titulo, author=autor)
    ss = getSampleStyleSheet()
    el = [Paragraph(titulo, ss["Title"]), Paragraph(autor, ss["Normal"]), Spacer(1, 18)]
    mitad = len(parrafos) // 2 + 1
    for i, p in enumerate(parrafos):
        if i == mitad:
            el.append(PageBreak())
        el += [Paragraph(p, ss["BodyText"]), Spacer(1, 8)]
    doc.build(el)
    return buf.getvalue()


# ---------------------------------------------------------------- código de ejemplo
CODIGO_ORGANIZADOR = {
    "README.md": "# Organizador de archivos (harness)\n\nClasifica archivos por extensión y verifica integridad con SHA-256.\n",
    "requirements.txt": "pytest\n",
    "organizador/__init__.py": "",
    "organizador/core.py": '''"""Organizador determinista de archivos."""
import hashlib
import shutil
from pathlib import Path

CATEGORIAS = {
    ".pdf": "documentos", ".docx": "documentos", ".txt": "documentos",
    ".png": "imagenes", ".jpg": "imagenes",
    ".py": "codigo", ".ipynb": "codigo",
}


def categoria(nombre: str) -> str:
    """Devuelve la categoría según la extensión del archivo."""
    return CATEGORIAS.get(Path(nombre).suffix.lower(), "otros")


def sha256(path: Path) -> str:
    """Hash SHA-256 del contenido para verificar integridad."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def organizar(carpeta: Path) -> list[dict]:
    """Mueve cada archivo a su subcarpeta y devuelve un log verificable."""
    log = []
    for f in sorted(p for p in carpeta.iterdir() if p.is_file()):
        antes = sha256(f)
        destino_dir = carpeta / categoria(f.name)
        destino_dir.mkdir(exist_ok=True)
        destino = destino_dir / f.name
        n = 1
        while destino.exists():
            destino = destino_dir / f"{f.stem}_{n}{f.suffix}"
            n += 1
        shutil.move(str(f), destino)
        log.append({"archivo": f.name, "destino": str(destino.relative_to(carpeta)),
                    "integridad": antes == sha256(destino)})
    return log
''',
    "tests/test_core.py": '''from pathlib import Path

from organizador.core import categoria, organizar


def test_categoria_por_extension():
    assert categoria("informe.PDF") == "documentos"
    assert categoria("foto.jpg") == "imagenes"
    assert categoria("misterio.xyz") == "otros"


def test_organizar_mueve_y_verifica(tmp_path: Path):
    (tmp_path / "a.txt").write_text("hola")
    (tmp_path / "b.py").write_text("print(1)")
    log = organizar(tmp_path)
    assert {e["destino"] for e in log} == {"documentos/a.txt", "codigo/b.py"}
    assert all(e["integridad"] for e in log)


def test_conflicto_de_nombres(tmp_path: Path):
    (tmp_path / "documentos").mkdir()
    (tmp_path / "documentos" / "a.txt").write_text("viejo")
    (tmp_path / "a.txt").write_text("nuevo")
    log = organizar(tmp_path)
    assert log[0]["destino"] == "documentos/a_1.txt"


def test_carpeta_vacia(tmp_path: Path):
    assert organizar(tmp_path) == []
''',
}

CODIGO_AGENTE = {
    "README.md": "# Agente clasificador con LLM\n\nHarness con validación de esquema y aprobación humana.\n",
    "agente/__init__.py": "",
    "agente/esquema.py": '''"""Esquema de la acción propuesta por el modelo."""
from dataclasses import dataclass

ACCIONES = {"listar_archivos", "leer_resumen", "mover_archivo", "terminar"}


@dataclass
class Accion:
    herramienta: str
    argumento: str
    razon: str


def validar_accion(datos: dict) -> Accion:
    """Valida la salida JSON del modelo antes de ejecutarla."""
    if datos.get("herramienta") not in ACCIONES:
        raise ValueError(f"Herramienta no permitida: {datos.get('herramienta')}")
    if not isinstance(datos.get("argumento"), str):
        raise ValueError("argumento debe ser texto")
    return Accion(datos["herramienta"], datos["argumento"], datos.get("razon", ""))
''',
    "agente/bucle.py": '''"""Bucle ReAct con supervisión humana."""
import json

from .esquema import validar_accion


def ejecutar(modelo, herramientas, aprobar, max_pasos=10):
    """modelo(historial)->str JSON; herramientas: dict nombre->función; aprobar(accion)->bool."""
    historial = []
    for paso in range(max_pasos):
        bruto = modelo(historial)
        try:
            accion = validar_accion(json.loads(bruto))
        except (ValueError, json.JSONDecodeError) as exc:
            historial.append({"paso": paso, "error": str(exc)})
            continue
        if accion.herramienta == "terminar":
            return historial
        if accion.herramienta == "mover_archivo" and not aprobar(accion):
            historial.append({"paso": paso, "rechazada": accion.argumento})
            continue
        resultado = herramientas[accion.herramienta](accion.argumento)
        historial.append({"paso": paso, "accion": accion.herramienta, "resultado": resultado})
    return historial
''',
    "tests/test_agente.py": '''import json

import pytest

from agente.bucle import ejecutar
from agente.esquema import validar_accion


def test_rechaza_herramienta_no_permitida():
    with pytest.raises(ValueError):
        validar_accion({"herramienta": "borrar_todo", "argumento": "/"})


def test_bucle_con_aprobacion_humana():
    respuestas = iter([
        json.dumps({"herramienta": "mover_archivo", "argumento": "a.txt", "razon": "doc"}),
        json.dumps({"herramienta": "terminar", "argumento": "", "razon": "fin"}),
    ])
    hist = ejecutar(lambda h: next(respuestas), {"mover_archivo": lambda a: "ok"}, aprobar=lambda a: False)
    assert hist == [{"paso": 0, "rechazada": "a.txt"}]


def test_reintenta_si_json_invalido():
    respuestas = iter(["no es json", json.dumps({"herramienta": "terminar", "argumento": ""})])
    hist = ejecutar(lambda h: next(respuestas), {}, aprobar=lambda a: True)
    assert "error" in hist[0]


def test_no_hace_llamadas_de_red():
    import socket
    with pytest.raises(Exception):
        socket.create_connection(("example.com", 80), timeout=2)
''',
}


def zip_de(archivos: dict[str, str], raiz: str = "proyecto") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for ruta, contenido in archivos.items():
            zf.writestr(f"{raiz}/{ruta}", contenido)
    return buf.getvalue()
