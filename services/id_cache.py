"""Local name-to-id lookup cache for the empowerHSA API.

The API is id-keyed (student_id/subject_id) but HomeSchoolingAi's UI/CLI
operate on names. This is just an id lookup cache, not a second source of
truth - content itself only ever lives in the API. Backed by
data/empower_ids.json; falls back to listing the API and matching by name
whenever the cache misses.
"""
import datetime
import json

from services import paths


def _load():
    path = paths.empower_ids_file()
    if not path.exists():
        return {"students": {}, "subjects": {}}
    with open(path, "r") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            data = {}
    data.setdefault("students", {})
    data.setdefault("subjects", {})
    return data


def _save(data):
    path = paths.empower_ids_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=4)


def _subject_key(student_name, subject_name):
    return f"{student_name}:{subject_name}"


def peek_student_id(student_name):
    """Cache-only lookup - no API fallback. Use for guards where a false
    positive from another student's same-named subject would be wrong."""
    return _load()["students"].get(student_name)


def peek_subject_id(student_name, subject_name):
    return _load()["subjects"].get(_subject_key(student_name, subject_name))


def set_student_id(student_name, student_id):
    data = _load()
    data["students"][student_name] = student_id
    _save(data)


def get_student_id(client, student_name):
    data = _load()
    cached = data["students"].get(student_name)
    if cached:
        return cached

    students = client.get_student() or []
    match = next((s for s in students if (s.get("name") or "").lower() == student_name.lower()), None)
    if not match:
        return None

    student_id = match["_id"]
    data["students"][student_name] = student_id
    _save(data)
    return student_id


def set_subject_id(student_name, subject_name, subject_id):
    data = _load()
    data["subjects"][_subject_key(student_name, subject_name)] = subject_id
    _save(data)


def get_student_subjects(student_name: str) -> dict:
    """Returns {subject_name: subject_id} for subjects cached for this student."""
    data = _load()
    prefix = f"{student_name}:"
    return {
        key[len(prefix):]: val
        for key, val in data["subjects"].items()
        if key.startswith(prefix)
    }


def get_subject_grade(student_name: str, subject_name: str) -> int | None:
    data = _load()
    return data.get("subject_grades", {}).get(_subject_key(student_name, subject_name))


def set_subject_grade(student_name: str, subject_name: str, grade: int) -> None:
    data = _load()
    data.setdefault("subject_grades", {})[_subject_key(student_name, subject_name)] = int(grade)
    _save(data)


def _bulk_key(student_name, school_year):
    return f"{student_name}:{school_year}"


def get_bulk_generation_status(student_name: str, school_year: int) -> dict | None:
    """Returns the last-recorded bulk-generation run for this (student, school_year),
    or None if bulk generation has never completed for it. Just a local marker for
    the Parent Portal UI - not a substitute for checking actual server content."""
    data = _load()
    return data.get("bulk_generation", {}).get(_bulk_key(student_name, school_year))


def set_bulk_generation_status(
    student_name: str, school_year: int, completed: int, total: int, errors: int,
    failed_weeks: list | None = None,
) -> None:
    data = _load()
    data.setdefault("bulk_generation", {})[_bulk_key(student_name, school_year)] = {
        "completed_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "completed": completed,
        "total": total,
        "errors": errors,
        "failed_weeks": failed_weeks or [],
    }
    _save(data)


def remove_subject(student_name: str, subject_name: str) -> None:
    """Removes a subject from the local cache for this student (API data unchanged)."""
    data = _load()
    _key = _subject_key(student_name, subject_name)
    data["subjects"].pop(_key, None)
    data.get("subject_grades", {}).pop(_key, None)
    _save(data)


def get_subject_id(client, student_name, subject_name):
    data = _load()
    key = _subject_key(student_name, subject_name)
    cached = data["subjects"].get(key)
    if cached:
        return cached

    subjects = client.get_subject() or []
    # empowerHSA's SubjectDb normalizes names via str.capitalize() server-side
    # (e.g. "Computer Science" -> "Computer science"), so match case-insensitively
    # rather than assuming the API echoes back the exact casing given to it.
    match = next((s for s in subjects if (s.get("name") or "").lower() == subject_name.lower()), None)

    if not match:
        # AI-generated daily/weekly breakdowns sometimes shorten a subject's name
        # instead of echoing it back verbatim (e.g. "The Evolution of Faith" ->
        # "Faith", "Social Studies / Economics" -> "Economics"). Fall back to a
        # substring match against this student's OWN already-known subjects (not
        # the global list, to avoid matching some other student's unrelated
        # subject of a similar name) before giving up. Deliberately NOT cached
        # under this shortened name - that would add a second "subject" entry
        # pointing at the same id, duplicating rows in the Curriculum tab.
        needle = subject_name.lower().strip()
        if not needle:
            return None
        for known_name, known_id in get_student_subjects(student_name).items():
            hay = known_name.lower().strip()
            if needle in hay or hay in needle:
                return known_id
        return None

    subject_id = match["_id"]
    data["subjects"][key] = subject_id
    _save(data)
    return subject_id


def get_canonical_subject_name(client, student_name: str, subject_name: str) -> str:
    """Maps a possibly-shortened AI-generated subject name (as it appears in a
    daily/weekly breakdown, e.g. "Faith") back to the real subject name on file
    (e.g. "The Evolution of Faith"), using the same resolution get_subject_id
    uses. Falls back to the input unchanged if it can't be resolved to any of
    this student's known subjects (e.g. a fully hallucinated subject name) -
    callers should still be able to display *something* in that case."""
    subject_id = get_subject_id(client, student_name, subject_name)
    if not subject_id:
        return subject_name
    for known_name, known_id in get_student_subjects(student_name).items():
        if known_id == subject_id:
            return known_name
    return subject_name
