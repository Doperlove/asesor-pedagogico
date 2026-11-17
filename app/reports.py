"""Informe integrado: consolida resultados por laboratorio, cohorte y estudiante, y genera PDF."""
from __future__ import annotations

import io
import statistics
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .evaluation import niveles_finales
from .grading import redondear
from .models import Cohorte, Competencia, Entrega, Evaluacion, Laboratorio, User
from .rubrics import RubricaSchema


def _evaluacion_vigente(db: Session, entrega_id: int, incluir_preliminares: bool) -> Evaluacion | None:
    q = select(Evaluacion).where(Evaluacion.entrega_id == entrega_id)
    pub = db.scalars(q.where(Evaluacion.estado == "publicada").order_by(Evaluacion.id.desc())).first()
    if pub or not incluir_preliminares:
        return pub
    return db.scalars(q.where(Evaluacion.estado == "preliminar").order_by(Evaluacion.id.desc())).first()


def _criterios_finales(ev: Evaluacion) -> list[dict]:
    rub = RubricaSchema.model_validate(ev.rubrica.contenido)
    niv = niveles_finales(ev)
    out = []
    for cr in rub.criterios:
        n = next(x for x in cr.niveles if x.id == niv[cr.id])
        out.append({"criterio_id": cr.id, "nombre": cr.nombre, "competencia_id": cr.competencia_id,
                    "peso": cr.peso, "nivel": n.nombre, "puntaje": n.puntaje})
    return out


def _nombres_competencias(db: Session) -> dict[str, str]:
    return {c.codigo: c.nombre for c in db.scalars(select(Competencia))}


def _nivel_texto(nota: float | None) -> str:
    if nota is None:
        return "sin datos"
    if nota >= 4.5:
        return "Excelente"
    if nota >= 4.0:
        return "Sobresaliente"
    if nota >= 3.5:
        return "Bueno"
    if nota >= get_settings().umbral_aprobacion:
        return "Aceptable"
    return "Insuficiente"


def informe_estudiante(db: Session, estudiante: User, incluir_preliminares: bool = False) -> dict:
    umbral = get_settings().umbral_aprobacion
    nombres = _nombres_competencias(db)
    cohortes = db.scalars(select(Cohorte).order_by(Cohorte.orden)).all()
    comp_acum: dict[str, dict] = {}
    salida_cohortes = []
    actividades_por_comp: dict[str, list[dict]] = {}
    recomendaciones = []
    pendientes = []
    todas_notas = []
    criterios_debiles: list[dict] = []

    for coh in cohortes:
        labs_out = []
        notas = []
        for lab in coh.laboratorios:
            entrega = db.scalars(select(Entrega).where(Entrega.laboratorio_id == lab.id, Entrega.estudiante_id == estudiante.id)
                                 .order_by(Entrega.id.desc())).first()
            ev = _evaluacion_vigente(db, entrega.id, incluir_preliminares) if entrega else None
            if not ev:
                labs_out.append({"laboratorio_id": lab.id, "laboratorio": lab.nombre, "estado": "sin entrega" if not entrega else "en evaluación", "nota": None})
                pendientes.append(f"{coh.nombre} · {lab.nombre}")
                continue
            nota = ev.nota_final if ev.estado == "publicada" else ev.nota_preliminar
            notas.append(nota)
            crits = _criterios_finales(ev)
            criterios_debiles += [{"laboratorio": lab.nombre, "cohorte": coh.nombre, "criterio": c["nombre"], "nivel": c["nivel"],
                                   "puntaje": c["puntaje"], "competencia_id": c["competencia_id"]} for c in crits if c["puntaje"] < umbral]
            for c in crits:
                a = comp_acum.setdefault(c["competencia_id"], {"suma": 0.0, "peso": 0.0, "por_cohorte": {}})
                a["suma"] += c["puntaje"] * c["peso"]
                a["peso"] += c["peso"]
                pc = a["por_cohorte"].setdefault(coh.nombre, [0.0, 0.0])
                pc[0] += c["puntaje"] * c["peso"]
                pc[1] += c["peso"]
            r = ev.respuesta_llm
            for act in r.get("actividades_fortalecimiento", []):
                actividades_por_comp.setdefault(act["competencia_id"], []).append(act | {"origen": lab.nombre})
            recomendaciones += [rec | {"origen": lab.nombre} for rec in r.get("recomendaciones", [])]
            labs_out.append({
                "laboratorio_id": lab.id, "laboratorio": lab.nombre, "entrega_id": entrega.id, "evaluacion_id": ev.id,
                "estado": "publicada" if ev.estado == "publicada" else "preliminar",
                "nota": nota, "nivel": _nivel_texto(nota), "criterios": crits,
                "fortalezas": r.get("fortalezas", []), "vacios": r.get("vacios", []),
                "aprendizajes": r.get("aprendizajes_demostrados", []),
                "rubrica_version": ev.rubrica.version, "modelo": f"{ev.proveedor}/{ev.modelo}",
            })
        promedio = redondear(statistics.mean(notas), 2) if notas else None
        todas_notas += notas
        salida_cohortes.append({"cohorte_id": coh.id, "cohorte": coh.nombre, "promedio": promedio,
                                "nivel": _nivel_texto(promedio), "laboratorios": labs_out,
                                "evaluados": len(notas), "total": len(coh.laboratorios)})

    competencias = []
    for cid, a in sorted(comp_acum.items()):
        prom = redondear(a["suma"] / a["peso"], 2) if a["peso"] else None
        por_coh = {k: redondear(v[0] / v[1], 2) for k, v in a["por_cohorte"].items() if v[1]}
        estado = "alcanzada" if prom is not None and prom >= 4.0 else ("en desarrollo" if prom is not None and prom >= umbral else "brecha")
        competencias.append({"id": cid, "nombre": nombres.get(cid, cid), "promedio": prom, "por_cohorte": por_coh, "estado": estado})

    # Progresión entre cohortes
    progresion = None
    con_datos = [c for c in salida_cohortes if c["promedio"] is not None]
    if len(con_datos) >= 2:
        delta = redondear(con_datos[-1]["promedio"] - con_datos[0]["promedio"], 2)
        progresion = {"desde": con_datos[0]["cohorte"], "hasta": con_datos[-1]["cohorte"], "delta": delta,
                      "tendencia": "mejora" if delta > 0.1 else ("descenso" if delta < -0.1 else "estable")}

    brechas = sorted([c for c in competencias if c["estado"] != "alcanzada"], key=lambda c: c["promedio"] or 0)
    plan = []
    for c in brechas:
        prioridad = "alta" if (c["promedio"] or 0) < umbral else "media"
        acts = []
        vistos = set()
        for a in actividades_por_comp.get(c["id"], []):
            if a["titulo"].lower() not in vistos:
                vistos.add(a["titulo"].lower())
                acts.append(a)
        if not acts:
            acts = [{"titulo": f"Práctica guiada: {c['nombre']}", "descripcion": "Repetir un laboratorio asociado aplicando los descriptores del nivel superior de la rúbrica y documentar evidencias verificables.", "origen": "plan general"}]
        plan.append({"competencia_id": c["id"], "competencia": c["nombre"], "promedio": c["promedio"], "prioridad": prioridad, "actividades": acts[:3]})

    cubiertas = {p["competencia_id"] for p in plan}
    for cd in criterios_debiles:
        if cd["competencia_id"] in cubiertas:
            continue
        cubiertas.add(cd["competencia_id"])
        acts = actividades_por_comp.get(cd["competencia_id"], [])[:2] or [{
            "titulo": f"Reforzar: {cd['criterio']}",
            "descripcion": f"En {cd['laboratorio']} este criterio quedó en nivel {cd['nivel']}. Rehaga esa sección siguiendo el descriptor del nivel superior.",
            "origen": cd["laboratorio"]}]
        plan.append({"competencia_id": cd["competencia_id"], "competencia": nombres.get(cd["competencia_id"], cd["competencia_id"]),
                     "promedio": next((c["promedio"] for c in competencias if c["id"] == cd["competencia_id"]), None),
                     "prioridad": "media", "motivo": f"Criterio débil: {cd['criterio']} ({cd['laboratorio']})", "actividades": acts})

    promedio_general = redondear(statistics.mean(todas_notas), 2) if todas_notas else None
    fuertes = [c["nombre"] for c in competencias if c["estado"] == "alcanzada"]
    resumen = []
    if promedio_general is not None:
        resumen.append(f"Promedio general {promedio_general:.2f} ({_nivel_texto(promedio_general).lower()}) en {len(todas_notas)} trabajos evaluados.")
    if progresion:
        resumen.append(f"De {progresion['desde']} a {progresion['hasta']} el promedio cambió {progresion['delta']:+.2f} ({progresion['tendencia']}).")
    if fuertes:
        resumen.append("Competencias alcanzadas: " + ", ".join(fuertes) + ".")
    if brechas:
        resumen.append("Requieren fortalecimiento: " + ", ".join(b["nombre"] for b in brechas) + ".")
    if pendientes:
        resumen.append(f"Hay {len(pendientes)} trabajo(s) sin evaluación publicada.")

    return {
        "estudiante": {"id": estudiante.id, "nombre": estudiante.nombre, "email": estudiante.email},
        "generado": datetime.now(timezone.utc).isoformat(),
        "incluye_preliminares": incluir_preliminares,
        "promedio_general": promedio_general,
        "nivel_general": _nivel_texto(promedio_general),
        "cohortes": salida_cohortes,
        "competencias": competencias,
        "progresion": progresion,
        "brechas": brechas,
        "criterios_debiles": criterios_debiles,
        "plan_fortalecimiento": plan,
        "recomendaciones": recomendaciones[:12],
        "pendientes": pendientes,
        "resumen": " ".join(resumen) or "Aún no hay evaluaciones publicadas.",
    }


def _stats(notas: list[float]) -> dict:
    if not notas:
        return {"n": 0, "promedio": None, "min": None, "max": None, "desviacion": None, "aprobados": 0}
    return {
        "n": len(notas), "promedio": redondear(statistics.mean(notas), 2), "min": min(notas), "max": max(notas),
        "desviacion": redondear(statistics.pstdev(notas), 2) if len(notas) > 1 else 0.0,
        "aprobados": sum(1 for n in notas if n >= get_settings().umbral_aprobacion),
    }


def informe_laboratorio(db: Session, lab: Laboratorio, incluir_preliminares: bool = True) -> dict:
    entregas = db.scalars(select(Entrega).where(Entrega.laboratorio_id == lab.id).order_by(Entrega.id)).all()
    ultimas: dict[int, Entrega] = {}
    for e in entregas:
        ultimas[e.estudiante_id] = e
    filas, notas = [], []
    crit_acum: dict[str, list[float]] = {}
    crit_nombres: dict[str, str] = {}
    for est_id, e in ultimas.items():
        ev = _evaluacion_vigente(db, e.id, incluir_preliminares)
        nota = None
        if ev:
            nota = ev.nota_final if ev.estado == "publicada" else ev.nota_preliminar
            notas.append(nota)
            for c in _criterios_finales(ev):
                crit_acum.setdefault(c["criterio_id"], []).append(c["puntaje"])
                crit_nombres[c["criterio_id"]] = c["nombre"]
        filas.append({"estudiante": e.estudiante.nombre, "estudiante_id": est_id, "entrega_id": e.id,
                      "estado": ev.estado if ev else e.estado, "nota": nota, "confianza": ev.confianza if ev else None})
    criterios = sorted(
        [{"criterio_id": k, "nombre": crit_nombres[k], "promedio": redondear(statistics.mean(v), 2)} for k, v in crit_acum.items()],
        key=lambda x: x["promedio"],
    )
    return {"laboratorio": lab.nombre, "laboratorio_id": lab.id, "cohorte": lab.cohorte.nombre,
            "estadisticas": _stats(notas), "entregas": filas, "criterios": criterios}


def informe_cohorte(db: Session, coh: Cohorte, incluir_preliminares: bool = True) -> dict:
    labs = [informe_laboratorio(db, lab, incluir_preliminares) for lab in coh.laboratorios]
    estudiantes: dict[int, dict] = {}
    for li in labs:
        for f in li["entregas"]:
            fila = estudiantes.setdefault(f["estudiante_id"], {"estudiante": f["estudiante"], "notas": {}})
            fila["notas"][li["laboratorio"]] = f["nota"]
    for fila in estudiantes.values():
        vals = [v for v in fila["notas"].values() if v is not None]
        fila["promedio"] = redondear(statistics.mean(vals), 2) if vals else None
    todas = [f["nota"] for li in labs for f in li["entregas"] if f["nota"] is not None]
    return {"cohorte": coh.nombre, "cohorte_id": coh.id, "estadisticas": _stats(todas),
            "laboratorios": [{"laboratorio": li["laboratorio"], "laboratorio_id": li["laboratorio_id"], **li["estadisticas"],
                              "criterio_mas_debil": li["criterios"][0] if li["criterios"] else None} for li in labs],
            "estudiantes": sorted(estudiantes.values(), key=lambda x: x["estudiante"])}


# ------------------------------------------------------------------ PDF
def pdf_estudiante(data: dict) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.8 * cm, bottomMargin=1.8 * cm,
                            title=f"Informe integrado - {data['estudiante']['nombre']}", author="Asesor Pedagógico Inteligente")
    ss = getSampleStyleSheet()
    teal = colors.HexColor("#0F766E")
    h1 = ParagraphStyle("h1", parent=ss["Title"], fontSize=18, textColor=teal, alignment=TA_LEFT, spaceAfter=4)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=13, textColor=teal, spaceBefore=12, spaceAfter=6)
    h3 = ParagraphStyle("h3", parent=ss["Heading3"], fontSize=11, spaceBefore=8, spaceAfter=3)
    body = ParagraphStyle("b", parent=ss["BodyText"], fontSize=9.5, leading=13)
    small = ParagraphStyle("s", parent=body, fontSize=8, textColor=colors.HexColor("#555555"))

    def esc(t) -> str:
        return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def tabla(filas, anchos, cab=True):
        t = Table(filas, colWidths=anchos, repeatRows=1 if cab else 0)
        st = [("FONTSIZE", (0, 0), (-1, -1), 8.5), ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CCCCCC")),
              ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
        if cab:
            st += [("BACKGROUND", (0, 0), (-1, 0), teal), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white)]
        t.setStyle(TableStyle(st))
        return t

    f = lambda n: "—" if n is None else f"{n:.1f}"  # noqa: E731
    f2 = lambda n: "—" if n is None else f"{n:.2f}"  # noqa: E731
    el = [
        Paragraph("Informe integrado de aprendizaje", h1),
        Paragraph(f"<b>{esc(data['estudiante']['nombre'])}</b> · {esc(data['estudiante']['email'])}", body),
        Paragraph(f"Generado: {data['generado'][:16].replace('T', ' ')} UTC · Asesor Pedagógico Inteligente"
                  + (" · <font color='#B45309'>Incluye notas preliminares (vista docente)</font>" if data["incluye_preliminares"] else ""), small),
        Spacer(1, 8),
        tabla([["Promedio general", "Nivel", "Progresión"],
               [f2(data["promedio_general"]), data["nivel_general"],
                f"{data['progresion']['delta']:+.2f} ({data['progresion']['tendencia']})" if data["progresion"] else "—"]],
              [5.5 * cm, 5.5 * cm, 6 * cm]),
        Spacer(1, 6), Paragraph(esc(data["resumen"]), body),
        Paragraph("Resultados por corte y laboratorio", h2),
    ]
    for c in data["cohortes"]:
        filas = [["Laboratorio", "Estado", "Nota", "Nivel"]]
        for lab in c["laboratorios"]:
            filas.append([Paragraph(esc(lab["laboratorio"]), body), lab["estado"], f(lab.get("nota")), lab.get("nivel", "—")])
        el += [Paragraph(f"{esc(c['cohorte'])} — promedio {f2(c['promedio'])} ({c['evaluados']}/{c['total']} evaluados)", h3),
               tabla(filas, [8 * cm, 3 * cm, 2 * cm, 4 * cm])]
    el.append(Paragraph("Competencias del curso", h2))
    filas = [["Competencia", "Promedio", "Por corte", "Estado"]]
    for c in data["competencias"]:
        filas.append([Paragraph(f"<b>{esc(c['id'])}</b> {esc(c['nombre'])}", body), f2(c["promedio"]),
                      Paragraph(esc(", ".join(f"{k}: {v:.2f}" for k, v in c["por_cohorte"].items())), body), c["estado"]])
    el.append(tabla(filas, [7.5 * cm, 2 * cm, 4.5 * cm, 3 * cm]) if len(filas) > 1 else Paragraph("Sin datos aún.", body))

    titulo_plan = Paragraph("Plan de fortalecimiento", h2)
    if not data["plan_fortalecimiento"]:
        el += [titulo_plan, Paragraph("No se identificaron brechas: todas las competencias evaluadas están alcanzadas.", body)]
    for i, p in enumerate(data["plan_fortalecimiento"]):
        bloque = ([titulo_plan] if i == 0 else []) + [Paragraph(f"{esc(p['competencia'])} — promedio {f2(p['promedio'])} · prioridad <b>{p['prioridad']}</b>", h3)]
        for a in p["actividades"]:
            bloque.append(Paragraph(f"• <b>{esc(a['titulo'])}</b>: {esc(a['descripcion'])} <font color='#777777'>({esc(a.get('origen', ''))})</font>", body))
        el.append(KeepTogether(bloque))

    el.append(Paragraph("Detalle por trabajo", h2))
    for c in data["cohortes"]:
        for lab in c["laboratorios"]:
            if lab.get("nota") is None:
                continue
            bloque = [Paragraph(f"{esc(lab['laboratorio'])} — {f(lab['nota'])} ({lab['estado']}, rúbrica v{lab['rubrica_version']}, {esc(lab['modelo'])})", h3)]
            filas = [["Criterio", "Peso", "Nivel", "Puntaje"]] + [
                [Paragraph(esc(cr["nombre"]), body), f"{cr['peso']:g} %", cr["nivel"], f"{cr['puntaje']:.1f}"] for cr in lab["criterios"]
            ]
            bloque.append(tabla(filas, [8.5 * cm, 2 * cm, 4.5 * cm, 2 * cm]))
            if lab["fortalezas"]:
                bloque.append(Paragraph("<b>Fortalezas:</b> " + esc("; ".join(lab["fortalezas"][:4])), body))
            if lab["vacios"]:
                bloque.append(Paragraph("<b>Por mejorar:</b> " + esc("; ".join(lab["vacios"][:4])), body))
            el.append(KeepTogether(bloque))
    if data["pendientes"]:
        el += [Paragraph("Trabajos pendientes", h2), Paragraph(esc("; ".join(data["pendientes"])), body)]
    el += [Spacer(1, 12), Paragraph("Las notas publicadas fueron aprobadas o ajustadas por el docente. La nota se calcula en el servidor "
                                    "a partir de los niveles de la rúbrica (Σ peso × puntaje), nunca por el modelo de lenguaje.", small)]
    doc.build(el)
    return buf.getvalue()
