"""Local name-to-id lookup cache for the empowerHSA API.

The API is id-keyed (student_id/subject_id) but HomeSchoolingAi's UI/CLI
operate on names. This is just an id lookup cache, not a second source of
truth - content itself only ever lives in the API. Backed by
data/empower_ids.json; falls back to listing the API and matching by name
whenever the cache misses.
"""
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
        return None

    subject_id = match["_id"]
    data["subjects"][key] = subject_id
    _save(data)
    return subject_id
