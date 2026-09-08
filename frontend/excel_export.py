"""
Generador del archivo Excel de notas "listo para llenar" para un curso.

Dado un curso (con su `course_type` ya asignado) y su roster de estudiantes,
arma un `openpyxl.Workbook` que replica -construido desde cero, sin empaquetar
ningún .xlsx binario como plantilla- el formato visual de los archivos reales
que ya usan los profesores: mismo orden de hojas, misma fuente ("Aptos
Narrow"), colores de pestaña (tabColor) por tema, bordes, alineación, formato
numérico, celdas combinadas y formato condicional. Los pesos/porcentajes y
puntajes máximos se leen siempre de `grade_templates.py` para que sigan
siendo configurables sin tocar este módulo.

Alcance de la réplica visual (ver PR para más detalle):
- Hojas "Estudiantes" y "Definitivas" de los 3 tipos: fidelidad completa
  (fuente, bordes, alineación, formato numérico, celdas combinadas, colores de
  pestaña y formato condicional), verificada con un script de comparación
  celda por celda contra los archivos de referencia.
- Hojas auxiliares de componentes (Parcial 1/2/3, Proyecto, Talleres y Quices
  para "ip"; Parcial C++/Java, Proyecto C++/Java, Talleres para "pa"): mismo
  orden, mismo color de pestaña y misma estructura de bordes/alineación, pero
  con encabezados de ejercicio GENÉRICOS (p. ej. "Punto 1", "Taller 01") en
  vez del contenido literal de un semestre específico -ese contenido cambia
  cada semestre y el profesor lo renombra directamente en la celda, igual que
  hace hoy con los pesos-. No se replica la hoja "Definitivas (2)" del
  archivo de PA porque es una copia de valores ya calculados que el profesor
  pegó para su propio uso (no hace parte de la plantilla "lista para
  llenar").

Nota sobre un bug conocido de openpyxl: `ws.cell(row=r, column=c,
value=None)` NO limpia el contenido de una celda existente (el argumento
`value=None` se ignora en esa llamada). Aquí no reutilizamos celdas —el
workbook se construye desde cero— así que no aplica, pero si en el futuro se
reutiliza una hoja, hay que limpiar con `ws.cell(row=r, column=c).value =
None`.
"""

import re

from openpyxl import Workbook
from openpyxl.formatting.rule import CellIsRule, FormulaRule
from openpyxl.styles import Alignment, Border, Color, Font, PatternFill, Side
from openpyxl.utils import column_index_from_string, get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

import grade_templates as gt

_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# ── Estilos compartidos ───────────────────────────────────────────────────
FONT_NAME = "Aptos Narrow"
FONT_SIZE = 11


def _theme(theme: int, tint: float = 0.0) -> Color:
    return Color(theme=theme, tint=tint)


_THEME1 = _theme(1, 0.0)
_BLACK = Color(rgb="FF000000")

HEADER_FONT = Font(name=FONT_NAME, size=FONT_SIZE, bold=True, italic=False, color=_THEME1)
DATA_FONT = Font(name=FONT_NAME, size=FONT_SIZE, bold=False, italic=False, color=_THEME1)
DATA_FONT_BOLD = Font(name=FONT_NAME, size=FONT_SIZE, bold=True, italic=False, color=_THEME1)
DATA_FONT_BLACK = Font(name=FONT_NAME, size=FONT_SIZE, bold=False, italic=False, color=_BLACK)

_THIN = Side(style="thin", color=Color(indexed=64))
_INVISIBLE = Side(style=None, color=None)
BORDER_ALL = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
BORDER_LRB = Border(left=_THIN, right=_THIN, top=_INVISIBLE, bottom=_THIN)

ALIGN_CENTER = Alignment(horizontal="center", vertical="center")
ALIGN_CENTER_WRAP = Alignment(horizontal="center", vertical="center", wrap_text=True)
ALIGN_H_CENTER = Alignment(horizontal="center")

NUMFMT_ID = "00000000000"
NUMFMT_GRADE_2 = "0.00"
NUMFMT_GRADE_1 = "0.0"
NUMFMT_PCT = "0%"
NUMFMT_INT = "0"

_FILL_FPIA_SUBTOTAL = PatternFill("solid", fgColor=_theme(5, 0.6))
_FILL_RETIRO = PatternFill("solid", fgColor=_theme(5, 0.8))


def _numeric_or_text(value: str):
    """Convierte el ID de un estudiante a número si es puramente numérico."""
    value = (value or "").strip()
    if value and re.fullmatch(r"-?\d+", value):
        return int(value)
    return value


def _set_cell(ws: Worksheet, row: int, col, value=None, font=None, border=None,
              alignment=None, number_format=None, fill=None):
    """Escribe una celda y le aplica el estilo indicado. `col` puede ser una
    letra ("A") o un índice 1-based."""
    col_idx = column_index_from_string(col) if isinstance(col, str) else col
    cell = ws.cell(row=row, column=col_idx)
    if value is not None:
        cell.value = value
    if font is not None:
        cell.font = font
    if border is not None:
        cell.border = border
    if alignment is not None:
        cell.alignment = alignment
    if number_format is not None:
        cell.number_format = number_format
    if fill is not None:
        cell.fill = fill
    return cell


# ── Hoja "Estudiantes" ────────────────────────────────────────────────────

def _build_students_sheet(wb: Workbook, course_type: str, students: list[dict]) -> Worksheet:
    ws = wb.create_sheet(gt.STUDENTS_SHEET_NAME)
    theme, tint = gt.STUDENTS_TAB_COLOR[course_type]
    ws.sheet_properties.tabColor = _theme(theme, tint)

    columns = gt.STUDENTS_COLUMNS[course_type]
    for col_letter, title, width, align in columns:
        header_align = Alignment(horizontal=align) if align else None
        if course_type == "pa" and col_letter == "A":
            header_align = Alignment(wrap_text=True)
        _set_cell(ws, 1, col_letter, value=title, font=HEADER_FONT, alignment=header_align)
        ws.column_dimensions[col_letter].width = width

    name_col, id_col = columns[0][0], columns[1][0]
    for i, student in enumerate(students):
        row = 2 + i
        _set_cell(ws, row, name_col, value=student.get("full_name") or "", font=DATA_FONT_BLACK)
        _set_cell(
            ws, row, id_col,
            value=_numeric_or_text(student.get("org_id")),
            font=DATA_FONT_BLACK, alignment=ALIGN_H_CENTER,
        )
    return ws


# ── Hoja "Definitivas" ────────────────────────────────────────────────────

def _apply_ip_data_style(ws, col_letter, row):
    if col_letter == "A":
        ws.cell(row=row, column=1).font = DATA_FONT_BOLD
        ws.cell(row=row, column=1).alignment = ALIGN_CENTER
        ws.cell(row=row, column=1).border = BORDER_ALL
    elif col_letter == "B":
        cell = ws.cell(row=row, column=2)
        cell.font = DATA_FONT_BOLD
        cell.alignment = ALIGN_CENTER_WRAP
        cell.border = BORDER_ALL
        cell.number_format = NUMFMT_ID
    elif col_letter == "C":
        cell = ws.cell(row=row, column=3)
        cell.font = DATA_FONT
        cell.alignment = ALIGN_CENTER
        cell.border = BORDER_ALL
    elif col_letter in ("D", "E", "F", "G", "H", "I", "J"):
        idx = column_index_from_string(col_letter)
        cell = ws.cell(row=row, column=idx)
        cell.font = DATA_FONT
        cell.alignment = ALIGN_CENTER
        cell.border = BORDER_ALL
        cell.number_format = NUMFMT_GRADE_2
    elif col_letter == "K":
        cell = ws.cell(row=row, column=11)
        cell.font = DATA_FONT_BOLD
        cell.alignment = ALIGN_CENTER
        cell.border = BORDER_ALL
        cell.number_format = NUMFMT_GRADE_2
    elif col_letter == "L":
        cell = ws.cell(row=row, column=12)
        cell.font = DATA_FONT_BLACK
        cell.alignment = ALIGN_H_CENTER
        cell.number_format = NUMFMT_GRADE_2
    elif col_letter in ("M", "N", "O"):
        idx = column_index_from_string(col_letter)
        cell = ws.cell(row=row, column=idx)
        cell.font = DATA_FONT
        cell.alignment = ALIGN_CENTER
        cell.border = BORDER_ALL


def _apply_pa_data_style(ws, col_letter, row):
    idx = column_index_from_string(col_letter)
    cell = ws.cell(row=row, column=idx)
    cell.alignment = ALIGN_CENTER_WRAP if col_letter == "B" else ALIGN_CENTER
    cell.border = BORDER_ALL
    if col_letter in ("A", "B"):
        cell.font = DATA_FONT_BOLD
        if col_letter == "B":
            cell.number_format = NUMFMT_ID
    elif col_letter == "C":
        cell.font = DATA_FONT
    elif col_letter == "J":
        cell.font = DATA_FONT_BOLD
        cell.number_format = NUMFMT_GRADE_1
    else:
        cell.font = DATA_FONT
        cell.number_format = NUMFMT_GRADE_1


def _apply_fpia_data_style(ws, col_letter, row):
    idx = column_index_from_string(col_letter)
    cell = ws.cell(row=row, column=idx)
    cell.border = BORDER_ALL
    if col_letter in gt.FPIA_FILL_COLS:
        cell.fill = _FILL_FPIA_SUBTOTAL
    if col_letter == "C":
        cell.font = DATA_FONT_BOLD
        cell.alignment = ALIGN_CENTER_WRAP
        cell.number_format = NUMFMT_ID
    elif col_letter in ("A", "B"):
        cell.font = DATA_FONT_BOLD
        cell.alignment = ALIGN_CENTER
    elif col_letter == "V":
        cell.font = DATA_FONT_BOLD
        cell.alignment = ALIGN_CENTER
        cell.number_format = NUMFMT_GRADE_1
    else:
        cell.font = DATA_FONT
        cell.alignment = ALIGN_CENTER
        if col_letter in gt.FPIA_DATA_DECIMAL_COLS:
            cell.number_format = NUMFMT_GRADE_1


_DATA_STYLERS = {
    "ip": _apply_ip_data_style,
    "pa": _apply_pa_data_style,
    "fpia": _apply_fpia_data_style,
}


def _build_definitivas_sheet(wb: Workbook, course_type: str, student_count: int) -> Worksheet:
    template = gt.get_template(course_type)
    headers = template["headers"]
    row_builder = template["row_builder"]

    ws = wb.create_sheet(gt.DEFINITIVAS_SHEET_NAME)
    theme, tint = gt.DEFINITIVAS_TAB_COLOR[course_type]
    ws.sheet_properties.tabColor = _theme(theme, tint)

    for merge_range in template["merges"]:
        ws.merge_cells(merge_range)
    if course_type == "fpia":
        for merge_range in gt.FPIA_HEADER_MERGES:
            ws.merge_cells(merge_range)

    fpia_header_fill_cols = {"L", "P", "T"}  # solo el título visible del grupo
    # En fpia los encabezados con texto largo (medición de un punto/tema) usan
    # una fuente más pequeña para que el título quepa en la columna angosta;
    # las columnas auxiliares sin texto (compañeras de un merge L1:M1, etc.)
    # y los encabezados cortos usan el tamaño normal.
    fpia_small_font_cols = {"E", "F", "G", "H", "I", "J", "K", "L", "N", "O", "P", "R", "S", "T"}

    for col_letter, title, row2_value in headers:
        col_idx = column_index_from_string(col_letter)
        has_title = bool(title)
        wrap = bool(title and "\n" in title)
        if course_type == "pa" and col_letter in ("H", "I"):
            wrap = True
        if course_type == "fpia" and col_letter in fpia_small_font_cols:
            wrap = True
        head_align = ALIGN_CENTER_WRAP if wrap else ALIGN_CENTER
        if course_type == "pa" and col_letter in ("A", "B", "C"):
            head_align = Alignment(vertical="center")
        if course_type == "fpia" and wrap:
            head_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
        if has_title:
            head_font = HEADER_FONT
            if course_type == "fpia" and col_letter in fpia_small_font_cols:
                head_font = Font(name=FONT_NAME, size=9, bold=True, color=_THEME1)
        else:
            head_font = DATA_FONT
            head_align = None
        head_cell = _set_cell(
            ws, 1, col_idx, value=title or None, font=head_font,
            border=BORDER_ALL, alignment=head_align,
        )
        if course_type == "fpia" and col_letter in fpia_header_fill_cols:
            head_cell.fill = _FILL_FPIA_SUBTOTAL

        if row2_value is not None:
            weight_cell = _set_cell(
                ws, 2, col_idx, value=row2_value, font=HEADER_FONT,
                border=BORDER_ALL, alignment=ALIGN_CENTER,
            )
            if course_type in ("ip", "pa"):
                weight_cell.number_format = NUMFMT_PCT
            elif course_type == "fpia":
                if col_letter in gt.FPIA_ROW2_INT_COLS:
                    weight_cell.number_format = NUMFMT_INT
                if col_letter in gt.FPIA_FILL_COLS:
                    weight_cell.fill = _FILL_FPIA_SUBTOTAL
        else:
            row2_align = Alignment(vertical="center") if course_type == "pa" and col_letter in ("A", "B", "C") else None
            row2_font = DATA_FONT_BOLD if course_type == "pa" and col_letter in ("A", "B", "C") else DATA_FONT
            _set_cell(ws, 2, col_idx, font=row2_font, border=BORDER_LRB, alignment=row2_align)

    if course_type == "ip":
        # Columna L ("Subtotal") no tiene encabezado propio en el archivo real
        # (queda en blanco en las filas 1-2), pero SÍ hereda la fuente por
        # defecto del libro (Aptos Narrow) en vez del Calibri de openpyxl.
        ws.cell(row=1, column=column_index_from_string("L")).font = DATA_FONT
        ws.cell(row=2, column=column_index_from_string("L")).font = DATA_FONT
    elif course_type == "pa":
        # Detalle exacto del archivo real: el borde compartido entre B1/C1 y
        # B2/C2 solo se dibuja una vez (abajo en fila 1 vs arriba en fila 2).
        for col in ("B", "C"):
            idx = column_index_from_string(col)
            b1, b2 = ws.cell(row=1, column=idx), ws.cell(row=2, column=idx)
            b1.border = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_INVISIBLE)
            b2.border = Border(left=_THIN, right=_THIN, top=_INVISIBLE, bottom=_THIN)
        ws.cell(row=2, column=column_index_from_string("A")).border = BORDER_ALL
    elif course_type == "fpia":
        # Detalle exacto del archivo real: el borde derecho de J1/K1 y el
        # izquierdo de M1/Q1/U1 (compañeras de merge) solo se dibuja una vez.
        for col in ("J", "K"):
            idx = column_index_from_string(col)
            ws.cell(row=1, column=idx).border = Border(left=_THIN, right=_INVISIBLE, top=_THIN, bottom=_THIN)
        for col in ("M", "Q", "U"):
            idx = column_index_from_string(col)
            ws.cell(row=1, column=idx).border = Border(left=_INVISIBLE, right=_THIN, top=_THIN, bottom=_THIN)

    first_data_row = 3
    last_data_row = first_data_row + student_count - 1
    styler = _DATA_STYLERS[course_type]

    for i in range(student_count):
        r = first_data_row + i
        er = 2 + i  # fila del estudiante en la hoja Estudiantes
        values = row_builder(r, er)
        for col_letter, value in values.items():
            col_idx = column_index_from_string(col_letter)
            ws.cell(row=r, column=col_idx).value = value
            styler(ws, col_letter, r)
        if course_type == "fpia":
            # La columna B no tiene fórmula/valor (queda sin usar), pero el
            # archivo real igual le aplica el mismo estilo que A/C (negrita,
            # centrada, con bordes).
            _apply_fpia_data_style(ws, "B", r)

    if template["has_summary"] and student_count > 0:
        final_col = template["final_col"]
        summary_first_row = last_data_row + 2
        for offset, label in enumerate(gt.SUMMARY_ROW_LABELS):
            row = summary_first_row + offset
            _set_cell(ws, row, 1, value=label, font=DATA_FONT_BOLD)
        total_row = summary_first_row
        retiro_row = summary_first_row + 1
        aprobados_row = summary_first_row + 2
        reprobado_row = summary_first_row + 3
        _set_cell(ws, total_row, 2, value=f"=COUNT(A{first_data_row}:A{last_data_row})", font=DATA_FONT)
        _set_cell(ws, retiro_row, 2, value=0, font=DATA_FONT, fill=_FILL_RETIRO)
        _set_cell(
            ws, aprobados_row, 2,
            value=f'=COUNTIF({final_col}{first_data_row}:{final_col}{last_data_row},">=2.95")',
            font=DATA_FONT,
        )
        _set_cell(
            ws, reprobado_row, 2,
            value=f"=B{total_row}-B{retiro_row}-B{aprobados_row}", font=DATA_FONT,
        )

    # Anchos de columna.
    default_widths = template["col_widths"]
    for col_letter, title, _ in headers:
        col_idx = column_index_from_string(col_letter)
        letter = get_column_letter(col_idx)
        if letter in default_widths:
            ws.column_dimensions[letter].width = default_widths[letter]
        elif title:
            longest_line = max((len(line) for line in title.split("\n")), default=0)
            ws.column_dimensions[letter].width = max(10, min(28, longest_line + 2))

    return ws


def _add_conditional_formatting(ws, course_type, first_data_row, last_data_row):
    if course_type == "ip":
        sqref = f"D{first_data_row}:K{last_data_row}"
    elif course_type == "pa":
        sqref = f"D{first_data_row}:J{last_data_row}"
    else:
        return
    ws.conditional_formatting.add(
        sqref,
        FormulaRule(formula=[f"LEN(TRIM(D{first_data_row}))=0"], font=Font(color="FF006100")),
    )
    ws.conditional_formatting.add(
        sqref,
        CellIsRule(operator="lessThan", formula=["2.95"], font=Font(color="FF9C0006")),
    )


# ── Hojas auxiliares de componentes (ip / pa) ────────────────────────────

def _build_aux_sheet(wb: Workbook, sheet_name: str, spec: dict, student_count: int) -> Worksheet:
    ws = wb.create_sheet(sheet_name)
    if spec.get("tab_color"):
        theme, tint = spec["tab_color"]
        ws.sheet_properties.tabColor = _theme(theme, tint)

    headers = spec["headers"]
    for i, title in enumerate(headers):
        col_idx = i + 1
        wrap = len(title) > 10
        head_align = ALIGN_CENTER_WRAP if wrap else ALIGN_CENTER
        _set_cell(ws, 1, col_idx, value=title, font=HEADER_FONT, border=BORDER_ALL, alignment=head_align)
        _set_cell(ws, 2, col_idx, font=DATA_FONT, border=BORDER_LRB)
        letter = get_column_letter(col_idx)
        if letter == "B":
            ws.column_dimensions[letter].width = 8.13
            ws.column_dimensions[letter].hidden = True
        elif letter == "A":
            ws.column_dimensions[letter].width = 4.25
        elif letter == "C":
            ws.column_dimensions[letter].width = 13.25
        else:
            longest = len(title)
            ws.column_dimensions[letter].width = max(10, min(35, longest + 4))

    grade_cols = spec.get("grade_cols", [])
    final_col = spec.get("final_col")
    final_formula = spec.get("final_formula")
    extra_formulas = spec.get("extra_formulas", {})

    for i in range(student_count):
        r = 3 + i
        er = 2 + i
        _set_cell(ws, r, "A", value=i + 1, font=DATA_FONT_BOLD, alignment=ALIGN_CENTER, border=BORDER_ALL)
        _set_cell(ws, r, "C", value=f"=Estudiantes!B{er}", font=DATA_FONT_BOLD,
                  alignment=ALIGN_CENTER_WRAP, border=BORDER_ALL, number_format=NUMFMT_ID)
        _set_cell(ws, r, "D", value=f"=Estudiantes!A{er}", font=DATA_FONT,
                  alignment=ALIGN_CENTER, border=BORDER_ALL)
        for col_letter in grade_cols:
            _set_cell(ws, r, col_letter, value=0, font=DATA_FONT,
                      alignment=ALIGN_CENTER_WRAP, border=BORDER_ALL, number_format=NUMFMT_GRADE_1)
        if final_col and final_formula:
            _set_cell(ws, r, final_col, value=final_formula.format(r=r), font=DATA_FONT,
                      alignment=ALIGN_CENTER, border=BORDER_ALL, number_format=NUMFMT_GRADE_2)
        for col_letter, formula in extra_formulas.items():
            _set_cell(ws, r, col_letter, value=formula.format(r=r), font=DATA_FONT,
                      alignment=ALIGN_CENTER, border=BORDER_ALL, number_format=NUMFMT_GRADE_2)
        comment_col = spec.get("comment_col")
        if comment_col:
            _set_cell(ws, r, comment_col, border=BORDER_ALL, alignment=ALIGN_CENTER_WRAP)

    return ws


def generate_course_workbook(course: dict, students: list[dict]) -> Workbook:
    """Genera el workbook de notas "listo para llenar" para `course`.

    `course` debe incluir `course_type` con uno de los valores válidos
    (`grade_templates.TEMPLATES`); de lo contrario lanza `ValueError` para que
    la ruta Flask lo traduzca en un error 400 pidiendo asignar el tipo antes.
    """
    course_type = (course or {}).get("course_type")
    if course_type not in gt.TEMPLATES:
        raise ValueError(
            "Este curso no tiene un tipo asignado (o es inválido). "
            "Asigna el tipo de curso (ip/pa/fpia) antes de generar el Excel."
        )

    template = gt.get_template(course_type)
    student_count = len(students)

    wb = Workbook()
    default_sheet = wb.active
    wb.remove(default_sheet)

    _build_students_sheet(wb, course_type, students)
    def_ws = _build_definitivas_sheet(wb, course_type, student_count)

    if student_count > 0:
        first_data_row = 3
        last_data_row = first_data_row + student_count - 1
        _add_conditional_formatting(def_ws, course_type, first_data_row, last_data_row)

    for sheet_name in template["sheet_order"]:
        if sheet_name in (gt.STUDENTS_SHEET_NAME, gt.DEFINITIVAS_SHEET_NAME):
            continue
        spec = template["aux_sheets"][sheet_name]
        _build_aux_sheet(wb, sheet_name, spec, student_count)

    # Reordena las hojas exactamente como en los archivos de referencia.
    for idx, sheet_name in enumerate(template["sheet_order"]):
        wb.move_sheet(sheet_name, offset=idx - wb.sheetnames.index(sheet_name))
    wb.active = 0

    return wb


def suggest_filename(course_name: str) -> str:
    """Nombre de archivo sugerido `{course_name}.xlsx`, sanitizado para Windows."""
    name = (course_name or "curso").strip()
    name = _INVALID_FILENAME_CHARS.sub("_", name)
    name = name.rstrip(" .") or "curso"
    return f"{name}.xlsx"
