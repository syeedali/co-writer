import json
import threading
from pathlib import Path
from unittest.mock import Mock, patch

from test_gtk_layout import GtkWindowTestCase
from cowriter.research import ClaimQuery, EvidenceSource, EvidenceSearch


class GtkFeatureTests(GtkWindowTestCase):
    def new_window(self):
        with patch.object(self.module.CoWriterWindow, "_refresh_models"), \
             patch.object(self.module.CoWriterWindow, "_schedule_autosave"):
            window = self.module.CoWriterWindow(self.app)
        self.addCleanup(window.destroy)
        window.present()
        self.settle()
        return window

    def dialog(self, window=None):
        window = window or self.win
        return next(dialog for dialog in self.module.Gtk.Window.list_toplevels()
                    if isinstance(dialog, self.module.Adw.MessageDialog)
                    and dialog.get_transient_for() is window)

    def test_dirty_indicator_autosave_and_save_have_distinct_meanings(self):
        page, _, buf = self.win._get_current_page()
        path = Path(self.win.open_tabs[page])
        original = path.read_text()
        buf.set_text("My unsaved draft", -1)
        self.assertTrue(buf.get_modified())
        self.assertTrue(self.win._tab_state[page]["label"].get_label().startswith("●"))
        self.win._autosave_documents()
        self.assertEqual(path.read_text(), original)
        self.assertEqual(self.win.save_status.get_label(), "Autosaved · unsaved")
        self.assertEqual(self.win._recovery_store.read(path, original)["text"], "My unsaved draft")
        self.win._on_save(None, None)
        self.assertEqual(path.read_text(), "My unsaved draft")
        self.assertFalse(buf.get_modified())
        self.assertEqual(self.win.save_status.get_label(), "Saved")
        self.assertFalse(self.win._recovery_store.path_for(path).exists())

    def test_failed_save_keeps_dirty_text_and_does_not_close(self):
        page, _, buf = self.win._get_current_page()
        path = Path(self.win.open_tabs[page])
        original = path.read_text()
        buf.set_text("Keep this draft", -1)
        callback = Mock()
        with patch.object(self.module, "atomic_write", side_effect=OSError("disk full")), \
             patch.object(self.win, "_show_error"):
            self.win._save_page(page, callback)
        callback.assert_called_once_with(False)
        self.assertEqual(path.read_text(), original)
        self.assertTrue(buf.get_modified())
        self.assertIn(page, self.win.open_tabs)

    def test_close_tab_cancel_then_save(self):
        page, _, buf = self.win._get_current_page()
        path = Path(self.win.open_tabs[page])
        buf.set_text("Save before closing", -1)
        self.win._close_tab_by_page(page)
        self.dialog().response("cancel")
        self.assertIn(page, self.win.open_tabs)
        self.win._close_tab_by_page(page)
        self.dialog().response("save")
        self.assertNotIn(page, self.win.open_tabs)
        self.assertEqual(path.read_text(), "Save before closing")

    def test_close_tab_discard_preserves_original_and_removes_recovery(self):
        page, _, buf = self.win._get_current_page()
        path = Path(self.win.open_tabs[page])
        original = path.read_text()
        buf.set_text("Discard this", -1)
        self.win._close_tab_by_page(page)
        self.dialog().response("discard")
        self.assertNotIn(page, self.win.open_tabs)
        self.assertEqual(path.read_text(), original)
        self.assertFalse(self.win._recovery_store.path_for(path).exists())

    def test_clean_window_close_finishes(self):
        self.win.close()
        self.settle()
        self.assertTrue(self.win._disposed)

    def test_restart_offers_recovery_without_overwriting_original(self):
        page, _, buf = self.win._get_current_page()
        path = Path(self.win.open_tabs[page])
        original = path.read_text()
        buf.set_text("Recover my draft", -1)
        self.win._autosave_documents()
        self.win._checkpoint_session()
        self.win.destroy()
        restored = self.new_window()
        self.dialog(restored).response("restore")
        _, _, restored_buf = restored._get_current_page()
        self.assertEqual(restored_buf.get_text(restored_buf.get_start_iter(), restored_buf.get_end_iter(), False),
                         "Recover my draft")
        self.assertTrue(restored_buf.get_modified())
        self.assertEqual(path.read_text(), original)

    def test_workspace_restores_tabs_cursor_size_and_pane_preference(self):
        second = self.module.WORK_DIR / "second.md"
        second.write_text("Second document with a remembered cursor")
        self.win._open_document(second)
        page, _, buf = self.win._get_current_page()
        buf.place_cursor(buf.get_iter_at_offset(12))
        self.resize(1100)
        self.win.files_toggle.set_active(False)
        self.win._remember_pane(self.win.files_split)
        self.win._pane_preferences["ai"] = False
        self.win._checkpoint_session()
        self.win.destroy()
        restored = self.new_window()
        self.assertEqual(restored.get_width(), 1100)
        self.assertEqual(restored.edit_notebook.get_n_pages(), 2)
        restored_page, _, restored_buf = restored._get_current_page()
        self.assertEqual(Path(restored.open_tabs[restored_page]), second)
        self.assertEqual(restored_buf.get_iter_at_mark(restored_buf.get_insert()).get_offset(), 12)
        self.assertFalse(restored.files_split.get_show_sidebar())
        restored.set_default_size(1400, 700)
        self.settle()
        self.assertFalse(restored.ai_split.get_show_sidebar())

    def test_search_wraps_and_replace_all_uses_unicode_offsets_and_one_undo(self):
        _, _, buf = self.win._get_current_page()
        original = "Café café CAFÉ — other"
        buf.set_text(original, -1)
        self.win._show_search(True)
        self.win.find_entry.set_text("café")
        self.assertEqual(len(self.win._search_matches(buf)), 3)
        buf.place_cursor(buf.get_end_iter())
        self.assertTrue(self.win._find_match())
        start, end = buf.get_selection_bounds()
        self.assertEqual((start.get_offset(), end.get_offset()), (0, 4))
        self.win.replace_entry.set_text("Tea")
        self.win._replace_all()
        self.assertEqual(buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False), "Tea Tea Tea — other")
        buf.undo()
        self.assertEqual(buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False), original)
        self.win.find_entry.set_text("")
        self.win._replace_all()
        self.assertEqual(buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False), original)

    def test_preview_includes_text_after_500_characters(self):
        _, _, buf = self.win._get_current_page()
        buf.set_text("# Heading\n\n" + "Paragraph. " * 100 + "**The end**", -1)
        preview = self.win._on_preview()
        self.addCleanup(preview.destroy)
        view = preview.get_content().get_content().get_child()
        rendered = view.get_buffer()
        text = rendered.get_text(rendered.get_start_iter(), rendered.get_end_iter(), False)
        self.assertTrue(text.rstrip().endswith("The end"))
        self.assertIsNotNone(rendered.get_tag_table().lookup("h1"))

    def test_save_as_for_imports_and_external_changes_protects_sources(self):
        imported = self.module.WORK_DIR / "source.pdf"
        imported.write_bytes(b"original binary document")
        with patch.object(self.module, "import_file_content", return_value="Imported text"):
            page = self.win._open_document(imported)
        self.win._get_buf_from_page(page).set_text("Edited text", -1)
        with patch.object(self.win, "_save_page_as") as save_as:
            self.win._save_page(page)
        save_as.assert_called_once()
        self.assertEqual(imported.read_bytes(), b"original binary document")
        text_file = self.module.WORK_DIR / "external.md"
        text_file.write_text("Original")
        page = self.win._open_document(text_file)
        self.win._get_buf_from_page(page).set_text("My edit", -1)
        text_file.write_text("Changed externally")
        with patch.object(self.win, "_save_page_as") as save_as:
            self.win._save_page(page)
        save_as.assert_called_once()
        self.assertEqual(text_file.read_text(), "Changed externally")

    def test_stop_rejects_queued_stream_and_completion_without_history_or_edits(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        finished = threading.Event()
        def lines():
            finished.set()
            yield json.dumps({"message": {"content": "Late result"}, "done": True}).encode()
        response.iter_lines.side_effect = lines
        callback = Mock()
        self.module.OLLAMA_MODEL = "test-model"
        self.win._available_models = ["test-model"]
        with patch.object(self.module.requests, "post", return_value=response):
            self.assertTrue(self.win._call_ollama("Test prompt", callback))
            self.assertTrue(finished.wait(2))
            self.win._on_stop_ai()
            self.settle()
        callback.assert_not_called()
        self.assertEqual(self.win.chat_history, [])
        self.assertFalse(self.win.ai_activity.get_visible())
        self.assertTrue(self.win.chat_entry.get_sensitive())
        chat = self.win.chat_buffer
        self.assertNotIn("Late result", chat.get_text(chat.get_start_iter(), chat.get_end_iter(), False))

    def test_shortcut_actions_are_registered(self):
        for name, shortcut in [("save", "<Control>s"), ("open-file", "<Control>o"),
                               ("close-tab", "<Control>w"), ("find", "<Control>f")]:
            self.assertIn(shortcut, self.app.get_accels_for_action("win." + name))

    def test_completed_stream_records_history_and_releases_controls(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.iter_lines.return_value = [
            json.dumps({"message": {"content": "A completed answer"}, "done": True}).encode()]
        callback = Mock()
        self.module.OLLAMA_MODEL = "test-model"
        self.win._available_models = ["test-model"]
        with patch.object(self.module.requests, "post", return_value=response):
            self.win._call_ollama("A question", callback)
            self.settle()
        callback.assert_called_once_with("A completed answer")
        self.assertEqual([entry["role"] for entry in self.win.chat_history], ["user", "assistant"])
        self.assertIsNone(self.win._job)
        self.assertFalse(self.win.ai_activity.get_visible())

    def test_research_stop_prevents_late_audit_and_additional_model_request(self):
        _, _, buf = self.win._get_current_page()
        buf.set_text("A claim to research.", -1)
        buf.place_cursor(buf.get_end_iter())
        claims = '{"claims":[{"claim":"A claim","query":"test query"}]}'
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.iter_lines.return_value = [json.dumps({"message": {"content": claims}, "done": True}).encode()]
        searching = threading.Event()
        release = threading.Event()
        completed = threading.Event()
        self.addCleanup(release.set)
        def lookup(*args, **kwargs):
            searching.set()
            release.wait(2)
            completed.set()
            return EvidenceSearch([], ())
        self.module.OLLAMA_MODEL = "test-model"
        self.win._available_models = ["test-model"]
        with patch.object(self.module.requests, "post", return_value=response) as post, \
             patch.object(self.module, "search_evidence", side_effect=lookup):
            self.win._on_fact_check(self.win._ai_action_buttons[-1])
            self.settle()
            self.assertTrue(searching.is_set())
            self.assertEqual(self.win.ai_activity_label.get_label(), "Searching sources…")
            self.win._on_stop_ai()
            release.set()
            self.assertTrue(completed.wait(2))
            self.settle()
        self.assertEqual(post.call_count, 1)
        self.assertEqual(list(self.module.VERSIONS_DIR.glob("evidence_audit_*")), [])
        self.assertIsNone(self.win._job)

    def test_assistant_task_dispatch_and_live_selection_hints(self):
        self.win._apply_models(["test-model"], self.win._model_generation)
        _, _, buf = self.win._get_current_page()
        buf.set_text("Select these words", -1)
        self.win.assistant_task.set_selected(1)
        self.assertFalse(self.win.assistant_run.get_sensitive())
        self.assertIn("highlight", self.win.assistant_context.get_label())
        buf.select_range(buf.get_start_iter(), buf.get_end_iter())
        self.assertTrue(self.win.assistant_run.get_sensitive())
        self.assertIn("selected text", self.win.assistant_context.get_label())
        with patch.object(self.win, "_on_ai_edit") as edit, patch.object(self.win, "_on_ask") as ask:
            self.win.chat_entry.emit("activate")
            edit.assert_called_once()
            ask.assert_not_called()
        self.win.assistant_task.set_selected(3)
        self.assertIn("new tab", self.win.assistant_help.get_label())
        with patch.object(self.win, "_on_draft") as draft:
            self.win._run_assistant_task()
            draft.assert_called_once()

    def test_source_selection_persists_and_empty_sources_disable_check(self):
        self.win._apply_models(["test-model"], self.win._model_generation)
        self.win.assistant_task.set_selected(4)
        _, _, buf = self.win._get_current_page()
        buf.set_text("A claim.", -1)
        buf.select_range(buf.get_start_iter(), buf.get_end_iter())
        self.assertTrue(self.win.evidence_button.get_sensitive())
        self.assertIn("selected text", self.win.evidence_context.get_label())
        for check in self.win.source_checks.values():
            check.set_active(False)
        self.assertFalse(self.win.evidence_button.get_sensitive())
        self.assertEqual(self.module.load_config()["evidence_providers"], [])
        self.win.source_checks["arxiv"].set_active(True)
        self.assertEqual(self.win._selected_evidence_providers(), ["arxiv"])
        self.assertTrue(self.win.evidence_button.get_sensitive())
        restored = self.new_window()
        self.assertEqual(restored._selected_evidence_providers(), ["arxiv"])
        self.win.assistant_task.set_selected(0)
        self.assertFalse(self.win.source_options.get_visible())
        self.assertTrue(self.win.chat_entry.get_visible())
        self.assertTrue(self.win.assistant_run.get_sensitive())

    def test_evidence_check_preserves_highlight_and_records_coverage_in_saved_report(self):
        self.win._apply_models(["test-model"], self.win._model_generation)
        _, _, buf = self.win._get_current_page()
        original = "Before. Highlight this claim. After."
        buf.set_text(original, -1)
        buf.select_range(buf.get_iter_at_offset(8), buf.get_iter_at_offset(29))
        selected = buf.get_text(*buf.get_selection_bounds(), False)
        self.win.source_checks["europe_pmc"].set_active(False)
        claim = ClaimQuery("A claim", "neutral query")
        source = EvidenceSource("A paper", "A", "2025", "", "Abstract", "https://arxiv.org/abs/2501.01234",
                                providers=("arXiv",), is_preprint=True)
        result = EvidenceSearch([source], ("arXiv: 1 publication(s) retrieved", "OpenAlex: unavailable"))
        self.win.assistant_task.set_selected(4)
        self.assertFalse(self.win.chat_entry.get_visible())
        self.assertTrue(self.win.source_options.get_visible())
        prompts = []
        def model(prompt, callback=None, error_callback=None, **kwargs):
            prompts.append(prompt)
            if kwargs.get("keep_job"):
                callback('{"claims":[{"claim":"A claim","query":"neutral query"}]}')
            else:
                self.win._finish_ai_job(kwargs["job"])
                callback("## Assessment\n\nNot verified. Check the linked source.")
            return True
        with patch.object(self.win, "_call_ollama", side_effect=model), \
             patch.object(self.module, "search_evidence", return_value=result) as lookup:
            self.win._run_assistant_task()
            self.settle()
        self.assertIn(selected, prompts[0])
        lookup.assert_called_once()
        self.assertEqual(lookup.call_args.args, ("neutral query",))
        self.assertEqual(lookup.call_args.kwargs["providers"], ["arxiv", "openalex"])
        self.assertEqual(buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False), original)
        report = self.win._last_evidence_report
        self.assertIsNotNone(report)
        text = report.read_text()
        self.assertIn("OpenAlex: unavailable", text)
        self.assertIn("Found via: arXiv", text)
        self.assertIn("Preprint", text)
        self.assertIn("https://arxiv.org/abs/", text)
        self.assertEqual(report.stat().st_mode & 0o777, 0o600)
        self.assertTrue(self.win.evidence_report_button.get_visible())
        with patch.object(self.win, "_on_preview") as preview:
            self.win._open_evidence_report()
            preview.assert_called_once()

    def test_busy_assistant_freezes_task_and_source_choices_until_stop(self):
        self.win._apply_models(["test-model"], self.win._model_generation)
        job = self.win._start_ai_job()
        self.assertFalse(self.win.assistant_task.get_sensitive())
        self.assertFalse(self.win.model_refresh.get_sensitive())
        self.assertTrue(all(not check.get_sensitive() for check in self.win.source_checks.values()))
        self.win._on_stop_ai()
        self.assertTrue(job.cancelled.is_set())
        self.assertTrue(self.win.assistant_task.get_sensitive())
        self.assertTrue(self.win.model_refresh.get_sensitive())
        self.assertTrue(all(check.get_sensitive() for check in self.win.source_checks.values()))

    def test_model_discovery_does_not_block_editing_or_replace_newer_results(self):
        waiting = threading.Event()
        release = threading.Event()
        self.addCleanup(release.set)
        def old_discovery():
            waiting.set()
            release.wait(2)
            return ["old-model"]
        # A side effect function keeps the first refresh blocked in its worker.
        count = [0]
        def discover():
            count[0] += 1
            return old_discovery() if count[0] == 1 else ["new-model"]
        waiting.clear()
        with patch.object(self.module, "get_available_models", side_effect=discover):
            self.win._refresh_models()
            self.assertTrue(waiting.wait(1))
            _, _, buf = self.win._get_current_page()
            buf.insert(buf.get_end_iter(), " Still editable.", -1)
            self.win._refresh_models()
            self.settle()
            self.assertEqual(self.win._available_models, ["new-model"])
            release.set()
            self.settle()
        self.assertEqual(self.win._available_models, ["new-model"])
