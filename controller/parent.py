"""Thin client over the empowerHSA API.

All curriculum generation and storage now happens server-side in empowerHSA
(D:\\empowerHSA) - this class no longer talks to OpenAI or writes local JSON.
It just resolves the student/subject names HomeSchoolingAi's UI and CLI work
with into the ids the API needs (via services/id_cache.py) and calls through
services/empower_client.py. See empowerHSA's dev_guide.md for the exact
request/response contract every method here is built against.

Week numbers are 1-based (1-4) at this class's boundary, matching the API
directly - callers using a 0-indexed week convention (e.g. the Streamlit UI)
convert at their own boundary, not here. Month numbers accept either a
zero-padded string ("08") or an int - int(month) handles both.
"""
from services import id_cache
from services.empower_client import EmpowerHSAClient


class Parent:
    def __init__(self):
        self.client = EmpowerHSAClient()

    def _student_id(self, name: str):
        return id_cache.get_student_id(self.client, name)

    def _subject_id(self, name: str, subject: str):
        return id_cache.get_subject_id(self.client, name, subject)

    def createYearlyLessonPlanForSubject(self, name: str, age, grade_level, subject: str):
        if id_cache.peek_subject_id(name, subject):
            print(f"You already have created a year plan for {name} with the subject {subject}.")
            return None

        student_id = self._student_id(name)
        result = self.client.generate_yearly_breakdown(
            age=int(age),
            grade=int(grade_level),
            subject=subject,
            name=None if student_id else name,
            student_id=student_id,
            subject_id=self._subject_id(name, subject),
        )
        id_cache.set_student_id(name, result["student_id"])
        id_cache.set_subject_id(name, subject, result["subject_id"])
        return result

    def updateWeeklylessonPlanWithNewSubject(self, name: str, subject_name: str, age, grade_level):
        """Adds a subject to a student mid-year. Reuses the same generation
        endpoint as createYearlyLessonPlanForSubject with the student's
        existing id, which merges into their existing months server-side."""
        student_id = self._student_id(name)
        if not student_id:
            print(f"No student named {name} found - create a yearly plan for at least one subject first.")
            return None
        result = self.client.generate_yearly_breakdown(
            age=int(age), grade=int(grade_level), subject=subject_name,
            student_id=student_id, subject_id=self._subject_id(name, subject_name),
        )
        id_cache.set_subject_id(name, subject_name, result["subject_id"])
        return result

    def createWeeklyBreakdown(self, name: str, month, week_number):
        """Generates (or idempotently re-fetches) the weekly topic plan,
        day-by-day breakdown, and end-of-week quiz for one week - the API
        does all three stages behind this one call."""
        student_id = self._student_id(name)
        if not student_id:
            print(f"No student named {name} found - generate a yearly plan first.")
            return None
        return self.client.generate_weekly_breakdown(student_id, int(month), int(week_number))

    def createWeeklyQuiz(self, name: str, month, week_number, age=None, grade=None):
        """The weekly quiz is generated as part of createWeeklyBreakdown now;
        this just re-fetches the week (idempotent re-POST), which includes it."""
        return self.createWeeklyBreakdown(name, month, week_number)

    def createDailyBreakDown(self, name: str, month, week_number, day: str):
        """Ensures the week is broken down, then generates every subject's
        lecture for one day - one generate_lesson call per subject."""
        week_data = self.createWeeklyBreakdown(name, month, week_number)
        if not week_data:
            return None

        day_data = next((d for d in week_data.get("days", []) if d.get("day_name") == day), None)
        if not day_data:
            print(f"No breakdown found for {day} in this week.")
            return None

        student_id = self._student_id(name)
        lessons = []
        for subject_breakdown in day_data.get("subjects", []):
            subject_name = subject_breakdown["subject_name"]
            subject_id = self._subject_id(name, subject_name)
            if not subject_id:
                print(f"No subject_id for '{subject_name}' - skipping")
                continue
            lessons.append(self.client.generate_lesson(student_id, subject_id, int(month), int(week_number), day))
        return lessons

    def generateLesson(self, name: str, subject: str, month, week_number, day: str):
        """Fetch-or-generate one subject's lesson for a day. Safe to call every
        time a lesson is opened in the UI - the API returns the existing
        lesson as-is if one was already generated."""
        student_id = self._student_id(name)
        subject_id = self._subject_id(name, subject)
        if not student_id or not subject_id:
            print(f"No student/subject id found for {name}/{subject} - generate a yearly plan first.")
            return None
        return self.client.generate_lesson(student_id, subject_id, int(month), int(week_number), day)

    def tryGetLesson(self, name: str, subject: str, month, week_number, day: str):
        """Like generateLesson, but never triggers generation - returns None if
        this subject's lesson for the day hasn't been generated yet. Use for
        UI status checks (e.g. sidebar completion coloring) that shouldn't
        cost an OpenAI call just to render."""
        student_id = self._student_id(name)
        subject_id = self._subject_id(name, subject)
        if not student_id or not subject_id:
            return None
        return self.client.try_get_lesson(
            student_id=student_id, subject_id=subject_id,
            month_number=int(month), week_of_the_month=int(week_number), day_name=day,
        )

    def markLessonComplete(self, lesson_id: str):
        return self.client.update_lesson_complete(lesson_id, complete=True)

    def recordProgress(self, name: str, subject_name: str, month, week_number, day: str,
                        quiz_grade, wrong_answers=None, quiz=None):
        student_id = self._student_id(name)
        if not student_id:
            print(f"No student named {name} found.")
            return None
        return self.client.record_progress(
            student_id, subject_name, int(month), int(week_number), day,
            quiz_grade, wrong_answers=wrong_answers, quiz=quiz,
        )

    def assessmentTest(self, name: str, age, assumed_grade,
                        subjects=("Mathematics", "Language Arts", "Science", "Social Studies")):
        student_id = self._student_id(name)
        if not student_id:
            student = self.client.create_or_update_student(name=name, age=int(age))
            student_id = student["_id"]
            id_cache.set_student_id(name, student_id)

        assessment_number = None
        results = []
        for subject in subjects:
            result = self.client.generate_assessment(
                student_id, int(age), int(assumed_grade),
                subject=subject, assessment_number=assessment_number,
            )
            assessment_number = result["assessment_number"]
            results.append(result)
        return results

    def getAssessment(self, name: str, assessment_number):
        student_id = self._student_id(name)
        if not student_id:
            return []
        return self.client.get_assessment(student_id=student_id, assessment_number=int(assessment_number))
