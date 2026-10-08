import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from cowriter.craft import (CraftNotes, REFERENCE_CARDS, anchor_at, apply_reading,
                            repetitions, resolve_anchor, rhyme_connections)
from cowriter.poetry import analyze, dictionary


class CraftTests(unittest.TestCase):
    def test_repetitions_find_case_insensitive_words_and_phrases_with_unicode_offsets(self):
        text = "😀 My lantern is glowing.\nHer lantern is glowing.\nGLOWING again."
        words = repetitions(text)
        glowing = next(group for group in words if group.phrase == "glowing")
        self.assertEqual([text[start:end].lower() for start, end in glowing.spans], ["glowing"] * 3)
        phrase = repetitions(text, size=3)
        self.assertEqual(phrase[0].phrase, "lantern is glowing")
        self.assertEqual(len(phrase[0].spans), 2)

    def test_repetition_filters_are_optional_and_code_is_excluded(self):
        text = "I see light. I see night. `light light`\n```\nnight night\n```"
        self.assertFalse(any(group.phrase == "i" for group in repetitions(text)))
        self.assertTrue(any(group.phrase == "i" for group in repetitions(text, include_common=True)))
        self.assertEqual(len(repetitions(text, query="light")[0].spans), 1)
        self.assertFalse(repetitions("light\nnight", size=2))

    def test_rhyme_map_connects_distant_lines_and_distinguishes_echoes_and_repetition(self):
        lines = analyze("light\nmoon\nnight\ntime\nlight", dictionary()).lines
        pairs = {(pair.left, pair.right): pair.kind for pair in rhyme_connections(lines)}
        self.assertEqual(pairs[0, 2], "Possible rhyme")
        self.assertEqual(pairs[0, 3], "Vowel echo")
        self.assertEqual(pairs[0, 4], "Repeated ending")
        self.assertNotIn((0, 1), pairs)

    def test_anchors_follow_unique_lines_but_hold_changed_and_ambiguous_lines_aside(self):
        text = "First\nAn important line\nLast"
        anchor = anchor_at(text, text.index("important"))
        moved = "New opening\n" + text
        self.assertEqual(resolve_anchor(moved, anchor), moved.index("An important"))
        self.assertIsNone(resolve_anchor(text.replace("important", "changed"), anchor))
        duplicate = "A\nRefrain\nB\nA\nRefrain\nB"
        self.assertIsNone(resolve_anchor(duplicate, anchor_at(duplicate, 2)))

    def test_duplicate_anchors_can_use_unique_neighbor_context(self):
        text = "First\nRefrain\nNext\nOther\nRefrain\nEnd"
        anchor = anchor_at(text, text.index("Refrain"))
        self.assertEqual(resolve_anchor("Prefix\n" + text, anchor), len("Prefix\nFirst\n"))

    def test_bookmark_at_empty_or_trailing_line_is_anchored_to_that_line(self):
        self.assertEqual(anchor_at("", 0)["text"], "")
        self.assertEqual(resolve_anchor("First\n", anchor_at("First\n", 6)), 6)

    def test_notes_are_private_per_source_and_preserve_source_document(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "poem.md"
            text = "fire\nlight"
            source.write_text(text)
            notes = CraftNotes(root / "notes", source)
            notes.data["focus"] = "Listen for breaths"
            notes.set_reading(text, 0, {"words": ["fire"], "stresses": ["1"], "custom": [True], "pauses": ["|"]})
            notes.save()
            restored = CraftNotes(root / "notes", source)
            line = apply_reading(analyze(text).lines[0], restored.reading(text, 0))
            self.assertEqual(line.syllables, "1")
            self.assertEqual(restored.data["focus"], "Listen for breaths")
            self.assertEqual(notes.path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(source.read_text(), text)
            other = CraftNotes(root / "notes", root / "other" / "poem.md")
            self.assertNotEqual(other.path, restored.path)
            self.assertEqual(other.data["focus"], "")

    def test_personal_marks_do_not_turn_unmarked_unknown_words_into_known_readings(self):
        line = analyze("light zzyxxyq").lines[0]
        record = {"words": ["light", "zzyxxyq"], "stresses": ["0", "?"], "custom": [True, False]}
        chosen = apply_reading(line, record)
        self.assertEqual(chosen.words[0].stresses, ("0",))
        self.assertTrue(chosen.words[1].guessed)
        self.assertTrue(chosen.syllables.startswith("≈"))

    def test_incompatible_and_malformed_readings_do_not_change_hints(self):
        line = analyze("fire").lines[0]
        for record in ({"words": ["other"], "stresses": ["1"]},
                       {"words": ["fire"], "stresses": ["invalid"]},
                       {"words": ["fire"], "stresses": ["1"], "custom": None},
                       {"words": ["fire"], "stresses": ["1"], "pauses": None}):
            self.assertEqual(apply_reading(line, record), line)

    def test_save_as_copy_is_independent_and_failed_save_preserves_previous_notes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = CraftNotes(root, root / "old.md")
            old.data["focus"] = "A small question"
            old.save()
            original = old.path.read_text()
            new = CraftNotes(root, root / "new.md", initial=old.data)
            new.data["focus"] = "Another question"
            self.assertEqual(old.data["focus"], "A small question")
            new.save()
            with patch("cowriter.craft.save_json", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    old.save()
            self.assertEqual(old.path.read_text(), original)

    def test_reference_cards_are_available_without_network_or_generation(self):
        self.assertEqual(len(REFERENCE_CARDS), 5)
        self.assertEqual(REFERENCE_CARDS[0][0], "Iambic pentameter")
        self.assertIn("Accentual verse", [card[0] for card in REFERENCE_CARDS])


if __name__ == "__main__":
    unittest.main()
