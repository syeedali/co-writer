"""Writer-owned craft annotations and small, deterministic exploration tools."""

import copy
import hashlib
from dataclasses import dataclass, replace
from pathlib import Path

from .poetry import WORDS, normalized, vowel_echo
from .proofreading import prose_mask
from .workspace import load_json, save_json


COMMON_WORDS = set("a an and are as at be been but by can did do does for from had has have he her him his i if in is it its me my of on or our she so that the their them then there these they this to us was we were what when who will with you your".split())


@dataclass(frozen=True)
class Repetition:
    phrase: str
    spans: tuple


def repetitions(text, size=1, include_common=False, query=""):
    tokens = list(WORDS.finditer(prose_mask(text)))
    wanted = tuple(normalized(word[0]) for word in WORDS.finditer(query))
    size = len(wanted) if wanted else max(1, min(3, size))
    groups = {}
    for index in range(len(tokens) - size + 1):
        words = tokens[index:index + size]
        if "\n" in text[words[0].start():words[-1].end()]:
            continue
        key = tuple(normalized(word[0]) for word in words)
        if wanted and key != wanted:
            continue
        if not wanted and not include_common and all(word in COMMON_WORDS for word in key):
            continue
        groups.setdefault(key, []).append((words[0].start(), words[-1].end()))
    return tuple(sorted((Repetition(" ".join(key), tuple(spans)) for key, spans in groups.items()
                         if len(spans) > 1 or wanted), key=lambda group: (-len(group.spans), group.spans[0][0])))


@dataclass(frozen=True)
class RhymeConnection:
    left: int
    right: int
    kind: str


def rhyme_connections(lines):
    """Pairwise possibilities allow alternate readings without merging families."""
    pairs = []
    for left, line in enumerate(lines):
        a = line.words[-1]
        for right in range(left + 1, len(lines)):
            b = lines[right].words[-1]
            if normalized(a.text) == normalized(b.text):
                kind = "Repeated ending"
            elif set(a.tails) & set(b.tails):
                kind = "Possible rhyme"
            elif ({vowel_echo(tail) for tail in a.tails} & {vowel_echo(tail) for tail in b.tails}) - {()}:
                kind = "Vowel echo"
            else:
                continue
            pairs.append(RhymeConnection(left, right, kind))
    return tuple(pairs)


def line_locations(text):
    result, offset = [], 0
    for number, raw in enumerate(text.splitlines(keepends=True), 1):
        result.append((number, offset, raw.rstrip("\r\n")))
        offset += len(raw)
    if not result or text.endswith("\n"):
        result.append((len(result) + 1, offset, ""))
    return result


def anchor_at(text, offset):
    lines = line_locations(text)
    if not lines:
        return None
    index = next((i for i, line in enumerate(lines)
                  if i + 1 == len(lines) or lines[i + 1][1] > offset), len(lines) - 1)
    return {"text": lines[index][2], "number": lines[index][0],
            "before": lines[index - 1][2] if index else None,
            "after": lines[index + 1][2] if index + 1 < len(lines) else None}


def resolve_anchor(text, anchor, locations=None):
    if not isinstance(anchor, dict) or not isinstance(anchor.get("text"), str):
        return None
    lines = line_locations(text) if locations is None else locations
    candidates = [i for i, line in enumerate(lines) if line[2] == anchor["text"]]
    if len(candidates) == 1:
        return lines[candidates[0]][1]
    contextual = [i for i in candidates
                  if (lines[i - 1][2] if i else None) == anchor.get("before")
                  and (lines[i + 1][2] if i + 1 < len(lines) else None) == anchor.get("after")]
    return lines[contextual[0]][1] if len(contextual) == 1 else None


class CraftNotes:
    """Private sidecars keyed by source path; never written into a manuscript."""

    def __init__(self, directory, source, initial=None):
        self.source = str(Path(source).resolve())
        digest = hashlib.sha256(self.source.encode("utf-8")).hexdigest()
        self.path = Path(directory) / (digest + ".json")
        self.dirty = False
        data = load_json(self.path)
        if data.get("source") != self.source:
            data = copy.deepcopy(initial) if initial else {}
        self.data = {"version": 1, "source": self.source,
                     "focus": data.get("focus", "") if isinstance(data.get("focus"), str) else "",
                     "note": data.get("note", "") if isinstance(data.get("note"), str) else ""}
        for key in ("readings", "bookmarks", "pairs", "motifs"):
            values = data.get(key, [])
            self.data[key] = [value for value in values[:1000] if isinstance(value, dict)] if isinstance(values, list) else []

    def save(self):
        save_json(self.path, self.data)
        self.dirty = False

    def reading(self, text, start):
        locations = line_locations(text)
        return next((record for record in self.data["readings"]
                     if valid_reading(record) and resolve_anchor(text, record.get("anchor"), locations) == start), None)

    def set_reading(self, text, start, reading):
        previous = self.reading(text, start)
        if previous:
            self.data["readings"].remove(previous)
        if reading is not None:
            self.data["readings"].append({"anchor": anchor_at(text, start), **reading})


def valid_reading(record):
    if not isinstance(record, dict):
        return False
    words, stresses = record.get("words"), record.get("stresses")
    if (not isinstance(words, list) or not words or any(not isinstance(word, str) for word in words)
            or not isinstance(stresses, list) or len(words) != len(stresses)
            or any(not isinstance(stress, str) or not 1 <= len(stress) <= 20
                   or set(stress) - set("012?") for stress in stresses)):
        return False
    custom, pauses = record.get("custom", [True] * len(words)), record.get("pauses", [])
    return (isinstance(custom, list) and len(custom) == len(words)
            and all(isinstance(value, bool) for value in custom)
            and isinstance(pauses, list) and all(value in ("", "|", "||") for value in pauses))


def apply_reading(line, record):
    """Reject incompatible annotations rather than attaching them to new words."""
    if not valid_reading(record) or record.get("words") != [word.text for word in line.words]:
        return line
    stresses = record.get("stresses")
    custom = record.get("custom", [True] * len(line.words))
    if (not isinstance(stresses, list) or len(stresses) != len(line.words)
            or not isinstance(custom, list) or len(custom) != len(line.words)
            or any(not isinstance(value, bool) for value in custom)
            or any(not isinstance(stress, str) or not 1 <= len(stress) <= 20
                   or set(stress) - set("012?") for stress in stresses)):
        return line
    return replace(line, words=tuple(replace(word, stresses=(stress,), guessed=False) if chosen else word
                                     for word, stress, chosen in zip(line.words, stresses, custom)))


REFERENCE_CARDS = (
    ("Iambic pentameter", "Five lighter–stronger pairs: · ● | · ● | · ● | · ● | · ●",
     "the RAIN | will FALL | and WASH | the DUST | aWAY",
     "Try speaking the example naturally, then exaggerating the beats. Real lines can vary the pattern; stress comes from your reading as well as the words."),
    ("Rhyming couplets", "Two neighboring lines whose endings rhyme.",
     "I leave a lamp beside the door.\nIts little light falls on the floor.",
     "A couplet can complete a thought or carry it onward. Listen for whether the ending gives you a landing, a surprise, or momentum."),
    ("Accentual verse", "Listen for strong beats; the syllables between them can vary.",
     "RAIN on the ROOF\nthe RAIN is on the ROOF",
     "Both can be read with two strong beats, with different numbers of lighter syllables. Choose a beat count and try different amounts of lighter speech between the beats."),
    ("End-stopping and enjambment", "A sentence can pause at the line ending or continue across it.",
     "End-stopped:\nI close the gate. The road is still.\n\nCarried across the break:\nI close the gate and listen for\nthe footsteps on the hill.",
     "Read both without forcing a pause at every line. Notice what the break holds back and which word gets attention."),
    ("Loose rhymes and echoes", "Different degrees of sound connection give you different textures.",
     "light / night — matching end sounds\nlight / time — shared vowel sound\nmoon / moon — a repeated ending",
     "You can name a connection a loose rhyme or leave an ending unpaired. The map records your choice without scoring it."),
)
