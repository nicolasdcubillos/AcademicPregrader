import os
import sys
import subprocess
import csv
import json
import hashlib
import zipfile
import configparser
import threading
import tempfile
import shutil
import time
import concurrent.futures
from pathlib import Path
import pdfplumber

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')


# ==============================
# CONFIGURACIÓN DE LENGUAJES
# ==============================

# Cada entrada define: extensiones de archivo fuente, lenguaje JPlag, y tipo de compilación
LANG_CONFIG = {
    "cpp":    {"src_ext": (".cpp", ".cc", ".cxx"), "jplag": "cpp",     "compile": "cpp"},
    "java":   {"src_ext": (".java",),               "jplag": "java",    "compile": "java"},
    "python": {"src_ext": (".py",),                 "jplag": "python3", "compile": "python"},
    "pdf":    {"src_ext": (".pdf",),                "jplag": "text",    "compile": None},
}
# Orden de prioridad para detección automática
LANG_PRIORITY = ["cpp", "java", "python", "pdf"]

LANG_LABELS = {
    "cpp":    "C++",
    "java":   "Java",
    "python": "Python",
    "pdf":    "PDF",
    "auto":   "Automático",
}


def detect_language(carpeta: Path) -> str | None:
    """Detecta el lenguaje de una entrega según los archivos presentes."""
    for lang in LANG_PRIORITY:
        exts = LANG_CONFIG[lang]["src_ext"]
        files = [f for f in carpeta.rglob("*")
                 if f.suffix.lower() in exts and not f.name.startswith(".")]
        if files:
            return lang
    return None


def find_submission_files(carpeta: Path, lang: str) -> list:
    """Retorna todos los archivos fuente de una entrega para el lenguaje dado."""
    exts = LANG_CONFIG[lang]["src_ext"]
    return sorted(
        f for f in carpeta.rglob("*")
        if f.suffix.lower() in exts and not f.name.startswith(".")
    )


# ==============================
# UTILIDADES
# ==============================

REQUIRED_KEYS = {"logica", "nota_final", "comentario"}


def clamp(n, min_val=0.0, max_val=5.0):
    return max(min_val, min(n, max_val))


def parse_student_name(folder_name: str) -> str:
    """Extrae el nombre del formato '160684-359120 - MARIA CASAS - 16 de marzo 2337'."""
    parts = folder_name.split(' - ')
    if len(parts) >= 2:
        return parts[1].strip().title()
    return folder_name


def normalize_code(code: str) -> str:
    code = code.lstrip('﻿')
    code = code.replace('\r\n', '\n').replace('\r', '\n')
    lines = [line.rstrip() for line in code.split('\n')]
    return '\n'.join(lines).strip()


def compute_evaluation_key(code: str, enunciado: str) -> str:
    h = hashlib.sha256()
    h.update(code.encode('utf-8'))
    h.update(enunciado.encode('utf-8'))
    return h.hexdigest()


def load_cache(cache_path: Path) -> dict:
    if cache_path.exists():
        try:
            return json.loads(cache_path.read_text(encoding='utf-8'))
        except Exception:
            print("  -> Advertencia: caché corrupta, se ignorará")
    return {}


def save_cache(cache_path: Path, cache: dict):
    cache_path.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2),
        encoding='utf-8'
    )


# ==============================
# EJECUTOR DE SUBPROCESOS
# ==============================

def run(cmd, input_text=None):
    return subprocess.run(
        cmd,
        input=input_text,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace"
    )


# ==============================
# EXTRACCIÓN DE TEXTO
# ==============================

def extract_pdf_text(pdf_path) -> str:
    """Extrae texto de un PDF (enunciado o entrega)."""
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"No se encontró: {pdf_path}")
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text += page.extract_text() or ""
    return text


def extract_submission_text(files: list, lang: str) -> str:
    """Extrae el contenido de una entrega para enviarlo al LLM."""
    if lang == "pdf":
        parts = []
        for f in files:
            try:
                parts.append(extract_pdf_text(str(f)))
            except Exception as e:
                parts.append(f"[Error leyendo PDF {f.name}: {e}]")
        return "\n\n".join(parts)
    else:
        parts = []
        for f in files:
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
                parts.append(f"// --- {f.name} ---\n{normalize_code(content)}")
            except Exception as e:
                parts.append(f"// Error leyendo {f.name}: {e}")
        return "\n\n".join(parts)


# ==============================
# COMPILACIÓN
# ==============================

def compile_submission(carpeta: Path, files: list, lang: str) -> tuple:
    """
    Intenta compilar la entrega según el lenguaje.
    Retorna (success: bool, error_msg: str).
    """
    if lang == "cpp":
        src = files[0]
        exe = src.with_suffix(".exe")
        result = run(["g++", str(src), "-o", str(exe)])
        return (result.returncode == 0, result.stderr)

    elif lang == "java":
        java_files = [str(f) for f in files]
        result = run(["javac", "-encoding", "UTF-8", "-d", str(carpeta)] + java_files)
        return (result.returncode == 0, result.stderr)

    elif lang == "python":
        errors = []
        for f in files[:5]:  # verificar hasta 5 archivos principales
            result = run(["python3", "-m", "py_compile", str(f)])
            if result.returncode != 0:
                errors.append(result.stderr.strip())
        return (len(errors) == 0, "\n".join(errors))

    # pdf y desconocidos no compilan
    return (True, "")


# ==============================
# DETECCIÓN DE PLAGIO (JPlag 6.x)
# ==============================

def _get_java_version() -> tuple:
    try:
        result = subprocess.run(
            ["java", "-version"],
            capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        output = (result.stderr or result.stdout or "").strip()
        return True, output
    except FileNotFoundError:
        return False, ""


JPLAG_MIN_JAVA = 25  # JPlag 6.3.0 requiere Java 25 (class file 69.0)


def _check_java_version(verbose: bool = True) -> bool:
    found, version_str = _get_java_version()
    if not found:
        if verbose:
            print(f"  -> Java no encontrado en PATH. JPlag requiere Java {JPLAG_MIN_JAVA}+.")
        return False

    import re
    match = re.search(r'"(\d+)[\._]', version_str)
    if not match:
        return True  # dejar que JPlag falle si hay problema

    major = int(match.group(1))
    if major == 1:
        match2 = re.search(r'"1\.(\d+)', version_str)
        major = int(match2.group(1)) if match2 else 8

    if major < JPLAG_MIN_JAVA:
        if verbose:
            print(f"  -> Java {major} detectado — JPlag requiere Java {JPLAG_MIN_JAVA}+.")
        return False
    return True


def run_plagiarism_check(base_path: Path, jplag_jar: str, threshold: float,
                         jplag_lang: str = "cpp") -> dict | None:
    """
    Ejecuta JPlag sobre base_path con el lenguaje indicado.
    Retorna dict {carpeta_name: {"con_quien": str, "porcentaje": float}}
    o None si JPlag falló.
    """
    if not _check_java_version(verbose=True):
        return None

    output_stem = base_path / ".jplag_results"
    output_file = base_path / ".jplag_results.jplag"
    for f in [output_stem, output_file]:
        if f.exists():
            f.unlink()

    cmd = [
        "java", "-jar", jplag_jar,
        str(base_path),
        "-l", jplag_lang,
        "--result-file", str(output_stem),
        "--cluster-skip",
    ]

    result = run(cmd)

    if result.returncode != 0:
        print("  -> Error ejecutando JPlag")
        stderr_out = result.stderr[:600]
        if 'UnsupportedClassVersionError' in stderr_out:
            print(f"  -> JPlag requiere Java {JPLAG_MIN_JAVA}+.")
        else:
            print(stderr_out)
        return None

    if not output_file.exists():
        print("  -> JPlag no generó archivo de resultados")
        return None

    try:
        with zipfile.ZipFile(output_file, "r") as zf:
            if "topComparisons.json" not in zf.namelist():
                print("  -> No se encontró topComparisons.json en resultados de JPlag")
                return None
            comparisons = json.loads(zf.read("topComparisons.json").decode("utf-8"))
    except Exception as e:
        print("  -> Error leyendo resultados de JPlag:", e)
        return None

    plagio_map = {}
    for comp in comparisons:
        student_a = comp.get("firstSubmission",  comp.get("first_submission",  ""))
        student_b = comp.get("secondSubmission", comp.get("second_submission", ""))
        similarities = comp.get("similarities", {})
        similarity = similarities.get("AVG", next(iter(similarities.values()), 0.0))

        if similarity >= threshold:
            pct = round(similarity * 100, 1)
            for student, partner in [(student_a, student_b), (student_b, student_a)]:
                existing = plagio_map.get(student)
                if existing is None or existing["porcentaje"] < pct:
                    plagio_map[student] = {"con_quien": partner, "porcentaje": pct}

    return plagio_map


# ==============================
# EVALUACIÓN CON LLM
# ==============================

_EVAL_SYSTEM_INSTRUCTION = (
    "Eres un evaluador universitario. "
    "Califica ÚNICAMENTE si la solución resuelve correctamente el problema según el enunciado. "
    "Nada más importa: ni estilo, ni nombres, ni indentación, ni comentarios. "
    "Sé generoso: en caso de duda, favorece al estudiante. "
    "Con los mismos inputs siempre produces la misma calificación."
)
_EVAL_RULES = """REGLAS:
- logica === nota_final: misma nota de 0.0 a 5.0, un decimal.
- Penaliza SOLO errores que producen resultados incorrectos o funcionalidad faltante.
- Ignora completamente: estilo, indentación, nombres de variables, comentarios, optimizaciones.
- Sé generoso: solución que resuelve el problema en esencia → nota ≥ 4.0.
- Solo baja de 3.0 si hay errores lógicos graves o funcionalidad central ausente.
- Si la nota es 5.0, el campo "comentario" debe ser "" (string vacío).
- comentario: 1-2 frases si la nota es < 5.0. Qué funciona y qué falla. Sin mencionar estilo.

ESCALA DE REFERENCIA:
5.0 → resuelve correctamente todos los casos del enunciado
4.0 → resuelve ~80% de los casos correctamente
3.0 → resuelve la mitad con errores moderados
2.0 → intento parcial con errores graves
1.0 → muy poco funciona
0.0 → no resuelve nada del enunciado"""


def _build_eval_prompt(code, enunciado):
    return f"""Evalúa la solución. Responde SOLO con este JSON (sin texto extra):
{{"logica": X.X, "nota_final": X.X, "comentario": "..."}}

{_EVAL_RULES}

ENUNCIADO:
{enunciado}

SOLUCIÓN:
{code}
"""


def _validate_eval_data(data):
    KEY_ALIASES = {
        "logica":     ["logica", "logic", "lógica", "logics"],
        "nota_final": ["nota_final", "note_final", "final_note", "final_grade",
                       "nota", "grade", "total", "score"],
        "comentario": ["comentario", "commentary", "comment", "comments",
                       "comentarios", "feedback"],
    }
    normalized = {}
    data_lower = {k.lower(): v for k, v in data.items()}
    for canonical, aliases in KEY_ALIASES.items():
        for alias in aliases:
            if alias in data_lower:
                normalized[canonical] = data_lower[alias]
                break
    for k, v in data_lower.items():
        if k not in normalized:
            normalized[k] = v

    if "nota_final" not in normalized and "logica" in normalized:
        normalized["nota_final"] = normalized["logica"]

    missing = REQUIRED_KEYS - normalized.keys()
    if missing:
        raise ValueError(f"Claves faltantes en JSON: {missing}")
    for key in ("logica", "nota_final"):
        float(normalized[key])
    return normalized


def _llm_evaluate_gemini(code, enunciado, model, api_key, max_retries=5):
    try:
        import google.generativeai as genai
    except ImportError:
        print("  -> Error: 'google-generativeai' no está instalado.")
        return None

    if not api_key:
        print("  -> Error: gemini_api_key no configurada.")
        print("  -> Configúrala en Configuración → API Key.")
        return None

    genai.configure(api_key=api_key)
    generation_config = {
        "temperature": 0.0, "top_p": 1.0, "top_k": 1,
        "max_output_tokens": 1024,
        "response_mime_type": "application/json",
    }
    gemini_model = genai.GenerativeModel(
        model_name=model,
        generation_config=generation_config,
        system_instruction=_EVAL_SYSTEM_INSTRUCTION,
    )
    prompt = _build_eval_prompt(code, enunciado)

    for attempt in range(1, max_retries + 1):
        if attempt > 1:
            print(f"  -> Reintento {attempt}/{max_retries}...")
            time.sleep(4)
        try:
            response = gemini_model.generate_content(prompt)
            data = json.loads(response.text)
            result = _validate_eval_data(data)
            print("  -> JSON validado correctamente")
            return result
        except Exception as exc:
            print(f"  -> ERROR en Gemini (intento {attempt}): {exc}")

    print("  -> Falló tras todos los reintentos")
    return None


def _llm_evaluate_openai(code, enunciado, model, api_key, max_retries=5):
    try:
        from openai import OpenAI
    except ImportError:
        print("  -> Error: 'openai' no está instalado.")
        return None

    if not api_key:
        print("  -> Error: openai_api_key no configurada.")
        print("  -> Configúrala en Configuración → API Key.")
        return None

    client = OpenAI(api_key=api_key)
    prompt = _build_eval_prompt(code, enunciado)

    for attempt in range(1, max_retries + 1):
        if attempt > 1:
            print(f"  -> Reintento {attempt}/{max_retries}...")
            time.sleep(4)
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": _EVAL_SYSTEM_INSTRUCTION},
                    {"role": "user",   "content": prompt},
                ],
                temperature=0.0, seed=42, max_tokens=1024,
                response_format={"type": "json_object"},
            )
            data = json.loads(response.choices[0].message.content)
            result = _validate_eval_data(data)
            print("  -> JSON validado correctamente")
            return result
        except Exception as exc:
            print(f"  -> ERROR en OpenAI (intento {attempt}): {exc}")
            if attempt < max_retries:
                import re as _re
                wait_match = _re.search(r'try again in ([0-9]+(?:\.[0-9]+)?)s', str(exc))
                if wait_match:
                    time.sleep(float(wait_match.group(1)) + 0.5)

    print("  -> Falló tras todos los reintentos")
    return None


def llm_evaluate(code, enunciado, provider, model, api_key=None, max_retries=5):
    print(f"  -> Enviando al LLM ({provider} / {model})...")
    if provider == "gemini":
        return _llm_evaluate_gemini(code, enunciado, model, api_key, max_retries)
    elif provider == "openai":
        return _llm_evaluate_openai(code, enunciado, model, api_key, max_retries)
    else:
        print(f"  -> Proveedor desconocido: '{provider}'")
        return None


# ==============================
# MAIN
# ==============================

def main(zip_path, enunciado_path):
    print("======================================")
    print("ACADEMIC PREGRADER - INICIO")
    print("ZIP:", zip_path)
    print("Enunciado:", enunciado_path)
    print("======================================")

    if not Path(zip_path).is_file():
        print("El archivo ZIP no existe:", zip_path)
        return
    if not Path(enunciado_path).is_file():
        print("El enunciado no existe:", enunciado_path)
        return

    config = configparser.RawConfigParser()
    config_dir = Path(os.environ.get("PREGRADER_CONFIG_DIR", str(Path(__file__).parent)))
    config_path = config_dir / "config.ini"
    if config_path.exists():
        config.read(config_path, encoding="utf-8")

    custom_instr = config.get("prompt", "system_instruction", fallback="").strip()
    if custom_instr:
        global _EVAL_SYSTEM_INSTRUCTION
        _EVAL_SYSTEM_INSTRUCTION = custom_instr

    custom_rules = config.get("prompt", "eval_rules", fallback="").strip()
    if custom_rules:
        global _EVAL_RULES
        _EVAL_RULES = custom_rules

    tmp_dir = tempfile.mkdtemp()
    try:
        _run_main(tmp_dir, zip_path, enunciado_path, config)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _run_main(tmp_dir, zip_path, enunciado_path, config):

    with zipfile.ZipFile(zip_path, 'r') as zf:
        zf.extractall(tmp_dir)
    tmp_path = Path(tmp_dir)
    top_dirs  = [d for d in tmp_path.iterdir() if d.is_dir()]
    top_files = [f for f in tmp_path.iterdir() if f.is_file()]
    base_path = top_dirs[0] if len(top_dirs) == 1 and not top_files else tmp_path

    enunciado_file = Path(enunciado_path)
    try:
        print("Leyendo enunciado PDF:", enunciado_path)
        enunciado_texto = extract_pdf_text(str(enunciado_file))
    except Exception as e:
        print("Error leyendo el PDF:", e)
        return

    # ── Config ────────────────────────────────────────────────────────────────
    llm_provider = config.get("llm", "provider", fallback="openai")
    llm_model    = config.get("llm", "model",    fallback="gpt-4o")
    if llm_provider == "gemini":
        llm_api_key = os.environ.get("GEMINI_API_KEY", "").strip() or config.get(
            "llm", "gemini_api_key", fallback=""
        )
    elif llm_provider == "openai":
        llm_api_key = os.environ.get("OPENAI_API_KEY", "").strip() or config.get(
            "llm", "openai_api_key", fallback=""
        )
    else:
        llm_api_key = ""
    enable_compilation = config.getboolean("steps", "enable_compilation", fallback=True)
    enable_plagiarism  = config.getboolean("steps", "enable_plagiarism",  fallback=False)
    enable_llm         = config.getboolean("steps", "enable_llm",         fallback=True)
    enable_cache       = config.getboolean("steps", "enable_cache",       fallback=False)
    jplag_jar          = config.get("paths",      "jplag_jar",  fallback="")
    plagiarism_threshold = config.getfloat("plagiarism", "threshold", fallback=0.7)
    submission_language  = config.get("submission", "language", fallback="auto")

    cache_path = base_path / ".evaluation_cache.json"
    cache = load_cache(cache_path) if enable_cache else {}
    if enable_cache:
        print("Caché habilitada. Entradas encontradas:", len(cache))
    else:
        print("Caché deshabilitada.")
    print("--------------------------------------")

    # ── Listar carpetas de estudiantes ────────────────────────────────────────
    estudiantes = sorted(
        [p for p in base_path.iterdir()
         if p.is_dir() and not p.name.startswith('.') and not p.name.startswith('__')],
        key=lambda p: p.name.lower()
    )
    print("Estudiantes encontrados:", len(estudiantes))

    # ── Detectar lenguaje dominante (para JPlag y modo auto) ──────────────────
    if submission_language == "auto":
        lang_counts: dict[str, int] = {}
        for carpeta in estudiantes:
            lang = detect_language(carpeta)
            if lang:
                lang_counts[lang] = lang_counts.get(lang, 0) + 1
        dominant_lang = max(lang_counts, key=lang_counts.get) if lang_counts else "cpp"
        print(f"Lenguaje detectado automáticamente: {LANG_LABELS.get(dominant_lang, dominant_lang)}")
        if len(lang_counts) > 1:
            detail = ", ".join(f"{LANG_LABELS.get(l,l)}: {n}" for l, n in lang_counts.items())
            print(f"  (distribución: {detail})")
    else:
        dominant_lang = submission_language
        print(f"Lenguaje configurado: {LANG_LABELS.get(dominant_lang, dominant_lang)}")

    jplag_lang = LANG_CONFIG.get(dominant_lang, {}).get("jplag", "cpp")

    # PDFs no compilan — desactivar compilación silenciosamente
    can_compile_lang = LANG_CONFIG.get(dominant_lang, {}).get("compile") is not None

    print("--------------------------------------")

    # ── Análisis de plagio ────────────────────────────────────────────────────
    plagio_map = {}
    if enable_plagiarism:
        if not jplag_jar or not Path(jplag_jar).exists():
            print("Advertencia: enable_plagiarism=true pero jplag_jar no encontrado.")
            print("  Ruta configurada:", jplag_jar or "(vacía)")
        else:
            print(f"Ejecutando análisis de plagio con JPlag ({jplag_lang})...")
            result = run_plagiarism_check(base_path, jplag_jar, plagiarism_threshold, jplag_lang)
            if result is None:
                print("  -> Análisis de plagio omitido por error.")
                print("     La evaluación continuará sin detección de plagio.")
            else:
                plagio_map = result
                if plagio_map:
                    print(f"Estudiantes con posible plagio detectado: {len(plagio_map)}")
                else:
                    print("Análisis de plagio completado. Sin similitudes sobre el umbral.")
    else:
        print("Análisis de plagio desactivado.")
    print("--------------------------------------")

    max_workers = config.getint("performance", "max_workers", fallback=3)
    print(f"Modo paralelo: {max_workers} workers")

    estudiantes_nombres = [parse_student_name(c.name) for c in estudiantes]
    print(f"##STUDENTS## {json.dumps(estudiantes_nombres, ensure_ascii=False)}", flush=True)
    print("--------------------------------------")

    resultados = []
    _print_lock = threading.Lock()
    _cache_lock = threading.Lock()

    def _process_student(carpeta):
        logs = []
        def log(msg): logs.append(msg)

        estudiante = parse_student_name(carpeta.name)
        log("Procesando: " + carpeta.name)

        # Determinar lenguaje de esta entrega
        if submission_language == "auto":
            lang = detect_language(carpeta)
            if lang is None:
                log("  -> No se encontraron archivos de entrega reconocidos")
                log("--------------------------------------")
                return None, logs
        else:
            lang = submission_language

        files = find_submission_files(carpeta, lang)
        if not files:
            log(f"  -> No se encontraron archivos {LANG_LABELS.get(lang, lang)}")
            log("--------------------------------------")
            return None, logs

        log(f"  -> Lenguaje: {LANG_LABELS.get(lang, lang)} ({len(files)} archivo(s))")

        # Datos de plagio
        plagio_info   = plagio_map.get(carpeta.name, {})
        con_quien_raw = plagio_info.get("con_quien", "")
        con_quien     = parse_student_name(con_quien_raw) if con_quien_raw else ""
        porcentaje    = plagio_info.get("porcentaje", "")
        if plagio_info:
            log(f"  -> Posible plagio detectado con {con_quien} ({porcentaje}%)")

        # Compilación
        compila_str = "N/A"
        if enable_compilation and can_compile_lang and LANG_CONFIG.get(lang, {}).get("compile"):
            log(f"  -> Compilando ({len(files)} archivo(s))...")
            success, error_msg = compile_submission(carpeta, files, lang)
            if not success:
                log("  -> Error de compilación")
                log("--------------------------------------")
                plagio_str = f"Con: {con_quien} ({porcentaje}%)" if plagio_info else ""
                return [estudiante, error_msg, plagio_str, 0.0, "Error de compilación"], logs
            log("  -> Compilación exitosa")
            compila_str = "SI"
        elif lang == "pdf":
            log("  -> PDF: compilación no aplica")
        else:
            log("  -> Compilación omitida")

        # Evaluación LLM
        logica     = 0.0
        comentario = ""
        resp       = None

        if enable_llm:
            code = extract_submission_text(files, lang)
            cache_key = compute_evaluation_key(code, enunciado_texto)

            with _cache_lock:
                resp = cache.get(cache_key)
            if resp is not None:
                log("  -> Resultado obtenido desde caché")
            else:
                resp = llm_evaluate(code, enunciado_texto,
                                    llm_provider, llm_model,
                                    api_key=llm_api_key)
                if resp is not None:
                    with _cache_lock:
                        if enable_cache:
                            cache[cache_key] = resp
                            save_cache(cache_path, cache)

            if resp is None:
                log("  -> Falló evaluación LLM")
                log("--------------------------------------")
                plagio_str = f"Con: {con_quien} ({porcentaje}%)" if plagio_info else ""
                return [estudiante, compila_str, plagio_str, 0.0, "ERROR evaluando LLM"], logs

            try:
                logica = round(clamp(float(resp.get("logica", resp.get("nota_final", 0)))), 1)
            except Exception:
                logica = 0.0

            comentario = "" if logica == 5.0 else resp.get("comentario", "")
            log("  -> Evaluación completada. Nota: " + str(logica))
        else:
            log("  -> Evaluación LLM omitida")

        plagio_str = f"Con: {con_quien} ({porcentaje}%)" if plagio_info else ""
        log("--------------------------------------")
        return [estudiante, compila_str, plagio_str, logica, comentario], logs

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_process_student, c) for c in estudiantes]
        for future in concurrent.futures.as_completed(futures):
            try:
                row, logs = future.result()
            except Exception as exc:
                with _print_lock:
                    print("  -> Error inesperado en worker:", exc)
                continue
            with _print_lock:
                for line in logs:
                    print(line)
            if row is not None:
                resultados.append(row)
                row_dict = {
                    "estudiante": row[0],
                    "compila":    row[1],
                    "plagio":     row[2],
                    "nota":       row[3],
                    "comentario": row[4],
                }
                print(f"##RESULT## {json.dumps(row_dict, ensure_ascii=False)}", flush=True)

    print("Procesamiento finalizado.")
    print(f"##DONE## {json.dumps({'count': len(resultados)}, ensure_ascii=False)}", flush=True)
    print("======================================")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso: python academic-pregrader.py <archivo.zip> <enunciado.pdf>")
    else:
        main(sys.argv[1], sys.argv[2])
