"""Thin HTTP client for the empowerHSA API.

Every generation/storage call HomeSchoolingAi used to make locally (OpenAI +
local JSON) now goes through this client instead - see empowerHSA's own
dev_guide.md for the authoritative request/response contract. One method per
endpoint, unwrapping the {"success": bool, "data"|"error": ...} envelope.
"""
import os

import requests
from dotenv import load_dotenv

load_dotenv()


class EmpowerHSAError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.message = message
        self.status = status


class EmpowerHSAClient:
    def __init__(self, base_url=None, api_key=None):
        self.base_url = (base_url or os.getenv("EMPOWER_HSA_BASE_URL", "http://127.0.0.1:8000")).rstrip("/")
        self.api_key = api_key or os.getenv("EMPOWER_HSA_API_KEY")

    def _request(self, method, path, params=None, json_body=None, timeout=120):
        url = f"{self.base_url}{path}"
        headers = {"X-API-Key": self.api_key, "Content-Type": "application/json"}
        response = requests.request(method, url, headers=headers, params=params, json=json_body, timeout=timeout)
        try:
            payload = response.json()
        except ValueError:
            raise EmpowerHSAError(f"Non-JSON response from {url}: {response.text[:200]}", response.status_code)
        if not payload.get("success"):
            raise EmpowerHSAError(payload.get("error", "Unknown error"), response.status_code)
        return payload.get("data")

    # ---- grade ----
    def create_or_update_grade(self, grade=None, grade_id=None, subject_ids=None, subject_names=None):
        body = {}
        if grade_id:
            body["grade_id"] = grade_id
        if grade is not None:
            body["grade"] = grade
        if subject_ids:
            body["subject_ids"] = subject_ids
        if subject_names:
            body["subject_names"] = subject_names
        return self._request("POST", "/api/grade", json_body=body)

    def get_grade(self, grade_id=None):
        return self._request("GET", "/api/grade", params={"grade_id": grade_id} if grade_id else None)

    def delete_grade(self, grade_id):
        return self._request("DELETE", "/api/grade", params={"grade_id": grade_id})

    # ---- student ----
    def create_or_update_student(self, name=None, age=None, grade=None, student_id=None):
        body = {}
        if student_id:
            body["student_id"] = student_id
        if name is not None:
            body["name"] = name
        if age is not None:
            body["age"] = age
        if grade is not None:
            body["grade"] = grade
        return self._request("POST", "/api/student", json_body=body)

    def get_student(self, student_id=None, school_year=None):
        params = {}
        if student_id:
            params["student_id"] = student_id
        if school_year is not None:
            params["school_year"] = school_year
        return self._request("GET", "/api/student", params=params or None)

    def delete_student(self, student_id):
        return self._request("DELETE", "/api/student", params={"student_id": student_id})

    # ---- subject ----
    def create_or_update_subject(self, subject_name=None, subject_id=None, topic_names=None, topic_ids=None):
        body = {}
        if subject_id:
            body["subject_id"] = subject_id
        if subject_name is not None:
            body["subject_name"] = subject_name
        if topic_names:
            body["topic_names"] = topic_names
        if topic_ids:
            body["topic_ids"] = topic_ids
        return self._request("POST", "/api/subject", json_body=body)

    def get_subject(self, subject_id=None, school_year=None):
        params = {}
        if subject_id:
            params["subject_id"] = subject_id
        if school_year is not None:
            params["school_year"] = school_year
        return self._request("GET", "/api/subject", params=params or None)

    def delete_subject(self, subject_id):
        return self._request("DELETE", "/api/subject", params={"subject_id": subject_id})

    # ---- generation pipeline ----
    def generate_yearly_breakdown(self, age, grade, subject, school_year, name=None, student_id=None, subject_id=None):
        body = {"age": age, "grade": grade, "subject": subject, "school_year": school_year}
        if student_id:
            body["student_id"] = student_id
        if name:
            body["name"] = name
        if subject_id:
            body["subject_id"] = subject_id
        return self._request("POST", "/api/yearly/breakdown/subject", json_body=body, timeout=300)

    def generate_weekly_breakdown(self, student_id, month_number, week_of_the_month, school_year):
        # Three sequential generation stages server-side (plan, days, then a
        # 20-question-per-subject quiz across every subject in the week) - can
        # comfortably run past the default timeout for a 6-7 subject week.
        body = {
            "student_id": student_id, "month_number": month_number,
            "week_of_the_month": week_of_the_month, "school_year": school_year,
        }
        return self._request("POST", "/api/weekly/breakdown", json_body=body, timeout=600)

    def get_weekly_breakdown(self, student_id, month_number, week_of_the_month, school_year):
        params = {
            "student_id": student_id, "month_number": month_number,
            "week_of_the_month": week_of_the_month, "school_year": school_year,
        }
        return self._request("GET", "/api/weekly/breakdown", params=params)

    def try_get_weekly_breakdown(self, **kwargs):
        """Like get_weekly_breakdown, but returns None instead of raising on a 404
        (not generated yet) - never triggers generation, unlike generate_weekly_breakdown."""
        try:
            return self.get_weekly_breakdown(**kwargs)
        except EmpowerHSAError as e:
            if e.status == 404:
                return None
            raise

    def delete_weekly_breakdown(self, student_id, month_number, week_of_the_month, school_year):
        """Destructive - wipes one week's plan/day-breakdown/quiz so it can be
        regenerated fresh (e.g. to backfill a subject added afterward). Does not
        delete any Lesson documents - those survive independently."""
        params = {
            "student_id": student_id, "month_number": month_number,
            "week_of_the_month": week_of_the_month, "school_year": school_year,
        }
        return self._request("DELETE", "/api/weekly/breakdown", params=params)

    def generate_lesson(self, student_id, subject_id, month_number, week_of_the_month, day_name, school_year):
        body = {
            "student_id": student_id,
            "subject_id": subject_id,
            "month_number": month_number,
            "week_of_the_month": week_of_the_month,
            "day_name": day_name,
            "school_year": school_year,
        }
        return self._request("POST", "/api/lesson", json_body=body, timeout=240)

    def get_lesson(self, lesson_id=None, student_id=None, subject_id=None,
                    month_number=None, week_of_the_month=None, day_name=None, school_year=None):
        if lesson_id:
            params = {"lesson_id": lesson_id}
        else:
            params = {
                "student_id": student_id,
                "subject_id": subject_id,
                "month_number": month_number,
                "week_of_the_month": week_of_the_month,
                "day_name": day_name,
                "school_year": school_year,
            }
        return self._request("GET", "/api/lesson", params=params)

    def try_get_lesson(self, **kwargs):
        """Like get_lesson, but returns None instead of raising on a 404 (not generated yet)."""
        try:
            return self.get_lesson(**kwargs)
        except EmpowerHSAError as e:
            if e.status == 404:
                return None
            raise

    def update_lesson_complete(self, lesson_id, complete=True):
        return self._request("POST", "/api/lesson", json_body={"lesson_id": lesson_id, "complete": complete})

    def delete_lesson(self, lesson_id):
        return self._request("DELETE", "/api/lesson", params={"lesson_id": lesson_id})

    # ---- progress ----
    def record_progress(self, student_id, subject_name, month_number, week_of_the_month, day_name,
                         quiz_grade, school_year, wrong_answers=None, quiz=None):
        body = {
            "student_id": student_id,
            "subject_name": subject_name,
            "month_number": month_number,
            "week_of_the_month": week_of_the_month,
            "day_name": day_name,
            "quiz_grade": quiz_grade,
            "school_year": school_year,
            "wrong_answers": wrong_answers or [],
            "quiz": quiz or [],
        }
        return self._request("POST", "/api/progress", json_body=body)

    def get_progress(self, student_id, subject_name, month_number, week_of_the_month, day_name, school_year):
        params = {
            "student_id": student_id,
            "subject_name": subject_name,
            "month_number": month_number,
            "week_of_the_month": week_of_the_month,
            "day_name": day_name,
            "school_year": school_year,
        }
        return self._request("GET", "/api/progress", params=params)

    def get_progress_month(self, student_id, month_number, school_year):
        """Every quiz attempt for a student across all subjects/weeks/days in one school month."""
        params = {
            "student_id": student_id,
            "month_number": month_number,
            "school_year": school_year,
        }
        return self._request("GET", "/api/progress", params=params)

    # ---- assessment ----
    def generate_assessment(self, student_id, age, assumed_grade, subject=None, subject_id=None, assessment_number=None):
        body = {"student_id": student_id, "age": age, "assumed_grade": assumed_grade}
        if subject:
            body["subject"] = subject
        if subject_id:
            body["subject_id"] = subject_id
        if assessment_number is not None:
            body["assessment_number"] = assessment_number
        return self._request("POST", "/api/assessment", json_body=body)

    def get_assessment(self, student_id=None, assessment_number=None, subject=None, assessment_id=None):
        if assessment_id:
            params = {"assessment_id": assessment_id}
        else:
            params = {"student_id": student_id, "assessment_number": assessment_number}
            if subject:
                params["subject"] = subject
        return self._request("GET", "/api/assessment", params=params)

    def delete_assessment(self, assessment_id):
        return self._request("DELETE", "/api/assessment", params={"assessment_id": assessment_id})

    # ---- bulk generation ----
    def start_bulk_breakdown(self, student_id: str, weeks: list, school_year: int) -> str:
        """Starts a server-side background job generating weekly breakdowns for
        each (month, week) pair. Returns the job_id to poll with get_bulk_status()."""
        data = self._request(
            "POST", "/api/bulk/weekly-breakdown",
            json_body={"student_id": student_id, "weeks": weeks, "school_year": school_year},
            timeout=30,
        )
        return data["job_id"]

    def get_bulk_status(self, job_id: str) -> dict:
        """Polls a bulk job. Returns {total, completed, errors, done, cancelled}."""
        return self._request(
            "GET", "/api/bulk/weekly-breakdown",
            params={"job_id": job_id},
            timeout=10,
        )

    def cancel_bulk_job(self, job_id: str) -> None:
        self._request("DELETE", "/api/bulk/weekly-breakdown", params={"job_id": job_id}, timeout=10)
