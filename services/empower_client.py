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
    def create_or_update_student(self, name=None, age=None, student_id=None):
        body = {}
        if student_id:
            body["student_id"] = student_id
        if name is not None:
            body["name"] = name
        if age is not None:
            body["age"] = age
        return self._request("POST", "/api/student", json_body=body)

    def get_student(self, student_id=None):
        return self._request("GET", "/api/student", params={"student_id": student_id} if student_id else None)

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

    def get_subject(self, subject_id=None):
        return self._request("GET", "/api/subject", params={"subject_id": subject_id} if subject_id else None)

    def delete_subject(self, subject_id):
        return self._request("DELETE", "/api/subject", params={"subject_id": subject_id})

    # ---- generation pipeline ----
    def generate_yearly_breakdown(self, age, grade, subject, name=None, student_id=None, subject_id=None):
        body = {"age": age, "grade": grade, "subject": subject}
        if student_id:
            body["student_id"] = student_id
        if name:
            body["name"] = name
        if subject_id:
            body["subject_id"] = subject_id
        return self._request("POST", "/api/yearly/breakdown/subject", json_body=body, timeout=300)

    def generate_weekly_breakdown(self, student_id, month_number, week_of_the_month):
        # Three sequential generation stages server-side (plan, days, then a
        # 20-question-per-subject quiz across every subject in the week) - can
        # comfortably run past the default timeout for a 6-7 subject week.
        body = {"student_id": student_id, "month_number": month_number, "week_of_the_month": week_of_the_month}
        return self._request("POST", "/api/weekly/breakdown", json_body=body, timeout=600)

    def generate_lesson(self, student_id, subject_id, month_number, week_of_the_month, day_name):
        body = {
            "student_id": student_id,
            "subject_id": subject_id,
            "month_number": month_number,
            "week_of_the_month": week_of_the_month,
            "day_name": day_name,
        }
        return self._request("POST", "/api/lesson", json_body=body, timeout=240)

    def get_lesson(self, lesson_id=None, student_id=None, subject_id=None,
                    month_number=None, week_of_the_month=None, day_name=None):
        if lesson_id:
            params = {"lesson_id": lesson_id}
        else:
            params = {
                "student_id": student_id,
                "subject_id": subject_id,
                "month_number": month_number,
                "week_of_the_month": week_of_the_month,
                "day_name": day_name,
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
                         quiz_grade, wrong_answers=None, quiz=None):
        body = {
            "student_id": student_id,
            "subject_name": subject_name,
            "month_number": month_number,
            "week_of_the_month": week_of_the_month,
            "day_name": day_name,
            "quiz_grade": quiz_grade,
            "wrong_answers": wrong_answers or [],
            "quiz": quiz or [],
        }
        return self._request("POST", "/api/progress", json_body=body)

    def get_progress(self, student_id, subject_name, month_number, week_of_the_month, day_name):
        params = {
            "student_id": student_id,
            "subject_name": subject_name,
            "month_number": month_number,
            "week_of_the_month": week_of_the_month,
            "day_name": day_name,
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
