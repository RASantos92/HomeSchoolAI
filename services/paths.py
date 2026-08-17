"""Canonical filesystem paths for the data/ directory layout.

All generated content lives under data/yearPlan/<student>/... in a fixed set of
shapes (year plan, weekly plans, weekly breakdown, daily subject, progress).
Every module that reads or writes one of these paths should build it here
instead of hand-formatting the string, so the on-disk layout has one definition.

Weeks are always the zero-indexed folder name (0-3) already used on disk and by
the Streamlit UI. Callers are responsible for converting a 1-based "week 1-4"
input into that zero-indexed value before calling these functions.
"""
from pathlib import Path

BREAKDOWN_FILENAME = "breakdown.json"
PROGRESS_FILENAME = "weekly_progress.json"
WEEKLY_QUIZ_FILENAME = "weekly_quiz.json"
WEEKLY_PLANS_FILENAME = "weeklyPlans.json"


def assessments_dir() -> Path:
    return Path("data/assessments")


def assessment_file(number) -> Path:
    return assessments_dir() / f"assessment{number}.json"


def year_plan_dir(name: str) -> Path:
    return Path("data/yearPlan") / name


def year_plan_file(name: str, grade_level, age, subject: str, number) -> Path:
    return year_plan_dir(name) / f"{grade_level}{age}{subject}yearPlan{number}.json"


def weekly_plans_dir(name: str) -> Path:
    return year_plan_dir(name) / "weeklyPlans"


def weekly_plans_file(name: str) -> Path:
    return weekly_plans_dir(name) / WEEKLY_PLANS_FILENAME


def weekly_breakdown_root(name: str) -> Path:
    return year_plan_dir(name) / "weeklyBreakdown"


def weekly_breakdown_dir(name: str, month: str, week) -> Path:
    return weekly_breakdown_root(name) / month / str(week)


def weekly_breakdown_file(name: str, month: str, week) -> Path:
    return weekly_breakdown_dir(name, month, week) / BREAKDOWN_FILENAME


def weekly_quiz_file(name: str, month: str, week) -> Path:
    return weekly_breakdown_dir(name, month, week) / WEEKLY_QUIZ_FILENAME


def daily_subject_dir(name: str, month: str, week, day: str) -> Path:
    return weekly_breakdown_dir(name, month, week) / day


def daily_subject_file(name: str, month: str, week, day: str, subject_name: str) -> Path:
    return daily_subject_dir(name, month, week, day) / f"{subject_name}.json"


def weekly_progress_file(name: str, month: str, week, day: str) -> Path:
    return daily_subject_dir(name, month, week, day) / PROGRESS_FILENAME


def dictionary_file() -> Path:
    return Path("data/dictionary.json")


def empower_ids_file() -> Path:
    return Path("data/empower_ids.json")


def school_year_config_file() -> Path:
    return Path("data/school_year_config.json")


def theme_file() -> Path:
    return Path("data/theme_preference.json")
