import configparser
import contextlib
import importlib.util
import io
import json
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).parents[1] / "academic-pregrader.py"
SPEC = importlib.util.spec_from_file_location("document_pregrader", MODULE_PATH)
PREGRADER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREGRADER)
HAS_LIBREOFFICE = bool(shutil.which("libreoffice") or shutil.which("soffice"))
HAS_JPLAG_JAVA = PREGRADER._check_java_version(verbose=False)
JPLAG_JAR = MODULE_PATH.parent / "jplag-6.3.0-jar-with-dependencies.jar"


def write_docx(path, text):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Override PartName="/word/document.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            '</Types>',
        )
        archive.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="word/document.xml"/></Relationships>',
        )
        archive.writestr(
            "word/document.xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f'<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>',
        )


class DocumentSubmissionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_docx_detection_preserves_code_priority_and_ignores_metadata(self):
        docx = self.root / "Entrega.DOCX"
        docx.touch()
        (self.root / ".hidden.docx").touch()
        self.assertEqual("pdf", PREGRADER.detect_language(self.root))
        self.assertEqual([docx], PREGRADER.find_submission_files(self.root, "pdf"))
        (self.root / "main.cpp").touch()
        self.assertEqual("cpp", PREGRADER.detect_language(self.root))

    def test_missing_converter_timeout_and_missing_pdf_are_explicit_errors(self):
        with patch.object(PREGRADER.shutil, "which", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "instala LibreOffice"):
                PREGRADER.convert_docx_to_pdf(self.root / "report.docx", self.root)
        with patch.object(PREGRADER.shutil, "which", return_value="/usr/bin/soffice"):
            with patch.object(
                PREGRADER.subprocess, "run",
                side_effect=subprocess.TimeoutExpired("soffice", 120),
            ):
                with self.assertRaisesRegex(RuntimeError, "120 segundos"):
                    PREGRADER.convert_docx_to_pdf(self.root / "report.docx", self.root)
            with patch.object(
                PREGRADER.subprocess, "run",
                return_value=subprocess.CompletedProcess([], 0, "", ""),
            ):
                with self.assertRaisesRegex(RuntimeError, "No se generó un PDF"):
                    PREGRADER.convert_docx_to_pdf(self.root / "report.docx", self.root)

    def test_mixed_files_use_pdf_reader_and_do_not_overwrite_originals(self):
        docx = self.root / "report.docx"
        docx.write_bytes(b"original DOCX")
        pdf = self.root / "report.pdf"
        pdf.write_bytes(b"original PDF")
        output_paths = []

        def convert(cmd, **kwargs):
            output_dir = Path(cmd[cmd.index("--outdir") + 1])
            output = output_dir / "report.pdf"
            output.write_bytes(b"converted PDF")
            output_paths.append(output)
            self.assertIn(f"-env:UserInstallation={(output_dir / 'profile').as_uri()}", cmd)
            self.assertEqual(120, kwargs["timeout"])
            return subprocess.CompletedProcess(cmd, 0, "", "")

        with patch.object(PREGRADER.shutil, "which", return_value="/usr/bin/soffice"), \
             patch.object(PREGRADER.subprocess, "run", side_effect=convert), \
             patch.object(PREGRADER, "extract_pdf_text",
                          side_effect=lambda path: Path(path).read_bytes().decode("ascii")):
            text = PREGRADER.extract_submission_text([docx, pdf], "pdf")
        self.assertEqual("converted PDF\n\noriginal PDF", text)
        self.assertEqual(b"original DOCX", docx.read_bytes())
        self.assertEqual(b"original PDF", pdf.read_bytes())
        self.assertFalse(output_paths[0].parent.exists())

    def test_blank_or_broken_documents_do_not_become_llm_input(self):
        for error in (None, RuntimeError("invalid PDF")):
            with self.subTest(error=error), \
                 patch.object(PREGRADER, "extract_pdf_text", return_value="", side_effect=error):
                with self.assertRaisesRegex(ValueError, "No se pudo leer"):
                    PREGRADER.extract_submission_text([self.root / "report.pdf"], "pdf")

    def test_each_student_receives_a_result_and_text_is_reused_for_jplag(self):
        archive = self.root / "submissions.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            for name, extension in (
                ("valid_pdf", "pdf"), ("valid_word", "docx"),
                ("broken", "pdf"), ("image", "png"),
            ):
                zf.writestr(f"{name}/report.{extension}", b"submission")
        statement = self.root / "statement.txt"
        statement.write_text("Assignment", encoding="utf-8")
        config = configparser.ConfigParser()
        config.read_dict({
            "submission": {"language": "pdf"},
            "steps": {"enable_compilation": "false", "enable_plagiarism": "true"},
            "paths": {"jplag_jar": str(JPLAG_JAR)},
        })
        extracted = self.root / "extracted"
        extracted.mkdir()

        def read(files, lang, root):
            if root.name == "broken":
                raise ValueError("invalid PDF")
            return f"Text for {root.name}"

        output = io.StringIO()
        with patch.object(PREGRADER, "extract_submission_text", side_effect=read) as extract, \
             patch.object(PREGRADER, "run_plagiarism_check", return_value={}) as plagiarism, \
             patch.object(PREGRADER, "llm_evaluate", return_value={
                 "logica": 4.5, "nota_final": 4.5, "comentario": "ok",
             }) as evaluate, contextlib.redirect_stdout(output):
            PREGRADER._run_main(extracted, archive, statement, config)
        results = [
            json.loads(line[len("##RESULT## "):])
            for line in output.getvalue().splitlines() if line.startswith("##RESULT## ")
        ]
        self.assertEqual(4, len(results))
        errors = {r["estudiante"]: r for r in results if r["estado"] == "error"}
        self.assertEqual({"broken", "image"}, set(errors))
        self.assertTrue(all(r["nota"] == "" for r in errors.values()))
        self.assertIn(".png", errors["image"]["comentario"])
        self.assertIn("invalid PDF", errors["broken"]["comentario"])
        self.assertEqual(3, extract.call_count)
        self.assertEqual(2, evaluate.call_count)
        self.assertEqual({
            "valid_pdf": "Text for valid_pdf", "valid_word": "Text for valid_word",
        }, plagiarism.call_args.kwargs["submission_texts"])
        summary = next(
            json.loads(line[len("##DONE## "):])
            for line in output.getvalue().splitlines() if line.startswith("##DONE## ")
        )
        self.assertEqual({"count": 4, "total": 4, "failed": 2}, summary)

    @unittest.skipUnless(HAS_LIBREOFFICE, "LibreOffice required")
    def test_real_parallel_docx_conversion_reuses_pdf_extraction(self):
        files = []
        for index in range(2):
            folder = self.root / str(index)
            folder.mkdir()
            path = folder / "Entrega.docx"
            write_docx(path, f"Documento del grupo {index}: batalla naval.")
            files.append(path)
        with ThreadPoolExecutor(max_workers=2) as executor:
            texts = list(executor.map(
                lambda path: PREGRADER.extract_submission_text([path], "pdf"), files
            ))
        for index, text in enumerate(texts):
            self.assertIn(f"Documento del grupo {index}: batalla naval.", text)
        self.assertEqual([], list(self.root.rglob("*.pdf")))

    @unittest.skipUnless(HAS_JPLAG_JAVA and JPLAG_JAR.is_file(), "JPlag and Java 25 required")
    def test_real_text_comparison_preserves_student_names_and_threshold(self):
        names = ["1-10 - Group 1", "2-10 - Group 2"]
        text = (
            "El juego batalla naval permite ubicar barcos en un tablero para dos jugadores. "
            "Cada participante elige una coordenada y comprueba si el disparo toca una nave. "
            "El programa mantiene turnos y cuenta las naves hundidas para determinar el ganador."
        )
        result = PREGRADER.run_plagiarism_check(
            self.root, str(JPLAG_JAR), 0.7, "text", dict.fromkeys(names, text)
        )
        self.assertIsNotNone(result)
        self.assertEqual(set(names), set(result))
        self.assertEqual({"con_quien": names[1], "porcentaje": 100.0}, result[names[0]])
        self.assertEqual([], list(self.root.iterdir()))

    def test_jplag_text_input_contains_only_extracted_submission_text(self):
        captured_roots = []

        def run_jplag(root, jar, threshold, lang):
            captured_roots.append(root)
            self.assertEqual(["a/submission.txt", "b/submission.txt"], sorted(
                path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()
            ))
            self.assertEqual("Text A", (root / "a/submission.txt").read_text())
            return {}

        with patch.object(PREGRADER, "_run_jplag", side_effect=run_jplag):
            PREGRADER.run_plagiarism_check(
                self.root, "jplag.jar", 0.7, "text", {"a": "Text A", "b": "Text B"}
            )
        self.assertFalse(captured_roots[0].exists())


if __name__ == "__main__":
    unittest.main()
