"""Datos iniciales: competencias, cohortes, laboratorios con rúbricas y usuarios de demostración.
Solo se ejecuta si la base está vacía. Desactivar en producción real con SEED_DEMO=false."""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import demo_content as dc
from . import ingest
from .config import get_settings
from .evaluation import evaluar, revisar, verificar_codigo
from .models import Cohorte, Competencia, Entrega, Laboratorio, Rubrica, User
from .rubrics import rubrica_sha256, validar_rubrica
from .security import hash_password

log = logging.getLogger("asesor.seed")
DEMO_PASSWORD_DEFAULT = "Demo-2026-Asesor"  # noqa: S105 - solo demo; en producción usar DEMO_PASSWORD o SEED_DEMO=false


def seed(db: Session, con_historial: bool = True) -> None:
    if db.scalars(select(User)).first():
        return
    pwd = get_settings().demo_password or DEMO_PASSWORD_DEFAULT
    docente = User(email="docente@demo.edu.co", nombre="Docente Demo", rol="docente", password_hash=hash_password(pwd))
    ana = User(email="ana.gomez@demo.edu.co", nombre="Ana Gómez (demo)", rol="estudiante", password_hash=hash_password(pwd))
    luis = User(email="luis.perez@demo.edu.co", nombre="Luis Pérez (demo)", rol="estudiante", password_hash=hash_password(pwd))
    db.add_all([docente, ana, luis])
    for codigo, nombre, desc in dc.COMPETENCIAS:
        db.add(Competencia(codigo=codigo, nombre=nombre, descripcion=desc))
    c1 = Cohorte(nombre="Corte 1", orden=1, descripcion="Primer corte: fundamentos y modelos de IA.")
    c2 = Cohorte(nombre="Corte 2", orden=2, descripcion="Segundo corte: agentes, harness y fábrica aumentada.")
    db.add_all([c1, c2])
    db.flush()
    catalogo = {c for c, _, _ in dc.COMPETENCIAS}
    labs: dict[str, Laboratorio] = {}
    for orden, (coh, nombre, desc, req, rub) in enumerate(dc.LABORATORIOS, start=1):
        lab = Laboratorio(cohorte_id=(c1 if coh == 1 else c2).id, nombre=nombre, descripcion=desc, orden=orden, requiere_codigo=req)
        db.add(lab)
        db.flush()
        res = validar_rubrica(rub, catalogo)
        assert res.valida, (nombre, res.errores)
        db.add(Rubrica(laboratorio_id=lab.id, version=1, contenido=rub, sha256=rubrica_sha256(rub), valida=True,
                       errores=[], advertencias=res.advertencias, activa=True, origen="json", creada_por_id=docente.id))
        labs[nombre] = lab
    db.commit()
    log.info("Datos de demostración creados. Usuario docente: docente@demo.edu.co")

    if not con_historial:
        return
    # Historial: algunas entregas ya evaluadas y publicadas para que el informe integrado tenga datos
    historial = [
        (ana, "Historia de la IA", None, "aprobada"),
        (ana, "Coloquio: observatorio de proyectos de IA", None, "aprobada"),
        (ana, "Harness 1: organizador con Python tradicional", dc.CODIGO_ORGANIZADOR, "ajustada"),
        (luis, "Historia de la IA", None, "aprobada"),
        (luis, "Harness 1: organizador con Python tradicional", dc.CODIGO_ORGANIZADOR, "aprobada"),
    ]
    for est, lab_nombre, codigo, decision in historial:
        try:
            lab = labs[lab_nombre]
            rub = db.scalars(select(Rubrica).where(Rubrica.laboratorio_id == lab.id, Rubrica.activa.is_(True))).one()
            pdf = dc.generar_pdf(f"Informe: {lab_nombre}", est.nombre, dc.texto_informe(lab_nombre))
            path, paginas, sha = ingest.procesar_pdf(pdf, "informe.pdf")
            cod = ingest.extraer_zip(dc.zip_de(codigo)) if codigo else None
            e = Entrega(laboratorio_id=lab.id, estudiante_id=est.id, rubrica_id=rub.id, subida_por_id=docente.id,
                        pdf_nombre="informe.pdf", pdf_path=str(path), pdf_sha256=sha, pdf_paginas=paginas,
                        codigo_origen="zip" if cod else None, codigo_path=str(cod.path) if cod else None,
                        codigo_sha256=cod.sha256 if cod else None, codigo_archivos=cod.archivos if cod else 0)
            db.add(e)
            db.commit()
            verificar_codigo(db, e, docente)
            ev = evaluar(db, e, docente)
            ajustes, just = {}, None
            if decision == "ajustada":
                cr = next(c for c in ev.resultado["criterios"] if c["metodo"] == "llm")
                rub_c = next(c for c in rub.contenido["criterios"] if c["id"] == cr["criterio_id"])
                ids = [n["id"] for n in rub_c["niveles"]]
                nuevo = ids[min(len(ids) - 1, ids.index(cr["nivel_id"]) + 1)]
                if nuevo == cr["nivel_id"]:
                    nuevo = ids[ids.index(cr["nivel_id"]) - 1]
                ajustes = {cr["criterio_id"]: nuevo}
                just = "Revisé el informe completo: el análisis de limitaciones justifica un nivel distinto al propuesto."
            revisar(db, ev, docente, decision, ajustes, just, "Revisado por el docente (datos de demostración).")
        except Exception:  # pragma: no cover - el historial es opcional
            log.exception("No se pudo crear historial de demo para %s", lab_nombre)
            db.rollback()
