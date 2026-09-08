"""
Comparador de estilo completo (full-workbook) contra los archivos de
referencia reales que usan los profesores. Genera un workbook por tipo con
el MISMO numero de estudiantes que la referencia y compara, celda por celda,
TODO el estilo (fuente, borde, relleno, alineacion, numfmt), mas: orden de
hojas, tabColor, merged_cells, column_dimensions (width/hidden), row_dimensions
(height, filas 1-2) y conditional_formatting (sqref+reglas), ignorando el
CONTENIDO de datos de notas/estudiantes.

Este test se salta automaticamente si los 3 archivos de referencia no estan
presentes en la maquina (no se empaquetan en el repo, son archivos reales de
profesores). Para correrlo localmente, coloca:
  - C:\\Users\\User\\Downloads\\IP 1189 M-J.xlsx
  - C:\\Users\\User\\Downloads\\PA 1243 M-J.xlsx
  - C:\\Users\\User\\Downloads\\FPIA 1329.xlsx
(o ajusta REF_FILES abajo a su ubicacion real).

Excepciones documentadas y aceptadas (no se reportan como diff, ver
KNOWN_ACCEPTED_DIFFS): son discrepancias puntuales ya investigadas que vienen
de ediciones manuales de un semestre concreto en el archivo de referencia
(filas de estudiante agregadas/editadas a mano con estilo distinto, un wrap
suelto, un relleno de resaltado puntual, o una hoja "generica" de
sub-ejercicios cuya estructura de merges cambia cada semestre) - no son parte
de la "plantilla" replicable. Cualquier diferencia NO listada ahi hace
fallar el test.
"""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import openpyxl
from openpyxl.utils import column_index_from_string, get_column_letter

sys.path.insert(0, str(Path(__file__).parents[1]))

import excel_export as ee
import grade_templates as gt

REF_FILES = {
    "ip": (r"C:\Users\User\Downloads\IP 1189 M-J.xlsx", 24),
    "pa": (r"C:\Users\User\Downloads\PA 1243 M-J.xlsx", 20),
    "fpia": (r"C:\Users\User\Downloads\FPIA 1329.xlsx", 20),
}

REFERENCE_FILES_PRESENT = all(os.path.exists(p) for p, _ in REF_FILES.values())

ACCEPTED_SHEET_EXCEPTIONS = {
    ("pa", "Definitivas (2)"): "pasted-values snapshot, only header/tabColor/CF compared",
}

KNOWN_ACCEPTED_DIFFS = {
    "ip": [
        # Las 2 ultimas filas de 24 estudiantes en el archivo real tienen
        # fuente/alineacion distintas al resto (agregadas/editadas a mano por
        # el profesor en un momento distinto), no es parte del patron.
        "Estudiantes: cell A24 style",
        "Estudiantes: cell C24 style",
        "Estudiantes: cell D24 style",
        "Estudiantes: cell A25 style",
        "Estudiantes: cell B25 style",
        "Estudiantes: cell C25 style",
        "Estudiantes: cell D25 style",
        # Un unico wrap_text=True suelto en el bloque resumen sin razon
        # estructural aparente.
        "Definitivas: cell G32 style",
        # "Parcial 3" en el archivo real tiene un merge ancho (p.ej. F1:I1)
        # en vez de merges por columna F1:F2/G1:G2/H1:H2; es una hoja
        # generica de "sub-ejercicios" que cada semestre se reestructura a
        # mano, no se replica su estructura exacta de merges.
        "Parcial 3: aux merges",
        "Parcial 3: cell F1 style",
        "Parcial 3: cell G1 style",
        "Parcial 3: cell H1 style",
        "Parcial 3: cell F2 style",
        "Parcial 3: cell G2 style",
        "Parcial 3: cell H2 style",
    ],
    "pa": [
        # Relleno de resaltado puntual sobre 3 celdas de nombre (edicion
        # manual del profesor, sin patron estructural).
        "Definitivas: cell C4 style",
        "Definitivas: cell C5 style",
        "Definitivas: cell C22 style",
        # Wrap suelto en una celda del bloque resumen.
        "Definitivas: cell I28 style",
        # Borde superior ausente en una columna de las hojas Proyecto C++/
        # Proyecto Java por una fusion de celdas particular del archivo real
        # (misma clase de excepcion que "Parcial 3" en ip).
        "Proyecto C++: cell F1 style",
        "Proyecto C++: cell F2 style",
        "Proyecto Java: cell F1 style",
        "Proyecto Java: cell F2 style",
    ],
    "fpia": [],
}


def _font_key(f):
    if f is None:
        return None
    c = f.color
    ck = None
    if c is not None:
        tint = getattr(c, "tint", 0) or 0
        ck = (c.type, getattr(c, "rgb", None), getattr(c, "theme", None), round(tint, 2))
    return (f.name, f.sz, bool(f.b), bool(f.i), ck)


def _align_key(a):
    if a is None:
        return None
    return (a.horizontal, a.vertical, bool(a.wrap_text))


def _side_key(s):
    if s is None or s.style is None:
        return None
    c = s.color
    ck = (c.type, getattr(c, "rgb", None), getattr(c, "indexed", None)) if c else None
    return (s.style, ck)


def _border_key(b):
    if b is None:
        return None
    return (_side_key(b.left), _side_key(b.right), _side_key(b.top), _side_key(b.bottom))


def _fill_key(f):
    if f is None or f.patternType is None:
        return None
    fg = f.fgColor
    bg = f.bgColor
    fgk = (fg.type, getattr(fg, "rgb", None), getattr(fg, "theme", None), round((getattr(fg, "tint", 0) or 0), 2)) if fg else None
    bgk = (bg.type, getattr(bg, "rgb", None), getattr(bg, "theme", None), round((getattr(bg, "tint", 0) or 0), 2)) if bg else None
    return (f.patternType, fgk, bgk)


def _cell_style_key(cell):
    return (
        _font_key(cell.font),
        _border_key(cell.border),
        _fill_key(cell.fill),
        _align_key(cell.alignment),
        cell.number_format,
    )


def _tabcolor_key(ws):
    c = ws.sheet_properties.tabColor
    if c is None:
        return None
    return (c.type, getattr(c, "rgb", None), getattr(c, "theme", None), round((getattr(c, "tint", 0) or 0), 2))


def _width_key(v):
    return None if v is None else round(v, 1)


def _cf_key(ws):
    out = []
    for cf in ws.conditional_formatting:
        rules = []
        for r in cf.rules:
            dxf = r.dxf
            font_c = dxf.font.color.rgb if (dxf and dxf.font and dxf.font.color) else None
            fill_bg = None
            if dxf and dxf.fill and dxf.fill.bgColor:
                bg = dxf.fill.bgColor
                fill_bg = (bg.type, getattr(bg, "rgb", None), getattr(bg, "theme", None))
            rules.append((r.type, r.operator, tuple(r.formula or []), font_c, fill_bg))
        out.append((str(cf.sqref), tuple(sorted(rules, key=str))))
    return sorted(out, key=str)


def _compare_sheet(ref_ws, gen_ws, sheet_label, diffs, aux_mode=False, max_row=None, max_col=None,
                    skip_col_widths=False):
    if _tabcolor_key(ref_ws) != _tabcolor_key(gen_ws):
        diffs.append(f"{sheet_label}: tabColor ref={_tabcolor_key(ref_ws)} gen={_tabcolor_key(gen_ws)}")

    col_limit = max_col or max(ref_ws.max_column, gen_ws.max_column)
    if not skip_col_widths:
        limit_letters = {get_column_letter(i) for i in range(1, col_limit + 1)}
        ref_widths = {l: (_width_key(d.width), bool(d.hidden)) for l, d in ref_ws.column_dimensions.items() if (d.width or d.hidden) and l in limit_letters}
        gen_widths = {l: (_width_key(d.width), bool(d.hidden)) for l, d in gen_ws.column_dimensions.items() if (d.width or d.hidden) and l in limit_letters}
        for letter in set(ref_widths) | set(gen_widths):
            rv, gv = ref_widths.get(letter), gen_widths.get(letter)
            if rv != gv:
                diffs.append(f"{sheet_label}: col {letter} width/hidden ref={rv} gen={gv}")

    for row in (1, 2):
        rh = ref_ws.row_dimensions[row].height
        gh = gen_ws.row_dimensions[row].height
        rhr = round(rh, 1) if rh else None
        ghr = round(gh, 1) if gh else None
        if rhr != ghr:
            diffs.append(f"{sheet_label}: row {row} height ref={rhr} gen={ghr}")

    ref_merges = set(str(m) for m in ref_ws.merged_cells.ranges)
    gen_merges = set(str(m) for m in gen_ws.merged_cells.ranges)
    if ref_merges != gen_merges and not aux_mode:
        diffs.append(f"{sheet_label}: merges ref={sorted(ref_merges)} gen={sorted(gen_merges)}")
    elif aux_mode:
        # En aux sheets solo exigimos que cada columna con encabezado tenga
        # su merge {col}1:{col}2 (no comparamos 1:1 por titulo literal).
        missing = gen_merges - ref_merges
        if missing:
            diffs.append(f"{sheet_label}: aux merges generados sin equivalente en ref: {sorted(missing)}")

    if not aux_mode:
        if _cf_key(ref_ws) != _cf_key(gen_ws):
            diffs.append(f"{sheet_label}: CF ref={_cf_key(ref_ws)} gen={_cf_key(gen_ws)}")

    row_limit = max_row if max_row is not None else (2 if aux_mode else max(ref_ws.max_row, gen_ws.max_row))
    for r in range(1, row_limit + 1):
        for c in range(1, col_limit + 1):
            rc = ref_ws.cell(row=r, column=c)
            gc = gen_ws.cell(row=r, column=c)
            rk = _cell_style_key(rc)
            gk = _cell_style_key(gc)
            if rk != gk:
                diffs.append(f"{sheet_label}: cell {rc.coordinate} style ref={rk} gen={gk}")


def _run(course_type):
    ref_path, count = REF_FILES[course_type]
    with tempfile.TemporaryDirectory() as td:
        tmp_ref = os.path.join(td, "ref.xlsx")
        shutil.copyfile(ref_path, tmp_ref)
        ref_wb = openpyxl.load_workbook(tmp_ref, data_only=False)

    students = [{"full_name": f"Apellido{i}, Nombre{i}", "org_id": str(1000 + i)} for i in range(count)]
    gen_wb = ee.generate_course_workbook({"name": f"Test {course_type}", "course_type": course_type}, students)

    diffs = []
    if ref_wb.sheetnames != gen_wb.sheetnames:
        diffs.append(f"sheet order ref={ref_wb.sheetnames} gen={gen_wb.sheetnames}")

    template = gt.get_template(course_type)
    aux_sheet_names = set(template.get("aux_sheets", {}).keys())

    students_cols = len(gt.STUDENTS_COLUMNS[course_type])
    def_headers = template["headers"]
    def_last_col = max(column_index_from_string(h[0]) for h in def_headers)
    def_last_row = 2 + count
    if template.get("has_summary") and count:
        def_last_row = def_last_row + 4 + len(gt.SUMMARY_ROW_LABELS)
    elif template.get("averages_cols") and count:
        def_last_row = def_last_row + 1

    for sheet_name in ref_wb.sheetnames:
        if sheet_name not in gen_wb.sheetnames:
            continue
        label = f"{sheet_name}"
        if (course_type, sheet_name) in ACCEPTED_SHEET_EXCEPTIONS:
            # Solo comparamos encabezado (fila 1) + tabColor/CF; la fila 2 y
            # los datos son una foto de valores pegados por el profesor, no
            # se pueden replicar literalmente (ver docstring del modulo).
            _compare_sheet(ref_wb[sheet_name], gen_wb[sheet_name], label, diffs,
                           aux_mode=True, max_col=def_last_col, max_row=1, skip_col_widths=True)
            continue
        if sheet_name == gt.STUDENTS_SHEET_NAME:
            _compare_sheet(ref_wb[sheet_name], gen_wb[sheet_name], label, diffs,
                           max_row=1 + count, max_col=students_cols)
        elif sheet_name == gt.DEFINITIVAS_SHEET_NAME:
            _compare_sheet(ref_wb[sheet_name], gen_wb[sheet_name], label, diffs,
                           max_row=def_last_row, max_col=def_last_col)
        elif sheet_name in aux_sheet_names:
            spec = template["aux_sheets"][sheet_name]
            aux_last_col = len(spec["headers"])
            _compare_sheet(ref_wb[sheet_name], gen_wb[sheet_name], label, diffs,
                           aux_mode=True, max_col=aux_last_col)
        else:
            _compare_sheet(ref_wb[sheet_name], gen_wb[sheet_name], label, diffs)

    return diffs


def _filter_known_diffs(course_type, diffs):
    patterns = KNOWN_ACCEPTED_DIFFS.get(course_type, [])
    unexplained = [d for d in diffs if not any(p in d for p in patterns)]
    return unexplained


@unittest.skipUnless(
    REFERENCE_FILES_PRESENT,
    "Archivos de referencia reales (IP/PA/FPIA .xlsx de profesores) no encontrados en esta maquina",
)
class ExcelReferenceStyleTests(unittest.TestCase):
    """Compara, celda por celda, el workbook generado contra los .xlsx reales
    de los profesores (no se empaquetan en el repo). Se salta automaticamente
    si esos archivos no estan presentes."""

    def _assert_zero_unexplained_diffs(self, course_type):
        diffs = _run(course_type)
        unexplained = _filter_known_diffs(course_type, diffs)
        if unexplained:
            self.fail(
                f"{course_type}: {len(unexplained)} diferencia(s) de estilo NO explicada(s) "
                f"contra el archivo de referencia:\n" + "\n".join(unexplained)
            )

    def test_ip_matches_reference_style(self):
        self._assert_zero_unexplained_diffs("ip")

    def test_pa_matches_reference_style(self):
        self._assert_zero_unexplained_diffs("pa")

    def test_fpia_matches_reference_style(self):
        self._assert_zero_unexplained_diffs("fpia")


if __name__ == "__main__":
    unittest.main()
