import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from cowriter.workspace import RecoveryStore, atomic_write, load_json


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.store = RecoveryStore(self.root / "autosaves")

    def test_same_named_documents_have_distinct_private_recovery_copies(self):
        first = self.root / "one/draft.md"
        second = self.root / "two/draft.md"
        self.store.write(first, "First unsaved draft", "First original")
        self.store.write(second, "Second unsaved draft", "Second original")
        self.assertNotEqual(self.store.path_for(first), self.store.path_for(second))
        self.assertEqual(self.store.read(first, "First original")["text"], "First unsaved draft")
        self.assertEqual(self.store.read(second, "Second original")["text"], "Second unsaved draft")
        self.assertEqual(os.stat(self.store.path_for(first)).st_mode & 0o777, 0o600)

    def test_recovery_identifies_disk_conflicts_and_ignores_saved_copies(self):
        source = self.root / "draft.md"
        self.store.write(source, "Recovered", "Original")
        self.assertFalse(self.store.read(source, "Original")["disk_changed"])
        self.assertTrue(self.store.read(source, "Changed elsewhere")["disk_changed"])
        self.assertIsNone(self.store.read(source, "Recovered"))
        self.store.remove(source)
        self.assertIsNone(self.store.read(source, "Original"))

    def test_failed_atomic_save_preserves_original_and_cleans_temporary_file(self):
        source = self.root / "draft.md"
        source.write_text("Original")
        with patch("cowriter.workspace.os.replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                atomic_write(source, "New draft")
        self.assertEqual(source.read_text(), "Original")
        self.assertEqual(list(self.root.glob(".cowriter-*")), [])

    def test_malformed_or_non_object_local_state_is_ignored(self):
        path = self.root / "session.json"
        for value in ["broken", "[]", '"text"']:
            path.write_text(value)
            self.assertEqual(load_json(path), {})


if __name__ == "__main__":
    unittest.main()
