"""Local article and evidence transfers; no remote publishing or shell commands."""
import json
import os
import shutil
import subprocess
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from .workspace import atomic_write, load_json, save_json, text_digest

MAX_BYTES = 8 * 1024 * 1024


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def review_record(context, assessment, report, claim_sources, coverage=()):
    return {
        "review_id": str(uuid.uuid4()), "generated_at": utc_now(),
        "model": context["model"], "scope": context["scope"],
        "reviewed_document": context["document"], "reviewed_passage": context["passage"],
        "assessment": assessment, "report": report,
        "claims": [{**asdict(claim), "coverage": list(coverage[i]) if i < len(coverage) else [],
                    "sources": [asdict(source) for source in sources]}
                   for i, (claim, sources) in enumerate(claim_sources)],
    }


def record_path(directory, source):
    return Path(directory) / (text_digest(str(Path(source).resolve())) + ".json")


def load_reviews(directory, source):
    record = load_json(record_path(directory, source))
    if record.get("source_document") != str(Path(source).resolve()):
        return []
    audits = record.get("audits", [])
    return audits[-10:] if isinstance(audits, list) else []


def save_review(directory, source, review):
    audits = load_reviews(directory, source)
    audits.append(review)
    save_json(record_path(directory, source), {
        "source_document": str(Path(source).resolve()), "audits": audits[-10:],
    })


def copy_reviews(directory, source, destination):
    if Path(source).resolve() != Path(destination).resolve():
        audits = load_reviews(directory, source)
        if audits:
            merged = load_reviews(directory, destination)
            known = {review.get("review_id") for review in merged}
            merged.extend(review for review in audits if review.get("review_id") not in known)
            save_json(record_path(directory, destination), {
                "source_document": str(Path(destination).resolve()), "audits": merged[-10:],
            })


def article_package(title, text, source, audits=()):
    if not text.strip():
        raise ValueError("Write an article before sending it to Open Pressroom.")
    if len(text.encode("utf-8")) > 1_000_000 or len(title.encode("utf-8")) > 256:
        raise ValueError("The article is too large for this transfer.")
    package = {"format": "cowriter.article", "version": 1, "title": title or "Untitled article",
               "source_document": str(Path(source).resolve()), "exported_at": utc_now(),
               "markdown": text, "audits": list(audits)[-10:]}
    def validate_strings(value):
        if isinstance(value, str):
            if any(not (ord(c) in (9, 10, 13) or 0x20 <= ord(c) <= 0xD7FF
                        or 0xE000 <= ord(c) <= 0xFFFD or 0x10000 <= ord(c) <= 0x10FFFF) for c in value):
                raise ValueError("The article or research contains unsupported control characters.")
        elif isinstance(value, dict):
            for item in value.values():
                validate_strings(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                validate_strings(item)
    validate_strings(package)
    encoded = json.dumps(package, ensure_ascii=False, indent=2)
    if len(encoded.encode("utf-8")) > MAX_BYTES:
        raise ValueError("The article and research exceed the 8 MiB transfer limit.")
    return encoded


def write_package(directory, title, text, source, audits=()):
    encoded = article_package(title, text, source, audits)
    path = Path(directory) / (str(uuid.uuid4()) + ".cowriter-article.json")
    atomic_write(path, encoded, private=True)
    return path


def executable():
    configured = os.environ.get("OPEN_PRESSROOM_EXECUTABLE")
    candidates = ([Path(configured).expanduser()] if configured else [])
    installed = shutil.which("open-pressroom-native")
    if installed:
        candidates.append(Path(installed))
    # Editable sibling checkouts, as used during the native rebuild.
    candidates.append(Path(__file__).resolve().parents[3] / "openpressroom/native/target/debug/open-pressroom-native")
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate.resolve())
    raise RuntimeError("Open Pressroom was not found. Build its native app or set OPEN_PRESSROOM_EXECUTABLE to its executable. The saved article package can also be imported manually.")


def launch(path):
    return subprocess.Popen([executable(), "--import-cowriter", str(Path(path).resolve())],
                            start_new_session=True, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)


def attach_report(directory, source, path):
    """User-selected legacy report: preserve it without inventing review context."""
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("The evidence report exceeds 8 MiB.")
    report = raw.decode("utf-8")
    if not report.lstrip().startswith("# Co-Writer Evidence Audit"):
        raise ValueError("Choose a Co-Writer Evidence Audit Markdown report.")
    generated = next((line.removeprefix("Generated: ").strip() for line in report.splitlines()
                      if line.startswith("Generated: ")), "Original date not recorded")
    review = {"review_id": str(uuid.uuid4()), "generated_at": generated, "model": "Not recorded",
              "scope": "Manually attached report; reviewed passage and draft not recorded",
              "reviewed_document": "", "reviewed_passage": "", "assessment": "",
              "report": report, "claims": []}
    save_review(directory, source, review)
    return review
