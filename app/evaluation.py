"""Orquestación: verificar código → construir prompt → LLM estructurado → validar → verificar
evidencias → niveles objetivos → nota en backend → alertas → evaluación preliminar → revisión docente."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from .code_check import analisis_estatico, ejecutar_pruebas
from .config import get_settings
from .evidence import Verificador, detectar_inyeccion
from .grading import calcular_nota, nivel_por_metrica
from .ingest import codigo_con_lineas, listar_codigo
from .llm.prompts import PROMPT_VERSION, SISTEMA_EVALUADOR, construir_prompt_evaluacion, mensaje_correccion
from .llm.providers import DEFAULTS, ConfigModelo, LLMError, crear_proveedor
from .llm.schemas import SCHEMA_VERSION, SalidaEvaluacion, schema_plano
from .models import Ajuste, Entrega, Evaluacion, User, Verificacion
from .rubrics import RubricaSchema
from .security import audit

MAX_INTENTOS = 3


class EvaluacionError(RuntimeError):
    pass


# ------------------------------------------------------------------ Configuración del modelo
def config_modelo(db: Session) -> ConfigModelo:
    s = get_settings()
    guardado = db.get(Ajuste, "modelo")
    v = guardado.valor if guardado else {}
    proveedor = v.get("proveedor") or s.llm_provider
    d = DEFAULTS.get(proveedor, DEFAULTS["mock"])
    return ConfigModelo(
        proveedor=proveedor,
        modelo=v.get("modelo") or (s.llm_model if proveedor == s.llm_provider and s.llm_model else d["model"]),
        base_url=v.get("base_url") or (s.llm_base_url if proveedor == s.llm_provider and s.llm_base_url else d["base_url"]),
        temperatura=float(v.get("temperatura", s.llm_temperature)),
        seed=int(v.get("seed", s.llm_seed)),
        timeout_s=s.llm_timeout_s,
    )


# ------------------------------------------------------------------ Verificación de código
def verificar_codigo(db: Session, entrega: Entrega, user: User | None) -> Verificacion:
    if not entrega.codigo_path:
        v = Verificacion(entrega_id=entrega.id, analisis={"disponible": False, "motivo": "La entrega no incluye código."},
                         pruebas={"ejecutadas": False, "motivo": "La entrega no incluye código.", "tasa_exito": 0.0}, sandbox={})
    else:
        path = Path(entrega.codigo_path)
        analisis = analisis_estatico(path)
        pruebas, sbx = ejecutar_pruebas(path)
        v = Verificacion(entrega_id=entrega.id, analisis=analisis, pruebas=pruebas, sandbox=sbx)
    db.add(v)
    if entrega.estado == "cargada":
        entrega.estado = "verificada"
    db.flush()
    audit(db, user, "verificar_codigo", "entrega", entrega.id, verificacion_id=v.id,
          pruebas=f"{v.pruebas.get('aprobadas', 0)}/{v.pruebas.get('total', 0)}", sandbox=v.sandbox.get("modo"))
    db.commit()
    return v


def ultima_verificacion(db: Session, entrega_id: int) -> Verificacion | None:
    return db.scalars(select(Verificacion).where(Verificacion.entrega_id == entrega_id).order_by(Verificacion.id.desc())).first()


# ------------------------------------------------------------------ Validación semántica de la salida
def validar_salida(salida: SalidaEvaluacion, rub: RubricaSchema) -> list[str]:
    errores: list[str] = []
    esperados = {c.id: c for c in rub.criterios if c.fuente == "llm"}
    vistos: set[str] = set()
    for ce in salida.criterios:
        cr = esperados.get(ce.criterio_id)
        if not cr:
            errores.append(f"El criterio '{ce.criterio_id}' no existe o no es de fuente llm.")
            continue
        if ce.criterio_id in vistos:
            errores.append(f"El criterio '{ce.criterio_id}' aparece repetido.")
        vistos.add(ce.criterio_id)
        ids = [n.id for n in cr.niveles]
        if ce.nivel_id not in ids:
            errores.append(f"Criterio {cr.id}: nivel '{ce.nivel_id}' inválido; use uno de {ids}.")
        elif ce.nivel_id != ids[0] and not ce.evidencias:
            errores.append(f"Criterio {cr.id}: un nivel superior al mínimo requiere al menos una evidencia textual.")
    for faltante in set(esperados) - vistos:
        errores.append(f"Falta evaluar el criterio '{faltante}'.")
    comp = {c.id for c in rub.competencias}
    for a in salida.actividades_fortalecimiento:
        if a.competencia_id not in comp:
            errores.append(f"Actividad '{a.titulo}': competencia_id '{a.competencia_id}' no existe en la rúbrica.")
    return errores


def _sha(*partes) -> str:
    h = hashlib.sha256()
    for p in partes:
        h.update(json.dumps(p, sort_keys=True, ensure_ascii=False, default=str).encode())
    return h.hexdigest()


# ------------------------------------------------------------------ Evaluación
def evaluar(db: Session, entrega: Entrega, user: User | None) -> Evaluacion:
    s = get_settings()
    rub_db = entrega.rubrica
    rub = RubricaSchema.model_validate(rub_db.contenido)
    verif = ultima_verificacion(db, entrega.id) or verificar_codigo(db, entrega, user)

    codigo_dir = Path(entrega.codigo_path) if entrega.codigo_path else None
    codigo_texto, _ = codigo_con_lineas(codigo_dir, int(s.llm_max_input_chars * 0.35)) if codigo_dir else ("", {})
    codigo_completo: dict[str, list[str]] = {}
    if codigo_dir:
        for f in listar_codigo(codigo_dir):
            codigo_completo[str(f.relative_to(codigo_dir))] = f.read_text(encoding="utf-8", errors="replace").splitlines()

    prompt = construir_prompt_evaluacion(
        laboratorio=entrega.laboratorio.nombre,
        cohorte=entrega.laboratorio.cohorte.nombre,
        rubrica=rub_db.contenido,
        informe_paginas=entrega.pdf_paginas,
        codigo_texto=codigo_texto,
        analisis=verif.analisis,
        pruebas=verif.pruebas,
        max_chars=s.llm_max_input_chars,
    )
    cfg = config_modelo(db)
    schema = schema_plano(SalidaEvaluacion)
    prompt_sha = _sha(PROMPT_VERSION, SISTEMA_EVALUADOR, prompt)
    entrada_sha = _sha(entrega.pdf_sha256, entrega.codigo_sha256, rub_db.sha256, SCHEMA_VERSION, PROMPT_VERSION, cfg.publico())

    proveedor = crear_proveedor(cfg)
    contexto = {"rubrica": rub_db.contenido, "paginas": entrega.pdf_paginas, "codigo": codigo_completo, "pruebas": verif.pruebas}
    mensajes: list[dict] = [{"role": "user", "content": prompt}]
    salida: SalidaEvaluacion | None = None
    uso_total = {"entrada": 0, "salida": 0}
    duracion = 0
    errores: list[str] = []
    intentos = 0
    for intento in range(1, MAX_INTENTOS + 1):
        intentos = intento
        try:
            resp = proveedor.generar(SISTEMA_EVALUADOR, mensajes, schema, "registrar_evaluacion", contexto)
        except LLMError as exc:
            raise EvaluacionError(str(exc)) from exc
        duracion += resp.duracion_ms
        for k in uso_total:
            uso_total[k] += resp.uso.get(k) or 0
        try:
            candidato = SalidaEvaluacion.model_validate(resp.datos)
            errores = validar_salida(candidato, rub)
        except ValidationError as exc:
            candidato = None
            errores = [f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()]
        if not errores:
            salida = candidato
            break
        mensajes += [
            {"role": "assistant", "content": json.dumps(resp.datos, ensure_ascii=False)[:20000]},
            {"role": "user", "content": mensaje_correccion(errores)},
        ]
    if salida is None:
        audit(db, user, "evaluacion_fallida", "entrega", entrega.id, errores=errores[:10], modelo=cfg.modelo)
        db.commit()
        raise EvaluacionError("El modelo no produjo una salida válida tras varios intentos: " + "; ".join(errores[:5]))

    # ---- Niveles: LLM para criterios cualitativos, backend para criterios objetivos
    verificador = Verificador(entrega.pdf_paginas, codigo_completo, verif.pruebas.get("salida", "") or "")
    por_id = {c.criterio_id: c for c in salida.criterios}
    alertas: list[dict] = []
    resultado_criterios = []
    niveles: dict[str, str] = {}
    total_ev = verificadas = 0
    for cr in rub.criterios:
        if cr.fuente == "llm":
            ce = por_id[cr.id]
            evs = []
            for ev in ce.evidencias:
                v = verificador.verificar(ev.fuente, ev.cita)
                total_ev += 1
                if v["estado"] != "no_encontrada":
                    verificadas += 1
                evs.append(ev.model_dump() | v)
            nivel_id = ce.nivel_id
            just = ce.justificacion
            sin_verificar = [e for e in evs if e["estado"] == "no_encontrada"]
            if evs and len(sin_verificar) == len(evs):
                alertas.append({"tipo": "evidencia", "severidad": "alta", "criterio_id": cr.id,
                                "mensaje": f"Ninguna evidencia del criterio «{cr.nombre}» se encontró en el material. Revise el nivel asignado."})
            elif sin_verificar:
                alertas.append({"tipo": "evidencia", "severidad": "media", "criterio_id": cr.id,
                                "mensaje": f"{len(sin_verificar)} de {len(evs)} citas del criterio «{cr.nombre}» no se encontraron textualmente."})
            metodo = "llm"
        else:
            if cr.fuente == "pruebas":
                metrica = float(verif.pruebas.get("tasa_exito") or 0.0)
                desc = f"Tasa de éxito de pruebas: {metrica} % ({verif.pruebas.get('aprobadas', 0)}/{verif.pruebas.get('total', 0)})."
                if verif.pruebas.get("inconsistente"):
                    alertas.append({"tipo": "pruebas", "severidad": "alta", "criterio_id": cr.id, "mensaje": verif.pruebas.get("motivo", "")})
                if not verif.pruebas.get("total"):
                    alertas.append({"tipo": "pruebas", "severidad": "media", "criterio_id": cr.id,
                                    "mensaje": f"Sin pruebas ejecutables: {verif.pruebas.get('motivo', 'no se encontraron pruebas')}."})
            else:
                metrica = float(verif.analisis.get("calidad") or 0.0)
                desc = f"Índice de calidad estática (ruff): {metrica}/100; {verif.analisis.get('hallazgos', 0)} hallazgos."
                if verif.analisis.get("calidad") is None:
                    alertas.append({"tipo": "analisis", "severidad": "media", "criterio_id": cr.id,
                                    "mensaje": f"Análisis estático no disponible: {verif.analisis.get('motivo', '')}"})
            nivel_id = nivel_por_metrica(cr, metrica)
            just = f"Nivel asignado automáticamente por el backend. {desc}"
            evs = [{"fuente": "pruebas" if cr.fuente == "pruebas" else "codigo", "cita": desc, "estado": "medicion", "ubicacion_verificada": "verificación automática"}]
            metodo = cr.fuente
        niveles[cr.id] = nivel_id
        nivel = next(n for n in cr.niveles if n.id == nivel_id)
        resultado_criterios.append({
            "criterio_id": cr.id, "nombre": cr.nombre, "competencia_id": cr.competencia_id, "peso": cr.peso,
            "metodo": metodo, "nivel_id": nivel_id, "nivel_nombre": nivel.nombre, "puntaje": nivel.puntaje,
            "descriptor": nivel.descriptor, "justificacion": just, "evidencias": evs,
        })

    calculo = calcular_nota(rub, niveles)
    confianza = round(100 * verificadas / total_ev, 1) if total_ev else 0.0

    inyeccion = detectar_inyeccion(" ".join(entrega.pdf_paginas), codigo_texto)
    if inyeccion:
        alertas.append({"tipo": "seguridad", "severidad": "alta",
                        "mensaje": "El material contiene posibles instrucciones dirigidas al evaluador: " + "; ".join(inyeccion[:3])})
    sbx = verif.sandbox or {}
    if sbx.get("aislamiento") == "parcial":
        alertas.append({"tipo": "sandbox", "severidad": "baja", "mensaje": "Las pruebas corrieron con aislamiento parcial (sin contenedor). Ver manual técnico."})
    if "truncado" in prompt:
        alertas.append({"tipo": "contexto", "severidad": "baja", "mensaje": "El material superó el límite de contexto y se truncó para el modelo."})
    if cfg.proveedor == "mock":
        alertas.append({"tipo": "modelo", "severidad": "baja", "mensaje": "Evaluación hecha con el evaluador heurístico de demostración (sin IA)."})

    # ---- Reproducibilidad: comparar con evaluaciones previas de la misma entrada
    previa = db.scalars(select(Evaluacion).where(Evaluacion.entrega_id == entrega.id, Evaluacion.entrada_sha256 == entrada_sha)
                        .order_by(Evaluacion.id.desc())).first()
    reproducibilidad = None
    if previa:
        prev_niv = {c["criterio_id"]: c["nivel_id"] for c in previa.resultado["criterios"]}
        difs = [cid for cid, nid in niveles.items() if prev_niv.get(cid) != nid]
        reproducibilidad = {"comparada_con": previa.id, "criterios_distintos": difs, "nota_previa": previa.nota_preliminar,
                            "identica": not difs}
        if difs:
            alertas.append({"tipo": "reproducibilidad", "severidad": "media",
                            "mensaje": f"Con la misma entrada, {len(difs)} criterio(s) cambiaron de nivel respecto a la evaluación #{previa.id}."})

    ev = Evaluacion(
        entrega_id=entrega.id, rubrica_id=rub_db.id, verificacion_id=verif.id,
        proveedor=cfg.proveedor, modelo=cfg.modelo,
        parametros={"temperatura": cfg.temperatura, "seed": cfg.seed, "base_url": cfg.base_url, "prompt_version": PROMPT_VERSION},
        schema_version=SCHEMA_VERSION, prompt_sha256=prompt_sha, entrada_sha256=entrada_sha,
        intentos=intentos, duracion_ms=duracion, uso_tokens=uso_total,
        respuesta_llm=salida.model_dump(),
        resultado={"criterios": resultado_criterios, "calculo": calculo, "reproducibilidad": reproducibilidad},
        alertas=alertas, confianza=confianza, nota_preliminar=calculo["nota"],
    )
    db.add(ev)
    entrega.estado = "evaluada" if entrega.estado != "publicada" else entrega.estado
    db.flush()
    audit(db, user, "evaluar", "evaluacion", ev.id, entrega_id=entrega.id, modelo=f"{cfg.proveedor}/{cfg.modelo}",
          nota_preliminar=ev.nota_preliminar, confianza=confianza, intentos=intentos)
    db.commit()
    return ev


# ------------------------------------------------------------------ Revisión docente
def revisar(db: Session, ev: Evaluacion, docente: User, decision: str, ajustes: dict[str, str] | None,
            justificacion: str | None, comentario: str | None) -> Evaluacion:
    if ev.estado != "preliminar":
        raise EvaluacionError("Solo se pueden revisar evaluaciones preliminares.")
    rub = RubricaSchema.model_validate(ev.rubrica.contenido)
    niveles = {c["criterio_id"]: c["nivel_id"] for c in ev.resultado["criterios"]}
    ajustes = {k: v for k, v in (ajustes or {}).items() if v and niveles.get(k) != v}
    if decision == "ajustada":
        if not ajustes:
            raise EvaluacionError("Para ajustar debe cambiar al menos un nivel de criterio.")
        if not justificacion or len(justificacion.strip()) < 15:
            raise EvaluacionError("El ajuste requiere una justificación de al menos 15 caracteres.")
        for cid, nid in ajustes.items():
            cr = next((c for c in rub.criterios if c.id == cid), None)
            if not cr or nid not in {n.id for n in cr.niveles}:
                raise EvaluacionError(f"Ajuste inválido para {cid}: {nid}")
        niveles.update(ajustes)
        nota = calcular_nota(rub, niveles)["nota"]
    elif decision == "aprobada":
        ajustes = {}
        nota = ev.nota_preliminar
    else:
        raise EvaluacionError("Decisión inválida (use 'aprobada' o 'ajustada').")

    # Una sola evaluación publicada por entrega
    for otra in db.scalars(select(Evaluacion).where(Evaluacion.entrega_id == ev.entrega_id, Evaluacion.estado == "publicada")):
        otra.estado = "reemplazada"
    ev.decision = decision
    ev.ajustes = ajustes
    ev.nota_final = nota
    ev.justificacion_docente = (justificacion or "").strip() or None
    ev.comentario_docente = (comentario or "").strip() or None
    ev.revisada_por_id = docente.id
    ev.revisada_at = datetime.now(timezone.utc)
    ev.estado = "publicada"
    ev.entrega.estado = "publicada"
    audit(db, docente, f"evaluacion_{decision}", "evaluacion", ev.id, nota_preliminar=ev.nota_preliminar,
          nota_final=nota, ajustes=ajustes)
    db.commit()
    return ev


def niveles_finales(ev: Evaluacion) -> dict[str, str]:
    n = {c["criterio_id"]: c["nivel_id"] for c in ev.resultado["criterios"]}
    n.update(ev.ajustes or {})
    return n
