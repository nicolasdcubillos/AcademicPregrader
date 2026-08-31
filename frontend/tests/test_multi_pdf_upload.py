import re
import shutil
import subprocess
import unittest
from html.parser import HTMLParser
from pathlib import Path

from jinja2 import Environment, FileSystemLoader


TEMPLATE_PATH = Path(__file__).parents[1] / "templates" / "index.html"


class _FileInputParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.file_inputs = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "input" and attributes.get("type") == "file":
            self.file_inputs.append(attributes)


class MultiPdfUploadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = TEMPLATE_PATH.read_text(encoding="utf-8")
        environment = Environment(loader=FileSystemLoader(TEMPLATE_PATH.parent))
        cls.rendered_html = environment.get_template(TEMPLATE_PATH.name).render(
            is_admin=False,
            active_course="",
            active_course_id="",
            courses=[],
        )

    def test_pdf_input_has_multi_file_semantics(self):
        parser = _FileInputParser()
        parser.feed(self.rendered_html)

        pdf_inputs = [
            attributes
            for attributes in parser.file_inputs
            if attributes.get("id") == "file-pdf"
        ]

        self.assertEqual(len(pdf_inputs), 1)
        self.assertEqual(pdf_inputs[0].get("name"), "pdf_file")
        self.assertEqual(pdf_inputs[0].get("accept"), "application/pdf,.pdf")
        self.assertEqual(pdf_inputs[0].get("multiple"), "multiple")

    def test_repeated_picker_selections_accumulate_pdf_files(self):
        self.assertRegex(
            self.template,
            re.compile(
                r"function onFileSelect\(type, input\).*?"
                r"setSelectedPdfFiles\(input\.files, true\);.*?"
                r"input\.value = '';",
                re.DOTALL,
            ),
        )
        self.assertIn("setSelectedPdfFiles(files, true);", self.template)
        self.assertIn("const combined = append ? [..._files.pdf, ...selected] : selected;", self.template)

    def test_drag_and_drop_keeps_all_pdf_files(self):
        self.assertRegex(
            self.template,
            re.compile(
                r"function onDrop\(e, type\).*?"
                r"Array\.from\(e\.dataTransfer\.files \|\| \[\]\).*?"
                r"setSelectedPdfFiles\(files, true\)",
                re.DOTALL,
            ),
        )

    @unittest.skipUnless(shutil.which("node"), "Node.js is required for the FormData test")
    def test_form_data_contains_every_selected_pdf(self):
        helper_match = re.search(
            r"function appendPregraderFiles\(formData, files\) \{.*?^    \}",
            self.template,
            re.DOTALL | re.MULTILINE,
        )
        self.assertIsNotNone(helper_match)
        self.assertIn("appendPregraderFiles(fd, _files);", self.template)

        script = f"""
{helper_match.group(0)}
const zip = new File(['zip'], 'entregas.zip', {{ type: 'application/zip' }});
const pdfs = [
  new File(['one'], 'uno.pdf', {{ type: 'application/pdf' }}),
  new File(['two'], 'dos.pdf', {{ type: 'application/pdf' }}),
];
const formData = new FormData();
appendPregraderFiles(formData, {{ zip, pdf: pdfs }});
const entries = [...formData.entries()];
if (entries.length !== 3) process.exit(1);
if (entries[0][0] !== 'zip_file' || entries[0][1].name !== 'entregas.zip') process.exit(2);
const uploadedPdfs = entries.filter(([key]) => key === 'pdf_file').map(([, file]) => file.name);
if (uploadedPdfs.join(',') !== 'uno.pdf,dos.pdf') process.exit(3);
"""
        subprocess.run(["node", "-e", script], check=True)


if __name__ == "__main__":
    unittest.main()
