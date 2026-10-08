"""Small offline sound tools: pronunciation hints, line rhythm and rhymes."""

import gzip
import re
import subprocess
import threading
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .proofreading import prose_mask


WORDS = re.compile(r"(?<!\w)[^\W\d_]+(?:['’\-][^\W\d_]+)*(?!\w)", re.UNICODE)
VOWELS = {"AA", "AE", "AH", "AO", "AW", "AY", "EH", "ER", "EY", "IH", "IY", "OW", "OY", "UH", "UW"}
STRESS_SYMBOLS = {"0": "·", "1": "●", "2": "◐", "?": "?"}


def normalized(word):
    return word.casefold().replace("’", "'")


def rhyme_tail(phones):
    """Sound from the final stressed vowel onwards, ignoring stress digits."""
    stressed = [index for index, phone in enumerate(phones) if phone[-1:] in ("1", "2")]
    if not stressed:
        return ()
    return tuple(re.sub(r"[012]$", "", phone) for phone in phones[stressed[-1]:])


def vowel_echo(tail):
    return tuple(phone for phone in tail if phone in VOWELS)


class Pronunciations:
    def __init__(self, entries, familiar_words=()):
        self.entries = entries
        self.familiar_words = set(familiar_words)
        self.rhymes = {}
        self.echoes = {}
        for word, variants in entries.items():
            if not re.fullmatch(r"[a-z]+(?:['-][a-z]+)*", word):
                continue
            for phones in variants:
                tail = rhyme_tail(phones)
                if tail:
                    self.rhymes.setdefault(tail, set()).add(word)
                    self.echoes.setdefault(vowel_echo(tail), set()).add(word)

    def lookup(self, word):
        return self.entries.get(normalized(word), ())

    def find_rhymes(self, word, limit=60, syllables=None):
        variants = self.lookup(word)
        exact, echoes = set(), set()
        for phones in variants:
            tail = rhyme_tail(phones)
            if tail:
                exact.update(self.rhymes.get(tail, ()))
                echoes.update(self.echoes.get(vowel_echo(tail), ()))
        target = normalized(word)
        exact.discard(target)
        echoes.difference_update(exact | {target})
        if syllables is not None:
            def matches(candidate):
                return any(sum(phone[-1:].isdigit() for phone in phones) == syllables
                           for phones in self.entries[candidate])
            exact = {candidate for candidate in exact if matches(candidate)}
            echoes = {candidate for candidate in echoes if matches(candidate)}

        def order(candidate):
            count = min(sum(phone[-1:].isdigit() for phone in p) for p in self.entries[candidate])
            return candidate not in self.familiar_words, count, len(candidate), candidate

        return RhymeMatches(bool(variants), tuple(sorted(exact, key=order)[:limit]),
                            tuple(sorted(echoes, key=order)[:limit]))


_dictionary_lock = threading.Lock()


def dictionary():
    # Only called by background workers; the UI never loads or indexes the file.
    with _dictionary_lock:
        return _load_dictionary()


@lru_cache(maxsize=1)
def _load_dictionary():
    entries = {}
    path = Path(__file__).resolve().parent / "poetry_data" / "cmudict.dict.gz"
    with gzip.open(str(path), "rt", encoding="utf-8") as stream:
        for line in stream:
            parts = line.split("#", 1)[0].split()
            if len(parts) < 2 or parts[0].startswith(";;;"):
                continue
            word = re.sub(r"\(\d+\)$", "", parts[0]).lower()
            phones = tuple(parts[1:])
            if phones not in entries.setdefault(word, []):
                entries[word].append(phones)
    return Pronunciations({word: tuple(variants) for word, variants in entries.items()}, _familiar_words())


def _familiar_words():
    """Prefer ordinary lowercase vocabulary over the many CMU proper names.

    Aspell is already used for spelling. Its absence affects ordering only;
    every poetry feature still works from the bundled dictionary alone.
    """
    try:
        process = subprocess.run(["aspell", "--lang=en_US", "dump", "master"],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 encoding="utf-8", timeout=3, check=False)
        if process.returncode == 0:
            return {line.split("/", 1)[0] for line in process.stdout.splitlines()
                    if line.split("/", 1)[0].islower()}
    except (OSError, subprocess.TimeoutExpired, UnicodeError):
        pass
    return set()


def estimated_syllables(word):
    """A fallback count only. Unknown words never receive invented stresses."""
    value = re.sub(r"[^a-z]", "", normalized(word))
    groups = len(re.findall(r"[aeiouy]+", value))
    if value.endswith("e") and not value.endswith(("le", "ye")) and groups > 1:
        groups -= 1
    if value.endswith("le") and len(value) > 2 and value[-3] in "aeiouy" and groups > 1:
        groups -= 1
    return max(1, groups)


@dataclass(frozen=True)
class RhymeMatches:
    known: bool
    exact: tuple
    echoes: tuple


@dataclass(frozen=True)
class WordSound:
    start: int
    end: int
    text: str
    stresses: tuple
    tails: tuple
    guessed: bool

    @property
    def minimum(self):
        return min(len(stress) for stress in self.stresses)

    @property
    def maximum(self):
        return max(len(stress) for stress in self.stresses)

    @property
    def rhythm(self):
        return " / ".join(" ".join(STRESS_SYMBOLS[ch] for ch in stress) for stress in self.stresses)


@dataclass(frozen=True)
class LineSound:
    number: int
    start: int
    end: int
    text: str
    words: tuple
    rhyme_group: int = -1

    @property
    def minimum(self):
        return sum(word.minimum for word in self.words)

    @property
    def maximum(self):
        return sum(word.maximum for word in self.words)

    @property
    def syllables(self):
        count = str(self.minimum) if self.minimum == self.maximum else f"{self.minimum}–{self.maximum}"
        return ("≈" if any(word.guessed for word in self.words) else "") + count

    @property
    def rhythm(self):
        # One possible dictionary reading; alternatives remain in word hints.
        return "   ".join(" ".join(STRESS_SYMBOLS[ch] for ch in word.stresses[0]) for word in self.words)


@dataclass(frozen=True)
class PoemSound:
    lines: tuple
    warning: str = ""


def analyze(text, pronunciations=None):
    source = pronunciations or dictionary()
    prose = prose_mask(text)
    lines, offset = [], 0
    # Keep blank/code lines out of the results while preserving document offsets.
    for number, line in enumerate(prose.splitlines(keepends=True), 1):
        words = []
        for match in WORDS.finditer(line):
            variants = source.lookup(match[0])
            stresses = tuple(dict.fromkeys("".join(phone[-1] for phone in phones if phone[-1:].isdigit())
                                           for phones in variants))
            stresses = tuple(stress for stress in stresses if stress)
            guessed = not stresses
            if guessed:
                stresses = ("?" * estimated_syllables(match[0]),)
            tails = tuple(dict.fromkeys(tail for tail in (rhyme_tail(p) for p in variants) if tail))
            words.append(WordSound(offset + match.start(), offset + match.end(), match[0], stresses, tails, guessed))
        if words:
            lines.append(LineSound(number, offset, offset + len(line.rstrip("\r\n")),
                                   text[offset:offset + len(line)].strip(), tuple(words)))
        offset += len(line)

    # Group matching line endings without forcing an A/B scheme on free verse.
    # Use one dictionary pronunciation consistently, avoiding transitive bridges
    # between unrelated pronunciations of ambiguous words such as “read”.
    endings = {}
    for index, line in enumerate(lines):
        if line.words[-1].tails:
            endings.setdefault(line.words[-1].tails[0], []).append(index)
    groups = {}
    for indices in endings.values():
        # Repeating the same word is an echo, not a newly discovered rhyme.
        if len({normalized(lines[index].words[-1].text) for index in indices}) > 1:
            group = len(set(groups.values()))
            groups.update({index: group for index in indices})
    return PoemSound(tuple(LineSound(line.number, line.start, line.end, line.text, line.words,
                                    groups.get(index, -1)) for index, line in enumerate(lines)))
