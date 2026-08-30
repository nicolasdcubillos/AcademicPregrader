"""
code_runner.py — Compilador/ejecutor ligero para la vista previa de código.

Compila y ejecuta código de estudiantes (Python, C++ o Java) en un
subproceso aislado, con timeouts estrictos y (en POSIX) límites de recursos
best-effort (CPU, memoria, procesos). Pensado para uso interno de un
evaluador ya autenticado sobre entregas ya subidas — NO es un sandbox de
seguridad completo (no aísla red ni sistema de archivos por contenedor), así
que este endpoint nunca debe exponerse sin autenticación ni fuera del
entorno de ejecución propio de la app (contenedor Docker / máquina local del
evaluador).
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

# Mismo marcador que usa backend/academic-pregrader.py al concatenar
# múltiples archivos de una entrega: "// --- nombre.ext ---"
FILE_MARKER_RE = re.compile(r"^// --- (.*) ---$", re.MULTILINE)

LANG_BY_EXT = {
    ".py": "python", ".ipynb": "python",
    ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".c": "cpp",
    ".java": "java",
}

MAX_OUTPUT_CHARS = 20_000
COMPILE_TIMEOUT_S = 20
RUN_TIMEOUT_S = 10
# Tope de pared para una sesión de consola interactiva: más generoso que RUN_TIMEOUT_S
# porque incluye el tiempo que el evaluador tarda en escribir la entrada.
INTERACTIVE_RUN_TIMEOUT_S = 180
MAX_MEMORY_MB = 512
MAX_PROCS = 64


def _limit_resources():
    """preexec_fn (solo POSIX): topa CPU, memoria virtual, nº de procesos y tamaño de archivo."""
    try:
        import resource
        cpu = RUN_TIMEOUT_S + COMPILE_TIMEOUT_S
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
        mem = MAX_MEMORY_MB * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
        resource.setrlimit(resource.RLIMIT_NPROC, (MAX_PROCS, MAX_PROCS))
        resource.setrlimit(resource.RLIMIT_FSIZE, (10 * 1024 * 1024, 10 * 1024 * 1024))
    except Exception:
        pass  # best-effort; en Windows o si falla, seguimos solo con el timeout


def _truncate(s: Optional[str]) -> str:
    s = s or ""
    if len(s) > MAX_OUTPUT_CHARS:
        return s[:MAX_OUTPUT_CHARS] + "\n… [salida truncada]"
    return s


def _safe_name(name: str) -> str:
    """Evita path traversal: solo el nombre de archivo, sin subcarpetas."""
    return Path(name).name or "file"


def parse_files(code: str) -> dict[str, str]:
    """Separa el texto '// --- archivo ---' concatenado en {nombre: contenido}."""
    if not code or not FILE_MARKER_RE.search(code):
        return {"main": code or ""}
    parts = FILE_MARKER_RE.split(code)
    files: dict[str, str] = {}
    it = iter(parts[1:])
    for name, body in zip(it, it):
        files[name.strip()] = body.strip("\n")
    return files


def detect_language(files: dict[str, str]) -> Optional[str]:
    for name in files:
        lang = LANG_BY_EXT.get(Path(name).suffix.lower())
        if lang:
            return lang
    return None


def _run_proc(cmd, cwd, stdin_text, timeout):
    kwargs = dict(
        cwd=cwd, input=stdin_text, text=True, capture_output=True,
        encoding="utf-8", errors="replace", timeout=timeout,
    )
    if sys.platform != "win32":
        kwargs["preexec_fn"] = _limit_resources
    try:
        result = subprocess.run(cmd, **kwargs)
        return result.returncode, result.stdout, result.stderr, False
    except subprocess.TimeoutExpired as e:
        stdout = e.stdout or ""
        stderr = (e.stderr or "") + "\n[Tiempo de ejecución agotado]"
        return None, stdout, stderr, True
    except FileNotFoundError as e:
        return None, "", f"Herramienta no disponible en el servidor: {e}", False


def _result(lang, stage, rc, out, err, timed_out, started) -> dict:
    return {
        "ok": (rc == 0) and not timed_out,
        "language": lang,
        "stage": stage,  # "compile" | "run"
        "exit_code": rc,
        "stdout": _truncate(out),
        "stderr": _truncate(err),
        "timed_out": timed_out,
        "duration_ms": int((time.time() - started) * 1000),
    }


def _pick_main_python_file(py_files: dict[str, str]) -> Optional[str]:
    if not py_files:
        return None
    if len(py_files) == 1:
        return next(iter(py_files))
    for name, content in py_files.items():
        if "__main__" in content or name.lower() == "main.py":
            return name
    return sorted(py_files)[0]


def _pick_main_java_class(files: dict[str, str]) -> Optional[str]:
    for name, content in files.items():
        if not name.lower().endswith(".java"):
            continue
        if re.search(r"public\s+static\s+void\s+main\s*\(", content):
            m = re.search(r"\bclass\s+(\w+)", content)
            if m:
                return m.group(1)
    return None


def _write_and_compile_cpp(files, tmp_dir, started):
    """Escribe los .cpp y compila. Devuelve (exe_path, None) si compiló bien,
    o (None, error_result) si falló."""
    cpp_files = []
    if list(files.keys()) == ["main"]:
        Path(tmp_dir, "main.cpp").write_text(files["main"], encoding="utf-8")
        cpp_files = ["main.cpp"]
    else:
        for name, content in files.items():
            safe = _safe_name(name)
            Path(tmp_dir, safe).write_text(content, encoding="utf-8")
            if Path(safe).suffix.lower() in (".cpp", ".cc", ".cxx", ".c"):
                cpp_files.append(safe)
        if not cpp_files:
            return None, {"ok": False, "stage": "compile", "language": "cpp",
                     "exit_code": None, "stdout": "", "timed_out": False,
                     "stderr": "No se encontró ningún archivo .cpp para compilar.",
                     "duration_ms": int((time.time() - started) * 1000)}

    exe_name = "program.out"
    compile_cmd = ["g++", "-O2", "-std=c++17"] + cpp_files + ["-o", exe_name]
    rc, out, err, timed_out = _run_proc(compile_cmd, tmp_dir, None, COMPILE_TIMEOUT_S)
    if rc != 0 or timed_out:
        return None, _result("cpp", "compile", rc, out, err, timed_out, started)
    return str(Path(tmp_dir) / exe_name), None


def _write_and_compile_java(files, tmp_dir, started):
    """Escribe los .java y compila. Devuelve (main_class, None) si compiló bien,
    o (None, error_result) si falló."""
    java_files = []
    if list(files.keys()) == ["main"]:
        m = re.search(r"\bclass\s+(\w+)", files["main"])
        cls = m.group(1) if m else "Main"
        Path(tmp_dir, f"{cls}.java").write_text(files["main"], encoding="utf-8")
        java_files = [f"{cls}.java"]
    else:
        for name, content in files.items():
            safe = _safe_name(name)
            if not safe.lower().endswith(".java"):
                continue
            Path(tmp_dir, safe).write_text(content, encoding="utf-8")
            java_files.append(safe)
        if not java_files:
            return None, {"ok": False, "stage": "compile", "language": "java",
                     "exit_code": None, "stdout": "", "timed_out": False,
                     "stderr": "No se encontró ningún archivo .java para compilar.",
                     "duration_ms": int((time.time() - started) * 1000)}

    compile_cmd = ["javac", "-encoding", "UTF-8"] + java_files
    rc, out, err, timed_out = _run_proc(compile_cmd, tmp_dir, None, COMPILE_TIMEOUT_S)
    if rc != 0 or timed_out:
        return None, _result("java", "compile", rc, out, err, timed_out, started)
    main_class = _pick_main_java_class(files) or Path(java_files[0]).stem
    return main_class, None


def _run_python(files, tmp_dir, stdin_text, started) -> dict:
    py_files = {n: c for n, c in files.items() if Path(n).suffix.lower() in (".py", "")}
    if not py_files or list(files.keys()) == ["main"]:
        main_name = "main.py"
        Path(tmp_dir, main_name).write_text(files.get("main", ""), encoding="utf-8")
    else:
        for name, content in files.items():
            Path(tmp_dir, _safe_name(name)).write_text(content, encoding="utf-8")
        main_name = _pick_main_python_file(py_files) or next(iter(py_files))

    rc, out, err, timed_out = _run_proc(
        [sys.executable, "-u", main_name], tmp_dir, stdin_text, RUN_TIMEOUT_S
    )
    return _result("python", "run", rc, out, err, timed_out, started)


def _run_cpp(files, tmp_dir, stdin_text, started) -> dict:
    exe_path, err_result = _write_and_compile_cpp(files, tmp_dir, started)
    if err_result:
        return err_result

    rc, out, err, timed_out = _run_proc([exe_path], tmp_dir, stdin_text, RUN_TIMEOUT_S)
    return _result("cpp", "run", rc, out, err, timed_out, started)


def _run_java(files, tmp_dir, stdin_text, started) -> dict:
    main_class, err_result = _write_and_compile_java(files, tmp_dir, started)
    if err_result:
        return err_result

    rc, out, err, timed_out = _run_proc(
        ["java", "-cp", tmp_dir, main_class], tmp_dir, stdin_text, RUN_TIMEOUT_S
    )
    return _result("java", "run", rc, out, err, timed_out, started)


def run_code(code: str, stdin_text: str = "", language: Optional[str] = None) -> dict:
    """Compila (si aplica) y ejecuta el código dado. Devuelve un dict listo para jsonify()."""
    files = parse_files(code)
    lang = language or detect_language(files)
    if lang not in ("python", "cpp", "java"):
        return {"ok": False, "error": "No se pudo determinar el lenguaje (Python, C++ o Java)."}

    tmp_dir = tempfile.mkdtemp(prefix="pregrader_run_")
    started = time.time()
    try:
        if lang == "python":
            return _run_python(files, tmp_dir, stdin_text, started)
        if lang == "cpp":
            return _run_cpp(files, tmp_dir, stdin_text, started)
        return _run_java(files, tmp_dir, stdin_text, started)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def prepare_interactive(code: str, language: Optional[str] = None):
    """Prepara una ejecución *interactiva* (consola real, sin stdin precargado):
    escribe los archivos y compila si aplica, pero NO ejecuta el programa final —
    eso lo hace el llamador conectándolo a un pty para poder enviarle stdin
    mientras corre, igual que en una terminal normal.

    Devuelve un dict:
      {"ok": False, ...}                                  si falló la detección o compilación
      {"ok": True, "language": ..., "cmd": [...], "tmp_dir": ...}   si quedó listo para correr
    El llamador es responsable de limpiar tmp_dir en cualquier caso.
    """
    files = parse_files(code)
    lang = language or detect_language(files)
    if lang not in ("python", "cpp", "java"):
        return {"ok": False, "error": "No se pudo determinar el lenguaje (Python, C++ o Java)."}

    tmp_dir = tempfile.mkdtemp(prefix="pregrader_run_")
    started = time.time()

    if lang == "python":
        py_files = {n: c for n, c in files.items() if Path(n).suffix.lower() in (".py", "")}
        if not py_files or list(files.keys()) == ["main"]:
            main_name = "main.py"
            Path(tmp_dir, main_name).write_text(files.get("main", ""), encoding="utf-8")
        else:
            for name, content in files.items():
                Path(tmp_dir, _safe_name(name)).write_text(content, encoding="utf-8")
            main_name = _pick_main_python_file(py_files) or next(iter(py_files))
        return {"ok": True, "language": "python", "cmd": [sys.executable, "-u", main_name], "tmp_dir": tmp_dir}

    if lang == "cpp":
        exe_path, err_result = _write_and_compile_cpp(files, tmp_dir, started)
        if err_result:
            return {**err_result, "tmp_dir": tmp_dir}
        return {"ok": True, "language": "cpp", "cmd": [exe_path], "tmp_dir": tmp_dir}

    main_class, err_result = _write_and_compile_java(files, tmp_dir, started)
    if err_result:
        return {**err_result, "tmp_dir": tmp_dir}
    return {"ok": True, "language": "java", "cmd": ["java", "-cp", tmp_dir, main_class], "tmp_dir": tmp_dir}

