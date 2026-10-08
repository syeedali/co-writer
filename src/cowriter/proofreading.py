"""Private, offline English proofreading. No network or model dependency."""

import re
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class Issue:
    start: int
    end: int
    kind: str
    message: str
    suggestions: tuple


@dataclass(frozen=True)
class CheckResult:
    issues: tuple
    warning: str = ""


# Keep valid words such as its, were, well, ill, shell and lets out of this
# list: deciding whether they need an apostrophe requires more context.
CONTRACTIONS = {
    "dont": "don't", "doesnt": "doesn't", "didnt": "didn't",
    "cant": "can't", "couldnt": "couldn't", "wont": "won't",
    "wouldnt": "wouldn't", "shouldnt": "shouldn't", "isnt": "isn't",
    "arent": "aren't", "wasnt": "wasn't", "werent": "weren't",
    "hasnt": "hasn't", "havent": "haven't", "hadnt": "hadn't",
    "mustnt": "mustn't", "neednt": "needn't", "youre": "you're",
    "youve": "you've", "youll": "you'll", "theyre": "they're",
    "theyve": "they've", "theyll": "they'll", "weve": "we've",
    "thats": "that's", "theres": "there's", "whats": "what's",
    "whos": "who's", "heres": "here's", "im": "I'm", "ive": "I've",
}
WORD = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*", re.UNICODE)


def prose_mask(text):
    """Replace code, URLs and Markdown destinations with equal-length spaces.

    Offsets stay in Python/GTK Unicode characters, including astral characters.
    Link labels and ordinary Markdown prose are still checked.
    """
    masked = list(text)

    def hide(start, end):
        masked[start:end] = ["\n" if ch == "\n" else " " for ch in text[start:end]]

    fence = None
    offset = 0
    for line in text.splitlines(keepends=True):
        marker = re.match(r" {0,3}(`{3,}|~{3,})", line)
        if fence:
            hide(offset, offset + len(line))
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence):
                if not line[marker.end():].strip():
                    fence = None
        elif marker:
            fence = marker[1]
            hide(offset, offset + len(line))
        elif line.startswith(("    ", "\t")):
            hide(offset, offset + len(line))
        elif re.match(r" {0,3}\[[^\]]+\]:\s*\S+", line):
            hide(offset, offset + len(line))
        offset += len(line)

    remaining = "".join(masked)
    for pattern in (
        r"(`+)[^`\n]*?\1",                    # inline code
        r"!?\[[^\]\n]*\]\((?:[^()\n]|\([^()\n]*\))*\)",
        r"https?://[^\s<>]+|www\.[^\s<>]+",    # bare links
        r"[\w.+-]+@[\w.-]+\.[\w-]+",         # email addresses
        r"<[^>\n]+>",                         # HTML and autolinks
    ):
        for match in re.finditer(pattern, remaining):
            if "](" in match[0] and match[0].startswith(("[", "![")):
                start = match.start() + match[0].index("](") + 2
                hide(start, match.end() - 1)
            else:
                hide(match.start(), match.end())
        remaining = "".join(masked)
    return "".join(masked)


def _case_like(replacement, original):
    if original.isupper() and len(original) > 1:
        return replacement.upper()
    if original[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def grammar_issues(text):
    """Target common mechanical slips, rather than rewriting the writer's style."""
    issues = []
    for match in WORD.finditer(text):
        word = match[0]
        normalized = word.lower().replace("’", "'")
        replacement = None
        if normalized in CONTRACTIONS:
            replacement = _case_like(CONTRACTIONS[normalized], word)
            message = "Possible missing apostrophe in a contraction."
        elif word == "i" or word.startswith(("i'", "i’")):
            replacement = "I" + word[1:]
            message = "Capitalize the pronoun “I”."
        if replacement:
            issues.append(Issue(match.start(), match.end(), "grammar", message, (replacement,)))

    # Repeating these function words is usually an accidental extra keystroke.
    # Avoid legitimate constructions such as “had had” and “that that”.
    for match in re.finditer(r"\b(the|a|an|and|or|to|of|in|for|with)[ \t]+\1\b", text, re.I):
        issues.append(Issue(match.start(), match.end(), "grammar",
                            "Possible repeated word.", (match[1],)))
    agreements = {
        "i": {"is": "am", "are": "am"},
        "you": {"is": "are", "was": "were"},
        "we": {"is": "are", "was": "were"},
        "they": {"is": "are", "was": "were"},
        # “If she were …” is a valid subjunctive, so do not flag were here.
        "he": {"are": "is", "don't": "doesn't"},
        "she": {"are": "is", "don't": "doesn't"},
        "it": {"are": "is", "don't": "doesn't"},
    }
    for match in re.finditer(r"\b(I|you|we|they|he|she|it)[ \t]+(is|are|was|were|don['’]t)\b", text, re.I):
        verb = match[2].lower().replace("’", "'")
        correct = agreements[match[1].lower()].get(verb)
        if correct:
            # Mark only the verb, so a lowercase i can be corrected separately.
            issues.append(Issue(match.start(2), match.end(2), "grammar",
                                "Check subject–verb agreement.", (_case_like(correct, match[2]),)))
    return issues


class AspellDictionary:
    """Batch unique words through the installed local dictionary over stdin."""

    def check(self, words):
        if not words:
            return {}, ""
        try:
            process = subprocess.run(
                ["aspell", "-a", "--lang=en_US", "--encoding=utf-8", "--mode=none",
                 "--sug-mode=fast"],
                # ^ forces text mode, even if a future tokenizer admits a pipe
                # command character. Document text never goes on the command line.
                input="".join("^" + word.replace("’", "'") + "\n" for word in words),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8",
                timeout=8, check=False,
            )
        except (OSError, subprocess.TimeoutExpired, UnicodeError):
            return {}, "Spelling unavailable. Install aspell and aspell-en; grammar checking is still active."
        if process.returncode:
            return {}, "English spelling dictionary unavailable. Install aspell and aspell-en; grammar checking is still active."
        blocks = process.stdout.split("\n", 1)[-1].strip().split("\n\n")
        if len(blocks) != len(words):
            return {}, "Spelling checker returned an incomplete result; grammar checking is still active."
        misspelled = {}
        for word, block in zip(words, blocks):
            lines = block.splitlines()
            if any(line.startswith(("&", "#", "?")) for line in lines):
                suggestions = []
                for line in lines:
                    if line.startswith(("&", "?")) and ": " in line:
                        suggestions.extend(line.split(": ", 1)[1].split(", "))
                if "’" in word:
                    suggestions = [suggestion.replace("'", "’") for suggestion in suggestions]
                misspelled[word] = tuple(dict.fromkeys(suggestions))[:5]
        return misspelled, ""


def check_text(text, dictionary=None, ignored=()):
    prose = prose_mask(text)
    ignored = {word.casefold() for word in ignored}
    grammar = grammar_issues(prose)
    covered = {offset for issue in grammar for offset in range(issue.start, issue.end)}
    tokens = [match for match in WORD.finditer(prose)
              if match[0].casefold() not in ignored
              # Do not flag identifiers, version strings or parts of filenames.
              and not (match.start() and (prose[match.start() - 1].isalnum()
                                         or prose[match.start() - 1] in "_/@"))
              and not (match.end() < len(prose) and (prose[match.end()].isalnum()
                                                    or prose[match.end()] == "_"))]
    words = list(dict.fromkeys(match[0] for match in tokens
                             if match.start() not in covered))
    misspelled, warning = (dictionary or AspellDictionary()).check(words)
    issues = [issue for issue in grammar if prose[issue.start:issue.end].casefold() not in ignored]
    for match in tokens:
        if match[0] in misspelled:
            issues.append(Issue(match.start(), match.end(), "spelling",
                                "Possible misspelling.", misspelled[match[0]]))
    return CheckResult(tuple(sorted(issues, key=lambda issue: (issue.start, issue.end))), warning)
