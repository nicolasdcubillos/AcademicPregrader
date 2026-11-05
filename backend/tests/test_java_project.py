import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import java_project as jp  # noqa: E402

HAS_JAVA = bool(shutil.which("javac") and shutil.which("java"))

PRODUCT = "package com.x.model;\npublic class Producto { public String hi() { return \"hola\"; } }\n"
MAIN = (
    "package com.x.app;\nimport com.x.model.Producto;\n"
    "public class Main { public static void main(String[] a) "
    "{ System.out.println(new Producto().hi()); } }\n"
)


def write(root: Path, rel: str, content: str = "") -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


class TempDirCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="jp_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)


class NoiseTests(TempDirCase):
    def test_is_noise_path(self):
        self.assertTrue(jp.is_noise_path((".idea", "workspace.xml")))
        self.assertTrue(jp.is_noise_path(("p", "target", "classes", "A.class")))
        self.assertTrue(jp.is_noise_path(("p", "src", "test", "java", "ATest.java")))
        self.assertFalse(jp.is_noise_path(("p", "src", "main", "java", "A.java")))

    def test_find_java_sources_skips_noise(self):
        write(self.tmp, "p/src/main/java/A.java", "class A {}")
        write(self.tmp, "p/src/test/java/ATest.java", "class ATest {}")
        write(self.tmp, "p/target/gen/B.java", "class B {}")
        found = jp.find_java_sources(self.tmp)
        self.assertEqual([f.name for f in found], ["A.java"])

    def test_prune_noise_removes_dirs(self):
        write(self.tmp, "p/.idea/x.xml", "<x/>")
        write(self.tmp, "p/src/main/java/A.java", "class A {}")
        jp.prune_noise(self.tmp)
        self.assertFalse((self.tmp / "p" / ".idea").exists())
        self.assertTrue((self.tmp / "p" / "src" / "main" / "java" / "A.java").exists())


class ArchiveTests(TempDirCase):
    def test_extracts_nested_zip_and_removes_archive(self):
        student = self.tmp / "student"
        student.mkdir()
        with zipfile.ZipFile(student / "proj.zip", "w") as zf:
            zf.writestr("proj/src/main/java/A.java", "class A {}")
        jp.extract_nested_archives(student)
        self.assertFalse((student / "proj.zip").exists())
        self.assertTrue((student / jp.EXTRACT_DIR / "proj" / "proj" / "src" / "main" / "java" / "A.java").exists())

    def test_zip_slip_entries_are_ignored(self):
        student = self.tmp / "student"
        student.mkdir()
        with zipfile.ZipFile(student / "evil.zip", "w") as zf:
            zf.writestr("../../escaped.txt", "x")
            zf.writestr("ok.txt", "y")
        jp.extract_nested_archives(student)
        self.assertFalse((self.tmp / "escaped.txt").exists())
        self.assertFalse((self.tmp.parent / "escaped.txt").exists())
        self.assertTrue((student / jp.EXTRACT_DIR / "evil" / "ok.txt").exists())

    def test_corrupt_zip_is_reported(self):
        student = self.tmp / "student"
        write(student, "bad.zip", "not a zip")
        logs = jp.extract_nested_archives(student)
        self.assertTrue(any("bad.zip" in line for line in logs))


class MainClassTests(TempDirCase):
    def test_find_main_classes_uses_package_and_prefers_main(self):
        helper = write(self.tmp, "Util.java", "public class Util { public static void main(String[] a) {} }")
        main = write(self.tmp, "app/Main.java", MAIN)
        model = write(self.tmp, "model/Producto.java", PRODUCT)
        self.assertEqual(jp.find_main_classes([helper, main, model]), ["com.x.app.Main", "Util"])

    def test_main_in_comment_is_ignored(self):
        f = write(self.tmp, "A.java", "// public static void main(String[] a)\nclass A {}")
        self.assertEqual(jp.find_main_classes([f]), [])

    def test_rel_label_starts_at_src(self):
        f = write(self.tmp, "_extracted/z/z/src/main/java/A.java", "class A {}")
        self.assertEqual(jp.rel_label(self.tmp, f), "src/main/java/A.java")


class SubmissionDateTests(unittest.TestCase):
    def test_parse_datetime(self):
        name = "ID-406128 - ANA PEREZ - 22 de octubre de 2026 2212"
        self.assertEqual(jp.parse_submission_datetime(name), (2026, 10, 22, 22, 12))
        self.assertEqual(jp.parse_submission_datetime("sin fecha"), ())

    def test_keep_latest_submission_per_student(self):
        folders = [
            Path("1-406128 - ANA PEREZ - 20 de octubre de 2026 2000"),
            Path("2-406128 - ANA PEREZ - 22 de octubre de 2026 0100"),
            Path("3-406128 - LUIS GOMEZ - 21 de octubre de 2026 1000"),
        ]

        def student(f):
            return f.name.split(" - ")[1]

        kept, dropped = jp.keep_latest_submissions(folders, student)
        self.assertEqual([f.name[:1] for f in kept], ["2", "3"])
        self.assertEqual([f.name[:1] for f in dropped], ["1"])


@unittest.skipUnless(HAS_JAVA, "requiere javac y java")
class CompileRunTests(TempDirCase):
    def test_compile_and_run_packaged_project(self):
        write(self.tmp, "src/main/java/com/x/model/Producto.java", PRODUCT)
        write(self.tmp, "src/main/java/com/x/app/Main.java", MAIN)
        files = jp.find_java_sources(self.tmp)
        out = self.tmp / "out"
        ok, err = jp.compile_java(self.tmp, files, out)
        self.assertTrue(ok, err)
        main_class = jp.find_main_classes(files)[0]
        self.assertEqual(main_class, "com.x.app.Main")
        run = jp.run_java_main(out, main_class)
        self.assertTrue(run["ok"])
        self.assertEqual(run["stdout"].strip(), "hola")

    def test_compile_error_is_reported(self):
        write(self.tmp, "A.java", "public class A { int x = ; }")
        ok, err = jp.compile_java(self.tmp, jp.find_java_sources(self.tmp), self.tmp / "out")
        self.assertFalse(ok)
        self.assertIn("A.java", err)

    def test_infinite_loop_times_out(self):
        write(self.tmp, "Loop.java", "public class Loop { public static void main(String[] a) { while (true) {} } }")
        files = jp.find_java_sources(self.tmp)
        out = self.tmp / "out"
        ok, err = jp.compile_java(self.tmp, files, out)
        self.assertTrue(ok, err)
        run = jp.run_java_main(out, "Loop", timeout=2)
        self.assertTrue(run["timed_out"])


if __name__ == "__main__":
    unittest.main()
