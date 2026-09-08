import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

import grade_templates as gt
import excel_export


def _students(n):
    return [
        {"full_name": f"Apellido{i}, Nombre{i}", "org_id": str(1000 + i)}
        for i in range(n)
    ]


class ExcelExportContentTests(unittest.TestCase):
    """Verifica contenido/fórmulas (no estilo) del workbook generado."""

    def _build(self, course_type, n=3):
        course = {"name": f"Curso {course_type}", "course_type": course_type}
        wb = excel_export.generate_course_workbook(course, _students(n))
        return wb

    def test_sheet_order_matches_reference_files(self):
        # Confirma el orden exacto de hojas replicado de los archivos reales
        # (ver PR: extraído de IP 1189 M-J.xlsx / PA 1243 M-J.xlsx / FPIA 1329.xlsx).
        self.assertEqual(
            self._build("ip").sheetnames,
            ["Estudiantes", "Definitivas", "Talleres y Quices",
             "Parcial 1", "Parcial 2", "Parcial 3", "Proyecto"],
        )
        self.assertEqual(
            self._build("pa").sheetnames,
            ["Estudiantes", "Definitivas", "Parcial C++", "Parcial Java",
             "Proyecto C++", "Proyecto Java", "Talleres"],
        )
        self.assertEqual(self._build("fpia").sheetnames, ["Estudiantes", "Definitivas"])

    def test_students_sheet_headers_per_type(self):
        # ip/pa mantienen Carrera/Semestre (y pa además Grupo) vacíos para que
        # el archivo se vea idéntico al que ya usan los profesores; fpia solo
        # tiene Apellido/ID/Carrera (no tiene columna Semestre).
        ip_headers = [c.value for c in self._build("ip")[gt.STUDENTS_SHEET_NAME][1]]
        self.assertEqual(ip_headers, ["Apellido, Nombre", "ID", "Carrera", "Semestre"])

        pa_headers = [c.value for c in self._build("pa")[gt.STUDENTS_SHEET_NAME][1]]
        self.assertEqual(pa_headers, ["Apellido, Nombre", "ID", "Carrera", "Semestre", "Grupo"])

        fpia_headers = [c.value for c in self._build("fpia")[gt.STUDENTS_SHEET_NAME][1]]
        self.assertEqual(fpia_headers, ["Apellido, Nombre", "ID", "Carrera"])

    def test_students_sheet_has_student_rows(self):
        wb = self._build("ip", n=3)
        ws = wb[gt.STUDENTS_SHEET_NAME]
        self.assertEqual(ws.cell(row=2, column=1).value, "Apellido0, Nombre0")
        self.assertEqual(ws.cell(row=2, column=2).value, 1000)
        self.assertEqual(ws.cell(row=4, column=1).value, "Apellido2, Nombre2")
        # Carrera/Semestre quedan vacíos para que el profesor los llene.
        self.assertIsNone(ws.cell(row=2, column=3).value)

    def test_fpia_headers_and_weights(self):
        wb = self._build("fpia", n=2)
        ws = wb[gt.DEFINITIVAS_SHEET_NAME]
        self.assertEqual(ws["E1"].value, "Uso de intérpretes online")
        self.assertEqual(ws["E2"].value, 20)
        self.assertEqual(ws["F1"].value, " Implementación de algoritmos")
        self.assertEqual(ws["F2"].value, 60)
        self.assertEqual(ws["L1"].value, "Subtotal\nEvaluaciones sumativas\n(50%)")
        self.assertEqual(ws["M2"].value, "Nota")
        self.assertEqual(ws["V1"].value, "Definitiva")

    def test_fpia_subtotal_denominators_are_not_empty(self):
        # Regresión: L2/P2/T2 son los denominadores de M/Q/U (=5*(L{r}/$L$2), etc.).
        # Si quedan vacíos, esas fórmulas producen #DIV/0! para todos los estudiantes.
        wb = self._build("fpia", n=2)
        ws = wb[gt.DEFINITIVAS_SHEET_NAME]
        self.assertIsNotNone(ws["L2"].value)
        self.assertIsNotNone(ws["P2"].value)
        self.assertIsNotNone(ws["T2"].value)
        self.assertEqual(ws["L2"].value, "=SUM(E2:K2)")
        self.assertEqual(ws["P2"].value, "=SUM(N2:O2)")
        self.assertEqual(ws["T2"].value, "=SUM(R2:S2)")

    def test_fpia_grades_are_zero_and_formulas_present(self):
        wb = self._build("fpia", n=2)
        ws = wb[gt.DEFINITIVAS_SHEET_NAME]
        for row in (3, 4):
            for col in ("E", "F", "G", "H", "I", "J", "K", "N", "O", "R", "S"):
                self.assertEqual(ws[f"{col}{row}"].value, 0)
            self.assertEqual(ws[f"L{row}"].value, f"=SUM(E{row}:K{row})")
            self.assertEqual(ws[f"M{row}"].value, f"=5*(L{row}/$L$2)")
            self.assertEqual(ws[f"P{row}"].value, f"=SUM(N{row}:O{row})")
            self.assertEqual(ws[f"Q{row}"].value, f"=5*(P{row}/$P$2)")
            self.assertEqual(ws[f"T{row}"].value, f"=SUM(R{row}:S{row})")
            self.assertEqual(ws[f"U{row}"].value, f"=5*(T{row}/$T$2)")
            self.assertEqual(ws[f"V{row}"].value, f"=+M{row}*0.5+Q{row}*0.25+U{row}*0.25")
        self.assertEqual(ws["C3"].value, "=Estudiantes!B2")
        self.assertEqual(ws["D3"].value, "=Estudiantes!A2")

    def test_ip_headers_weights_and_formulas_reference_aux_sheets(self):
        wb = self._build("ip", n=3)
        ws = wb[gt.DEFINITIVAS_SHEET_NAME]
        self.assertEqual(ws["D1"].value, "Parcial 1")
        self.assertEqual(ws["D2"].value, 0.2)
        self.assertEqual(ws["K1"].value, "Definitiva")
        self.assertEqual(ws["K2"].value, "=SUM(D2:J2)")  # chequeo de que los pesos suman 100%
        # D..J son fórmulas que referencian las hojas auxiliares (Parcial 1/2/3,
        # Proyecto, Talleres y Quices) -no ceros- para que Definitivas quede
        # conectada a esas hojas, tal como en los archivos reales.
        self.assertEqual(ws["D3"].value, "=+'Parcial 1'!G3")
        self.assertEqual(ws["E3"].value, "='Parcial 2'!G3")
        self.assertEqual(ws["F3"].value, "='Parcial 3'!K3")
        self.assertEqual(ws["G3"].value, "=+Proyecto!E3")
        self.assertEqual(ws["H3"].value, "='Talleres y Quices'!S3+IF(L3>4.5,0.4,0)")
        self.assertEqual(ws["I3"].value, "=Proyecto!F3")
        self.assertEqual(ws["J3"].value, "=Proyecto!G3")
        self.assertEqual(
            ws["K3"].value,
            "=D3*$D$2+E3*$E$2+F3*$F$2+G3*$G$2+I3*$I$2+J3*$J$2+H3*$H$2",
        )
        self.assertEqual(ws["L3"].value, "=AVERAGE(G3,I3,J3)")
        self.assertEqual(ws["M1"].value, "Estado")
        self.assertEqual(ws["N1"].value, "Alerta de riesgo")
        self.assertEqual(ws["O1"].value, "Nota minima necesaria")
        # Bloque resumen 2 filas después de la última fila de estudiantes (5 -> 7).
        self.assertEqual(ws["A7"].value, "Total")
        self.assertEqual(ws["B7"].value, "=COUNT(A3:A5)")
        self.assertEqual(ws["A8"].value, "Retiro")
        self.assertEqual(ws["B8"].value, 0)
        self.assertEqual(ws["A9"].value, "Aprobados")
        self.assertEqual(ws["B9"].value, '=COUNTIF(K3:K5,">=2.95")')
        self.assertEqual(ws["A10"].value, "Reprobado")
        self.assertEqual(ws["B10"].value, "=B7-B8-B9")

    def test_ip_aux_sheets_have_formulas_and_zero_grades(self):
        wb = self._build("ip", n=2)
        parcial1 = wb["Parcial 1"]
        self.assertEqual(parcial1["C3"].value, "=Estudiantes!B2")
        self.assertEqual(parcial1["D3"].value, "=Estudiantes!A2")
        self.assertEqual(parcial1["E3"].value, 0)
        self.assertEqual(parcial1["F3"].value, 0)
        self.assertEqual(parcial1["G3"].value, "=+F3+E3")

        proyecto = wb["Proyecto"]
        self.assertEqual(proyecto["E3"].value, 0)
        self.assertEqual(proyecto["F3"].value, 0)
        self.assertEqual(proyecto["G3"].value, 0)

    def test_pa_headers_weights_and_formulas_reference_aux_sheets(self):
        wb = self._build("pa", n=2)
        ws = wb[gt.DEFINITIVAS_SHEET_NAME]
        self.assertEqual(ws["D1"].value, "Parcial C++")
        self.assertEqual(ws["D2"].value, 0.25)
        self.assertEqual(ws["J1"].value, "Definitiva")
        self.assertEqual(ws["J2"].value, "=SUM(D2:I2)")
        self.assertEqual(ws["D3"].value, "='Parcial C++'!M3")
        self.assertEqual(ws["E3"].value, "=+'Parcial Java'!M3")
        self.assertEqual(ws["F3"].value, "='Proyecto C++'!H3")
        self.assertEqual(ws["G3"].value, "=IF('Proyecto Java'!I3>5,5,'Proyecto Java'!I3)")
        self.assertEqual(ws["H3"].value, "=Talleres!U3")
        self.assertEqual(ws["I3"].value, "=Talleres!V3")
        self.assertEqual(
            ws["J3"].value,
            "=D3*$D$2+E3*$E$2+H3*$H$2+I3*$I$2+G3*$G$2+F3*$F$2",
        )
        self.assertEqual(ws["A6"].value, "Total")
        self.assertEqual(ws["B6"].value, "=COUNT(A3:A4)")

    def test_pa_aux_sheets_have_formulas_and_zero_grades(self):
        wb = self._build("pa", n=2)
        talleres = wb["Talleres"]
        self.assertEqual(talleres["E3"].value, 0)
        self.assertEqual(talleres["U3"].value, "=IFERROR(AVERAGE(E3:M3), 0)")
        self.assertEqual(talleres["V3"].value, "=IFERROR(AVERAGE(N3:T3), 0)")

    def test_invalid_course_type_raises(self):
        with self.assertRaises(ValueError):
            excel_export.generate_course_workbook(
                {"name": "Sin tipo", "course_type": None}, _students(1)
            )
        with self.assertRaises(ValueError):
            excel_export.generate_course_workbook(
                {"name": "Tipo raro", "course_type": "bogus"}, _students(1)
            )

    def test_suggest_filename_sanitizes(self):
        self.assertEqual(excel_export.suggest_filename("Curso: A/B"), "Curso_ A_B.xlsx")
        self.assertEqual(excel_export.suggest_filename(""), "curso.xlsx")


class ExcelExportStyleTests(unittest.TestCase):
    """Verifica la fidelidad visual (fuente, bordes, numfmt, tabColor, orden de
    hojas, formato condicional) replicada de los archivos reales de referencia.
    No compara contra los .xlsx originales (no se empaquetan en el repo);
    valida que excel_export.py aplique consistentemente los estilos que se
    confirmaron por extracción directa de esos archivos."""

    def _build(self, course_type, n=3):
        course = {"name": f"Curso {course_type}", "course_type": course_type}
        return excel_export.generate_course_workbook(course, _students(n))

    def test_font_is_aptos_narrow_everywhere_relevant(self):
        for course_type in ("ip", "pa", "fpia"):
            with self.subTest(course_type=course_type):
                wb = self._build(course_type)
                for sheet_name in ("Estudiantes", "Definitivas"):
                    ws = wb[sheet_name]
                    header_cell = ws.cell(row=1, column=1)
                    self.assertEqual(header_cell.font.name, "Aptos Narrow")
                    self.assertTrue(header_cell.font.bold)

    def test_tab_colors_match_reference(self):
        for course_type in ("ip", "pa", "fpia"):
            with self.subTest(course_type=course_type):
                wb = self._build(course_type)
                est_tab = wb["Estudiantes"].sheet_properties.tabColor
                def_tab = wb["Definitivas"].sheet_properties.tabColor
                self.assertEqual(est_tab.theme, 5)
                self.assertEqual(def_tab.theme, 9)

    def test_definitivas_header_cells_have_thin_borders(self):
        for course_type in ("ip", "pa", "fpia"):
            with self.subTest(course_type=course_type):
                ws = self._build(course_type)[gt.DEFINITIVAS_SHEET_NAME]
                self.assertEqual(ws["A1"].border.left.style, "thin")
                self.assertEqual(ws["A1"].border.bottom.style, "thin")

    def test_ip_merges_and_numfmt(self):
        ws = self._build("ip")[gt.DEFINITIVAS_SHEET_NAME]
        merges = {str(m) for m in ws.merged_cells.ranges}
        self.assertEqual(merges, {"A1:A2", "B1:B2", "C1:C2"})
        self.assertEqual(ws["D2"].number_format, "0%")
        self.assertEqual(ws["D3"].number_format, "0.00")
        self.assertEqual(ws["K3"].number_format, "0.00")

    def test_pa_numfmt_uses_one_decimal(self):
        ws = self._build("pa")[gt.DEFINITIVAS_SHEET_NAME]
        self.assertEqual(ws["D2"].number_format, "0%")
        self.assertEqual(ws["D3"].number_format, "0.0")
        self.assertEqual(ws["J3"].number_format, "0.0")

    def test_fpia_merges_and_fill(self):
        ws = self._build("fpia")[gt.DEFINITIVAS_SHEET_NAME]
        merges = {str(m) for m in ws.merged_cells.ranges}
        self.assertIn("L1:M1", merges)
        self.assertIn("P1:Q1", merges)
        self.assertIn("T1:U1", merges)
        self.assertIn("A1:A2", merges)
        # Relleno theme5/tint0.6 en columnas de subtotal/nota (fila 1, 2 y datos).
        self.assertIsNotNone(ws["L1"].fill)
        self.assertEqual(ws["L1"].fill.fill_type, "solid")
        self.assertEqual(ws["L3"].fill.fill_type, "solid")

    def test_ip_conditional_formatting_present(self):
        wb = self._build("ip", n=5)
        ws = wb[gt.DEFINITIVAS_SHEET_NAME]
        ranges = [str(cf.sqref) for cf in ws.conditional_formatting]
        self.assertTrue(any("D3:K7" in r for r in ranges))

    def test_pa_conditional_formatting_present(self):
        wb = self._build("pa", n=4)
        ws = wb[gt.DEFINITIVAS_SHEET_NAME]
        ranges = [str(cf.sqref) for cf in ws.conditional_formatting]
        self.assertTrue(any("D3:J6" in r for r in ranges))

    def test_column_widths_applied(self):
        ws = self._build("ip")[gt.DEFINITIVAS_SHEET_NAME]
        self.assertAlmostEqual(ws.column_dimensions["A"].width, 4.25)
        self.assertAlmostEqual(ws.column_dimensions["C"].width, 33.38)


if __name__ == "__main__":
    unittest.main()
