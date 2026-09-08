"""
Plantillas de calificación por tipo de curso.

Cada curso registrado en el sistema está vinculado a uno de tres tipos fijos
(ver `auth.VALID_COURSE_TYPES`): "ip" (Introducción a la Programación), "pa"
(Programación Avanzada) o "fpia" (Fundamentos de Programación IA).

Este módulo es la única fuente de los valores "editables por el profesor":
pesos/porcentajes y puntajes máximos por defecto de cada componente de
calificación, además de la estructura de columnas/hojas y las fórmulas que
las conectan. `excel_export.py` es responsable de todo el estilo visual
(fuentes, colores, bordes, formato condicional) y arma el workbook completo
—incluyendo las hojas auxiliares de componentes— replicando el formato de los
archivos reales que usan los profesores, pero leyendo los valores de aquí
para que sigan siendo configurables sin tocar código de estilo.

Los encabezados de "Definitivas" se describen como listas de `(columna,
texto_fila_1, valor_fila_2)`. `valor_fila_2` es el peso/máximo por defecto
(editable por el profesor) o `None` si la celda de fila 2 debe quedar vacía.
"""

COURSE_TYPE_LABELS = {
    "ip": "Introducción a la Programación",
    "pa": "Programación Avanzada",
    "fpia": "Fundamentos de Programación IA",
}

STUDENTS_SHEET_NAME = "Estudiantes"
DEFINITIVAS_SHEET_NAME = "Definitivas"


def _student_ref(col: str, er: int) -> str:
    """Referencia a la celda de la hoja Estudiantes en la fila `er`."""
    return f"={STUDENTS_SHEET_NAME}!{col}{er}"


# ── Hoja "Estudiantes" por tipo ───────────────────────────────────────────
# (columna, encabezado, ancho, alineación_horizontal_encabezado)
# "Carrera"/"Semestre"/"Grupo" se dejan siempre vacíos: la app no gestiona
# esos datos, pero se mantienen para que el archivo se vea idéntico al que ya
# usan los profesores y ellos puedan llenarlos a mano.
STUDENTS_COLUMNS = {
    "ip": [
        ("A", "Apellido, Nombre", 33.88, None),
        ("B", "ID", 12.88, "center"),
        ("C", "Carrera", 28.75, None),
        ("D", "Semestre", 17.12, None),
    ],
    "pa": [
        ("A", "Apellido, Nombre", 36.57, None),
        ("B", "ID", 12.86, "center"),
        ("C", "Carrera", 28.71, None),
        ("D", "Semestre", 17.14, None),
        ("E", "Grupo", 8.86, "center"),
    ],
    "fpia": [
        ("A", "Apellido, Nombre", 32.0, "center"),
        ("B", "ID", 11.0, "center"),
        ("C", "Carrera", 25.13, "center"),
    ],
}
STUDENTS_TAB_COLOR = {"ip": (5, 0.6), "pa": (5, 0.6), "fpia": (5, 0.6)}
DEFINITIVAS_TAB_COLOR = {"ip": (9, 0.6), "pa": (9, 0.6), "fpia": (9, 0.6)}


# ── Tipo fpia — Fundamentos de Programación IA ───────────────────────────────
# Solo tiene 2 hojas: Estudiantes y Definitivas (sin hojas de componentes).

FPIA_SHEET_ORDER = [STUDENTS_SHEET_NAME, DEFINITIVAS_SHEET_NAME]

_FPIA_HEADERS = [
    ("A", "#", None),
    ("B", "#", None),
    ("C", "ID", None),
    ("D", "Nombre", None),
    ("E", "Uso de intérpretes online", 20),
    ("F", " Implementación de algoritmos", 60),
    ("G", "Funciones y descomposición de problemas", 40),
    ("H", "Clases Objetos y descomposición de problemas", 40),
    ("I", "Ejercicio introductorio a Pandas", 40),
    ("J", "Cuestionario Individual", 10),
    ("K", "Cuestionario Individual M3", 10),
    ("L", "Subtotal\nEvaluaciones sumativas\n(50%)", "=SUM(E2:K2)"),
    ("M", "", "Nota"),
    ("N", "P. intermedia Componente teórico", 40),
    ("O", "P. intermedia Componente práctico", 60),
    ("P", "Subtotal\nPrueba evaluativa intermedia\n(25%)", "=SUM(N2:O2)"),
    ("Q", "", "Nota"),
    ("R", "P. final Componente teórico", 50),
    ("S", "P. final Componente práctico", 60),
    ("T", "Subtotal\nPrueba evaluativa final\n (25%)", "=SUM(R2:S2)"),
    ("U", "", "Nota"),
    ("V", "Definitiva", None),
]

# Columnas cuya fila 2 (máximos) usa numfmt "0" en vez del "General" por defecto.
FPIA_ROW2_INT_COLS = {"E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "O", "P", "Q", "R", "S", "T", "U"}
# Columnas de subtotal/nota con relleno theme5/tint0.6 (igual en fila 1, 2 y datos).
FPIA_FILL_COLS = {"L", "M", "P", "Q", "T", "U"}
# Merges de encabezado de fila 1 (subtotal + nota comparten título arriba) y
# los pares de 2 filas (#, ID, Nombre, Definitiva) que también son merge en el
# archivo real.
FPIA_HEADER_MERGES = [
    "A1:A2", "B1:B2", "C1:C2", "D1:D2",
    "L1:M1", "P1:Q1", "T1:U1", "V1:V2",
]

# Columnas de notas crudas que arrancan en 0.
_FPIA_RAW_GRADE_COLS = ["E", "F", "G", "H", "I", "J", "K", "N", "O", "R", "S"]
# numfmt "0.0" en las columnas de "Nota"/subtotales finales por estilo original.
FPIA_DATA_DECIMAL_COLS = {"M", "Q", "R", "T", "U", "V"}


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
# Además de "Estudiantes"/"Definitivas" se generan las hojas de componentes de
# las que "Definitivas" trae sus fórmulas, en el orden exacto de los archivos
# reales. El contenido de esas hojas (títulos de talleres/puntos) es un valor
# por defecto genérico -editable por el profesor cada semestre-, no el
# contenido literal de un semestre específico.

IP_SHEET_ORDER = [
    STUDENTS_SHEET_NAME,
    DEFINITIVAS_SHEET_NAME,
    "Talleres y Quices",
    "Parcial 1",
    "Parcial 2",
    "Parcial 3",
    "Proyecto",
]

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
    ("K", "Definitiva", "=SUM(D2:J2)"),
    ("M", "Estado", None),
    ("N", "Alerta de riesgo", None),
    ("O", "Nota minima necesaria", None),
]

_IP_FINAL_COL = "K"
IP_DEFINITIVAS_COL_WIDTHS = {
    "A": 4.25, "B": 13.25, "C": 33.38, "D": 12.88, "H": 15.88, "I": 12.88,
    "L": 13.0, "M": 14.0, "N": 24.0, "O": 24.0,
}
IP_DEFINITIVAS_MERGES = ["A1:A2", "B1:B2", "C1:C2"]


def _ip_row(r: int, er: int) -> dict:
    row = {
        "A": r - 2,
        "B": _student_ref("B", er),
        "C": _student_ref("A", er),
        "D": f"=+'Parcial 1'!G{r}",
        "E": f"='Parcial 2'!G{r}",
        "F": f"='Parcial 3'!K{r}",
        "G": f"=+Proyecto!E{r}",
        "H": f"='Talleres y Quices'!S{r}+IF(L{r}>4.5,0.4,0)",
        "I": f"=Proyecto!F{r}",
        "J": f"=Proyecto!G{r}",
        "K": (
            f"=D{r}*$D$2+E{r}*$E$2+F{r}*$F$2+G{r}*$G$2"
            f"+I{r}*$I$2+J{r}*$J$2+H{r}*$H$2"
        ),
        "L": f"=AVERAGE(G{r},I{r},J{r})",
        "M": f'=IF($B{r}="","",IF(K{r}>=2.95,"Aprobado","Reprobado"))',
        "N": (
            f'=IF($B{r}="","",IF(COUNTIF(D{r}:J{r},0)>0,'
            f'"Tiene componente(s) en 0",IF(AND(M{r}="Aprobado",K{r}<3.3),'
            f'"Aprobo por margen estrecho",IF(AND(M{r}="Reprobado",K{r}>=2.5),'
            f'"Cerca de aprobar",""))))'
        ),
        "O": (
            f'=IF($B{r}="","",IF(M{r}="Aprobado","Ya aprobo",'
            f'IF(COUNTIF(D{r}:J{r},0)=0,"No aplica (sin componentes en 0)",'
            f'IF((3-K{r})/SUMPRODUCT((D{r}:J{r}=0)*$D$2:$J$2)>5,"Inalcanzable",'
            f'ROUND((3-K{r})/SUMPRODUCT((D{r}:J{r}=0)*$D$2:$J$2),2)))))'
        ),
    }
    return row


# Hojas de componentes de ip: headers/columnas de nota/columna+fórmula del
# subtotal "Definitiva" de cada hoja, referenciado desde Definitivas!.
IP_AUX_SHEETS = {
    "Talleres y Quices": {
        "tab_color": None,
        "headers": [
            "#", "#", "ID", "Nombre",
            "Taller 01", "Taller 02", "Taller 03", "Taller 04", "Taller 05",
            "Taller 06", "Taller 07", "Taller 08", "Taller 09", "Taller 10",
            "Taller 11", "Taller 12", "Taller 13", "Taller 14", "Definitiva",
        ],
        "grade_cols": list("EFGHIJKLMNOPQR"),
        "final_col": "S",
        "final_formula": "=IFERROR(AVERAGE(E{r}:R{r}), 0)",
        "comment_col": None,
    },
    "Parcial 1": {
        "tab_color": None,
        "headers": ["#", "#", "ID", "Nombre", "Punto 1", "Punto 2", "Parcial 1", "Comentarios"],
        "grade_cols": ["E", "F"],
        "final_col": "G",
        "final_formula": "=+F{r}+E{r}",
        "comment_col": "H",
    },
    "Parcial 2": {
        "tab_color": None,
        "headers": ["#", "#", "ID", "Nombre", "Punto 1", "Punto 2", "Parcial 2", "Comentarios"],
        "grade_cols": ["E", "F"],
        "final_col": "G",
        "final_formula": "=E{r}+F{r}",
        "comment_col": "H",
    },
    "Parcial 3": {
        "tab_color": None,
        "headers": ["#", "#", "ID", "Nombre", "Punto 1", "Punto 2", "Parcial 3", "Comentarios"],
        "grade_cols": ["E", "F"],
        "final_col": "K",
        "final_formula": "=SUM(E{r}:J{r})/20",
        "comment_col": "L",
    },
    "Proyecto": {
        "tab_color": None,
        "headers": ["#", "#", "ID", "Nombre", "Proyecto 1", "Proyecto 2", "Sustentación", "Comentarios", "Grupo"],
        "grade_cols": ["E", "F", "G"],
        "final_col": None,
        "final_formula": None,
        "comment_col": "H",
    },
}


# ── Tipo pa — Programación Avanzada ──────────────────────────────────────────

PA_SHEET_ORDER = [
    STUDENTS_SHEET_NAME,
    DEFINITIVAS_SHEET_NAME,
    "Parcial C++",
    "Parcial Java",
    "Proyecto C++",
    "Proyecto Java",
    "Talleres",
]

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
    ("J", "Definitiva", "=SUM(D2:I2)"),
]

_PA_FINAL_COL = "J"
PA_DEFINITIVAS_COL_WIDTHS = {"A": 4.29, "B": 13.29, "C": 33.43, "D": 14.43, "K": 13.57}


def _pa_row(r: int, er: int) -> dict:
    row = {
        "A": r - 2,
        "B": _student_ref("B", er),
        "C": _student_ref("A", er),
        "D": f"='Parcial C++'!M{r}",
        "E": f"=+'Parcial Java'!M{r}",
        "F": f"='Proyecto C++'!H{r}",
        "G": f"=IF('Proyecto Java'!I{r}>5,5,'Proyecto Java'!I{r})",
        "H": f"=Talleres!U{r}",
        "I": f"=Talleres!V{r}",
        "J": f"=D{r}*$D$2+E{r}*$E$2+H{r}*$H$2+I{r}*$I$2+G{r}*$G$2+F{r}*$F$2",
    }
    return row


PA_AUX_SHEETS = {
    "Parcial C++": {
        "tab_color": (5, 0.8),
        "headers": [
            "#", "#", "ID", "Nombre",
            "Punto 1", "Punto 2", "Punto 3", "Punto 4",
            "Punto 5", "Punto 6", "Punto 7", "Punto 8",
            "Parcial C++ (0-5)", "Comentarios",
        ],
        "grade_cols": list("EFGHIJKL"),
        "final_col": "M",
        "final_formula": "=IFERROR(AVERAGE(E{r}:L{r}), 0)",
        "comment_col": "N",
    },
    "Parcial Java": {
        "tab_color": (5, 0.8),
        "headers": [
            "#", "#", "ID", "Nombre",
            "Punto 1", "Punto 2", "Punto 3", "Punto 4",
            "Punto 5", "Punto 6", "Punto 7", "Punto 8",
            "Parcial Java (0-5)", "Comentarios",
        ],
        "grade_cols": list("EFGHIJKL"),
        "final_col": "M",
        "final_formula": "=IFERROR(AVERAGE(E{r}:L{r}), 0)",
        "comment_col": "N",
    },
    "Proyecto C++": {
        "tab_color": (7, 0.8),
        "headers": ["#", "#", "ID", "Nombre", "Entrega 1", "Entrega 2", "Sustentación", "Proyecto C++ (0-5)", "Comentarios"],
        "grade_cols": ["E", "F", "G"],
        "final_col": "H",
        "final_formula": "=IFERROR(AVERAGE(E{r}:G{r}), 0)",
        "comment_col": "I",
    },
    "Proyecto Java": {
        "tab_color": (7, 0.8),
        "headers": ["#", "#", "ID", "Nombre", "Entrega 1", "Entrega 2", "Sustentación", "Proyecto Java (0-5)", "Comentarios"],
        "grade_cols": ["E", "F", "G"],
        "final_col": "I",
        "final_formula": "=IFERROR(AVERAGE(E{r}:G{r}), 0)",
        "comment_col": "J",
    },
    "Talleres": {
        "tab_color": (8, 0.8),
        "headers": [
            "#", "#", "ID", "Nombre",
            "Taller 01", "Taller 02", "Taller 03", "Taller 04",
            "Taller 05", "Taller 06", "Taller 07", "Taller 08",
            "Taller 09", "Taller 10", "Taller 11", "Taller 12",
            "Taller 13", "Taller 14", "Taller 15", "Taller 16",
            "Talleres C++ (0-5)", "Talleres Java (0-5)",
        ],
        "grade_cols": list("EFGHIJKLMNOPQRST"),
        "final_col": "U",
        "final_formula": "=IFERROR(AVERAGE(E{r}:M{r}), 0)",
        "extra_formulas": {"V": "=IFERROR(AVERAGE(N{r}:T{r}), 0)"},
        "comment_col": None,
    },
}

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
        "sheet_order": FPIA_SHEET_ORDER,
        "col_widths": {},
        "merges": [],
        "aux_sheets": {},
    },
    "ip": {
        "headers": _IP_HEADERS,
        "row_builder": _ip_row,
        "final_col": _IP_FINAL_COL,
        "has_summary": True,
        "sheet_order": IP_SHEET_ORDER,
        "col_widths": IP_DEFINITIVAS_COL_WIDTHS,
        "merges": IP_DEFINITIVAS_MERGES,
        "aux_sheets": IP_AUX_SHEETS,
    },
    "pa": {
        "headers": _PA_HEADERS,
        "row_builder": _pa_row,
        "final_col": _PA_FINAL_COL,
        "has_summary": True,
        "sheet_order": PA_SHEET_ORDER,
        "col_widths": PA_DEFINITIVAS_COL_WIDTHS,
        "merges": [],
        "aux_sheets": PA_AUX_SHEETS,
    },
}


def get_template(course_type: str) -> dict:
    """Devuelve la plantilla del tipo de curso, o lanza KeyError si no existe."""
    return TEMPLATES[course_type]
