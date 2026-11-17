"""Ejecución aislada del código subido por estudiantes.

Modos (SANDBOX_MODE):
- docker : contenedor efímero, --network none, límites de memoria/CPU/procesos,
           sistema de archivos de solo lectura salvo /work y /tmp, usuario sin privilegios.
- unshare: espacio de nombres de red vacío (sin red) + límites de recursos del kernel
           (CPU, memoria, tamaño de archivos, descriptores) + entorno limpio.
- rlimit : solo límites de recursos + bloqueo de sockets en Python (aislamiento parcial;
           útil en plataformas que no permiten contenedores anidados).
- auto   : docker → unshare → rlimit, el primero disponible.

Siempre: copia temporal del código, timeout duro (se mata el grupo de procesos),
variables de entorno vacías (sin secretos) y salida truncada.
"""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path

from .config import get_settings

MAX_SALIDA = 20_000

_BLOQUEO_RED = '''
import socket as _s
class _SinRed(_s.socket):
    def connect(self, *a, **k):
        raise PermissionError("Red deshabilitada en el sandbox del Asesor Pedagógico")
    connect_ex = connect
    def sendto(self, *a, **k):
        raise PermissionError("Red deshabilitada en el sandbox del Asesor Pedagógico")
_s.socket = _SinRed
def _no(*a, **k):
    raise PermissionError("Red deshabilitada en el sandbox del Asesor Pedagógico")
_s.create_connection = _no
_s.getaddrinfo = _no
'''


@dataclass
class ResultadoSandbox:
    modo: str
    aislamiento: str  # completo | alto | parcial
    red: str
    codigo_salida: int | None
    tiempo_agotado: bool
    duracion_s: float
    salida: str
    limites: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return asdict(self)


@lru_cache
def _docker_disponible() -> bool:
    if not shutil.which("docker"):
        return False
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=10).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


@lru_cache
def _unshare_disponible() -> bool:
    if not shutil.which("unshare"):
        return False
    try:
        return subprocess.run(["unshare", "-rn", "true"], capture_output=True, timeout=10).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def modo_efectivo() -> str:
    s = get_settings()
    pedido = s.sandbox_mode
    if pedido == "docker" or (pedido == "auto" and _docker_disponible()):
        if _docker_disponible():
            return "docker"
        if pedido == "docker":
            raise RuntimeError("SANDBOX_MODE=docker pero Docker no está disponible.")
    if pedido in ("unshare", "auto") and _unshare_disponible():
        return "unshare"
    if pedido == "unshare":
        raise RuntimeError("SANDBOX_MODE=unshare pero el kernel no permite espacios de nombres de usuario.")
    if os.name == "nt":
        raise RuntimeError("El sandbox requiere Linux. En Windows ejecute la plataforma con Docker o WSL2 (ver docs/DESPLIEGUE_GRATIS.md).")
    if s.allow_rlimit_fallback or pedido == "rlimit":
        return "rlimit"
    raise RuntimeError("No hay un sandbox disponible y ALLOW_RLIMIT_FALLBACK=false.")


def _limites_kernel(mem_mb: int, cpu_s: int):
    def aplicar() -> None:  # se ejecuta en el hijo antes de exec
        import resource

        os.setsid()
        mem = mem_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_s, cpu_s + 1))
        resource.setrlimit(resource.RLIMIT_FSIZE, (50 * 1024 * 1024, 50 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

    return aplicar


def ejecutar(codigo_dir: Path, comando: list[str], timeout_s: int | None = None,
             rutas_python: list[str] | None = None) -> tuple[ResultadoSandbox, Path]:
    """Copia el código a un directorio temporal y ejecuta `comando` (relativo a la copia).

    Devuelve el resultado y la carpeta de trabajo (el llamador la borra tras leer reportes).
    """
    s = get_settings()
    timeout_s = timeout_s or s.sandbox_timeout_s
    modo = modo_efectivo()
    trabajo = Path(tempfile.mkdtemp(prefix="asesor_sbx_"))
    shutil.copytree(codigo_dir, trabajo / "work", symlinks=False)
    work = trabajo / "work"
    limites = {"timeout_s": timeout_s, "memoria_mb": s.sandbox_memory_mb, "cpus": s.sandbox_cpus}

    if modo == "docker":
        os.chmod(trabajo, 0o777)  # noqa: S103 - copia temporal; el contenedor corre como nobody
        for root, dirs, files in os.walk(work):
            for d in dirs:
                os.chmod(os.path.join(root, d), 0o777)  # noqa: S103
            for f in files:
                os.chmod(os.path.join(root, f), 0o666)  # noqa: S103
        cmd = [
            "docker", "run", "--rm", "--network", "none",
            "--memory", f"{s.sandbox_memory_mb}m", "--memory-swap", f"{s.sandbox_memory_mb}m",
            "--cpus", str(s.sandbox_cpus), "--pids-limit", "128",
            "--read-only", "--tmpfs", "/tmp:rw,size=64m",  # noqa: S108 - tmpfs dentro del contenedor "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--user", "65534:65534",
            "-v", f"{work}:/work:rw", "-w", "/work", "-e", "HOME=/tmp",
            "-e", "PYTHONPATH=" + ":".join(["/work"] + [f"/work/{r}" for r in (rutas_python or [])]),
            s.sandbox_image, *comando,
        ]
        preexec = None
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
        aislamiento, red = "completo", "deshabilitada (--network none)"
    else:
        sitedir = trabajo / "_site"
        sitedir.mkdir()
        (sitedir / "sitecustomize.py").write_text(_BLOQUEO_RED)
        env = {
            "PATH": os.path.dirname(sys.executable) + ":/usr/bin:/bin",
            "HOME": str(trabajo),
            "PYTHONPATH": ":".join([str(sitedir), str(work)] + [str(work / r) for r in (rutas_python or [])]),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0",
            "MPLBACKEND": "Agg",
        }
        comando = [sys.executable if c == "python" else c for c in comando]
        if modo == "unshare":
            cmd = ["unshare", "-rn", "--", *comando]
            aislamiento, red = "alto", "deshabilitada (namespace de red vacío)"
        else:
            cmd = comando
            aislamiento, red = "parcial", "bloqueada a nivel de Python (sitecustomize)"
        preexec = _limites_kernel(s.sandbox_memory_mb, timeout_s)

    inicio = time.monotonic()
    agotado = False
    try:
        proc = subprocess.Popen(
            cmd, cwd=work, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, preexec_fn=preexec,
        )
        try:
            out, _ = proc.communicate(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            agotado = True
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                proc.kill()
            out, _ = proc.communicate()
        rc = proc.returncode
    except OSError as exc:
        out, rc = f"No se pudo iniciar el sandbox: {exc}".encode(), None
    dur = round(time.monotonic() - inicio, 2)
    texto = out.decode("utf-8", errors="replace") if isinstance(out, bytes) else str(out)
    if len(texto) > MAX_SALIDA:
        texto = texto[:MAX_SALIDA // 2] + "\n[... salida truncada ...]\n" + texto[-MAX_SALIDA // 2:]
    return (
        ResultadoSandbox(modo=modo, aislamiento=aislamiento, red=red, codigo_salida=rc,
                         tiempo_agotado=agotado, duracion_s=dur, salida=texto, limites=limites),
        trabajo,
    )


def info_sandbox() -> dict:
    try:
        modo = modo_efectivo()
    except RuntimeError as exc:
        return {"modo": "no-disponible", "error": str(exc)}
    return {
        "modo": modo,
        "docker": _docker_disponible(),
        "unshare": _unshare_disponible(),
        "limites": {
            "timeout_s": get_settings().sandbox_timeout_s,
            "memoria_mb": get_settings().sandbox_memory_mb,
        },
    }
