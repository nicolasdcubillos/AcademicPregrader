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

# fpia Estudiantes: filas de datos en A y C quedan centradas (A además con
# wrap_text); pa: A (nombre) también wrap+center, E (Grupo) centrado; ip no
# centra ninguna columna de datos.
STUDENTS_DATA_ALIGN_CENTER = {"fpia": {"A", "C"}, "pa": {"E"}}
STUDENTS_DATA_WRAP_COLS = {"fpia": {"A"}, "pa": {"A"}}

# Altura explícita de la fila 1 (encabezado) de "Estudiantes". La referencia
# de ip sí trae una altura explícita de 15.0pt; fpia también; pa deja la
# altura por defecto de la hoja (no se debe escribir row_dimensions para no
# introducir una diferencia con el archivo real).
STUDENTS_HEADER_ROW_HEIGHT = {"ip": 15.0, "pa": None, "fpia": 15.0}


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

# Anchos de columna reales de Definitivas (extraídos de FPIA 1329.xlsx); las
# columnas que no aparecen aquí quedan con el ancho por defecto de la hoja.
# La columna B ("#" auxiliar sin uso) está oculta en el archivo real.
FPIA_DEFINITIVAS_COL_WIDTHS = {
    "A": 4.25, "B": 8.125, "C": 13.25, "D": 33.375, "E": 16.125,
    "L": 15.875, "N": 12.875,
}
FPIA_DEFINITIVAS_HIDDEN_COLS = {"B"}

# Fila de promedios (=AVERAGE(...)) justo debajo de la última fila de
# estudiante: en el archivo real cubre de L a V (los subtotales/nota/
# definitiva), no las columnas de notas crudas.
FPIA_AVERAGES_COLS = ("L", "V")

# Formato condicional: 2 reglas (blancos / <3) en la columna "Definitiva",
# incluyendo la fila de promedios (V{first}:V{last+1}).
FPIA_CF_COL = "V"
FPIA_CF_THRESHOLD = "3"

# Alturas de fila 1/2 de "Definitivas": la 58.5pt de la fila 1 es necesaria
# para que los encabezados multilínea de subtotal (L/P/T) no queden cortados.
FPIA_DEFINITIVAS_ROW_HEIGHTS = {1: 58.5, 2: 22.5}


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

# Bloque resumen (Total/Retiro/Aprobados/Reprobado): en el archivo real las
# etiquetas van en la columna F y los valores en G, empezando 4 filas después
# de la última fila de estudiante (no 2, y no en A/B).
IP_SUMMARY_LABEL_COL = "F"
IP_SUMMARY_VALUE_COL = "G"

# Fila de promedios (=AVERAGE(...)) inmediatamente después de la última fila
# de estudiante, para las columnas D..K (todas las de nota + Definitiva).
IP_AVERAGES_COLS = ("D", "K")

# Formato condicional (blancos / <2.95) sobre las columnas de nota D..K.
IP_CF_RANGE = ("D", "K")
IP_CF_THRESHOLD = "2.95"

# Alturas de fila 1/2 de "Definitivas" (la referencia usa el alto por
# defecto de la hoja, no se necesita override).
IP_DEFINITIVAS_ROW_HEIGHTS: dict = {}

# Alturas de fila 1/2 por hoja auxiliar (extraídas de IP 1189 M-J.xlsx). Las
# filas de datos (3+) tienen alturas ad-hoc en el archivo real (comentarios
# largos de un semestre puntual) que no se replican -son ruido de edición,
# no parte de la plantilla-.
IP_AUX_ROW_HEIGHTS = {
    "Talleres y Quices": {1: 19.5, 2: 19.5},
    "Parcial 1": {1: 15.0},
    "Parcial 2": {1: 15.0, 2: 14.25},
    "Parcial 3": {1: 14.45, 2: 30.0},
    "Proyecto": {1: 14.45, 2: 15.0},
}


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
        "final_numfmt": "0.0",
        "comment_col": None,
        "wrap_final_col": True,
        # Único aux sheet cuyos encabezados de nota usan Calibri negro (no
        # Aptos Narrow) en el archivo real -detalle histórico de ese tab-, y
        # cuyo borde de columnas de nota va en negro (rgb) en vez del gris
        # indexado por defecto.
        "grade_header_font": "calibri_black",
        "grade_border_color": "black",
        "widths": {"A": 4.25, "B": 8.125, "C": 13.25, "D": 33.375, "E": 23.75, "S": 24.25},
        "cf_range": None,
    },
    "Parcial 1": {
        "tab_color": None,
        "headers": ["#", "#", "ID", "Nombre", "Punto 1", "Punto 2", "Parcial 1", "Comentarios"],
        "grade_cols": ["E", "F"],
        "final_col": "G",
        "final_formula": "=+F{r}+E{r}",
        "final_numfmt": "0.00",
        "comment_col": "H",
        "no_wrap_cols": {"H"},
        "widths": {"A": 4.25, "B": 8.125, "C": 13.25, "D": 33.375, "E": 26.25, "F": 30.625, "G": 18.25, "H": 54.75},
        "cf_range": ("E", "H"),
    },
    "Parcial 2": {
        "tab_color": None,
        "headers": ["#", "#", "ID", "Nombre", "Punto 1", "Punto 2", "Parcial 2", "Comentarios"],
        "grade_cols": ["E", "F"],
        "final_col": "G",
        "final_formula": "=E{r}+F{r}",
        "final_numfmt": "0.00",
        "comment_col": "H",
        "no_wrap_cols": {"H"},
        "widths": {"A": 4.25, "B": 8.125, "C": 13.25, "D": 33.375, "E": 27.875, "G": 24.75, "H": 38.625},
        "cf_range": ("E", "H"),
    },
    "Parcial 3": {
        "tab_color": None,
        "headers": ["#", "#", "ID", "Nombre", "Punto 1", "Punto 2", "Parcial 3", "Comentarios"],
        "grade_cols": ["E", "F"],
        "final_col": "K",
        "final_formula": "=SUM(E{r}:J{r})/20",
        "final_numfmt": "0.00",
        "comment_col": "L",
        "widths": {"A": 4.25, "B": 8.125, "C": 13.25, "D": 33.375, "E": 26.25, "F": 32.125, "L": 20.375},
        "cf_range": ("E", "L"),
    },
    "Proyecto": {
        "tab_color": None,
        "headers": ["#", "#", "ID", "Nombre", "Proyecto 1", "Proyecto 2", "Sustentación", "Comentarios", "Grupo"],
        "grade_cols": ["E", "F", "G"],
        "final_col": None,
        "final_formula": None,
        "final_numfmt": None,
        "comment_col": "H",
        "no_wrap_cols": {"E", "F", "G", "H"},
        "widths": {"A": 4.25, "B": 8.125, "C": 13.25, "D": 33.375, "E": 18.25, "H": 54.625},
        "cf_range": ("E", "H"),
    },
}


# ── Tipo pa — Programación Avanzada ──────────────────────────────────────────

PA_DEFINITIVAS_2_SHEET_NAME = "Definitivas (2)"

PA_SHEET_ORDER = [
    STUDENTS_SHEET_NAME,
    PA_DEFINITIVAS_2_SHEET_NAME,
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

# Bloque resumen: etiquetas en H, valores en I (a diferencia de ip que usa
# F/G), empezando 4 filas después de la última fila de estudiante.
PA_SUMMARY_LABEL_COL = "H"
PA_SUMMARY_VALUE_COL = "I"

# Fila de promedios (=AVERAGE(...)) inmediatamente después de la última fila
# de estudiante, para las columnas D..J (notas + Definitiva).
PA_AVERAGES_COLS = ("D", "J")

# Formato condicional (blancos / <2.95) sobre las columnas de nota D..J.
PA_CF_RANGE = ("D", "J")
PA_CF_THRESHOLD = "2.95"

# "Definitivas (2)" es una hoja adicional presente en el archivo real de pa,
# ubicada justo después de "Estudiantes". En el archivo real el profesor
# pega ahí los valores ya calculados de fin de semestre (una foto estática,
# sin fórmulas) para su propio archivo -no podemos reproducir ese contenido
# puntual-. Generamos la hoja con la MISMA estructura/estilo/fórmulas que
# "Definitivas" para que el archivo tenga la hoja y se vea igual; el
# profesor puede pegar ahí sus valores finales como hace habitualmente.

# Alturas de fila 1/2 de "Definitivas" (default de la hoja en la referencia).
PA_DEFINITIVAS_ROW_HEIGHTS: dict = {}

# Alturas de fila 1/2 por hoja auxiliar (extraídas de PA 1243 M-J.xlsx).
PA_AUX_ROW_HEIGHTS = {
    "Parcial C++": {1: 18.0, 2: 18.0},
    "Parcial Java": {1: 23.25, 2: 23.25},
    "Proyecto C++": {1: 16.5, 2: 16.5},
    "Proyecto Java": {1: 33.0},
    "Talleres": {1: 26.25, 2: 26.25},
}


def _pa_row(r: int, er: int) -> dict:
    row = {
        "A": r - 2,
        "B": _student_ref("B", er),
        "C": _student_ref("A", er),
        "D": f"='Parcial C++'!M{r}",
        "E": f"=+'Parcial Java'!M{r}",
        "F": f"='Proyecto C++'!H{r}",
        "G": f"=IF('Proyecto Java'!H{r}>5,5,'Proyecto Java'!H{r})",
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
        "final_numfmt": "0.00",
        "comment_col": "N",
        "no_wrap_cols": {"N"},
        "small_font_cols": {"G", "L"},
        "widths": {"A": 4.29, "B": 8.14, "C": 13.29, "D": 39.43, "E": 27.0, "M": 18.29, "N": 54.71},
        "cf_range": ("E", "L"),
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
        "final_numfmt": "0.00",
        "comment_col": "N",
        "no_wrap_cols": {"N"},
        "small_font_cols": {"K"},
        "widths": {"A": 4.29, "B": 8.14, "C": 13.29, "D": 38.57, "E": 19.14, "G": 21.57, "I": 22.43, "J": 21.57, "K": 25.29, "L": 21.57, "N": 38.57},
        "cf_range": ("E", "L"),
    },
    "Proyecto C++": {
        "tab_color": (7, 0.8),
        "headers": ["#", "#", "ID", "Nombre", "Entrega 1", "Entrega 2", "Sustentación", "Proyecto C++ (0-5)", "Comentarios"],
        "grade_cols": ["E", "F", "G"],
        "final_col": "H",
        "final_formula": "=IFERROR(AVERAGE(E{r}:G{r}), 0)",
        "final_numfmt": "0.00",
        "comment_col": "I",
        "widths": {"A": 4.29, "B": 8.14, "C": 13.29, "D": 41.0, "E": 18.3, "G": 54.6, "H": 15.3},
        "cf_range": ("E", "H"),
        "grade_border_color": "black",
        "border_black_cols": {"G", "H", "I"},
        "no_wrap_cols": {"G", "I"},
        "wrap_final_col": True,
    },
    "Proyecto Java": {
        "tab_color": (7, 0.8),
        "headers": ["#", "#", "ID", "Nombre", "Entrega 1", "Entrega 2", "Sustentación", "Proyecto Java (0-5)", "Comentarios"],
        "grade_cols": ["E", "F", "G"],
        "final_col": "H",
        "final_formula": "=IFERROR(AVERAGE(E{r}:G{r}), 0)",
        "final_numfmt": "0.00",
        "comment_col": "I",
        "widths": {"A": 4.29, "B": 8.14, "C": 13.29, "D": 41.0, "E": 18.3, "G": 12.0, "H": 54.6, "I": 15.3},
        "cf_range": ("E", "H"),
        "grade_border_color": "black",
        "border_black_cols": {"H", "I"},
        "no_wrap_cols": {"I"},
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
        "final_numfmt": "0.00",
        "extra_formulas": {"V": "=IFERROR(AVERAGE(N{r}:T{r}), 0)"},
        "comment_col": None,
        "widths": {"A": 4.29, "B": 8.14, "C": 13.29, "D": 40.4, "E": 23.7, "R": 24.3, "T": 24.3, "U": 15.1},
        "cf_range": ("E", "V"),
        "wrap_final_col": True,
        "wrap_cols": {"V"},
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
        "col_widths": FPIA_DEFINITIVAS_COL_WIDTHS,
        "hidden_cols": FPIA_DEFINITIVAS_HIDDEN_COLS,
        "merges": [],
        "aux_sheets": {},
        "aux_row_heights": {},
        "definitivas_row_heights": FPIA_DEFINITIVAS_ROW_HEIGHTS,
        "summary_label_col": None,
        "summary_value_col": None,
        "averages_cols": FPIA_AVERAGES_COLS,
        "cf_range": (FPIA_CF_COL, FPIA_CF_COL),
        "cf_threshold": FPIA_CF_THRESHOLD,
        "cf_includes_averages_row": True,
        "has_definitivas_2": False,
    },
    "ip": {
        "headers": _IP_HEADERS,
        "row_builder": _ip_row,
        "final_col": _IP_FINAL_COL,
        "has_summary": True,
        "sheet_order": IP_SHEET_ORDER,
        "col_widths": IP_DEFINITIVAS_COL_WIDTHS,
        "hidden_cols": set(),
        "merges": IP_DEFINITIVAS_MERGES,
        "aux_sheets": IP_AUX_SHEETS,
        "aux_row_heights": IP_AUX_ROW_HEIGHTS,
        "definitivas_row_heights": IP_DEFINITIVAS_ROW_HEIGHTS,
        "summary_label_col": IP_SUMMARY_LABEL_COL,
        "summary_value_col": IP_SUMMARY_VALUE_COL,
        "averages_cols": IP_AVERAGES_COLS,
        "cf_range": IP_CF_RANGE,
        "cf_threshold": IP_CF_THRESHOLD,
        "cf_includes_averages_row": False,
        "has_definitivas_2": False,
    },
    "pa": {
        "headers": _PA_HEADERS,
        "row_builder": _pa_row,
        "final_col": _PA_FINAL_COL,
        "has_summary": True,
        "sheet_order": PA_SHEET_ORDER,
        "col_widths": PA_DEFINITIVAS_COL_WIDTHS,
        "hidden_cols": set(),
        "merges": [],
        "aux_sheets": PA_AUX_SHEETS,
        "aux_row_heights": PA_AUX_ROW_HEIGHTS,
        "definitivas_row_heights": PA_DEFINITIVAS_ROW_HEIGHTS,
        "summary_label_col": PA_SUMMARY_LABEL_COL,
        "summary_value_col": PA_SUMMARY_VALUE_COL,
        "averages_cols": PA_AVERAGES_COLS,
        "cf_range": PA_CF_RANGE,
        "cf_threshold": PA_CF_THRESHOLD,
        "cf_includes_averages_row": False,
        "has_definitivas_2": True,
        "definitivas_2_sheet_name": PA_DEFINITIVAS_2_SHEET_NAME,
    },
}


def get_template(course_type: str) -> dict:
    """Devuelve la plantilla del tipo de curso, o lanza KeyError si no existe."""
    return TEMPLATES[course_type]
