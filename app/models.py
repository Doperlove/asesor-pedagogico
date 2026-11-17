"""Modelo de datos.

Decisiones clave para la confianza:
- Las versiones de rúbrica son inmutables: editar crea una versión nueva.
- Cada entrega queda atada a la versión de rúbrica vigente al momento de subirla.
- Cada evaluación guarda modelo, parámetros, hashes de entrada/prompt, respuesta
  estructurada, evidencias verificadas y resultados de pruebas.
- La nota la calcula el backend; el docente aprueba o ajusta antes de publicar.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    nombre: Mapped[str] = mapped_column(String(200))
    rol: Mapped[str] = mapped_column(String(20))  # docente | estudiante
    password_hash: Mapped[str] = mapped_column(String(200))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Competencia(Base):
    """Catálogo de competencias / resultados de aprendizaje del curso."""

    __tablename__ = "competencias"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(30), unique=True)
    nombre: Mapped[str] = mapped_column(String(300))
    descripcion: Mapped[str] = mapped_column(Text, default="")


class Cohorte(Base):
    __tablename__ = "cohortes"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))
    orden: Mapped[int] = mapped_column(Integer, default=1)
    descripcion: Mapped[str] = mapped_column(Text, default="")
    laboratorios: Mapped[list[Laboratorio]] = relationship(back_populates="cohorte", order_by="Laboratorio.orden")


class Laboratorio(Base):
    __tablename__ = "laboratorios"

    id: Mapped[int] = mapped_column(primary_key=True)
    cohorte_id: Mapped[int] = mapped_column(ForeignKey("cohortes.id"))
    nombre: Mapped[str] = mapped_column(String(200))
    descripcion: Mapped[str] = mapped_column(Text, default="")
    orden: Mapped[int] = mapped_column(Integer, default=1)
    requiere_codigo: Mapped[bool] = mapped_column(Boolean, default=True)
    cohorte: Mapped[Cohorte] = relationship(back_populates="laboratorios")


class Rubrica(Base):
    """Una versión inmutable de la rúbrica de un laboratorio."""

    __tablename__ = "rubricas"
    __table_args__ = (UniqueConstraint("laboratorio_id", "version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    laboratorio_id: Mapped[int] = mapped_column(ForeignKey("laboratorios.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    contenido: Mapped[dict] = mapped_column(JSON)
    sha256: Mapped[str] = mapped_column(String(64))
    valida: Mapped[bool] = mapped_column(Boolean, default=False)
    errores: Mapped[list] = mapped_column(JSON, default=list)
    advertencias: Mapped[list] = mapped_column(JSON, default=list)
    activa: Mapped[bool] = mapped_column(Boolean, default=False)
    origen: Mapped[str] = mapped_column(String(30), default="json")  # json | formulario | documento
    creada_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Entrega(Base):
    __tablename__ = "entregas"

    id: Mapped[int] = mapped_column(primary_key=True)
    laboratorio_id: Mapped[int] = mapped_column(ForeignKey("laboratorios.id"), index=True)
    estudiante_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    rubrica_id: Mapped[int] = mapped_column(ForeignKey("rubricas.id"))
    subida_por_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))

    pdf_nombre: Mapped[str] = mapped_column(String(255))
    pdf_path: Mapped[str] = mapped_column(String(500))
    pdf_sha256: Mapped[str] = mapped_column(String(64))
    pdf_paginas: Mapped[list] = mapped_column(JSON, default=list)  # texto por página

    codigo_origen: Mapped[str | None] = mapped_column(String(20), nullable=True)  # zip | github
    codigo_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    codigo_commit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    codigo_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    codigo_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    codigo_archivos: Mapped[int] = mapped_column(Integer, default=0)

    extra_url: Mapped[str | None] = mapped_column(String(500), nullable=True)  # video / presentación
    extra_nombre: Mapped[str | None] = mapped_column(String(255), nullable=True)
    extra_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    estado: Mapped[str] = mapped_column(String(20), default="cargada")  # cargada|verificada|evaluada|publicada
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    laboratorio: Mapped[Laboratorio] = relationship()
    estudiante: Mapped[User] = relationship(foreign_keys=[estudiante_id])
    rubrica: Mapped[Rubrica] = relationship()


class Verificacion(Base):
    """Resultado de comprobaciones objetivas sobre el código."""

    __tablename__ = "verificaciones"

    id: Mapped[int] = mapped_column(primary_key=True)
    entrega_id: Mapped[int] = mapped_column(ForeignKey("entregas.id"), index=True)
    analisis: Mapped[dict] = mapped_column(JSON, default=dict)
    pruebas: Mapped[dict] = mapped_column(JSON, default=dict)
    sandbox: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Evaluacion(Base):
    __tablename__ = "evaluaciones"

    id: Mapped[int] = mapped_column(primary_key=True)
    entrega_id: Mapped[int] = mapped_column(ForeignKey("entregas.id"), index=True)
    rubrica_id: Mapped[int] = mapped_column(ForeignKey("rubricas.id"))
    verificacion_id: Mapped[int | None] = mapped_column(ForeignKey("verificaciones.id"), nullable=True)

    # Trazabilidad del modelo
    proveedor: Mapped[str] = mapped_column(String(30))
    modelo: Mapped[str] = mapped_column(String(120))
    parametros: Mapped[dict] = mapped_column(JSON, default=dict)
    schema_version: Mapped[str] = mapped_column(String(20))
    prompt_sha256: Mapped[str] = mapped_column(String(64))
    entrada_sha256: Mapped[str] = mapped_column(String(64))
    intentos: Mapped[int] = mapped_column(Integer, default=1)
    duracion_ms: Mapped[int] = mapped_column(Integer, default=0)
    uso_tokens: Mapped[dict] = mapped_column(JSON, default=dict)

    respuesta_llm: Mapped[dict] = mapped_column(JSON)  # salida validada con Pydantic
    resultado: Mapped[dict] = mapped_column(JSON)  # criterios con niveles, puntajes y evidencias verificadas
    alertas: Mapped[list] = mapped_column(JSON, default=list)
    confianza: Mapped[float] = mapped_column(Float, default=0.0)  # % evidencias verificadas

    nota_preliminar: Mapped[float] = mapped_column(Float)
    nota_final: Mapped[float | None] = mapped_column(Float, nullable=True)
    estado: Mapped[str] = mapped_column(String(20), default="preliminar")  # preliminar | publicada | descartada
    decision: Mapped[str | None] = mapped_column(String(20), nullable=True)  # aprobada | ajustada
    ajustes: Mapped[dict] = mapped_column(JSON, default=dict)  # criterio_id -> nivel_id
    justificacion_docente: Mapped[str | None] = mapped_column(Text, nullable=True)
    comentario_docente: Mapped[str | None] = mapped_column(Text, nullable=True)
    revisada_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    revisada_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    entrega: Mapped[Entrega] = relationship()
    rubrica: Mapped[Rubrica] = relationship()


class Ajuste(Base):
    """Configuración editable en caliente (p. ej. el conector de modelo)."""

    __tablename__ = "ajustes"

    clave: Mapped[str] = mapped_column(String(80), primary_key=True)
    valor: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Auditoria(Base):
    __tablename__ = "auditoria"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    accion: Mapped[str] = mapped_column(String(80), index=True)
    entidad: Mapped[str] = mapped_column(String(40))
    entidad_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detalle: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
