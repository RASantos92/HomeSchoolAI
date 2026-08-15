from pathlib import Path

from services import paths


def test_assessment_file():
    assert paths.assessment_file(7) == Path("data/assessments/assessment7.json")


def test_year_plan_file():
    assert paths.year_plan_file("Hayden", 8, 15, "Algebra", 2) == Path("data/yearPlan/Hayden/815AlgebrayearPlan2.json")


def test_weekly_plans_file():
    assert paths.weekly_plans_file("Hayden") == Path("data/yearPlan/Hayden/weeklyPlans/weeklyPlans.json")


def test_weekly_breakdown_dir_is_zero_indexed_week():
    assert paths.weekly_breakdown_dir("Hayden", "08", 0) == Path("data/yearPlan/Hayden/weeklyBreakdown/08/0")


def test_weekly_breakdown_file():
    assert paths.weekly_breakdown_file("Hayden", "08", 0) == Path("data/yearPlan/Hayden/weeklyBreakdown/08/0/breakdown.json")


def test_weekly_quiz_file():
    assert paths.weekly_quiz_file("Hayden", "08", 0) == Path("data/yearPlan/Hayden/weeklyBreakdown/08/0/weekly_quiz.json")


def test_daily_subject_dir():
    assert paths.daily_subject_dir("Hayden", "08", 0, "Monday") == Path("data/yearPlan/Hayden/weeklyBreakdown/08/0/Monday")


def test_daily_subject_file():
    assert paths.daily_subject_file("Hayden", "08", 0, "Monday", "Algebra") == Path(
        "data/yearPlan/Hayden/weeklyBreakdown/08/0/Monday/Algebra.json"
    )


def test_weekly_progress_file():
    assert paths.weekly_progress_file("Hayden", "08", 0, "Monday") == Path(
        "data/yearPlan/Hayden/weeklyBreakdown/08/0/Monday/weekly_progress.json"
    )


def test_dictionary_file():
    assert paths.dictionary_file() == Path("data/dictionary.json")


def test_casing_is_consistent_across_related_builders():
    # Regression guard: weekly_breakdown_dir/file/quiz/daily_subject builders must all
    # share the same on-disk "weeklyBreakdown" root - this is exactly the class of
    # lowercase/camelCase mismatch bug that used to exist in controller/parent.py.
    root = paths.weekly_breakdown_root("Hayden")
    assert str(root).endswith("weeklyBreakdown")
    assert paths.weekly_breakdown_dir("Hayden", "08", 0).parts[:len(root.parts)] == root.parts
