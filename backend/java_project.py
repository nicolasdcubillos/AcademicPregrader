"""
java_project.py — Soporte para calificar proyectos Java completos.

Una entrega Java típica es un proyecto (Maven/IntelliJ/Eclipse) comprimido en
un .zip/.rar dentro de la carpeta del estudiante. Este módulo se encarga de:

  * extraer los archivos comprimidos anidados,
  * descartar el ruido (.idea, target, __MACOSX, src/test, ...),
  * localizar las fuentes respetando la estructura de paquetes,
  * compilar el proyecto completo y ejecutar la clase principal,
  * elegir la entrega más reciente cuando un estudiante entregó varias veces.

Es independiente del resto del pregrader (sin dependencias externas) para
poder probarlo de forma aislada.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Optional

ARCHIVE_EXTS = (".zip", ".rar", ".7z")
EXTRACT_DIR = "_extracted"

# Carpetas que nunca forman parte del código del estudiante.
NOISE_DIRS = {
    "__macosx", ".idea", ".git", ".vscode", ".settings", ".gradle", ".mvn",
    "target", "build", "out", "bin", "test-classes", "node_modules",
}

MAX_EXTRACT_BYTES = 200 * 1024 * 1024
MAX_ARCHIVE_DEPTH = 2
COMPILE_TIMEOUT_S = 60
RUN_TIMEOUT_S = 10
MAX_OUTPUT_CHARS = 4000
MAX_ERROR_CHARS = 2000

_MAIN_RE = re.compile(r"public\s+static\s+void\s+main\s*\(")
_PACKAGE_RE = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.MULTILINE)
_CLASS_RE = re.compile(r"\b(?:class|enum|record|interface)\s+(\w+)")
_PREFERRED_MAIN_NAMES = ("main", "app", "application")


# ==============================
# EXTRACCIÓN DE ARCHIVOS COMPRIMIDOS
# ==============================

def _external_extractor(archive: Path, dest: Path) -> Optional[str]:
    """Extrae .rar/.7z con una herramienta externa. Devuelve None si OK o el error."""
    candidates = [
        ["7z", "x", "-y", f"-o{dest}", str(archive)],
        ["7za", "x", "-y", f"-o{dest}", str(archive)],
        ["unrar", "x", "-y", str(archive), str(dest) + "/"],
        ["bsdtar", "-xf", str(archive), "-C", str(dest)],
        ["tar", "-xf", str(archive), "-C", str(dest)],
    ]
    for cmd in candidates:
        if shutil.which(cmd[0]) is None:
            continue
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120,
                                    encoding="utf-8", errors="replace")
        except (subprocess.TimeoutExpired, OSError) as exc:
            return str(exc)
        if result.returncode == 0:
            return None
    return f"no hay un extractor disponible para {archive.suffix} (instala 7z)"


def _extract_zip(archive: Path, dest: Path) -> Optional[str]:
    try:
        with zipfile.ZipFile(archive) as zf:
            members = [m for m in zf.infolist()
                       if not m.filename.startswith("__MACOSX/")]
            if sum(m.file_size for m in members) > MAX_EXTRACT_BYTES:
                return "el archivo descomprimido excede el tamaño máximo permitido"
            dest_root = dest.resolve()
            for member in members:
                target = (dest / member.filename).resolve()
                if dest_root != target and dest_root not in target.parents:
                    continue  # zip-slip: ignorar rutas fuera del destino
                zf.extract(member, dest)
    except zipfile.BadZipFile:
        return "ZIP corrupto o inválido"
    except Exception as exc:
        return str(exc)
    return None


def extract_nested_archives(folder: Path, depth: int = 0) -> list:
    """Extrae los .zip/.rar/.7z dentro de la carpeta de un estudiante.

    El contenido queda en '<folder>/_extracted/<nombre>/'. Devuelve mensajes
    de log. Procesa archivos anidados hasta MAX_ARCHIVE_DEPTH niveles.
    """
    logs = []
    if depth >= MAX_ARCHIVE_DEPTH:
        return logs
    archives = sorted(
        f for f in folder.rglob("*")
        if f.is_file() and f.suffix.lower() in ARCHIVE_EXTS
        and not any(p.lower() in NOISE_DIRS for p in f.relative_to(folder).parts[:-1])
    )
    for archive in archives:
        dest = folder / EXTRACT_DIR / archive.stem
        n = 1
        while dest.exists():
            n += 1
            dest = folder / EXTRACT_DIR / f"{archive.stem}_{n}"
        dest.mkdir(parents=True)
        if archive.suffix.lower() == ".zip":
            error = _extract_zip(archive, dest)
        else:
            error = _external_extractor(archive, dest)
        if error:
            logs.append(f"  -> No se pudo extraer {archive.name}: {error}")
            shutil.rmtree(dest, ignore_errors=True)
            continue
        logs.append(f"  -> Archivo comprimido extraído: {archive.name}")
        try:
            archive.unlink()
        except OSError:
            pass
        logs.extend(extract_nested_archives(dest, depth + 1))
    return logs


# ==============================
# LIMPIEZA Y LOCALIZACIÓN DE FUENTES
# ==============================

def is_noise_path(rel_parts) -> bool:
    """True si la ruta (relativa a la carpeta del estudiante) es ruido de IDE/build/tests."""
    dirs = [p.lower() for p in rel_parts[:-1]]
    if any(d in NOISE_DIRS for d in dirs):
        return True
    for i, d in enumerate(dirs[:-1]):
        if d == "src" and dirs[i + 1] == "test":
            return True
    return False


def prune_noise(folder: Path) -> int:
    """Elimina del disco carpetas de ruido y tests. Devuelve cuántas se borraron."""
    removed = 0
    for path in sorted(folder.rglob("*"), key=lambda p: len(p.parts)):
        if not path.is_dir() or not path.exists():
            continue
        rel = path.relative_to(folder).parts
        if is_noise_path(rel + ("_",)):
            shutil.rmtree(path, ignore_errors=True)
            removed += 1
    return removed


def find_java_sources(folder: Path) -> list:
    """Todos los .java del proyecto, sin ruido (IDE/build/tests)."""
    return sorted(
        f for f in folder.rglob("*.java")
        if f.is_file()
        and not f.name.startswith(".")
        and not is_noise_path(f.relative_to(folder).parts)
    )


def rel_label(folder: Path, file: Path) -> str:
    """Ruta legible del archivo dentro del proyecto (desde 'src/' si existe)."""
    parts = file.relative_to(folder).parts
    if "src" in parts[:-1]:
        parts = parts[parts.index("src"):]
    elif parts[0] == EXTRACT_DIR and len(parts) > 2:
        parts = parts[2:]
    return PurePosixPath(*parts).as_posix()


# ==============================
# COMPILACIÓN Y EJECUCIÓN
# ==============================

def _clean_compile_errors(stderr: str, folder: Path) -> str:
    text = (stderr or "").replace(str(folder) + "\\", "").replace(str(folder) + "/", "")
    text = text.strip()
    if len(text) > MAX_ERROR_CHARS:
        text = text[:MAX_ERROR_CHARS] + "\n… [truncado]"
    return text


def compile_java(folder: Path, files: list, out_dir: Path) -> tuple:
    """Compila todas las fuentes juntas hacia out_dir. Retorna (ok, error_msg)."""
    if not files:
        return False, "No se encontraron archivos .java"
    out_dir.mkdir(parents=True, exist_ok=True)
    base = ["javac", "-proc:none", "-nowarn", "-d", str(out_dir)]
    stderr = ""
    for encoding in ("UTF-8", "windows-1252"):
        cmd = base + ["-encoding", encoding] + [str(f) for f in files]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True,
                                    encoding="utf-8", errors="replace",
                                    timeout=COMPILE_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            return False, "Tiempo de compilación agotado"
        except FileNotFoundError:
            return False, "javac no está disponible en el servidor"
        if result.returncode == 0:
            return True, ""
        stderr = result.stderr
        if "unmappable character" not in stderr:
            break
    return False, _clean_compile_errors(stderr, folder)


def class_name_for(source: str, filename_stem: str) -> str:
    m = re.search(r"\bpublic\s+(?:final\s+|abstract\s+)*(?:class|enum|record)\s+(\w+)", source)
    if m:
        return m.group(1)
    m = _CLASS_RE.search(source)
    return m.group(1) if m else filename_stem


def find_main_classes(files: list) -> list:
    """Nombres completos (paquete.Clase) de las clases con main(), la más probable primero."""
    found = []
    for f in files:
        try:
            src = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        src = re.sub(r"/\*.*?\*/|//[^\n]*", "", src, flags=re.DOTALL)
        if not _MAIN_RE.search(src):
            continue
        pkg = _PACKAGE_RE.search(src)
        cls = class_name_for(src, f.stem)
        found.append(f"{pkg.group(1)}.{cls}" if pkg else cls)

    def rank(fqcn):
        simple = fqcn.rsplit(".", 1)[-1].lower()
        priority = _PREFERRED_MAIN_NAMES.index(simple) if simple in _PREFERRED_MAIN_NAMES else len(_PREFERRED_MAIN_NAMES)
        return (priority, fqcn)

    return sorted(dict.fromkeys(found), key=rank)


def _limit_resources():
    try:
        import resource
        cpu = RUN_TIMEOUT_S + 5
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
        resource.setrlimit(resource.RLIMIT_FSIZE, (10 * 1024 * 1024, 10 * 1024 * 1024))
    except Exception:
        pass


def _kill_tree(proc: subprocess.Popen) -> None:
    """Mata el proceso y sus hijos (en Windows 'java' es un shim que lanza otro proceso)."""
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           capture_output=True, timeout=10)
        else:
            import os
            import signal
            os.killpg(proc.pid, signal.SIGKILL)
    except Exception:
        pass
    try:
        proc.kill()
    except Exception:
        pass


def _truncate(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    text = text or ""
    return text if len(text) <= limit else text[:limit] + "\n… [salida truncada]"


def run_java_main(out_dir: Path, main_class: str, timeout: int = RUN_TIMEOUT_S) -> dict:
    """Ejecuta la clase principal sin entrada (stdin cerrado) y captura la salida."""
    kwargs = dict(stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                  text=True, encoding="utf-8", errors="replace")
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["preexec_fn"] = _limit_resources
        kwargs["start_new_session"] = True
    cmd = ["java", "-Xmx256m", "-XX:+UseSerialGC", "-Dfile.encoding=UTF-8",
           "-Dstdout.encoding=UTF-8", "-Dstderr.encoding=UTF-8",
           "-cp", str(out_dir), main_class]
    with tempfile.TemporaryDirectory(prefix="pregrader_java_run_") as cwd:
        try:
            proc = subprocess.Popen(cmd, cwd=cwd, **kwargs)
        except FileNotFoundError:
            return {"ok": False, "timed_out": False, "exit_code": None,
                    "stdout": "", "stderr": "java no está disponible en el servidor"}
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
            try:
                stdout, stderr = proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                stdout, stderr = "", ""
            return {"ok": False, "timed_out": True, "exit_code": None,
                    "stdout": _truncate(stdout), "stderr": _truncate(stderr)}
    return {"ok": proc.returncode == 0, "timed_out": False, "exit_code": proc.returncode,
            "stdout": _truncate(stdout), "stderr": _truncate(stderr)}


def describe_run(main_class: str, run: dict) -> str:
    """Texto para el LLM con el resultado de ejecutar la clase principal."""
    lines = [f"Clase principal ejecutada: {main_class}"]
    if run.get("timed_out"):
        lines.append(f"La ejecución excedió el límite de {RUN_TIMEOUT_S}s y fue detenida.")
    elif run.get("exit_code") not in (0, None):
        lines.append(f"La ejecución terminó con código de salida {run['exit_code']}.")
    lines.append("SALIDA ESTÁNDAR:")
    lines.append(run.get("stdout", "").strip() or "(sin salida)")
    if run.get("stderr", "").strip():
        lines.append("SALIDA DE ERROR:")
        lines.append(run["stderr"].strip())
    return "\n".join(lines)


# ==============================
# ENTREGAS MÚLTIPLES DEL MISMO ESTUDIANTE
# ==============================

_MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}
_DATE_RE = re.compile(
    r"(\d{1,2})\s+de\s+([a-záéíóú]+)(?:\s+de)?\s*(\d{4})?\s+(\d{2})(\d{2})\s*$",
    re.IGNORECASE,
)


def parse_submission_datetime(folder_name: str) -> tuple:
    """(año, mes, día, hora, minuto) desde '... - 22 de octubre de 2026 2212'; () si no se puede."""
    last = folder_name.rsplit(" - ", 1)[-1].strip()
    m = _DATE_RE.search(last)
    if not m or m.group(2).lower() not in _MONTHS:
        return ()
    year = int(m.group(3)) if m.group(3) else 0
    return (year, _MONTHS[m.group(2).lower()], int(m.group(1)), int(m.group(4)), int(m.group(5)))


def keep_latest_submissions(folders: list, student_of) -> tuple:
    """Deja una sola carpeta por estudiante: la entrega más reciente.

    student_of(folder) -> nombre del estudiante. Retorna (conservadas, descartadas),
    ambas en el orden original.
    """
    best: dict = {}
    for folder in folders:
        key = student_of(folder).strip().lower()
        stamp = parse_submission_datetime(folder.name)
        current = best.get(key)
        if current is None or (stamp, folder.name) > (current[0], current[1].name):
            best[key] = (stamp, folder)
    kept_set = {id(v[1]) for v in best.values()}
    kept = [f for f in folders if id(f) in kept_set]
    dropped = [f for f in folders if id(f) not in kept_set]
    return kept, dropped
