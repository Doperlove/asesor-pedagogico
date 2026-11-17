"""Importa los 9 trabajos del artifact original (data.json) como entregas del estudiante.

Uso (dentro del contenedor):  python scripts/importar_artifact.py /app/data/import/data.json
Cada trabajo se convierte en un PDF con su texto extraído e imágenes. El artifact no guardaba
los archivos originales ni el código fuente: el código se agrega luego en una nueva entrega.
"""
import base64
import html
import io
import json
import re
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from reportlab.lib.pagesizes import letter  # noqa: E402
from reportlab.lib.styles import getSampleStyleSheet  # noqa: E402
from reportlab.lib.units import cm  # noqa: E402
from reportlab.platypus import Image, Paragraph, Preformatted, SimpleDocTemplate, Spacer  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app import ingest  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.models import Entrega, Laboratorio, Rubrica, User  # noqa: E402
from app.security import audit, hash_password  # noqa: E402

# id del artifact -> prefijo del nombre del laboratorio en la plataforma
MAPA = {
    "c1-historia": "Historia de la IA",
    "c1-cumanday": "Manizales resiliente",
    "c1-vibecode": "Ingeniero aumentado",
    "c1-parcial": "Primer parcial",
    "c2-coloquio": "Coloquio",
    "c2-organizador": "Harness 1",
    "c2-nube": "Harness 2",
    "c2-local": "Harness 3",
    "c2-harness": "Harness 4",
}
EMAIL = "dyramirezc106025@umanizales.edu.co"
NOMBRE = "Daniel Yesid Ramírez Cifuentes"


def md_a_flowables(texto: str, ss) -> list:
    el, codigo, buf = [], False, []
    for linea in texto.splitlines():
        if linea.strip().startswith("```"):
            if codigo:
                el.append(Preformatted("\n".join(buf)[:6000], ss["Code"]))
                buf = []
            codigo = not codigo
            continue
        if codigo:
            buf.append(linea)
            continue
        t = linea.strip()
        if not t:
            continue
        m = re.match(r"^(#{1,4})\s+(.*)", t)
        seguro = html.escape(t)
        seguro = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", seguro)
        seguro = re.sub(r"`([^`]+)`", r"<font face='Courier'>\1</font>", seguro)
        if m:
            nivel = len(m.group(1))
            el.append(Paragraph(html.escape(m.group(2)), ss["Heading%d" % min(nivel + 1, 4)]))
        elif t.startswith(("- ", "* ")):
            el.append(Paragraph("• " + seguro[2:], ss["BodyText"]))
        elif t.startswith("|"):
            el.append(Paragraph(f"<font face='Courier' size='7'>{seguro}</font>", ss["BodyText"]))
        else:
            el.append(Paragraph(seguro, ss["BodyText"]))
    if buf:
        el.append(Preformatted("\n".join(buf)[:6000], ss["Code"]))
    return el


def imagen(data_uri: str, ancho_max=16 * cm):
    raw = base64.b64decode(data_uri.split(",", 1)[1])
    img = Image(io.BytesIO(raw))
    escala = min(1.0, ancho_max / img.imageWidth)
    img.drawWidth, img.drawHeight = img.imageWidth * escala, img.imageHeight * escala
    return img


def generar_pdf(lab: dict) -> bytes:
    ss = getSampleStyleSheet()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, title=lab["title"], author=NOMBRE)
    el = [Paragraph(html.escape(lab["title"]), ss["Title"]),
          Paragraph(f"{lab['corte']} · Archivo original: {html.escape(lab['file'])} ({lab['sizeKB']} KB)", ss["Italic"]),
          Paragraph("Documento reconstruido a partir del texto extraído en la autoevaluación previa.", ss["Italic"]),
          Spacer(1, 12)]
    if lab["kind"] == "video":
        el.append(Paragraph(
            f"Entrega en video ({lab.get('seconds', 0)} s). Este documento contiene {len(lab.get('frames', []))} fotogramas "
            "representativos del video con su marca de tiempo. El video narra la historia de la inteligencia artificial: "
            "la lógica formal, el test de Turing, la conferencia de Dartmouth, los sistemas expertos, las redes neuronales, "
            "el aprendizaje profundo y los modelos de lenguaje actuales.", ss["BodyText"]))
        for fr in lab.get("frames", []):
            el += [Spacer(1, 8), Paragraph(f"Fotograma en el segundo {fr.get('t')}", ss["Heading4"]), imagen(fr["src"], 12 * cm)]
    else:
        texto = lab.get("text") or ""
        el += md_a_flowables(texto, ss)
        if len(texto) >= 40000:
            el.append(Paragraph("[El texto original superaba 40.000 caracteres y se conservó recortado.]", ss["Italic"]))
        for i, uri in enumerate(lab.get("images") or [], start=1):
            el += [Spacer(1, 8), Paragraph(f"Figura {i}", ss["Heading4"]), imagen(uri)]
    doc.build(el)
    return buf.getvalue()


def main(ruta: str) -> None:
    data = json.loads(Path(ruta).read_text(encoding="utf-8"))
    init_db()
    db = SessionLocal()
    docente = db.scalars(select(User).where(User.rol == "docente")).first()
    est = db.scalars(select(User).where(User.email == EMAIL)).first()
    clave = None
    if not est:
        clave = "Daniel-" + secrets.token_hex(3)
        est = User(email=EMAIL, nombre=NOMBRE, rol="estudiante", password_hash=hash_password(clave))
        db.add(est)
        db.flush()
        audit(db, docente, "crear_usuario", "usuario", est.id, rol="estudiante", origen="importacion")
        db.commit()
    salida = Path(ruta).parent / "pdf"
    salida.mkdir(exist_ok=True)
    for lab in data["labs"]:
        prefijo = MAPA[lab["id"]]
        lab_db = next(x for x in db.scalars(select(Laboratorio)) if x.nombre.startswith(prefijo))
        rub = db.scalars(select(Rubrica).where(Rubrica.laboratorio_id == lab_db.id, Rubrica.activa.is_(True))).one()
        pdf = generar_pdf(lab)
        nombre = re.sub(r"\.(md|docx|mp4)$", "", lab["file"]) + ".pdf"
        (salida / nombre).write_bytes(pdf)
        ya = db.scalars(select(Entrega).where(Entrega.laboratorio_id == lab_db.id, Entrega.estudiante_id == est.id)).first()
        if ya:
            print(f"  ya existía: {lab_db.nombre}")
            continue
        path, paginas, sha = ingest.procesar_pdf(pdf, nombre)
        e = Entrega(laboratorio_id=lab_db.id, estudiante_id=est.id, rubrica_id=rub.id, subida_por_id=docente.id,
                    pdf_nombre=nombre, pdf_path=str(path), pdf_sha256=sha, pdf_paginas=paginas)
        db.add(e)
        db.flush()
        audit(db, docente, "entrega_cargada", "entrega", e.id, laboratorio_id=lab_db.id, estudiante_id=est.id,
              rubrica_version=rub.version, origen="importacion_artifact", codigo="pendiente" if lab_db.requiere_codigo else "no_requerido")
        db.commit()
        print(f"  OK {lab_db.nombre}: {len(paginas)} págs. {'(código pendiente)' if lab_db.requiere_codigo else ''}")
    if clave:
        print(f"ESTUDIANTE_CREADO {EMAIL} {clave}")


if __name__ == "__main__":
    main(sys.argv[1])
