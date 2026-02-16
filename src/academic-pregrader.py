import os
import sys
import glob
import subprocess
import configparser
import csv
import json
import tempfile

def run(cmd, input_text=None):
    return subprocess.run(cmd, input=input_text, text=True, capture_output=True)

def extract_pdf_text(pdf_path):
    txt_path = pdf_path.replace(".pdf", ".txt")
    subprocess.run(["pdftotext", pdf_path, txt_path])
    return open(txt_path, "r", encoding="utf-8", errors="ignore").read()

def compile_cpp(cpp_file):
    exe = cpp_file + ".out"
    proc = run(["g++", cpp_file, "-std=c++17", "-O2", "-o", exe])
    if proc.returncode == 0:
        return True, ""
    else:
        return False, proc.stderr[:500]

def run_jplag(folder, jplag_jar):
    out_dir = os.path.join(folder, "reporte_plagio")
    if not os.path.exists(out_dir):
        os.makedirs(out_dir)

    cmd = ["java", "-jar", jplag_jar, "-l", "cpp17", "-s", folder, "-r", out_dir, "--json"]
    proc = run(cmd)
    return out_dir

def parse_jplag_json(report_dir, threshold):
    # Busca archivo JSON generado por JPlag
    json_files = glob.glob(os.path.join(report_dir, "*.json"))
    results = {}

    if not json_files:
        return results

    data = json.load(open(json_files[0], "r", encoding="utf-8"))

    # Estructura aproximada: depende de versión de JPlag, esto es heurístico
    for match in data.get("matches", []):
        a = os.path.basename(match["submission1"])
        b = os.path.basename(match["submission2"])
        sim = match["similarity"]

        if sim >= threshold:
            results.setdefault(a, []).append((b, sim))
            results.setdefault(b, []).append((a, sim))

    return results

def llm_evaluate(code, enunciado, rubrica, llm_cmd, model):
    prompt = f"""
Enunciado:
{enunciado}

Rúbrica:
{rubrica}

Código del estudiante:
{code}

Evalúa y devuelve SOLO un JSON válido con:
- logica (0-5)
- estructura (0-3)
- estilo (0-2)
- total
- comentario
"""

    proc = run([llm_cmd, "run", model], input_text=prompt)
    return proc.stdout

def main(folder):
    config = configparser.ConfigParser()
    config.read(os.path.join(folder, "config.ini"))

    enable_compilation = config.getboolean("steps", "enable_compilation", fallback=True)
    enable_plagiarism = config.getboolean("steps", "enable_plagiarism", fallback=True)
    enable_llm = config.getboolean("steps", "enable_llm", fallback=True)

    jplag_jar = config.get("paths", "jplag_jar", fallback="")
    llm_cmd = config.get("llm", "command", fallback="ollama")
    llm_model = config.get("llm", "model", fallback="llama3")
    plag_threshold = config.getfloat("plagiarism", "threshold", fallback=0.7)

    enunciado_pdf = os.path.join(folder, "enunciado.pdf")
    rubrica_txt = os.path.join(folder, "rubrica.txt")

    enunciado_texto = extract_pdf_text(enunciado_pdf)
    rubrica = open(rubrica_txt, "r", encoding="utf-8").read()

    resultados = {}

    cpp_files = glob.glob(os.path.join(folder, "*.cpp"))

    # Paso 1: Compilación
    for cpp in cpp_files:
        nombre = os.path.basename(cpp)
        resultados[nombre] = {
            "compila": True,
            "error": "",
            "plagio": False,
            "con_quien": "",
            "porcentaje": "",
            "logica": 0,
            "estructura": 0,
            "estilo": 0,
            "total": 0,
            "comentario": ""
        }

        if enable_compilation:
            ok, err = compile_cpp(cpp)
            resultados[nombre]["compila"] = ok
            resultados[nombre]["error"] = err

    # Paso 2: Plagio
    plagios = {}
    if enable_plagiarism:
        report_dir = run_jplag(folder, jplag_jar)
        plagios = parse_jplag_json(report_dir, plag_threshold)

        for nombre, matches in plagios.items():
            if matches:
                otro, sim = matches[0]
                resultados[nombre]["plagio"] = True
                resultados[nombre]["con_quien"] = otro
                resultados[nombre]["porcentaje"] = round(sim * 100, 2)

    # Paso 3: LLM
    if enable_llm:
        for cpp in cpp_files:
            nombre = os.path.basename(cpp)
            if resultados[nombre]["plagio"]:
                continue  # saltamos plagios
            code = open(cpp, "r", encoding="utf-8", errors="ignore").read()

            resp = llm_evaluate(code, enunciado_texto, rubrica, llm_cmd, llm_model)

            try:
                json_start = resp.find("{")
                json_end = resp.rfind("}") + 1
                data = json.loads(resp[json_start:json_end])

                resultados[nombre]["logica"] = data.get("logica", 0)
                resultados[nombre]["estructura"] = data.get("estructura", 0)
                resultados[nombre]["estilo"] = data.get("estilo", 0)
                resultados[nombre]["total"] = data.get("total", 0)
                resultados[nombre]["comentario"] = data.get("comentario", "")
            except Exception as e:
                resultados[nombre]["comentario"] = "ERROR parseando LLM"

    # CSV final
    out_csv = os.path.join(folder, "resultados.csv")
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Nombre","Compila","ErrorCompilacion","Plagio","ConQuien","Porcentaje",
            "Logica","Estructura","Estilo","Total","Comentario"
        ])

        for nombre, d in resultados.items():
            writer.writerow([
                nombre,
                "SI" if d["compila"] else "NO",
                d["error"],
                "SI" if d["plagio"] else "NO",
                d["con_quien"],
                d["porcentaje"],
                d["logica"],
                d["estructura"],
                d["estilo"],
                d["total"],
                d["comentario"]
            ])

    print("✅ Evaluación completada. Resultado en:", out_csv)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python evaluar.py <folder_evaluacion>")
        sys.exit(1)

    main(sys.argv[1])