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


class ExcelExportTests(unittest.TestCase):
    def _build(self, course_type, n=3):
        course = {"name": f"Curso {course_type}", "course_type": course_type}
        wb = excel_export.generate_course_workbook(course, _students(n))
        return wb

    def test_students_sheet_has_only_two_header_columns(self):
        for course_type in ("ip", "pa", "fpia"):
            with self.subTest(course_type=course_type):
                wb = self._build(course_type)
                ws = wb[gt.STUDENTS_SHEET_NAME]
                header = [c.value for c in ws[1]]
                self.assertEqual(header, ["Apellido, Nombre", "ID"])
                # No hay una tercera columna con datos ni encabezado (p. ej. "Carrera").
                self.assertIsNone(ws.cell(row=1, column=3).value)

    def test_students_sheet_has_student_rows(self):
        wb = self._build("ip", n=3)
        ws = wb[gt.STUDENTS_SHEET_NAME]
        self.assertEqual(ws.cell(row=2, column=1).value, "Apellido0, Nombre0")
        self.assertEqual(ws.cell(row=2, column=2).value, 1000)
        self.assertEqual(ws.cell(row=4, column=1).value, "Apellido2, Nombre2")

    def test_fpia_headers_and_weights(self):
        wb = self._build("fpia", n=2)
        ws = wb[gt.DEFINITIVAS_SHEET_NAME]
        self.assertEqual(ws["E1"].value, "Uso de intérpretes online")
        self.assertEqual(ws["E2"].value, 20)
        self.assertEqual(ws["F1"].value, "Implementación de algoritmos")
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

    def test_ip_headers_weights_and_summary(self):
        wb = self._build("ip", n=3)
        ws = wb[gt.DEFINITIVAS_SHEET_NAME]
        self.assertEqual(ws["D1"].value, "Parcial 1")
        self.assertEqual(ws["D2"].value, 0.2)
        self.assertEqual(ws["K1"].value, "Definitiva")
        for row in (3, 4, 5):
            for col in ("D", "E", "F", "G", "H", "I", "J"):
                self.assertEqual(ws[f"{col}{row}"].value, 0)
        self.assertEqual(
            ws["K3"].value,
            "=D3*$D$2+E3*$E$2+F3*$F$2+G3*$G$2+H3*$H$2+I3*$I$2+J3*$J$2",
        )
        # Bloque resumen 2 filas después de la última fila de estudiantes (5 -> 7).
        self.assertEqual(ws["A7"].value, "Total")
        self.assertEqual(ws["B7"].value, "=COUNT(A3:A5)")
        self.assertEqual(ws["A8"].value, "Retiro")
        self.assertEqual(ws["B8"].value, 0)
        self.assertEqual(ws["A9"].value, "Aprobados")
        self.assertEqual(ws["B9"].value, '=COUNTIF(K3:K5,">=2.95")')
        self.assertEqual(ws["A10"].value, "Reprobado")
        self.assertEqual(ws["B10"].value, "=B7-B8-B9")

    def test_pa_headers_weights_and_summary(self):
        wb = self._build("pa", n=2)
        ws = wb[gt.DEFINITIVAS_SHEET_NAME]
        self.assertEqual(ws["D1"].value, "Parcial C++")
        self.assertEqual(ws["D2"].value, 0.25)
        self.assertEqual(ws["J1"].value, "Definitiva")
        for row in (3, 4):
            for col in ("D", "E", "F", "G", "H", "I"):
                self.assertEqual(ws[f"{col}{row}"].value, 0)
        self.assertEqual(
            ws["J3"].value,
            "=D3*$D$2+E3*$E$2+F3*$F$2+G3*$G$2+H3*$H$2+I3*$I$2",
        )
        self.assertEqual(ws["A6"].value, "Total")
        self.assertEqual(ws["B6"].value, "=COUNT(A3:A4)")

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


if __name__ == "__main__":
    unittest.main()
