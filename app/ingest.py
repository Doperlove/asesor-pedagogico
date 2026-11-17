"""Ingesta segura de archivos: PDF del informe, código (ZIP o GitHub) y anexos opcionales."""
from __future__ import annotations

import hashlib
import io
import re
import shutil
import stat
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import httpx
from pypdf import PdfReader

from .config import get_settings

MIN_TEXTO_PDF = 300  # caracteres mínimos para considerar el PDF "de texto legible"
MAX_ZIP_ARCHIVOS = 3000
MAX_ZIP_DESCOMPRIMIDO = 80 * 1024 * 1024
IGNORAR_DIRS = {"__MACOSX", ".git", "node_modules", ".venv", "venv", "env", "__pycache__", ".idea", ".vscode", "dist", "build", ".mypy_cache", ".pytest_cache"}
EXT_CODIGO = {".py", ".ipynb", ".js", ".ts", ".tsx", ".jsx", ".java", ".kt", ".c", ".cpp", ".h", ".cs", ".go", ".rs", ".rb", ".php", ".sql", ".sh", ".html", ".css", ".md", ".toml", ".yaml", ".yml", ".json", ".txt", ".cfg", ".ini"}
GITHUB_RE = re.compile(r"^https://github\.com/(?P<owner>[A-Za-z0-9_.\-]{1,100})/(?P<repo>[A-Za-z0-9_.\-]{1,100}?)(?:\.git)?(?:/tree/(?P<ref>[A-Za-z0-9_.\-/]{1,200}))?/?$")
EXT_EXTRA = {".mp4", ".webm", ".mov", ".pptx", ".pdf", ".key", ".odp"}


class IngestaError(ValueError):
    """Error con mensaje apto para mostrar al usuario."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_dir(path: Path) -> str:
    h = hashlib.sha256()
    for f in sorted(p for p in path.rglob("*") if p.is_file()):
        h.update(str(f.relative_to(path)).encode())
        h.update(f.read_bytes())
    return h.hexdigest()


def nueva_carpeta(tipo: str) -> Path:
    base = get_settings().storage_dir / tipo / uuid.uuid4().hex
    base.mkdir(parents=True, exist_ok=False)
    return base


# ---------------------------------------------------------------- PDF
def procesar_pdf(data: bytes, nombre: str) -> tuple[Path, list[str], str]:
    if not data.startswith(b"%PDF"):
        raise IngestaError("El informe debe ser un archivo PDF válido.")
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise IngestaError("El PDF está protegido con contraseña; súbalo sin cifrar.")
        paginas = [(p.extract_text() or "").strip() for p in reader.pages]
    except IngestaError:
        raise
    except Exception as exc:  # pypdf lanza varios tipos
        raise IngestaError(f"No se pudo leer el PDF: {exc}") from exc
    texto = "\n".join(paginas)
    if len(re.sub(r"\s+", "", texto)) < MIN_TEXTO_PDF:
        raise IngestaError(
            "El PDF no tiene texto legible (parece escaneado o es una imagen). "
            "Exporte el informe desde Word/Docs como PDF con texto seleccionable."
        )
    carpeta = nueva_carpeta("informes")
    destino = carpeta / "informe.pdf"
    destino.write_bytes(data)
    return destino, paginas, sha256_bytes(data)


# ---------------------------------------------------------------- ZIP
@dataclass
class CodigoIngerido:
    path: Path
    sha256: str
    archivos: int
    origen: str
    ref: str | None = None
    commit: str | None = None


def _ruta_segura(nombre: str) -> PurePosixPath | None:
    p = PurePosixPath(nombre.replace("\\", "/"))
    if p.is_absolute() or ".." in p.parts or not p.parts:
        return None
    if any(part in IGNORAR_DIRS for part in p.parts):
        return None
    return p


def extraer_zip(data: bytes, origen: str = "zip", ref: str | None = None, commit: str | None = None) -> CodigoIngerido:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise IngestaError("El archivo de código no es un ZIP válido.") from exc
    infos = zf.infolist()
    if len(infos) > MAX_ZIP_ARCHIVOS:
        raise IngestaError(f"El ZIP tiene demasiados archivos ({len(infos)}; máximo {MAX_ZIP_ARCHIVOS}).")
    total = sum(i.file_size for i in infos)
    if total > MAX_ZIP_DESCOMPRIMIDO:
        raise IngestaError("El ZIP descomprimido supera 80 MB; quite datasets, binarios o entornos virtuales.")

    carpeta = nueva_carpeta("codigo")
    destino = carpeta / "src"
    destino.mkdir()
    n = 0
    for info in infos:
        # Los ZIP creados en Windows (Compress-Archive) marcan las carpetas con "\\" en vez de "/"
        if info.is_dir() or info.filename.endswith(("/", "\\")):
            continue
        # rechazar enlaces simbólicos (bits de modo Unix dentro del ZIP)
        if stat.S_ISLNK(info.external_attr >> 16):
            continue
        rel = _ruta_segura(info.filename)
        if rel is None:
            continue
        out = destino.joinpath(*rel.parts)
        if not out.resolve().is_relative_to(destino.resolve()):
            continue
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(out, "wb") as dst:
                shutil.copyfileobj(src, dst, length=1024 * 1024)
        except (NotADirectoryError, IsADirectoryError, FileExistsError):
            continue  # conflicto archivo/carpeta con el mismo nombre: se omite esa entrada
        n += 1
    if n == 0:
        shutil.rmtree(carpeta, ignore_errors=True)
        raise IngestaError("El ZIP no contiene archivos de código utilizables.")

    # Si todo quedó dentro de una sola carpeta raíz (típico de GitHub), aplanar
    hijos = list(destino.iterdir())
    if len(hijos) == 1 and hijos[0].is_dir():
        raiz = hijos[0]
        for item in raiz.iterdir():
            shutil.move(str(item), destino / item.name)
        raiz.rmdir()
    return CodigoIngerido(path=destino, sha256=sha256_dir(destino), archivos=n, origen=origen, ref=ref, commit=commit)


# ---------------------------------------------------------------- GitHub
def descargar_github(url: str) -> CodigoIngerido:
    """Descarga un repositorio público (o privado con GITHUB_TOKEN) fijando el commit exacto."""
    m = GITHUB_RE.match(url.strip())
    if not m:
        raise IngestaError("URL de GitHub inválida. Use https://github.com/usuario/repositorio (opcional /tree/rama).")
    owner, repo, ref = m["owner"], m["repo"], m["ref"]
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "asesor-pedagogico"}
    token = get_settings().github_token
    if token:
        headers["Authorization"] = f"Bearer {token}"
    api = f"https://api.github.com/repos/{owner}/{repo}"
    try:
        with httpx.Client(timeout=60, headers=headers, follow_redirects=True) as client:
            if not ref:
                info = client.get(api)
                if info.status_code == 404:
                    raise IngestaError("Repositorio no encontrado o privado.")
                info.raise_for_status()
                ref = info.json()["default_branch"]
            c = client.get(f"{api}/commits/{ref}")
            if c.status_code == 404:
                raise IngestaError(f"No existe la rama o commit '{ref}'.")
            c.raise_for_status()
            sha = c.json()["sha"]
            z = client.get(f"{api}/zipball/{sha}")
            z.raise_for_status()
            if len(z.content) > MAX_ZIP_DESCOMPRIMIDO:
                raise IngestaError("El repositorio es demasiado grande (más de 80 MB comprimido).")
    except httpx.HTTPError as exc:
        raise IngestaError(f"No se pudo descargar el repositorio: {exc}") from exc
    return extraer_zip(z.content, origen="github", ref=url.strip(), commit=sha)


# ---------------------------------------------------------------- Lectura de código para el LLM
def listar_codigo(path: Path) -> list[Path]:
    archivos = []
    for f in sorted(path.rglob("*")):
        if f.is_file() and f.suffix.lower() in EXT_CODIGO and f.stat().st_size < 400_000:
            archivos.append(f)
    return archivos


def codigo_con_lineas(path: Path, max_chars: int) -> tuple[str, dict[str, list[str]]]:
    """Texto con encabezado por archivo y números de línea; prioriza código fuente sobre datos."""
    prioridad = {".py": 0, ".ipynb": 1, ".java": 0, ".js": 0, ".ts": 0, ".md": 2, ".txt": 3, ".json": 4}
    archivos = sorted(listar_codigo(path), key=lambda f: (prioridad.get(f.suffix.lower(), 2), len(f.parts), str(f)))
    mapa: dict[str, list[str]] = {}
    partes: list[str] = []
    usado = 0
    for f in archivos:
        rel = str(f.relative_to(path))
        try:
            lineas = f.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        mapa[rel] = lineas
        bloque = f"### ARCHIVO: {rel}\n" + "\n".join(f"{i + 1:>4}| {ln}" for i, ln in enumerate(lineas)) + "\n"
        if usado + len(bloque) > max_chars:
            restante = max_chars - usado
            if restante > 500:
                partes.append(bloque[:restante] + "\n[... truncado ...]\n")
            partes.append(f"[Se omitieron archivos por límite de contexto: {len(archivos) - len(mapa)} restantes]")
            break
        partes.append(bloque)
        usado += len(bloque)
    return "\n".join(partes), mapa
