import importlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))


class GtkAppHelperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        with patch.object(Path, "home", return_value=Path(cls.temp_dir.name)):
            sys.modules.pop("cowriter.gtk_app", None)
            cls.app = importlib.import_module("cowriter.gtk_app")

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    def test_invalid_config_falls_back_to_empty_config(self):
        self.app.CONFIG_FILE.write_text("not json", encoding="utf-8")

        self.assertEqual(self.app.load_config(), {})

    def test_model_discovery_excludes_embedding_models(self):
        response = Mock(status_code=200)
        response.json.return_value = {
            "models": [
                {"name": "gemma4:12b"},
                {"name": "embeddinggemma:latest"},
                {"name": "nomic-embed-text:latest"},
            ]
        }

        with patch.object(self.app.requests, "get", return_value=response):
            self.assertEqual(self.app.get_available_models(), ["gemma4:12b"])

    def test_numbered_snapshot_preserves_lines(self):
        self.assertEqual(
            self.app.make_numbered_snapshot("First\n\nThird"),
            "1: First\n2: \n3: Third",
        )

    def test_html_import_removes_scripts_and_decodes_entities(self):
        path = Path(self.temp_dir.name) / "sample.html"
        path.write_text(
            "<style>hidden</style><p>Hello &amp; goodbye</p><script>ignored()</script>",
            encoding="utf-8",
        )

        self.assertEqual(self.app.import_file_content(path), "Hello & goodbye")

    def test_text_marks_keep_ai_edit_selection_stable(self):
        buf = self.app.Gtk.TextBuffer()
        buf.set_text("alpha beta", -1)
        start_mark = buf.create_mark(None, buf.get_iter_at_offset(0), True)
        end_mark = buf.create_mark(None, buf.get_iter_at_offset(5), False)
        buf.insert(buf.get_end_iter(), " gamma", -1)

        selected = buf.get_text(
            buf.get_iter_at_mark(start_mark),
            buf.get_iter_at_mark(end_mark),
            False,
        )
        self.assertEqual(selected, "alpha")

    def test_continue_uses_selected_passage_and_inserts_after_it_in_both_directions(self):
        original = "Above paragraph.\nTarget paragraph.\nBelow paragraph."
        start = original.index("Target paragraph.")
        end = start + len("Target paragraph.")

        for reverse in (False, True):
            with self.subTest(reverse=reverse):
                buf = self.app.Gtk.TextBuffer()
                buf.set_text(original, -1)
                insert = buf.get_iter_at_offset(start if reverse else end)
                bound = buf.get_iter_at_offset(end if reverse else start)
                buf.select_range(insert, bound)

                window = Mock()
                window._get_current_page.return_value = (None, None, buf)
                self.app.CoWriterWindow._on_continue(window, None)

                prompt = window._call_ollama.call_args.args[0]
                self.assertIn("Selected passage to continue:\n\nTarget paragraph.", prompt)
                self.assertNotIn("Above paragraph.", prompt)
                self.assertFalse(window._call_ollama.call_args.kwargs["include_history"])
                self.assertFalse(window._call_ollama.call_args.kwargs["record_history"])
                self.assertFalse(window._call_ollama.call_args.kwargs["think"])
                self.assertEqual(
                    window._call_ollama.call_args.kwargs["system_prompt"],
                    self.app.CONTINUATION_SYSTEM,
                )

                continuation_callback = window._call_ollama.call_args.args[1]
                continuation_callback("New sentence.")
                preview_args = window._show_continuation_preview.call_args.args
                insert_mark = preview_args[1]
                self.assertEqual(buf.get_iter_at_mark(insert_mark).get_offset(), end)
                self.assertTrue(preview_args[3])
                buf.place_cursor(buf.get_start_iter())

                self.app.CoWriterWindow._handle_continuation_response(
                    window, "insert", buf, insert_mark, "New sentence.", True
                )
                self.assertEqual(
                    buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False),
                    "Above paragraph.\nTarget paragraph.\nNew sentence.\nBelow paragraph.",
                )

    def test_continue_without_selection_keeps_cursor_behavior(self):
        buf = self.app.Gtk.TextBuffer()
        buf.set_text("First sentence. Second sentence.", -1)
        buf.place_cursor(buf.get_end_iter())
        window = Mock()
        window._get_current_page.return_value = (None, None, buf)

        self.app.CoWriterWindow._on_continue(window, None)

        prompt = window._call_ollama.call_args.args[0]
        self.assertIn("Continue writing from here:\n\nFirst sentence. Second sentence.", prompt)
        continuation_callback = window._call_ollama.call_args.args[1]
        continuation_callback("Third sentence.")
        insert_mark = window._show_continuation_preview.call_args.args[1]
        self.app.CoWriterWindow._handle_continuation_response(
            window, "insert", buf, insert_mark, "Third sentence.", False
        )
        self.assertEqual(
            buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False),
            "First sentence. Second sentence. Third sentence.",
        )

    def test_continue_retries_an_empty_model_response_once(self):
        buf = self.app.Gtk.TextBuffer()
        buf.set_text("Opening sentence.", -1)
        buf.place_cursor(buf.get_end_iter())
        window = Mock()
        window._get_current_page.return_value = (None, None, buf)

        self.app.CoWriterWindow._on_continue(window, None)
        first_callback = window._call_ollama.call_args.args[1]
        first_callback("  ")

        self.assertEqual(window._call_ollama.call_count, 2)
        self.assertEqual(window._call_ollama.call_args.kwargs["temperature"], 0.4)
        self.assertFalse(window._show_continuation_preview.called)

        retry_callback = window._call_ollama.call_args.args[1]
        retry_callback("A second sentence.")
        self.assertEqual(window._call_ollama.call_count, 2)
        self.assertEqual(
            window._show_continuation_preview.call_args.args[2],
            "A second sentence.",
        )


if __name__ == "__main__":
    unittest.main()
