import json

from controller.data_manipulation import DataManipulation


def test_scan_subject_lectures_filters_by_letter_count():
    dm = DataManipulation()
    lecture = "A cat sat on the mat near a spectacular waterfall discussing philosophy"
    result = dm.scan_subject_lectures(lecture, letter_count=8)
    words = {w for group in result.values() for w in group}
    assert words == {"spectacular", "waterfall", "discussing", "philosophy"}
    assert all(len(w) >= 8 for w in words)


def test_flatten_words_by_length_map_dedupes_and_lowercases():
    words_by_len = {5: {"Hello", "hello,"}, 6: {"Python"}}
    flattened = DataManipulation._flatten_words_by_length_map(words_by_len)
    assert flattened == ["hello", "python"]


def test_build_dictionary_creates_file_when_missing(tmp_path, monkeypatch):
    """Regression test: build_dictionary used to be a no-op when json_path didn't exist yet."""
    dm = DataManipulation()
    json_path = tmp_path / "dictionary.json"
    assert not json_path.exists()

    monkeypatch.setattr(DataManipulation, "_fetch_definition", staticmethod(lambda word, timeout=8: ("a small furry animal", "noun")))

    stats = dm.build_dictionary({3: {"cat"}}, json_path=str(json_path), sleep_between=0, overwrite=False)

    assert json_path.exists()
    assert stats == {"added": 1, "updated": 0, "skipped": 0, "total": 1}
    saved = json.loads(json_path.read_text(encoding="utf-8"))
    assert saved["cat"]["definition"] == "a small furry animal"


def test_build_dictionary_skips_existing_definition_unless_overwrite(tmp_path, monkeypatch):
    dm = DataManipulation()
    json_path = tmp_path / "dictionary.json"
    json_path.write_text(json.dumps({"cat": {"definition": "existing definition", "pos": "noun"}}), encoding="utf-8")

    calls = []
    monkeypatch.setattr(
        DataManipulation,
        "_fetch_definition",
        staticmethod(lambda word, timeout=8: calls.append(word) or ("new definition", "noun")),
    )

    stats = dm.build_dictionary({3: {"cat"}}, json_path=str(json_path), sleep_between=0, overwrite=False)

    assert stats == {"added": 0, "updated": 0, "skipped": 1, "total": 1}
    assert calls == []  # never hit the network for a word that already has a definition
    saved = json.loads(json_path.read_text(encoding="utf-8"))
    assert saved["cat"]["definition"] == "existing definition"
