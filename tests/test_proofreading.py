import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from cowriter.proofreading import AspellDictionary, check_text, prose_mask


class ProofreadingTests(unittest.TestCase):
    def grammar(self, text):
        dictionary = Mock()
        dictionary.check.return_value = ({}, "")
        return check_text(text, dictionary).issues

    def test_apostrophes_and_pronoun_capitalization_have_precise_replacements(self):
        text = "i dont think Im ready. ive tried. i’m sure Youre right. THEYRE ready."
        issues = self.grammar(text)
        self.assertEqual([(text[i.start:i.end], i.suggestions[0]) for i in issues], [
            ("i", "I"), ("dont", "don't"), ("Im", "I'm"), ("ive", "I've"),
            ("i’m", "I’m"), ("Youre", "You're"), ("THEYRE", "THEY'RE"),
        ])

    def test_valid_contractions_and_ambiguous_words_are_left_alone(self):
        text = "I'm sure I’ve done well. Its shell is ill. We were ready. Lets go of it. If she were here."
        self.assertEqual(self.grammar(text), ())

    def test_repeated_words_and_simple_agreement(self):
        text = "The the dog is here. They is ready. He don't know. I had had enough."
        issues = self.grammar(text)
        self.assertEqual([(text[i.start:i.end], i.suggestions[0]) for i in issues], [
            ("The the", "The"), ("is", "are"), ("don't", "doesn't"),
        ])

    def test_unicode_offsets_and_dictionary_suggestions(self):
        text = "😀 Café — Misspealling, grammer and i dont know."
        dictionary = Mock()
        dictionary.check.return_value = ({"Misspealling": ("Misspelling",), "grammer": ("grammar",)}, "")
        issues = check_text(text, dictionary).issues
        self.assertEqual([(text[i.start:i.end], i.kind) for i in issues], [
            ("Misspealling", "spelling"), ("grammer", "spelling"), ("i", "grammar"), ("dont", "grammar"),
        ])
        self.assertNotIn("dont", dictionary.check.call_args[0][0])

    def test_markdown_code_and_destinations_are_excluded_but_labels_are_checked(self):
        text = ("[grammer](https://example.com/dont) `i dont`\n"
                "```python\ni dont\n```\n~~~\ngrammer\n~~~\n"
                "    i dont\n\n[ref]: https://example.com/grammer\n"
                "Email person@grammer.test or https://grammer.test/dont.\n"
                "i dont know.")
        masked = prose_mask(text)
        self.assertEqual(len(masked), len(text))
        self.assertEqual(masked.count("grammer"), 1)
        self.assertEqual(masked.count("dont"), 1)
        self.assertEqual([text[i.start:i.end] for i in self.grammar(text)], ["i", "dont"])

    def test_unclosed_code_fence_is_excluded(self):
        self.assertEqual(self.grammar("Good.\n```\ni dont"), ())

    def test_personal_words_are_case_insensitive_and_skip_dictionary(self):
        dictionary = Mock()
        dictionary.check.return_value = ({}, "")
        result = check_text("Membrie and MEMBRIE.", dictionary, ignored={"membrie"})
        self.assertEqual(result.issues, ())
        self.assertEqual(dictionary.check.call_args[0][0], ["and"])

    def test_aspell_uses_literal_stdin_and_handles_curly_apostrophes(self):
        response = Mock(returncode=0, stdout="@(#) Aspell\n& grammer 1 1: grammar\n\n*\n\n")
        with patch("cowriter.proofreading.subprocess.run", return_value=response) as run:
            misspelled, warning = AspellDictionary().check(["grammer", "don’t"])
        self.assertEqual(misspelled, {"grammer": ("grammar",)})
        self.assertFalse(warning)
        self.assertEqual(run.call_args.kwargs["input"], "^grammer\n^don't\n")
        self.assertNotIn("shell", run.call_args.kwargs)
        self.assertNotIn("grammer", run.call_args.args[0])

    def test_missing_dictionary_and_timeout_preserve_grammar_checks(self):
        for failure in (FileNotFoundError(), subprocess.TimeoutExpired("aspell", 8)):
            with self.subTest(failure=failure), patch("cowriter.proofreading.subprocess.run", side_effect=failure):
                result = check_text("i dont know.")
                self.assertTrue(result.warning)
                self.assertEqual([i.suggestions[0] for i in result.issues], ["I", "don't"])

    def test_failed_and_incomplete_checker_responses_are_reported(self):
        for response in (Mock(returncode=1), Mock(returncode=0, stdout="@(#) Aspell\n*\n\n")):
            with patch("cowriter.proofreading.subprocess.run", return_value=response):
                self.assertTrue(AspellDictionary().check(["word", "another"])[1])

    @unittest.skipUnless(shutil.which("aspell"), "Requires local Aspell")
    def test_installed_dictionary_catches_the_requested_misspellings(self):
        result = check_text("Misspealling grammer. I don't know. I’m ready.")
        if result.warning:
            self.skipTest(result.warning)
        self.assertEqual(len(result.issues), 2)
        self.assertIn("Misspelling", result.issues[0].suggestions)
        self.assertIn("grammar", result.issues[1].suggestions)


if __name__ == "__main__":
    unittest.main()
