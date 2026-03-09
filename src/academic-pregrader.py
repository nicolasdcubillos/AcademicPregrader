import os
import sys
import subprocess
import csv
import json
import hashlib
import zipfile
import configparser
from pathlib import Path
import pdfplumber


# ==============================
# UTILIDADES
# ==============================

REQUIRED_KEYS = {"logica", "estructura", "estilo", "nota_final", "comentario"}


def clamp(n, min_val=0.0, max_val=5.0):
    return max(min_val, min(n, max_val))


def normalize_code(code: str) -> str:
    """Normaliza el texto del código para que entradas idénticas produzcan el mismo hash."""
    code = code.lstrip('\ufeff')                          # quitar BOM
    code = code.replace('\r\n', '\n').replace('\r', '\n')  # unificar saltos de línea
    lines = [line.rstrip() for line in code.split('\n')]  # quitar espacios al final de cada línea
    return '\n'.join(lines).strip()


def compute_evaluation_key(code: str, enunciado: str, rubrica: str) -> str:
    """SHA-256 de los tres inputs para usar como clave de caché."""
    h = hashlib.sha256()
    h.update(code.encode('utf-8'))
    h.update(enunciado.encode('utf-8'))
    h.update(rubrica.encode('utf-8'))
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
# EXTRAER TEXTO DEL PDF (pdfplumber)
# ==============================

def extract_pdf_text(pdf_path):
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"No se encontró el archivo de enunciado: {pdf_path}")

    print("Leyendo enunciado PDF:", pdf_path)

    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text += page.extract_text() or ""
    return text


# ==============================
# COMPILAR C++
# ==============================

def compile_cpp(source_file):
    exe_file = source_file.with_suffix(".exe")

    cmd = ["g++", str(source_file), "-o", str(exe_file)]
    result = run(cmd)

    if result.returncode != 0:
        return False, result.stderr

    return True, exe_file


# ==============================
# DETECCIÓN DE PLAGIO (JPlag v4+)
# ==============================

def run_plagiarism_check(base_path: Path, jplag_jar: str, threshold: float) -> dict:
    """
    Ejecuta JPlag v4+ sobre la carpeta base y devuelve un dict por estudiante:
    { "nombre_carpeta": {"con_quien": str, "porcentaje": float} }
    Solo incluye estudiantes que superan el umbral de similitud.
    """
    output_zip = base_path / ".jplag_results.zip"
    if output_zip.exists():
        output_zip.unlink()

    cmd = [
        "java", "-jar", jplag_jar,
        str(base_path),
        "-l", "cpp2",
        "--result-file", str(output_zip),
    ]

    result = run(cmd)

    if result.returncode != 0:
        print("  -> Error ejecutando JPlag")
        print(result.stderr[:500])
        return {}

    if not output_zip.exists():
        print("  -> JPlag no generó archivo de resultados")
        return {}

    try:
        with zipfile.ZipFile(output_zip, "r") as zf:
            names = zf.namelist()
            json_name = next(
                (n for n in names if "overview" in n.lower() and n.endswith(".json")),
                None
            )
            if json_name is None:
                print("  -> No se encontró overview.json en los resultados de JPlag")
                return {}
            data = json.loads(zf.read(json_name).decode("utf-8"))
    except Exception as e:
        print("  -> Error leyendo resultados de JPlag:", e)
        return {}

    plagio_map = {}

    for comp in data.get("top_comparisons", []):
        student_a = comp.get("first_submission", "")
        student_b = comp.get("second_submission", "")
        similarities = comp.get("similarities", {})
        # JPlag reporta similitud entre 0.0 y 1.0
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

def llm_evaluate(code, enunciado, rubrica, llm_cmd, model, max_retries=3):
    print("  -> Enviando código al LLM...")

    prompt = f"""
    Eres un evaluador automático de código para un curso universitario.
    Debes calificar de forma consistente, objetiva y moderadamente flexible (no excesivamente estricta),
    siguiendo EXCLUSIVAMENTE la rúbrica proporcionada.

    ========================
    FORMATO DE SALIDA (OBLIGATORIO)
    ========================
    - Responde ÚNICAMENTE con JSON válido.
    - No escribas texto antes ni después.
    - No uses markdown.
    - No uses bloques de código.
    - No agregues llaves adicionales.
    - Usa EXACTAMENTE estas llaves:
    "logica", "estructura", "estilo", "nota_final", "comentario"

    - "logica", "estructura", "estilo", "nota_final" deben ser números (no strings).
    - Usa como máximo 1 decimal.
    - No uses más de 1 decimal.
    - Todos los valores deben estar estrictamente entre 0.0 y 5.0.
    - Si un valor calculado supera 5.0, redúcelo a 5.0.
    - Si es menor que 0.0, súbelo a 0.0.

    ========================
    ESCALA
    ========================
    - logica: 0.0 a 5.0
    - estructura: 0.0 a 5.0
    - estilo: 0.0 a 5.0
    - nota_final: 0.0 a 5.0

    Si la rúbrica usa otra escala (ej. 0-100), conviértela proporcionalmente a escala 0-5 ANTES de responder.

    ========================
    CONSISTENCIA
    ========================
    - Con el mismo enunciado, rúbrica y código, la variación máxima permitida es ±0.1.
    - No penalices dos veces el mismo error salvo que la rúbrica lo indique explícitamente.
    - En caso de duda, aplica penalización moderada.
    - Si el código cumple razonablemente el enunciado, la nota no debe ser baja.

    ========================
    ORDEN DE EVALUACIÓN
    ========================
    1) Aplica primero la rúbrica.
    2) Prioriza cumplimiento funcional.
    3) Penaliza en este orden: errores críticos > errores funcionales > detalles de estilo.
    4) No inventes errores que no estén visibles.

    ========================
    DEFINICIÓN DE CATEGORÍAS
    ========================
    logica:
    - Cumple requerimientos del enunciado
    - Produce resultados correctos en casos típicos
    - Manejo básico de errores si aplica
    - Sin errores graves evidentes

    estructura:
    - Organización clara
    - Nombres comprensibles
    - Separación lógica razonable
    - Modularidad si aplica

    estilo:
    - Formato consistente
    - Convenciones básicas del lenguaje
    - Claridad mínima
    - Comentarios solo si la rúbrica lo exige

    ========================
    CÁLCULO DE nota_final
    ========================
    - Calcula nota_final como el promedio simple de (logica + estructura + estilo) / 3
    - Redondea a 1 decimal exacto.
    - Si la rúbrica define pesos distintos, aplícalos y menciona en el comentario que se usó ponderación.
    - Asegúrate de que nota_final coincida matemáticamente con los valores anteriores.

    ========================
    COMENTARIO (OBLIGATORIO)
    ========================
    - 2 a 4 frases máximo.
    - 1 frase: principal fortaleza.
    - 1-2 frases: máximo dos mejoras concretas.
    - No repitas la nota.
    - No uses tono severo.

    ========================
    RUBRICA
    ========================
    {rubrica}

    ========================
    ENTRADA
    ========================

    ENUNCIADO:
    {enunciado}

    CODIGO:
    {code}

    ========================
    SALIDA (SOLO JSON)
    ========================
    {{
    "logica": numero,
    "estructura": numero,
    "estilo": numero,
    "nota_final": numero,
    "comentario": "texto"
    }}
    """

    for attempt in range(1, max_retries + 1):
        if attempt > 1:
            print(f"  -> Reintento {attempt}/{max_retries}...")

        proc = run([
            llm_cmd,
            "run",
            model,
            "--temperature", "0",
            "--top-p", "1"
        ], input_text=prompt)

        if proc.returncode != 0:
            print(f"  -> Error ejecutando LLM (intento {attempt})")
            print(proc.stderr[:500])
            continue

        raw = proc.stdout.strip()

        try:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start == -1 or end == 0:
                raise ValueError("No se encontró JSON en la respuesta")
            json_text = raw[start:end]
            data = json.loads(json_text)

            missing = REQUIRED_KEYS - data.keys()
            if missing:
                raise ValueError(f"Claves faltantes en JSON: {missing}")

            for key in ("logica", "estructura", "estilo", "nota_final"):
                float(data[key])  # valida que sean numéricos

            print("  -> JSON parseado y validado correctamente")
            return data

        except Exception as e:
            print(f"  -> ERROR parseando LLM (intento {attempt}): {e}")
            print("  -> Respuesta recibida:")
            print(raw[:500])

    print("  -> Falló tras todos los reintentos")
    return None


# ==============================
# MAIN
# ==============================

def main(base_folder):

    print("======================================")
    print("ACADEMIC PREGRADER - INICIO")
    print("Carpeta base:", base_folder)
    print("======================================")

    base_path = Path(base_folder)

    if not base_path.exists():
        print("La carpeta base no existe:", base_folder)
        return

    # Leer configuración
    config = configparser.ConfigParser()
    config_path = Path(__file__).parent / "config.ini"
    if config_path.exists():
        config.read(config_path, encoding="utf-8")

    enunciado_file = base_path / "enunciado.pdf"
    rubrica_file = base_path / "rubrica.txt"

    if not enunciado_file.exists():
        print("No se encontró enunciado.pdf")
        return

    if not rubrica_file.exists():
        rubrica_file = Path(__file__).parent / "rubrica.txt"
        if not rubrica_file.exists():
            print("No se encontró rubrica.txt")
            return
        print("Usando rubrica por defecto:", rubrica_file)

    try:
        enunciado_texto = extract_pdf_text(str(enunciado_file))
    except Exception as e:
        print("Error leyendo el PDF:", e)
        return

    rubrica = rubrica_file.read_text(encoding="utf-8")

    llm_cmd = config.get("llm", "command", fallback="ollama")
    llm_model = config.get("llm", "model", fallback="llama3")

    enable_compilation   = config.getboolean("steps", "enable_compilation",  fallback=True)
    enable_plagiarism    = config.getboolean("steps", "enable_plagiarism",   fallback=False)
    enable_llm           = config.getboolean("steps", "enable_llm",          fallback=True)
    jplag_jar            = config.get("paths", "jplag_jar", fallback="")
    plagiarism_threshold = config.getfloat("plagiarism", "threshold", fallback=0.7)

    cache_path = base_path / ".evaluation_cache.json"
    cache = load_cache(cache_path)
    print("Entradas en caché:", len(cache))
    print("--------------------------------------")

    # Análisis de plagio global (antes de evaluar estudiante por estudiante)
    plagio_map = {}
    if enable_plagiarism:
        if not jplag_jar or not Path(jplag_jar).exists():
            print("Advertencia: enable_plagiarism=true pero jplag_jar no encontrado.")
            print("  Ruta configurada:", jplag_jar or "(vacía)")
        else:
            print("Ejecutando análisis de plagio con JPlag...")
            plagio_map = run_plagiarism_check(base_path, jplag_jar, plagiarism_threshold)
            print("Estudiantes con posible plagio detectado:", len(plagio_map))
    else:
        print("Análisis de plagio desactivado (enable_plagiarism=false).")
    print("--------------------------------------")

    resultados = []

    # Ordenar alfabéticamente para que el CSV sea siempre consistente
    estudiantes = sorted([p for p in base_path.iterdir() if p.is_dir()], key=lambda p: p.name.lower())
    print("Estudiantes encontrados:", len(estudiantes))
    print("--------------------------------------")

    for carpeta in estudiantes:

        estudiante = carpeta.name
        print("Procesando:", estudiante)

        cpp_files = list(carpeta.rglob("*.cpp"))

        if not cpp_files:
            print("  -> No se encontró archivo .cpp")
            continue

        source_file = cpp_files[0]

        # Datos de plagio para este estudiante
        plagio_info = plagio_map.get(estudiante, {})
        plagio_flag = "SI" if plagio_info else "NO"
        con_quien   = plagio_info.get("con_quien", "")
        porcentaje  = plagio_info.get("porcentaje", "")

        if plagio_flag == "SI":
            print(f"  -> Posible plagio detectado con {con_quien} ({porcentaje}%)")

        # Compilación
        compila_flag      = "N/A"
        error_compilacion = ""
        if enable_compilation:
            print("  -> Compilando:", source_file.name)
            compila, resultado = compile_cpp(source_file)
            if not compila:
                print("  -> Error de compilación")
                resultados.append([
                    estudiante, "NO", resultado,
                    plagio_flag, con_quien, porcentaje,
                    0, 0, 0, 0,
                    "Error de compilación"
                ])
                continue
            print("  -> Compilación exitosa")
            compila_flag = "SI"
        else:
            print("  -> Compilación omitida (enable_compilation=false)")

        # Evaluación LLM
        logica, estructura, estilo, total = 0.0, 0.0, 0.0, 0.0
        comentario = ""
        resp = None

        if enable_llm:
            code_raw = source_file.read_text(encoding="utf-8", errors="replace")
            code = normalize_code(code_raw)
            cache_key = compute_evaluation_key(code, enunciado_texto, rubrica)

            if cache_key in cache:
                print("  -> Resultado obtenido desde caché")
                resp = cache[cache_key]
            else:
                resp = llm_evaluate(code, enunciado_texto, rubrica, llm_cmd, llm_model)
                if resp is not None:
                    cache[cache_key] = resp
                    save_cache(cache_path, cache)

            if resp is None:
                print("  -> Falló evaluación LLM")
                resultados.append([
                    estudiante, compila_flag, error_compilacion,
                    plagio_flag, con_quien, porcentaje,
                    0, 0, 0, 0,
                    "ERROR parseando LLM"
                ])
                continue

            try:
                logica     = round(clamp(float(resp.get("logica",     0))), 1)
                estructura = round(clamp(float(resp.get("estructura", 0))), 1)
                estilo     = round(clamp(float(resp.get("estilo",     0))), 1)
            except Exception:
                logica, estructura, estilo = 0.0, 0.0, 0.0

            comentario = resp.get("comentario", "")
            # Siempre recalculamos nota_final aquí, ignorando el valor del LLM
            total = round((logica + estructura + estilo) / 3, 1)
            print("  -> Evaluación completada. Total:", total)
        else:
            print("  -> Evaluación LLM omitida (enable_llm=false)")

        resultados.append([
            estudiante, compila_flag, error_compilacion,
            plagio_flag, con_quien, porcentaje,
            logica, estructura, estilo, total,
            comentario
        ])

        print("--------------------------------------")

    print("Procesamiento finalizado.")
    print("Generando archivo resultados.csv")

    out_csv = base_path / "resultados.csv"

    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Estudiante",
            "Compila",
            "ErrorCompilacion",
            "Plagio",
            "ConQuien",
            "Porcentaje",
            "Logica",
            "Estructura",
            "Estilo",
            "Total",
            "Comentario"
        ])
        writer.writerows(resultados)

    print("Archivo resultados.csv generado correctamente")
    print("Ruta:", out_csv)
    print("======================================")


# ==============================
# ENTRY POINT
# ==============================

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python academic-pregrader.py <carpeta_base>")
    else:
        main(sys.argv[1])