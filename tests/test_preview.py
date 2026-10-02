import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from cowriter.preview import markdown_runs, safe_link


class PreviewTests(unittest.TestCase):
    def test_preview_renders_complete_document_and_inline_styles(self):
        source = "# Heading\n\n**Bold** and *italic*.\n\n" + "Paragraph.\n\n" * 100 + "Final paragraph."
        runs = list(markdown_runs(source))
        text = "".join(run[0] for run in runs)
        self.assertTrue(text.rstrip().endswith("Final paragraph."))
        self.assertGreater(len(text), 500)
        self.assertIn(("Heading", ("h1",), None), runs)
        self.assertIn(("Bold", ("bold",), None), runs)
        self.assertIn(("italic", ("italic",), None), runs)

    def test_lists_code_quotes_and_tables_remain_readable(self):
        source = "3. Three\n4. Four\n\n> A quote\n\n```python\nprint('ok')\n```\n\n| A | B |\n|---|---|\n| one | two |"
        runs = list(markdown_runs(source))
        text = "".join(run[0] for run in runs)
        for phrase in ["3. Three", "4. Four", "A quote", "print('ok')", "one", "two"]:
            self.assertIn(phrase, text)
        self.assertIn(("A quote", ("quote",), None), runs)

    def test_markup_and_images_do_not_execute_or_fetch_resources(self):
        runs = list(markdown_runs('<script>alert(1)</script>\n\n![Photo](https://example.com/private.png)\n\n[Site](https://example.com)'))
        text = "".join(run[0] for run in runs)
        self.assertIn("<script>alert(1)</script>", text)
        self.assertIn("[Image: Photo]", text)
        self.assertEqual([target for _, _, target in runs if target], ["https://example.com"])
        for target in ["javascript:alert(1)", "file:///tmp/private.md", "data:text/html,hello"]:
            self.assertFalse(safe_link(target))


if __name__ == "__main__":
    unittest.main()
