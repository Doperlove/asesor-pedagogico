"""API REST de la plataforma."""
from __future__ import annotations

import io
import json
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import ingest
from .config import get_settings
from .db import get_db
from .evaluation import EvaluacionError, config_modelo, evaluar, revisar, ultima_verificacion, verificar_codigo
from .llm.prompts import SISTEMA_RUBRICA
from .llm.providers import DEFAULTS, PROVEEDORES, ConfigModelo, LLMError, crear_proveedor
from .llm.schemas import SalidaRubrica, schema_plano
from .models import Ajuste, Auditoria, Cohorte, Competencia, Entrega, Evaluacion, Laboratorio, Rubrica, User, Verificacion
from .reports import informe_cohorte, informe_estudiante, informe_laboratorio, pdf_estudiante
from .rubrics import rubrica_json_schema, rubrica_sha256, validar_rubrica
from .sandbox import info_sandbox
from .security import (
    COOKIE_NAME,
    audit,
    can_see_student,
    create_token,
    current_user,
    hash_password,
    login_limiter,
    require_docente,
    verify_password,
)

router = APIRouter(prefix="/api")


# ================================================================== helpers
def _u(u: User) -> dict:
    return {"id": u.id, "email": u.email, "nombre": u.nombre, "rol": u.rol, "activo": u.activo}


async def _leer(upload: UploadFile, max_mb: int | None = None) -> bytes:
    limite = (max_mb or get_settings().max_upload_mb) * 1024 * 1024
    data = await upload.read(limite + 1)
    if len(data) > limite:
        raise HTTPException(413, f"El archivo {upload.filename} supera {limite // (1024 * 1024)} MB.")
    return data


def _catalogo(db: Session) -> set[str]:
    return set(db.scalars(select(Competencia.codigo)))


def _rubrica_dict(r: Rubrica, completa: bool = True) -> dict:
    d = {"id": r.id, "laboratorio_id": r.laboratorio_id, "version": r.version, "valida": r.valida, "activa": r.activa,
         "errores": r.errores, "advertencias": r.advertencias, "origen": r.origen, "sha256": r.sha256,
         "created_at": r.created_at.isoformat(), "nombre": r.contenido.get("nombre", ""),
         "criterios": len(r.contenido.get("criterios", []))}
    if completa:
        d["contenido"] = r.contenido
    return d


def _rubrica_activa(db: Session, lab_id: int) -> Rubrica | None:
    return db.scalars(select(Rubrica).where(Rubrica.laboratorio_id == lab_id, Rubrica.activa.is_(True))).first()


def _ev_dict(ev: Evaluacion, para_estudiante: bool = False) -> dict:
    d = {
        "id": ev.id, "entrega_id": ev.entrega_id, "rubrica_id": ev.rubrica_id, "rubrica_version": ev.rubrica.version,
        "estado": ev.estado, "nota_preliminar": ev.nota_preliminar, "nota_final": ev.nota_final,
        "decision": ev.decision, "ajustes": ev.ajustes, "comentario_docente": ev.comentario_docente,
        "justificacion_docente": ev.justificacion_docente,
        "revisada_at": ev.revisada_at.isoformat() if ev.revisada_at else None,
        "created_at": ev.created_at.isoformat(), "resultado": ev.resultado, "respuesta": ev.respuesta_llm,
        "confianza": ev.confianza, "alertas": ev.alertas,
        "trazabilidad": {"proveedor": ev.proveedor, "modelo": ev.modelo, "parametros": ev.parametros,
                         "schema_version": ev.schema_version, "prompt_sha256": ev.prompt_sha256,
                         "entrada_sha256": ev.entrada_sha256, "intentos": ev.intentos, "duracion_ms": ev.duracion_ms,
                         "uso_tokens": ev.uso_tokens, "verificacion_id": ev.verificacion_id},
    }
    if para_estudiante:
        d.pop("nota_preliminar")
        d["alertas"] = []
    return d


def _entrega_dict(db: Session, e: Entrega, user: User, detalle: bool = False) -> dict:
    d = {
        "id": e.id, "laboratorio_id": e.laboratorio_id, "laboratorio": e.laboratorio.nombre,
        "cohorte": e.laboratorio.cohorte.nombre, "estudiante_id": e.estudiante_id, "estudiante": e.estudiante.nombre,
        "estado": e.estado, "created_at": e.created_at.isoformat(), "pdf_nombre": e.pdf_nombre,
        "pdf_paginas": len(e.pdf_paginas), "pdf_sha256": e.pdf_sha256, "codigo_origen": e.codigo_origen,
        "codigo_ref": e.codigo_ref, "codigo_commit": e.codigo_commit, "codigo_archivos": e.codigo_archivos,
        "codigo_sha256": e.codigo_sha256, "extra_url": e.extra_url, "extra_nombre": e.extra_nombre,
        "rubrica_id": e.rubrica_id, "rubrica_version": e.rubrica.version, "rubrica_nombre": e.rubrica.contenido.get("nombre"),
    }
    evs = db.scalars(select(Evaluacion).where(Evaluacion.entrega_id == e.id).order_by(Evaluacion.id.desc())).all()
    pub = next((x for x in evs if x.estado == "publicada"), None)
    pre = next((x for x in evs if x.estado == "preliminar"), None)
    d["nota_publicada"] = pub.nota_final if pub else None
    if user.rol == "docente":
        d["nota_preliminar"] = pre.nota_preliminar if pre else None
    if detalle:
        d["rubrica"] = e.rubrica.contenido
        if user.rol == "docente":
            v = ultima_verificacion(db, e.id)
            d["verificacion"] = {"id": v.id, "analisis": v.analisis, "pruebas": v.pruebas, "sandbox": v.sandbox,
                                 "created_at": v.created_at.isoformat()} if v else None
            d["evaluaciones"] = [_ev_dict(x) for x in evs]
        else:
            d["evaluaciones"] = [_ev_dict(x, para_estudiante=True) for x in evs if x.estado == "publicada"]
    return d


def _get_entrega(db: Session, entrega_id: int, user: User) -> Entrega:
    e = db.get(Entrega, entrega_id)
    if not e or not can_see_student(user, e.estudiante_id):
        raise HTTPException(404, "Entrega no encontrada")
    return e


# ================================================================== auth
class LoginIn(BaseModel):
    email: EmailStr
    password: str


@router.post("/auth/login")
def login(data: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    key = f"{request.client.host if request.client else '?'}:{data.email.lower()}"
    login_limiter.check(key)
    user = db.scalars(select(User).where(func.lower(User.email) == data.email.lower())).first()
    if not user or not user.activo or not verify_password(data.password, user.password_hash):
        login_limiter.fail(key)
        audit(db, None, "login_fallido", "usuario", None, email=data.email.lower())
        db.commit()
        raise HTTPException(401, "Correo o contraseña incorrectos")
    login_limiter.reset(key)
    token = create_token(user)
    s = get_settings()
    response.set_cookie(COOKIE_NAME, token, httponly=True, secure=s.cookie_secure, samesite="strict", max_age=s.token_minutes * 60, path="/")
    audit(db, user, "login", "usuario", user.id)
    db.commit()
    return {"usuario": _u(user)}


@router.post("/auth/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/auth/me")
def me(user: User = Depends(current_user)):
    return {"usuario": _u(user)}


class PasswordIn(BaseModel):
    actual: str
    nueva: str = Field(min_length=10)


@router.post("/auth/password")
def cambiar_password(data: PasswordIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not verify_password(data.actual, user.password_hash):
        raise HTTPException(400, "La contraseña actual no coincide")
    user.password_hash = hash_password(data.nueva)
    audit(db, user, "cambiar_password", "usuario", user.id)
    db.commit()
    return {"ok": True}


# ================================================================== usuarios
class UsuarioIn(BaseModel):
    email: EmailStr
    nombre: str = Field(min_length=3, max_length=200)
    rol: Literal["docente", "estudiante"] = "estudiante"
    password: str = Field(min_length=10)


@router.get("/usuarios")
def listar_usuarios(rol: str | None = None, _: User = Depends(require_docente), db: Session = Depends(get_db)):
    q = select(User).order_by(User.nombre)
    if rol:
        q = q.where(User.rol == rol)
    return [_u(u) for u in db.scalars(q)]


@router.post("/usuarios", status_code=201)
def crear_usuario(data: UsuarioIn, doc: User = Depends(require_docente), db: Session = Depends(get_db)):
    if db.scalars(select(User).where(func.lower(User.email) == data.email.lower())).first():
        raise HTTPException(409, "Ya existe un usuario con ese correo")
    u = User(email=data.email.lower(), nombre=data.nombre, rol=data.rol, password_hash=hash_password(data.password))
    db.add(u)
    db.flush()
    audit(db, doc, "crear_usuario", "usuario", u.id, rol=u.rol)
    db.commit()
    return _u(u)


# ================================================================== curso
@router.get("/cohortes")
def listar_cohortes(user: User = Depends(current_user), db: Session = Depends(get_db)):
    out = []
    for c in db.scalars(select(Cohorte).order_by(Cohorte.orden)):
        labs = []
        for lab in c.laboratorios:
            r = _rubrica_activa(db, lab.id)
            q = select(Entrega).where(Entrega.laboratorio_id == lab.id)
            if user.rol != "docente":
                q = q.where(Entrega.estudiante_id == user.id)
            entregas = db.scalars(q).all()
            pendientes = 0
            if user.rol == "docente":
                pendientes = db.scalar(select(func.count(Evaluacion.id)).join(Entrega).where(
                    Entrega.laboratorio_id == lab.id, Evaluacion.estado == "preliminar")) or 0
            labs.append({"id": lab.id, "nombre": lab.nombre, "descripcion": lab.descripcion, "orden": lab.orden,
                         "requiere_codigo": lab.requiere_codigo,
                         "rubrica": _rubrica_dict(r, completa=False) if r else None,
                         "entregas": len(entregas), "publicadas": sum(1 for e in entregas if e.estado == "publicada"),
                         "pendientes_revision": pendientes})
        out.append({"id": c.id, "nombre": c.nombre, "orden": c.orden, "descripcion": c.descripcion, "laboratorios": labs})
    return out


class CohorteIn(BaseModel):
    nombre: str = Field(min_length=2)
    orden: int = 1
    descripcion: str = ""


@router.post("/cohortes", status_code=201)
def crear_cohorte(data: CohorteIn, doc: User = Depends(require_docente), db: Session = Depends(get_db)):
    c = Cohorte(**data.model_dump())
    db.add(c)
    db.flush()
    audit(db, doc, "crear_cohorte", "cohorte", c.id)
    db.commit()
    return {"id": c.id}


class LabIn(BaseModel):
    cohorte_id: int
    nombre: str = Field(min_length=2)
    descripcion: str = ""
    orden: int = 1
    requiere_codigo: bool = True


@router.post("/laboratorios", status_code=201)
def crear_lab(data: LabIn, doc: User = Depends(require_docente), db: Session = Depends(get_db)):
    if not db.get(Cohorte, data.cohorte_id):
        raise HTTPException(404, "Cohorte no existe")
    lab = Laboratorio(**data.model_dump())
    db.add(lab)
    db.flush()
    audit(db, doc, "crear_laboratorio", "laboratorio", lab.id)
    db.commit()
    return {"id": lab.id}


@router.get("/competencias")
def listar_competencias(_: User = Depends(current_user), db: Session = Depends(get_db)):
    return [{"codigo": c.codigo, "nombre": c.nombre, "descripcion": c.descripcion} for c in db.scalars(select(Competencia).order_by(Competencia.codigo))]


# ================================================================== rúbricas
class RubricaIn(BaseModel):
    contenido: dict
    origen: Literal["json", "formulario", "documento"] = "json"
    activar: bool = True


@router.get("/rubricas/esquema")
def esquema_rubrica(_: User = Depends(current_user)):
    return rubrica_json_schema()


@router.post("/rubricas/validar")
def validar(data: RubricaIn, _: User = Depends(require_docente), db: Session = Depends(get_db)):
    r = validar_rubrica(data.contenido, _catalogo(db))
    return {"valida": r.valida, "errores": r.errores, "advertencias": r.advertencias}


@router.get("/laboratorios/{lab_id}/rubricas")
def versiones(lab_id: int, _: User = Depends(require_docente), db: Session = Depends(get_db)):
    return [_rubrica_dict(r, completa=False) for r in db.scalars(select(Rubrica).where(Rubrica.laboratorio_id == lab_id).order_by(Rubrica.version.desc()))]


@router.get("/rubricas/{rid}")
def ver_rubrica(rid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = db.get(Rubrica, rid)
    if not r:
        raise HTTPException(404, "Rúbrica no encontrada")
    return _rubrica_dict(r)


def _guardar_rubrica(db: Session, lab: Laboratorio, contenido: dict, origen: str, activar: bool, doc: User) -> Rubrica:
    res = validar_rubrica(contenido, _catalogo(db))
    ultima = db.scalar(select(func.max(Rubrica.version)).where(Rubrica.laboratorio_id == lab.id)) or 0
    r = Rubrica(laboratorio_id=lab.id, version=ultima + 1, contenido=contenido, sha256=rubrica_sha256(contenido),
                valida=res.valida, errores=res.errores, advertencias=res.advertencias, origen=origen, creada_por_id=doc.id)
    db.add(r)
    db.flush()
    if res.valida and activar:
        for otra in db.scalars(select(Rubrica).where(Rubrica.laboratorio_id == lab.id, Rubrica.id != r.id)):
            otra.activa = False
        r.activa = True
    audit(db, doc, "rubrica_creada" if res.valida else "rubrica_rechazada", "rubrica", r.id,
          laboratorio_id=lab.id, version=r.version, errores=res.errores[:10])
    db.commit()
    return r


@router.post("/laboratorios/{lab_id}/rubricas")
def crear_rubrica(lab_id: int, data: RubricaIn, doc: User = Depends(require_docente), db: Session = Depends(get_db)):
    lab = db.get(Laboratorio, lab_id)
    if not lab:
        raise HTTPException(404, "Laboratorio no existe")
    r = _guardar_rubrica(db, lab, data.contenido, data.origen, data.activar, doc)
    if not r.valida:
        raise HTTPException(422, {"mensaje": "Rúbrica rechazada: corrija los errores.", "errores": r.errores,
                                  "advertencias": r.advertencias, "borrador_id": r.id})
    return _rubrica_dict(r)


@router.post("/laboratorios/{lab_id}/rubricas/documento")
async def rubrica_desde_documento(lab_id: int, archivo: UploadFile = File(...), doc: User = Depends(require_docente), db: Session = Depends(get_db)):
    """Acepta JSON directamente, o PDF/DOCX/TXT que se convierten con el LLM y luego se validan."""
    lab = db.get(Laboratorio, lab_id)
    if not lab:
        raise HTTPException(404, "Laboratorio no existe")
    data = await _leer(archivo, 10)
    nombre = (archivo.filename or "").lower()
    if nombre.endswith(".json"):
        try:
            contenido = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HTTPException(422, {"mensaje": f"JSON inválido: {exc}", "errores": [str(exc)]}) from exc
        origen = "json"
    else:
        if nombre.endswith(".pdf"):
            from pypdf import PdfReader

            texto = "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(data)).pages)
        elif nombre.endswith(".docx"):
            from docx import Document

            d = Document(io.BytesIO(data))
            partes = [p.text for p in d.paragraphs]
            for t in d.tables:
                for row in t.rows:
                    partes.append(" | ".join(c.text.strip() for c in row.cells))
            texto = "\n".join(partes)
        elif nombre.endswith((".txt", ".md")):
            texto = data.decode("utf-8", errors="replace")
        else:
            raise HTTPException(415, "Formato no soportado. Use JSON, PDF, DOCX, TXT o MD.")
        cfg = config_modelo(db)
        catalogo = [{"id": c.codigo, "nombre": c.nombre} for c in db.scalars(select(Competencia))]
        prompt = (f"Catálogo de competencias del curso (úsalas como id si corresponden): {json.dumps(catalogo, ensure_ascii=False)}\n\n"
                  f"Formato de salida (JSON Schema): {json.dumps(rubrica_json_schema(), ensure_ascii=False)}\n\n"
                  f"<<<DOCUMENTO>>>\n{texto[:40000]}\n<<<FIN>>>")
        try:
            resp = crear_proveedor(cfg).generar(SISTEMA_RUBRICA, [{"role": "user", "content": prompt}],
                                                schema_plano(SalidaRubrica), "registrar_rubrica")
        except LLMError as exc:
            raise HTTPException(502, str(exc)) from exc
        contenido = resp.datos
        origen = "documento"
    r = _guardar_rubrica(db, lab, contenido, origen, True, doc)
    if not r.valida:
        raise HTTPException(422, {"mensaje": "La rúbrica tiene problemas. Revísela en el editor y corríjala.",
                                  "errores": r.errores, "advertencias": r.advertencias, "borrador_id": r.id})
    return _rubrica_dict(r)


@router.post("/rubricas/{rid}/activar")
def activar_rubrica(rid: int, doc: User = Depends(require_docente), db: Session = Depends(get_db)):
    r = db.get(Rubrica, rid)
    if not r:
        raise HTTPException(404, "Rúbrica no encontrada")
    if not r.valida:
        raise HTTPException(422, "No se puede activar una rúbrica con errores.")
    for otra in db.scalars(select(Rubrica).where(Rubrica.laboratorio_id == r.laboratorio_id)):
        otra.activa = otra.id == r.id
    audit(db, doc, "rubrica_activada", "rubrica", r.id)
    db.commit()
    return _rubrica_dict(r)


# ================================================================== entregas
@router.post("/entregas", status_code=201)
async def crear_entrega(
    laboratorio_id: int = Form(...),
    estudiante_id: int | None = Form(None),
    informe: UploadFile = File(...),
    codigo_zip: UploadFile | None = File(None),
    github_url: str | None = Form(None),
    extra_url: str | None = Form(None),
    extra: UploadFile | None = File(None),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    lab = db.get(Laboratorio, laboratorio_id)
    if not lab:
        raise HTTPException(404, "Laboratorio no existe")
    est_id = estudiante_id if user.rol == "docente" and estudiante_id else user.id
    est = db.get(User, est_id)
    if not est or est.rol != "estudiante":
        raise HTTPException(422, "Debe seleccionar un estudiante válido.")
    rub = _rubrica_activa(db, lab.id)
    if not rub:
        raise HTTPException(409, "El laboratorio no tiene una rúbrica válida activa. El docente debe cargarla primero.")
    github_url = (github_url or "").strip() or None
    tiene_zip = codigo_zip is not None and (codigo_zip.filename or "") != ""
    if lab.requiere_codigo and not tiene_zip and not github_url:
        raise HTTPException(422, "Este laboratorio exige código fuente: suba un ZIP o indique la URL de GitHub.")
    if extra_url and not extra_url.startswith(("https://", "http://")):
        raise HTTPException(422, "El enlace opcional debe empezar por http(s)://")

    try:
        pdf_bytes = await _leer(informe)
        pdf_path, paginas, pdf_sha = ingest.procesar_pdf(pdf_bytes, informe.filename or "informe.pdf")
        codigo = None
        if tiene_zip:
            codigo = ingest.extraer_zip(await _leer(codigo_zip, 50))  # type: ignore[arg-type]
        elif github_url:
            codigo = ingest.descargar_github(github_url)
        extra_path = extra_nombre = None
        if extra is not None and (extra.filename or ""):
            ext = "." + (extra.filename or "").rsplit(".", 1)[-1].lower()
            if ext not in ingest.EXT_EXTRA:
                raise ingest.IngestaError("Anexo no permitido: use video (mp4/webm/mov) o presentación (pptx/pdf/odp).")
            carpeta = ingest.nueva_carpeta("anexos")
            p = carpeta / f"anexo{ext}"
            p.write_bytes(await _leer(extra, 200))
            extra_path, extra_nombre = str(p), extra.filename
    except ingest.IngestaError as exc:
        raise HTTPException(422, str(exc)) from exc

    e = Entrega(
        laboratorio_id=lab.id, estudiante_id=est.id, rubrica_id=rub.id, subida_por_id=user.id,
        pdf_nombre=(informe.filename or "informe.pdf")[:250], pdf_path=str(pdf_path), pdf_sha256=pdf_sha, pdf_paginas=paginas,
        codigo_origen=codigo.origen if codigo else None, codigo_ref=codigo.ref if codigo else None,
        codigo_commit=codigo.commit if codigo else None, codigo_path=str(codigo.path) if codigo else None,
        codigo_sha256=codigo.sha256 if codigo else None, codigo_archivos=codigo.archivos if codigo else 0,
        extra_url=extra_url, extra_path=extra_path, extra_nombre=extra_nombre,
    )
    db.add(e)
    db.flush()
    audit(db, user, "entrega_cargada", "entrega", e.id, laboratorio_id=lab.id, estudiante_id=est.id,
          rubrica_id=rub.id, rubrica_version=rub.version, pdf_sha256=pdf_sha, codigo_sha256=e.codigo_sha256)
    db.commit()
    return _entrega_dict(db, e, user)


@router.get("/entregas")
def listar_entregas(laboratorio_id: int | None = None, estudiante_id: int | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(Entrega).order_by(Entrega.id.desc())
    if user.rol != "docente":
        q = q.where(Entrega.estudiante_id == user.id)
    elif estudiante_id:
        q = q.where(Entrega.estudiante_id == estudiante_id)
    if laboratorio_id:
        q = q.where(Entrega.laboratorio_id == laboratorio_id)
    return [_entrega_dict(db, e, user) for e in db.scalars(q)]


@router.get("/entregas/{eid}")
def ver_entrega(eid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _entrega_dict(db, _get_entrega(db, eid, user), user, detalle=True)


@router.get("/entregas/{eid}/informe.pdf")
def descargar_informe(eid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    e = _get_entrega(db, eid, user)
    return FileResponse(e.pdf_path, media_type="application/pdf", filename=e.pdf_nombre)


@router.get("/entregas/{eid}/anexo")
def descargar_anexo(eid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    e = _get_entrega(db, eid, user)
    if not e.extra_path:
        raise HTTPException(404, "La entrega no tiene anexo")
    return FileResponse(e.extra_path, filename=e.extra_nombre or "anexo")


@router.post("/entregas/{eid}/verificar")
def verificar(eid: int, doc: User = Depends(require_docente), db: Session = Depends(get_db)):
    e = _get_entrega(db, eid, doc)
    try:
        v = verificar_codigo(db, e, doc)
    except RuntimeError as exc:
        raise HTTPException(500, str(exc)) from exc
    return {"id": v.id, "analisis": v.analisis, "pruebas": v.pruebas, "sandbox": v.sandbox}


@router.post("/entregas/{eid}/evaluar")
def evaluar_entrega(eid: int, doc: User = Depends(require_docente), db: Session = Depends(get_db)):
    e = _get_entrega(db, eid, doc)
    try:
        ev = evaluar(db, e, doc)
    except EvaluacionError as exc:
        raise HTTPException(502, str(exc)) from exc
    return _ev_dict(ev)


# ================================================================== evaluaciones y revisión docente
@router.get("/evaluaciones/{evid}")
def ver_evaluacion(evid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ev = db.get(Evaluacion, evid)
    if not ev or not can_see_student(user, ev.entrega.estudiante_id):
        raise HTTPException(404, "Evaluación no encontrada")
    if user.rol != "docente" and ev.estado != "publicada":
        raise HTTPException(404, "Evaluación no publicada")
    return _ev_dict(ev, para_estudiante=user.rol != "docente")


class RevisionIn(BaseModel):
    decision: Literal["aprobada", "ajustada"]
    ajustes: dict[str, str] = Field(default_factory=dict)
    justificacion: str | None = None
    comentario: str | None = None


@router.post("/evaluaciones/{evid}/revision")
def revisar_evaluacion(evid: int, data: RevisionIn, doc: User = Depends(require_docente), db: Session = Depends(get_db)):
    ev = db.get(Evaluacion, evid)
    if not ev:
        raise HTTPException(404, "Evaluación no encontrada")
    try:
        ev = revisar(db, ev, doc, data.decision, data.ajustes, data.justificacion, data.comentario)
    except EvaluacionError as exc:
        raise HTTPException(422, str(exc)) from exc
    return _ev_dict(ev)


@router.get("/revisiones/pendientes")
def pendientes(doc: User = Depends(require_docente), db: Session = Depends(get_db)):
    out = []
    for ev in db.scalars(select(Evaluacion).where(Evaluacion.estado == "preliminar").order_by(Evaluacion.id.desc())):
        e = ev.entrega
        out.append({"evaluacion_id": ev.id, "entrega_id": e.id, "estudiante": e.estudiante.nombre, "laboratorio": e.laboratorio.nombre,
                    "cohorte": e.laboratorio.cohorte.nombre, "nota_preliminar": ev.nota_preliminar, "confianza": ev.confianza,
                    "alertas": len([a for a in ev.alertas if a.get("severidad") in ("alta", "media")]), "created_at": ev.created_at.isoformat()})
    return out


# ================================================================== informes
@router.get("/informes/estudiante/{sid}")
def informe_est(sid: int, preliminares: bool = False, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not can_see_student(user, sid):
        raise HTTPException(404, "No encontrado")
    est = db.get(User, sid)
    if not est or est.rol != "estudiante":
        raise HTTPException(404, "Estudiante no encontrado")
    return informe_estudiante(db, est, incluir_preliminares=preliminares and user.rol == "docente")


@router.get("/informes/estudiante/{sid}/pdf")
def informe_est_pdf(sid: int, preliminares: bool = False, user: User = Depends(current_user), db: Session = Depends(get_db)):
    data = informe_est(sid, preliminares, user, db)
    pdf = pdf_estudiante(data)
    audit(db, user, "informe_descargado", "usuario", sid, preliminares=data["incluye_preliminares"])
    db.commit()
    import unicodedata
    from urllib.parse import quote

    base = "informe_integrado_" + "_".join(data["estudiante"]["nombre"].split()) + ".pdf"
    ascii_ = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode())
    disp = f"attachment; filename=\"{ascii_}\"; filename*=UTF-8''{quote(base)}"
    return StreamingResponse(io.BytesIO(pdf), media_type="application/pdf", headers={"Content-Disposition": disp})


@router.get("/informes/cohorte/{cid}")
def informe_coh(cid: int, _: User = Depends(require_docente), db: Session = Depends(get_db)):
    c = db.get(Cohorte, cid)
    if not c:
        raise HTTPException(404, "Cohorte no encontrada")
    return informe_cohorte(db, c)


@router.get("/informes/laboratorio/{lid}")
def informe_lab(lid: int, _: User = Depends(require_docente), db: Session = Depends(get_db)):
    lab = db.get(Laboratorio, lid)
    if not lab:
        raise HTTPException(404, "Laboratorio no encontrado")
    return informe_laboratorio(db, lab)


# ================================================================== configuración del modelo
class ModeloIn(BaseModel):
    proveedor: Literal["mock", "ollama", "gemini", "openai", "anthropic"]
    modelo: str = ""
    base_url: str = ""
    temperatura: float = Field(0.0, ge=0, le=1)
    seed: int = 42


def _config_publica(db: Session) -> dict:
    s = get_settings()
    cfg = config_modelo(db)
    return {
        "actual": cfg.publico(),
        "proveedores": {k: DEFAULTS[k] for k in PROVEEDORES},
        "credenciales": {"openai": bool(s.openai_api_key), "anthropic": bool(s.anthropic_api_key), "gemini": bool(s.gemini_api_key)},
        "openai_json_mode": s.openai_json_mode,
        "sandbox": info_sandbox(),
    }


@router.get("/config/modelo")
def ver_config(_: User = Depends(require_docente), db: Session = Depends(get_db)):
    return _config_publica(db)


@router.put("/config/modelo")
def guardar_config(data: ModeloIn, doc: User = Depends(require_docente), db: Session = Depends(get_db)):
    valor = data.model_dump()
    a = db.get(Ajuste, "modelo")
    if a:
        a.valor = valor
    else:
        db.add(Ajuste(clave="modelo", valor=valor))
    audit(db, doc, "config_modelo", "ajuste", None, **valor)
    db.commit()
    return _config_publica(db)


@router.post("/config/modelo/probar")
def probar_modelo(doc: User = Depends(require_docente), db: Session = Depends(get_db)):
    cfg = config_modelo(db)
    if cfg.proveedor == "mock":
        return {"ok": True, "mensaje": "Evaluador heurístico disponible (no usa red)."}
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}, "mensaje": {"type": "string"}}, "required": ["ok", "mensaje"]}
    try:
        r = crear_proveedor(ConfigModelo(**{**cfg.__dict__, "timeout_s": 60})).generar(
            "Responde solo JSON.", [{"role": "user", "content": 'Devuelve {"ok": true, "mensaje": "conectado"}'}], schema, "probar")
    except LLMError as exc:
        return {"ok": False, "mensaje": str(exc)}
    return {"ok": bool(r.datos.get("ok")), "mensaje": f"Respuesta en {r.duracion_ms} ms: {r.datos}"}


# ================================================================== auditoría
@router.get("/auditoria")
def auditoria(limite: int = Query(200, le=1000), entidad: str | None = None, entidad_id: int | None = None,
              _: User = Depends(require_docente), db: Session = Depends(get_db)):
    q = select(Auditoria).order_by(Auditoria.id.desc()).limit(limite)
    if entidad:
        q = q.where(Auditoria.entidad == entidad)
    if entidad_id:
        q = q.where(Auditoria.entidad_id == entidad_id)
    nombres = {u.id: u.nombre for u in db.scalars(select(User))}
    return [{"id": a.id, "fecha": a.created_at.isoformat(), "usuario": nombres.get(a.usuario_id, "—"), "accion": a.accion,
             "entidad": a.entidad, "entidad_id": a.entidad_id, "detalle": a.detalle} for a in db.scalars(q)]


@router.get("/salud")
def salud(db: Session = Depends(get_db)):
    db.execute(select(1))
    return {"ok": True, "app": get_settings().app_name}


@router.get("/verificaciones/{vid}")
def ver_verificacion(vid: int, doc: User = Depends(require_docente), db: Session = Depends(get_db)):
    v = db.get(Verificacion, vid)
    if not v:
        raise HTTPException(404, "No encontrada")
    return {"id": v.id, "entrega_id": v.entrega_id, "analisis": v.analisis, "pruebas": v.pruebas, "sandbox": v.sandbox}
