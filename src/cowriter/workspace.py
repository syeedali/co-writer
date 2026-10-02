"""Local, atomic workspace state and recovery copies."""

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def text_digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def atomic_write(path, text, private=False):
    """Replace a file only after its complete contents have reached disk."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".cowriter-", dir=str(path.parent))
    try:
        if not private and path.exists():
            os.fchmod(fd, path.stat().st_mode & 0o777)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load_json(path):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def save_json(path, value):
    atomic_write(path, json.dumps(value, indent=2, ensure_ascii=False), private=True)


class RecoveryStore:
    def __init__(self, directory):
        self.directory = Path(directory)

    def path_for(self, source):
        # Same-named documents in different folders must never collide.
        key = text_digest(str(Path(source).resolve()))
        return self.directory / (key + ".draft.json")

    def write(self, source, text, baseline):
        save_json(self.path_for(source), {
            "source": str(Path(source).resolve()), "text": text,
            "baseline": text_digest(baseline),
            "saved_at": datetime.now(timezone.utc).isoformat(),
        })

    def read(self, source, disk_text):
        record = load_json(self.path_for(source))
        if (record.get("source") == str(Path(source).resolve())
                and isinstance(record.get("text"), str)
                and record["text"] != disk_text):
            record["disk_changed"] = record.get("baseline") != text_digest(disk_text)
            return record
        return None

    def remove(self, source):
        try:
            self.path_for(source).unlink()
        except FileNotFoundError:
            pass

    def sources(self):
        if not self.directory.exists():
            return []
        return [record["source"] for record in
                (load_json(path) for path in self.directory.glob("*.draft.json"))
                if isinstance(record.get("source"), str)]
