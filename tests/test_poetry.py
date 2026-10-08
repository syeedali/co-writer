import gzip
import hashlib
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from cowriter import poetry


class PoetryTests(unittest.TestCase):
    def setUp(self):
        self.words = poetry.Pronunciations({
            "the": (("DH", "AH0"),), "moon": (("M", "UW1", "N"),),
            "spoon": (("S", "P", "UW1", "N"),), "tune": (("T", "UW1", "N"),),
            "blue": (("B", "L", "UW1"),), "light": (("L", "AY1", "T"),),
            "night": (("N", "AY1", "T"),), "bite": (("B", "AY1", "T"),),
            "kite": (("K", "AY1", "T"),), "time": (("T", "AY1", "M"),),
            "fire": (("F", "AY1", "ER0"), ("F", "AY1", "R")),
            "read": (("R", "EH1", "D"), ("R", "IY1", "D")),
            "bed": (("B", "EH1", "D"),), "reed": (("R", "IY1", "D"),),
            "poetry": (("P", "OW1", "AH0", "T", "R", "IY0"),),
            "don't": (("D", "OW1", "N", "T"),),
        })

    def test_syllables_and_stress_come_from_pronunciation(self):
        result = poetry.analyze("the moon\npoetry", self.words)
        self.assertEqual([line.syllables for line in result.lines], ["2", "3"])
        self.assertEqual(result.lines[0].rhythm, "·   ●")
        self.assertEqual(result.lines[1].rhythm, "● · ·")

    def test_multiple_readings_preserve_syllable_range(self):
        word = poetry.analyze("fire", self.words).lines[0].words[0]
        self.assertEqual((word.minimum, word.maximum), (1, 2))
        self.assertEqual(word.stresses, ("10", "1"))
        self.assertEqual(poetry.analyze("fire", self.words).lines[0].syllables, "1–2")
        self.assertFalse(word.guessed)

    def test_unknown_words_are_estimates_without_invented_stress_or_rhymes(self):
        line = poetry.analyze("Membrie moon", self.words).lines[0]
        self.assertTrue(line.syllables.startswith("≈"))
        word = line.words[0]
        self.assertTrue(word.guessed)
        self.assertEqual(set(word.stresses[0]), {"?"})
        self.assertEqual(word.tails, ())
        self.assertFalse(self.words.find_rhymes("Membrie").known)

    def test_rhymes_are_phonetic_and_vowel_echoes_are_separate(self):
        rhymes = self.words.find_rhymes("LIGHT")
        self.assertEqual(set(rhymes.exact), {"night", "bite", "kite"})
        self.assertIn("time", rhymes.echoes)
        self.assertFalse(set(rhymes.exact) & set(rhymes.echoes))
        self.assertNotIn("light", rhymes.exact + rhymes.echoes)

    def test_lookup_uses_all_pronunciations(self):
        self.assertEqual(set(self.words.find_rhymes("read").exact), {"bed", "reed"})

    def test_line_endings_group_by_sound_not_spelling(self):
        lines = poetry.analyze("light\nnight\nmoon\nspoon\npoetry", self.words).lines
        self.assertEqual([line.rhyme_group for line in lines], [0, 0, 1, 1, -1])

    def test_same_word_repeated_is_not_mislabeled_as_a_new_rhyme(self):
        self.assertEqual([line.rhyme_group for line in poetry.analyze("moon\nMoon", self.words).lines], [-1, -1])

    def test_ambiguous_pronunciations_do_not_bridge_unrelated_rhyme_groups(self):
        lines = poetry.analyze("bed\nread\nreed", self.words).lines
        self.assertEqual([line.rhyme_group for line in lines], [0, 0, -1])

    def test_unicode_blank_lines_and_markdown_preserve_offsets(self):
        text = "😀 the moon\n\n```\nmisspelled\n```\n[light](https://night.invalid)\n`unknown` night\n"
        result = poetry.analyze(text, self.words)
        self.assertEqual([line.number for line in result.lines], [1, 6, 7])
        for line in result.lines:
            for word in line.words:
                self.assertEqual(text[word.start:word.end], word.text)
                self.assertFalse(word.guessed)
        self.assertEqual(result.lines[1].words[-1].text, "light")

    def test_curly_apostrophes_use_normalized_dictionary_lookup(self):
        self.assertFalse(poetry.analyze("don’t", self.words).lines[0].words[0].guessed)

    def test_familiar_words_rank_before_names_and_results_are_bounded(self):
        words = poetry.Pronunciations(self.words.entries, familiar_words={"kite"})
        self.assertEqual(words.find_rhymes("light", 1).exact, ("kite",))

    def test_syllable_filter_applies_before_limiting_and_checks_alternate_readings(self):
        entries = {**self.words.entries, "alight": (("AH0", "L", "AY1", "T"),)}
        words = poetry.Pronunciations(entries)
        result = words.find_rhymes("light", limit=1, syllables=2)
        self.assertEqual(result.exact, ("alight",))
        self.assertIn("fire", result.echoes)
        self.assertNotIn("night", result.exact)

    def test_missing_aspell_only_affects_optional_rhyme_ranking(self):
        with patch.object(poetry.subprocess, "run", side_effect=FileNotFoundError()):
            self.assertEqual(poetry._familiar_words(), set())
        self.assertTrue(self.words.find_rhymes("light").exact)

    def test_bundled_dictionary_has_provenance_license_and_expected_words(self):
        source = Path(poetry.__file__).parent / "poetry_data"
        raw = gzip.decompress((source / "cmudict.dict.gz").read_bytes())
        self.assertIn(hashlib.sha256(raw).hexdigest(), (source / "SOURCE.md").read_text())
        self.assertIn("Carnegie Mellon", (source / "CMUDICT-LICENSE").read_text())
        words = poetry.dictionary()
        self.assertGreater(len(words.entries), 120000)
        self.assertIn("night", words.find_rhymes("light").exact)
        self.assertEqual(poetry.analyze("poetry", words).lines[0].minimum, 3)


if __name__ == "__main__":
    unittest.main()
