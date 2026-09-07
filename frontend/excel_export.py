"""
Generador del archivo Excel de notas "listo para llenar" para un curso.

Dado un curso (con su `course_type` ya asignado) y su roster de estudiantes,
arma un `openpyxl.Workbook` con:

- Hoja "Estudiantes": nombre completo + ID de cada estudiante (sin columna de
  carrera).
- Hoja "Definitivas": la estructura de columnas, pesos/máximos por defecto y
  fórmulas correspondientes a la plantilla del tipo de curso
  (`grade_templates.py`), con las notas de los estudiantes en 0.

Nota sobre un bug conocido de openpyxl: `ws.cell(row=r, column=c,
value=None)` NO limpia el contenido de una celda existente (el argumento
`value=None` se ignora en esa llamada). Aquí no reutilizamos celdas —el
workbook se construye desde cero— así que no aplica, pero si en el futuro se
reutiliza una hoja, hay que limpiar con `ws.cell(row=r, column=c).value =
None`.
"""

import re

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import column_index_from_string, get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

import grade_templates as gt

_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

_HEADER_FONT = Font(bold=True, size=11)
_HEADER_FILL = PatternFill("solid", fgColor="1E293B")
_HEADER_FONT_WHITE = Font(bold=True, size=11, color="FFFFFF")
_HEADER_ALIGN = Alignment(horizontal="center", vertical="center", wrap_text=True)
_WEIGHT_FONT = Font(italic=True, size=10, color="475569")
_GRADE_NUMBER_FORMAT = "0.00"


def _numeric_or_text(value: str):
    """Convierte el ID de un estudiante a número si es puramente numérico."""
    value = (value or "").strip()
    if value and re.fullmatch(r"-?\d+", value):
        return int(value)
    return value


def _build_students_sheet(wb: Workbook, students: list[dict]) -> Worksheet:
    ws = wb.create_sheet(gt.STUDENTS_SHEET_NAME)
    ws.append(gt.STUDENTS_HEADERS)
    for col_idx in range(1, len(gt.STUDENTS_HEADERS) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.font = _HEADER_FONT_WHITE
        cell.fill = _HEADER_FILL
        cell.alignment = _HEADER_ALIGN

    for i, student in enumerate(students):
        row = 2 + i
        ws.cell(row=row, column=1).value = student.get("full_name") or ""
        ws.cell(row=row, column=2).value = _numeric_or_text(student.get("org_id"))

    ws.column_dimensions["A"].width = 38
    ws.column_dimensions["B"].width = 14
    ws.freeze_panes = "A2"
    return ws


def _build_definitivas_sheet(wb: Workbook, course_type: str, student_count: int) -> Worksheet:
    template = gt.get_template(course_type)
    headers = template["headers"]
    row_builder = template["row_builder"]

    ws = wb.create_sheet(gt.DEFINITIVAS_SHEET_NAME)

    for col_letter, title, row2_value in headers:
        col_idx = column_index_from_string(col_letter)
        head_cell = ws.cell(row=1, column=col_idx)
        head_cell.value = title
        head_cell.font = _HEADER_FONT
        head_cell.alignment = _HEADER_ALIGN
        if row2_value is not None:
            weight_cell = ws.cell(row=2, column=col_idx)
            weight_cell.value = row2_value
            weight_cell.font = _WEIGHT_FONT
            weight_cell.alignment = Alignment(horizontal="center", vertical="center")

    first_data_row = 3
    last_data_row = first_data_row + student_count - 1

    for i in range(student_count):
        r = first_data_row + i
        er = 2 + i  # fila del estudiante en la hoja Estudiantes
        values = row_builder(r, er)
        for col_letter, value in values.items():
            col_idx = column_index_from_string(col_letter)
            cell = ws.cell(row=r, column=col_idx)
            cell.value = value
            is_number_or_formula = isinstance(value, (int, float)) or (
                isinstance(value, str) and value.startswith("=")
            )
            if is_number_or_formula and col_letter != "A":
                cell.number_format = _GRADE_NUMBER_FORMAT

    if template["has_summary"] and student_count > 0:
        final_col = template["final_col"]
        summary_first_row = last_data_row + 2
        for offset, label in enumerate(gt.SUMMARY_ROW_LABELS):
            row = summary_first_row + offset
            ws.cell(row=row, column=1).value = label
            ws.cell(row=row, column=1).font = Font(bold=True)
        total_row = summary_first_row
        retiro_row = summary_first_row + 1
        aprobados_row = summary_first_row + 2
        reprobado_row = summary_first_row + 3
        ws.cell(row=total_row, column=2).value = f"=COUNT(A{first_data_row}:A{last_data_row})"
        ws.cell(row=retiro_row, column=2).value = 0
        ws.cell(row=aprobados_row, column=2).value = (
            f'=COUNTIF({final_col}{first_data_row}:{final_col}{last_data_row},">=2.95")'
        )
        ws.cell(row=reprobado_row, column=2).value = (
            f"=B{total_row}-B{retiro_row}-B{aprobados_row}"
        )

    # Anchos de columna: más ancho para encabezados largos con salto de línea.
    for col_letter, title, _ in headers:
        col_idx = column_index_from_string(col_letter)
        width = 12
        if title:
            longest_line = max((len(line) for line in title.split("\n")), default=0)
            width = max(10, min(28, longest_line + 2))
        ws.column_dimensions[get_column_letter(col_idx)].width = width

    ws.row_dimensions[1].height = 45
    ws.freeze_panes = "A3"
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

    wb = Workbook()
    # Elimina la hoja por defecto que crea openpyxl; construimos las nuestras.
    default_sheet = wb.active
    wb.remove(default_sheet)

    _build_students_sheet(wb, students)
    _build_definitivas_sheet(wb, course_type, len(students))

    # La hoja de resumen para el profesor debe abrirse primero.
    wb.move_sheet(gt.DEFINITIVAS_SHEET_NAME, offset=-1)
    wb.active = 0

    return wb


def suggest_filename(course_name: str) -> str:
    """Nombre de archivo sugerido `{course_name}.xlsx`, sanitizado para Windows."""
    name = (course_name or "curso").strip()
    name = _INVALID_FILENAME_CHARS.sub("_", name)
    name = name.rstrip(" .") or "curso"
    return f"{name}.xlsx"
