"""
Plantillas de calificación por tipo de curso.

Cada curso registrado en el sistema está vinculado a uno de tres tipos fijos
(ver `auth.VALID_COURSE_TYPES`): "ip" (Introducción a la Programación), "pa"
(Programación Avanzada) o "fpia" (Fundamentos de Programación IA). Este módulo
describe, para cada tipo, la estructura exacta de la hoja "Definitivas"
(encabezados, pesos/máximos por defecto y fórmulas) que `excel_export.py` usa
para generar el archivo "listo para llenar". La hoja "Estudiantes" es igual
para los 3 tipos: solo dos columnas (nombre completo, ID), sin columna de
carrera.

Los encabezados se describen como listas de `(columna, texto_fila_1,
valor_fila_2)`. `valor_fila_2` es el peso/máximo por defecto (editable por el
profesor) o `None` si la celda de fila 2 debe quedar vacía.
"""

COURSE_TYPE_LABELS = {
    "ip": "Introducción a la Programación",
    "pa": "Programación Avanzada",
    "fpia": "Fundamentos de Programación IA",
}

# ── Hoja "Estudiantes" (igual para los 3 tipos) ──────────────────────────────
STUDENTS_SHEET_NAME = "Estudiantes"
STUDENTS_HEADERS = ["Apellido, Nombre", "ID"]

DEFINITIVAS_SHEET_NAME = "Definitivas"


def _student_ref(col: str, er: int) -> str:
    """Referencia a la celda de la hoja Estudiantes en la fila `er`."""
    return f"={STUDENTS_SHEET_NAME}!{col}{er}"


# ── Tipo fpia — Fundamentos de Programación IA ───────────────────────────────

_FPIA_HEADERS = [
    ("A", "#", None),
    ("B", "#", None),
    ("C", "ID", None),
    ("D", "Nombre", None),
    ("E", "Uso de intérpretes online", 20),
    ("F", "Implementación de algoritmos", 60),
    ("G", "Funciones y descomposición de problemas", 40),
    ("H", "Clases Objetos y descomposición de problemas", 40),
    ("I", "Ejercicio introductorio a Pandas", 40),
    ("J", "Cuestionario Individual", 10),
    ("K", "Cuestionario Individual M3", 10),
    ("L", "Subtotal\nEvaluaciones sumativas\n(50%)", None),
    ("M", "", "Nota"),
    ("N", "P. intermedia Componente teórico", 40),
    ("O", "P. intermedia Componente práctico", 60),
    ("P", "Subtotal\nPrueba evaluativa intermedia\n(25%)", None),
    ("Q", "", "Nota"),
    ("R", "P. final Componente teórico", 50),
    ("S", "P. final Componente práctico", 60),
    ("T", "Subtotal\nPrueba evaluativa final\n (25%)", None),
    ("U", "", "Nota"),
    ("V", "Definitiva", None),
]

# Columnas de notas crudas que arrancan en 0.
_FPIA_RAW_GRADE_COLS = ["E", "F", "G", "H", "I", "J", "K", "N", "O", "R", "S"]


def _fpia_row(r: int, er: int) -> dict:
    row = {
        "A": r - 2,  # número de fila del estudiante (1, 2, 3…)
        "C": _student_ref("B", er),
        "D": _student_ref("A", er),
        "L": f"=SUM(E{r}:K{r})",
        "M": f"=5*(L{r}/$L$2)",
        "P": f"=SUM(N{r}:O{r})",
        "Q": f"=5*(P{r}/$P$2)",
        "T": f"=SUM(R{r}:S{r})",
        "U": f"=5*(T{r}/$T$2)",
        "V": f"=+M{r}*0.5+Q{r}*0.25+U{r}*0.25",
    }
    for col in _FPIA_RAW_GRADE_COLS:
        row[col] = 0
    return row


# ── Tipo ip — Introducción a la Programación ─────────────────────────────────

_IP_HEADERS = [
    ("A", "#", None),
    ("B", "ID", None),
    ("C", "Nombre", None),
    ("D", "Parcial 1", 0.2),
    ("E", "Parcial 2", 0.2),
    ("F", "Parcial 3", 0.2),
    ("G", "Proyecto 1", 0.07),
    ("H", "Talleres / Quices", 0.15),
    ("I", "Proyecto 2", 0.08),
    ("J", "Sustentación", 0.10),
    ("K", "Definitiva", None),
]

_IP_RAW_GRADE_COLS = ["D", "E", "F", "G", "H", "I", "J"]
_IP_FINAL_COL = "K"


def _ip_row(r: int, er: int) -> dict:
    row = {
        "A": r - 2,
        "B": _student_ref("B", er),
        "C": _student_ref("A", er),
        "K": (
            f"=D{r}*$D$2+E{r}*$E$2+F{r}*$F$2+G{r}*$G$2"
            f"+H{r}*$H$2+I{r}*$I$2+J{r}*$J$2"
        ),
    }
    for col in _IP_RAW_GRADE_COLS:
        row[col] = 0
    return row


# ── Tipo pa — Programación Avanzada ──────────────────────────────────────────

_PA_HEADERS = [
    ("A", "#", None),
    ("B", "ID", None),
    ("C", "Nombre", None),
    ("D", "Parcial C++", 0.25),
    ("E", "Parcial Java", 0.25),
    ("F", "Proyecto C++", 0.15),
    ("G", "Proyecto Java", 0.15),
    ("H", "Talleres C++", 0.10),
    ("I", "Talleres Java", 0.10),
    ("J", "Definitiva", None),
]

_PA_RAW_GRADE_COLS = ["D", "E", "F", "G", "H", "I"]
_PA_FINAL_COL = "J"


def _pa_row(r: int, er: int) -> dict:
    row = {
        "A": r - 2,
        "B": _student_ref("B", er),
        "C": _student_ref("A", er),
        "J": (
            f"=D{r}*$D$2+E{r}*$E$2+F{r}*$F$2+G{r}*$G$2+H{r}*$H$2+I{r}*$I$2"
        ),
    }
    for col in _PA_RAW_GRADE_COLS:
        row[col] = 0
    return row


SUMMARY_ROW_LABELS = ["Total", "Retiro", "Aprobados", "Reprobado"]
"""Etiquetas del bloque resumen (ip/pa), en orden, 2 filas debajo de la
última fila de estudiantes. `excel_export.py` construye las fórmulas usando
`final_col` de la plantilla (COUNT/COUNTIF sobre la columna de la Definitiva
y referencias entre las propias celdas del bloque para "Reprobado")."""

# ── Registro central ──────────────────────────────────────────────────────────

TEMPLATES = {
    "fpia": {
        "headers": _FPIA_HEADERS,
        "row_builder": _fpia_row,
        "final_col": "V",
        "has_summary": False,
    },
    "ip": {
        "headers": _IP_HEADERS,
        "row_builder": _ip_row,
        "final_col": _IP_FINAL_COL,
        "has_summary": True,
    },
    "pa": {
        "headers": _PA_HEADERS,
        "row_builder": _pa_row,
        "final_col": _PA_FINAL_COL,
        "has_summary": True,
    },
}


def get_template(course_type: str) -> dict:
    """Devuelve la plantilla del tipo de curso, o lanza KeyError si no existe."""
    return TEMPLATES[course_type]
