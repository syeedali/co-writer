import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cowriter.exporting import export_document, import_office_text, plain_text, document_blocks


SAMPLE = """# A document

A **clear** passage with *emphasis* and a [source](https://example.com/paper).

- First item
- Second item

```python
    preserved_indent()
```

| Claim | Source |
|---|---|
| A claim | A paper |
"""


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def test_office_exports_preserve_semantic_content_and_safe_links(self):
        for extension in ("odt", "docx"):
            with self.subTest(extension=extension):
                path = self.root / ("sample." + extension)
                export_document(path, SAMPLE)
                restored = import_office_text(path)
                self.assertIn("# A document", restored)
                self.assertIn("**clear**", restored)
                self.assertIn("*emphasis*", restored)
                self.assertIn("[source](https://example.com/paper)", restored)
                self.assertIn("preserved_indent", restored)
                self.assertIn("A claim", restored)
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                with ZipFile(path) as archive:
                    xml = archive.read("content.xml" if extension == "odt" else "word/document.xml").decode()
                    self.assertNotIn("**clear**", xml)

    def test_pdf_wraps_and_paginates_long_documents_with_clickable_links(self):
        from pypdf import PdfReader
        path = self.root / "long.pdf"
        text = SAMPLE + ("Long paragraph for checking page wrapping. " * 35 + "\n\n") * 25 + "FINAL PASSAGE"
        export_document(path, text)
        reader = PdfReader(path)
        self.assertGreater(len(reader.pages), 3)
        combined = "\n".join(page.extract_text() for page in reader.pages)
        self.assertIn("FINAL PASSAGE", combined)
        self.assertIn("Page 1", combined)
        self.assertNotIn("**clear**", combined)
        urls = [annotation.get_object().get('/A', {}).get('/URI')
                for page in reader.pages for annotation in page.get('/Annots', [])]
        self.assertIn("https://example.com/paper", urls)
        table_path = self.root / "tall-table.pdf"
        export_document(table_path, "| Claim | Evidence |\n|---|---|\n| Long claim | " + "Long evidence. " * 600 + " END OF ROW |")
        table_reader = PdfReader(table_path)
        self.assertGreater(len(table_reader.pages), 1)
        self.assertIn("END OF ROW", "\n".join(page.extract_text() for page in table_reader.pages))

    def test_writer_lists_and_links_in_table_cells_import_as_markdown(self):
        from odf.opendocument import OpenDocumentText
        from odf.text import List, ListItem, ListStyle, ListLevelStyleNumber, P, A
        from odf.table import Table, TableRow, TableCell
        doc = OpenDocumentText()
        style = ListStyle(name="Numbered")
        style.addElement(ListLevelStyleNumber(level=1, numformat="1"))
        doc.styles.addElement(style)
        items = List(stylename=style)
        for text in ("First revision", "Second revision"):
            item = ListItem()
            item.addElement(P(text=text))
            items.addElement(item)
        doc.text.addElement(items)
        table, row, cell = Table(), TableRow(), TableCell()
        paragraph = P()
        paragraph.addElement(A(href="https://example.com/evidence", text="Evidence"))
        cell.addElement(paragraph)
        row.addElement(cell)
        table.addElement(row)
        doc.text.addElement(table)
        path = self.root / "writer.odt"
        doc.save(str(path), addsuffix=False)
        imported = import_office_text(path)
        self.assertIn("1. First revision", imported)
        self.assertIn("2. Second revision", imported)
        self.assertIn("[Evidence](https://example.com/evidence)", imported)

    def test_html_formats_markdown_without_loading_images_or_running_html(self):
        path = self.root / "sample.html"
        export_document(path, SAMPLE + '\n<script>alert(1)</script>\n![image](https://example.com/image.png)\n[bad](javascript:alert(1))')
        html = path.read_text()
        self.assertIn("<h1>A document</h1>", html)
        self.assertIn("<strong>clear</strong>", html)
        self.assertNotIn("<script>", html)
        self.assertNotIn("<img", html)
        self.assertNotIn('href="javascript:', html)

    def test_failed_export_preserves_original_and_cleans_scratch_file(self):
        path = self.root / "existing.odt"
        path.write_bytes(b"original")
        with patch("cowriter.exporting._odt", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                export_document(path, SAMPLE)
        self.assertEqual(path.read_bytes(), b"original")
        self.assertEqual(list(self.root.glob('.cowriter-export-*')), [])
        with self.assertRaises(ValueError):
            export_document(self.root / "unsupported.xyz", SAMPLE)

    def test_email_text_has_readable_content_and_separates_table_cells(self):
        text = plain_text(SAMPLE)
        self.assertIn("A clear passage", text)
        self.assertIn("source (https://example.com/paper)", text)
        self.assertNotIn("**", text)
        self.assertIn("A claim | A paper", text)
        self.assertEqual(document_blocks("3. First\n4. Next")[0].marker, "3. ")
