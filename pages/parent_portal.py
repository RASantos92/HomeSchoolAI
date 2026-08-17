"""Parent portal — password-gated admin panel for managing students,
curriculum generation, assessments, and data in empowerHSA."""

import datetime
import re
from collections import defaultdict
from statistics import mean

import streamlit as st
from streamlit_calendar import calendar as st_calendar

from controller.parent import Parent
from services import id_cache, school_year as sy
from services.empower_client import EmpowerHSAClient, EmpowerHSAError

_PASSWORD = "Mrafoe@143"
_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

st.set_page_config(page_title="Parent Portal", layout="wide")
st.title("Parent Portal")

# ── Auth gate ──────────────────────────────────────────────────────────────
if not st.session_state.get("parent_logged_in"):
    with st.form("login"):
        pwd = st.text_input("Password", type="password")
        if st.form_submit_button("Log in"):
            if pwd == _PASSWORD:
                st.session_state["parent_logged_in"] = True
                st.rerun()
            else:
                st.error("Incorrect password.")
    st.stop()

if st.button("Log out", key="logout"):
    st.session_state.pop("parent_logged_in", None)
    st.rerun()

# ── Vacation day state — initialized once per browser session from disk ────
if "vac_initialized" not in st.session_state:
    _cfg = sy.load_config()
    st.session_state["vacation_days"] = list(_cfg.get("vacation_days", []))
    st.session_state["vac_initialized"] = True

# ── Shared clients (created per render; EmpowerHSAClient is stateless) ────
_client = EmpowerHSAClient()
_pc = Parent()


def _all_students():
    try:
        return _client.get_student() or []
    except EmpowerHSAError as e:
        st.error(f"Could not load students: {e}")
        return []


def _all_subjects():
    try:
        return _client.get_subject() or []
    except EmpowerHSAError as e:
        st.error(f"Could not load subjects: {e}")
        return []


def _all_grades():
    try:
        return _client.get_grade() or []
    except EmpowerHSAError as e:
        st.error(f"Could not load grades: {e}")
        return []


def _resolve_student_grade_number(client, student_obj):
    """Student.grade is a Link[Grade] server-side, so the list/detail response
    carries a grade reference (or None), not the grade number directly -
    resolve it to the int the edit form should show."""
    g = student_obj.get("grade")
    if g is None:
        return None
    if isinstance(g, int):
        return g
    if isinstance(g, dict):
        grade_id = g.get("id") or g.get("_id")
        if grade_id:
            try:
                grade_doc = client.get_grade(grade_id=grade_id)
                if grade_doc:
                    return grade_doc.get("grade")
            except EmpowerHSAError:
                return None
    return None


@st.dialog("Year Plan")
def _show_year_plan(subject_name, subject_id, school_year):
    """Shows the topics actually generated for a subject's yearly breakdown -
    i.e. what the 'Year Plan' status on the Curriculum tab is referencing.
    Scoped to one school year - a topic generated under a different year
    doesn't count here, even if the subject itself spans multiple years."""
    try:
        data = _client.get_subject(subject_id=subject_id, school_year=school_year)
    except EmpowerHSAError as e:
        st.error(str(e))
        return
    topics = (data or {}).get("topics", [])
    _sy_label = f"{school_year}-{str(school_year + 1)[2:]}"
    st.caption(f"**{subject_name}** — {len(topics)} topic(s) generated for {_sy_label}")
    if not topics:
        st.info("No topics generated yet — use Regen or Add Subject to generate this year's plan.")
    for t in topics:
        st.markdown(f"- **{t.get('name', '—')}**")
        for sub in t.get("sub_topics") or []:
            sub_name = sub.get("name") if isinstance(sub, dict) else sub
            if sub_name:
                st.markdown(f"  - {sub_name}")


@st.dialog("Weekly Breakdown")
def _show_weekly_breakdown(week_data, month_number, week_number):
    """Shows the topic plan, day-by-day breakdown, and quiz size for a week
    that's already been generated - the read-only companion to Generate
    Weekly Breakdown, fetched via the never-generates GET endpoint."""
    st.caption(f"Month {month_number}, Week {week_number}")
    if week_data.get("intro"):
        st.markdown(f"**Intro:** {week_data['intro']}")
    if week_data.get("summary"):
        st.markdown(f"**Summary:** {week_data['summary']}")
    _topics = [t.get("value") for t in (week_data.get("topics") or [])]
    if _topics:
        st.markdown("**Topics:** " + ", ".join(_topics))
    st.markdown(f"**Quiz questions:** {len(week_data.get('quiz') or [])}")
    st.divider()
    for _d in week_data.get("days", []):
        with st.expander(_d.get("day_name", "—")):
            for _s in _d.get("subjects", []):
                st.markdown(f"**{_s.get('subject_name', '—')}** — {_s.get('subject_topic', '—')}")
                st.caption(_s.get("subject_daily_intro", ""))


@st.fragment(run_every=5)
def _bulk_status_panel():
    """Auto-polling fragment — re-executes every 5 s while a bulk job is running."""
    _job_id = st.session_state.get("_bulk_job_id")
    if not _job_id:
        return
    _c = EmpowerHSAClient()
    try:
        _status = _c.get_bulk_status(_job_id)
    except EmpowerHSAError as _ex:
        if _ex.status == 404:
            st.warning(
                "Bulk job not found — the empowerHSA server may have restarted. "
                "You can start a new bulk generation."
            )
            if st.button("Clear lost job", key="_bulk_lost"):
                st.session_state.pop("_bulk_job_id", None)
                st.rerun()
            return
        st.error(str(_ex))
        return

    _done = _status.get("done", False)
    _total = _status.get("total", 1)
    _completed = _status.get("completed", 0)
    _errors = _status.get("errors", [])
    _cancelled = _status.get("cancelled", False)

    st.progress(min(_completed / _total, 1.0))

    if _done or _cancelled:
        if _cancelled and not _done:
            st.warning(f"Cancelled after {_completed}/{_total} weeks.")
        elif _errors:
            st.error(f"Finished with {len(_errors)} error(s):")
            for _e in _errors:
                st.caption(f"• {_e}")
        else:
            st.success(f"All {_completed} school weeks generated successfully!")
        if _done:
            _bulk_student = st.session_state.get("_bulk_job_student")
            _bulk_year = st.session_state.get("_bulk_job_school_year")
            if _bulk_student and _bulk_year:
                # bulk_controller.py logs each failure as "Month {n} Week {n}: <reason>" -
                # pull the (month, week) back out so a failed week can be retried directly
                # instead of the user re-typing coordinates from a dismissible error message.
                _failed_weeks = [
                    [int(_m), int(_w)]
                    for _m, _w in re.findall(r"Month (\d+) Week (\d+):", " ".join(_errors))
                ]
                id_cache.set_bulk_generation_status(
                    _bulk_student, _bulk_year, _completed, _total, len(_errors), _failed_weeks
                )
        if st.button("Dismiss", key="_bulk_dismiss"):
            st.session_state.pop("_bulk_job_id", None)
            st.rerun()
    else:
        st.caption(f"Generating… {_completed} / {_total} weeks done")
        if _errors:
            with st.expander(f"{len(_errors)} error(s) so far"):
                for _e in _errors:
                    st.caption(f"• {_e}")
        if st.button("Cancel", key="_bulk_cancel"):
            try:
                _c.cancel_bulk_job(_job_id)
            except Exception:
                pass
            st.session_state.pop("_bulk_job_id", None)
            st.rerun()


# ── Main tabs ─────────────────────────────────────────────────────────────
tab_students, tab_curriculum, tab_assessments, tab_manage, tab_school_year, tab_help = st.tabs(
    ["Students", "Curriculum", "Assessments", "Manage", "School Year", "Help"]
)

# ═══════════════════════════════════════════════════════════════════════════
# STUDENTS
# ═══════════════════════════════════════════════════════════════════════════
with tab_students:
    st.subheader("Add Student")
    with st.form("add_student"):
        c1, c2 = st.columns(2)
        new_name = c1.text_input("Name")
        new_age = c2.number_input("Age", min_value=4, max_value=18, value=10)
        if st.form_submit_button("Add"):
            name = new_name.strip()
            if not name:
                st.warning("Please enter a name.")
            else:
                try:
                    result = _client.create_or_update_student(name=name, age=int(new_age))
                    id_cache.set_student_id(name, result["_id"])
                    st.success(f"Student **{name}** added.")
                    st.rerun()
                except EmpowerHSAError as e:
                    st.error(str(e))

    st.divider()
    st.subheader("All Students")
    students = _all_students()
    if not students:
        st.info("No students found.")
    else:
        for s in students:
            c1, c2, c3, c4 = st.columns([3, 2, 1, 1])
            c1.write(f"**{s.get('name', '—')}**")
            c2.write(f"Age {s.get('age', '?')}")
            _edit_key = f"_edit_stu_{s['_id']}"
            if c3.button("Edit", key=f"edit_stu_{s['_id']}"):
                st.session_state[_edit_key] = not st.session_state.get(_edit_key, False)
                st.rerun()
            if c4.button("Delete", key=f"del_stu_{s['_id']}"):
                try:
                    _client.delete_student(s["_id"])
                    st.success("Student deleted.")
                    st.rerun()
                except EmpowerHSAError as e:
                    st.error(str(e))

            if st.session_state.get(_edit_key):
                _default_grade_num = _resolve_student_grade_number(_client, s) or 5
                with st.form(f"edit_student_{s['_id']}"):
                    ec1, ec2, ec3 = st.columns(3)
                    e_name = ec1.text_input("Name", value=s.get("name", ""))
                    e_age = ec2.number_input(
                        "Age", min_value=4, max_value=18, value=int(s.get("age") or 10)
                    )
                    e_grade = ec3.number_input(
                        "Grade", min_value=1, max_value=12, value=int(_default_grade_num)
                    )
                    if st.form_submit_button("Save Changes"):
                        new_name = e_name.strip()
                        if not new_name:
                            st.warning("Name can't be empty.")
                        else:
                            try:
                                _client.create_or_update_student(
                                    name=new_name, age=int(e_age), grade=int(e_grade),
                                    student_id=s["_id"],
                                )
                                if new_name != s.get("name"):
                                    id_cache.set_student_id(new_name, s["_id"])
                                st.session_state.pop(_edit_key, None)
                                st.success(f"**{new_name}** updated.")
                                st.rerun()
                            except EmpowerHSAError as ex:
                                st.error(str(ex))

# ═══════════════════════════════════════════════════════════════════════════
# CURRICULUM
# ═══════════════════════════════════════════════════════════════════════════
with tab_curriculum:
    students = _all_students()
    names = [s["name"] for s in students]

    if not names:
        st.info("Add a student in the **Students** tab first.")
    else:
        selected = st.selectbox("Student", names, key="curr_sel")
        stu_obj = next((s for s in students if s["name"] == selected), {})
        default_age = int(stu_obj.get("age", 10))

        # ── Subject management panel ──────────────────────────────────────
        _existing_subjects = id_cache.get_student_subjects(selected)
        _stu_id = stu_obj.get("_id", "")
        _curr_school_year = sy.load_config().get("school_year_start")
        _default_subject_grade = _resolve_student_grade_number(_client, stu_obj) or 5
        _month_count = None
        _stu_detail = None
        if _stu_id:
            try:
                _stu_detail = _client.get_student(student_id=_stu_id, school_year=_curr_school_year)
                _month_count = (_stu_detail or {}).get("year_count")
            except EmpowerHSAError:
                _month_count = None
        if _month_count is None:
            _month_count = len(stu_obj.get("year", []))  # server didn't return year_count yet

        # Scope the subject list to subjects with actual content in the CURRENT
        # school year - id_cache.get_student_subjects() is per-student, not
        # per-year, so without this a subject from a past school year (or one
        # whose yearly plan hasn't been regenerated yet this year) would show
        # up here identically to one that's actually active. Falls back to the
        # unfiltered (all-time) list if the server hasn't started returning
        # 'subjects_this_year' yet.
        _subjects_this_year = (_stu_detail or {}).get("subjects_this_year")
        if _subjects_this_year is not None:
            _year_names_lower = {n.lower() for n in _subjects_this_year}
            _existing_subjects = {
                _n: _sid for _n, _sid in _existing_subjects.items()
                if _n.lower() in _year_names_lower
            }

        st.subheader(f"{selected}'s Subjects")

        if not _existing_subjects:
            st.info("No subjects yet — add one below.")
        else:
            st.caption(
                f"This student has calendar content in {_month_count}/10 school months this year "
                "(student-wide — see each subject's own Year Plan status below, not this number)."
            )
            # Per-subject topic counts, so the Year Plan column reflects each subject
            # individually instead of the shared student-level month count above.
            _subject_topic_counts = {}
            for _sn, _sid_lookup in _existing_subjects.items():
                try:
                    _sdoc = _client.get_subject(subject_id=_sid_lookup, school_year=_curr_school_year)
                    _subject_topic_counts[_sn] = len((_sdoc or {}).get("topics", []))
                except EmpowerHSAError:
                    _subject_topic_counts[_sn] = None

            # Header row
            _hc = st.columns([3, 1, 2, 2, 1, 1])
            _hc[0].markdown("**Subject**")
            _hc[1].markdown("**Grade**")
            _hc[2].markdown("**Year Plan**")
            _hc[3].markdown("**Breakdowns**")
            st.divider()

            # The per-subject "Check" button below tests today's actual school day
            # (not a fixed month/week) so it reflects whatever's really been generated.
            _chk_smart = sy.get_smart_day(sy.load_config())
            _chk_sm, _chk_sw, _chk_sd = _chk_smart if _chk_smart else (1, 1, "Monday")
            _chk_cal_month = sy.school_month_to_calendar_month(_chk_sm)

            for _sname in sorted(_existing_subjects.keys()):
                _sid = _existing_subjects[_sname]
                _chk_key = f"_bk_{selected}_{_sname}"
                _grade_changed_key = f"_grade_changed_{_sname}"
                _regen_open_key = f"_regen_open_{_sname}"

                _cached_grade = id_cache.get_subject_grade(selected, _sname)
                _grade_changed = st.session_state.get(_grade_changed_key, False)

                _row = st.columns([3, 1, 2, 2, 1, 1])

                # Subject name — flag if grade was bumped but not yet regenerated
                _name_label = f"**{_sname}**"
                if _grade_changed:
                    _name_label += " ⚠ regen needed"
                _row[0].markdown(_name_label)

                # Grade column: type a grade level directly (target grade for content generation)
                _new_grade_val = int(_row[1].number_input(
                    "Grade", min_value=1, max_value=12, value=_cached_grade or _default_subject_grade,
                    key=f"grade_{_sname}", label_visibility="collapsed",
                    help="Target grade level for this subject (then Regen to apply)",
                ))
                if _new_grade_val != (_cached_grade or _default_subject_grade):
                    id_cache.set_subject_grade(selected, _sname, _new_grade_val)
                    st.session_state[_grade_changed_key] = True
                    st.session_state.pop(_chk_key, None)
                    st.rerun()

                # Year Plan column: click to see the topics actually generated for
                # THIS subject specifically (not the student-wide month count above).
                _topic_count = _subject_topic_counts.get(_sname)
                if _row[2].button(
                    f"✓ {_topic_count} topics" if _topic_count else "Not started",
                    key=f"yp_{_sname}",
                    help="View the topics generated for this subject",
                ):
                    _show_year_plan(_sname, _sid, _curr_school_year)

                # Breakdown spot-check
                _chk_status = st.session_state.get(_chk_key, "—")
                _row[3].caption(_chk_status)
                if _row[3].button(
                    "Check", key=f"chk_{_sname}",
                    help=f"Test Month {_chk_sm} Week {_chk_sw} {_chk_sd} (today's school day)",
                ):
                    try:
                        _lesson = _client.try_get_lesson(
                            student_id=_stu_id,
                            subject_id=_sid,
                            month_number=_chk_cal_month,
                            week_of_the_month=_chk_sw,
                            day_name=_chk_sd,
                            school_year=sy.load_config().get("school_year_start"),
                        )
                        st.session_state[_chk_key] = "✓ Lessons exist" if _lesson else "Not generated"
                    except Exception:
                        st.session_state[_chk_key] = "Error checking"
                    st.rerun()

                # Regenerate button — opens inline form
                if _row[4].button("Regen", key=f"regen_btn_{_sname}", help="Regenerate yearly plan"):
                    st.session_state[_regen_open_key] = not st.session_state.get(_regen_open_key, False)
                    st.rerun()

                # Remove button
                if _row[5].button("✕", key=f"rm_{_sname}", help="Remove from local list"):
                    id_cache.remove_subject(selected, _sname)
                    st.session_state.pop(_chk_key, None)
                    st.session_state.pop(_grade_changed_key, None)
                    st.rerun()

                # Inline regenerate form (toggled)
                if st.session_state.get(_regen_open_key):
                    _default_grade = id_cache.get_subject_grade(selected, _sname) or _default_subject_grade
                    with st.form(f"regen_form_{_sname}"):
                        _fc1, _fc2 = st.columns(2)
                        _r_age = _fc1.number_input(
                            "Age", min_value=4, max_value=18, value=default_age, key=f"ra_{_sname}"
                        )
                        _r_grade = _fc2.number_input(
                            "Grade", min_value=1, max_value=12, value=_default_grade, key=f"rg_{_sname}"
                        )
                        if st.form_submit_button(f"Regenerate {_sname} for Grade {_default_grade}"):
                            with st.spinner(f"Regenerating {_sname} grade {int(_r_grade)} — may take up to 5 minutes…"):
                                try:
                                    _pc.createYearlyLessonPlanForSubject(
                                        selected, int(_r_age), int(_r_grade), _sname
                                    )
                                    id_cache.set_subject_grade(selected, _sname, int(_r_grade))
                                    st.session_state.pop(_regen_open_key, None)
                                    st.session_state.pop(_grade_changed_key, None)
                                    st.session_state.pop(_chk_key, None)
                                    st.success(f"**{_sname}** grade {int(_r_grade)} yearly plan generated!")
                                    st.rerun()
                                except Exception as _e:
                                    st.error(str(_e))

        st.divider()

        # ── Add a new subject ─────────────────────────────────────────────
        with st.expander("Add Subject", expanded=not bool(_existing_subjects)):
            st.caption(
                "Generates a full 10-month topic outline. "
                "Safe to re-run — the server merges rather than overwrites."
            )
            with st.form("yearly"):
                c1, c2, c3 = st.columns(3)
                yr_subject = c1.text_input("Subject name")
                yr_age = c2.number_input("Age", min_value=4, max_value=18, value=default_age, key="yr_age")
                yr_grade = c3.number_input(
                    "Grade level", min_value=1, max_value=12, value=_default_subject_grade, key="yr_grade"
                )
                if st.form_submit_button("Generate Yearly Plan"):
                    subj = yr_subject.strip()
                    if not subj:
                        st.warning("Enter a subject name.")
                    else:
                        with st.spinner("Generating — this may take up to 5 minutes…"):
                            try:
                                _pc.createYearlyLessonPlanForSubject(selected, int(yr_age), int(yr_grade), subj)
                                id_cache.set_subject_grade(selected, subj, int(yr_grade))
                                st.success(f"Grade {int(yr_grade)} yearly plan for **{subj}** created!")
                                st.rerun()
                            except Exception as e:
                                st.error(str(e))

        # ── Weekly breakdown ──────────────────────────────────────────────
        with st.expander("Weekly Breakdown"):
            st.caption(
                "Generates the topic plan, day-by-day breakdown, and end-of-week quiz "
                "for one week across all of the student's subjects. Idempotent — safe to re-run."
            )
            _cfg = sy.load_config()
            _subjects = id_cache.get_student_subjects(selected)
            _smart_m, _smart_w = sy.get_smart_week(_cfg)

            # Status for whichever month/week is currently selected in the form below
            # (falls back to the smart default before the widgets first render).
            _wk_check_m = int(st.session_state.get("wk_m", _smart_m))
            _wk_check_w = int(st.session_state.get("wk_w", _smart_w))
            _wk_data = _pc.tryGetWeeklyBreakdown(
                selected, sy.school_month_to_calendar_month(_wk_check_m), _wk_check_w
            )
            if _wk_data:
                st.success(f"✓ Month {_wk_check_m} Week {_wk_check_w} has already been generated.")
                if st.button("View Weekly Breakdown", key="view_wk_bd"):
                    _show_weekly_breakdown(_wk_data, _wk_check_m, _wk_check_w)
            else:
                st.info(f"Month {_wk_check_m} Week {_wk_check_w} has not been generated yet.")

            with st.form("weekly"):
                c1, c2 = st.columns(2)
                wk_month = c1.number_input("Month (1–10)", min_value=1, max_value=10, value=_smart_m, key="wk_m")
                wk_week = c2.number_input("Week (1–4)", min_value=1, max_value=4, value=_smart_w, key="wk_w")
                if st.form_submit_button("Generate Weekly Breakdown"):
                    if sy.is_vacation_week(_cfg, int(wk_month), int(wk_week)):
                        st.warning(
                            f"Month {int(wk_month)} ({sy.MONTH_NAMES[int(wk_month)]}) "
                            f"Week {int(wk_week)} is marked as a vacation week in your "
                            "school year calendar. Generating anyway."
                        )
                    with st.spinner("Generating — may take several minutes for many subjects…"):
                        try:
                            _cal_month = sy.school_month_to_calendar_month(int(wk_month))
                            _pc.createWeeklyBreakdown(selected, str(_cal_month), int(wk_week))
                            st.success(f"Week {wk_week} of month {wk_month} generated!")
                            st.rerun()
                        except Exception as e:
                            st.error(str(e))

        # ── Daily lessons ─────────────────────────────────────────────────
        with st.expander("Daily Lessons"):
            st.caption(
                "Generates lessons for one day, one subject at a time - only for subjects that "
                "don't already have this day's lesson. Requires the weekly breakdown for this "
                "month/week to already exist."
            )
            _smart_day = sy.get_smart_day(_cfg)
            _smart_dm, _smart_dw, _smart_dd = _smart_day if _smart_day else (1, 1, "Monday")

            # Status for whichever month/week/day is currently selected in the form below.
            _dl_check_m = int(st.session_state.get("dl_m", _smart_dm))
            _dl_check_w = int(st.session_state.get("dl_w", _smart_dw))
            _dl_check_day = st.session_state.get("dl_day", _smart_dd)
            _dl_cal_month = sy.school_month_to_calendar_month(_dl_check_m)
            if _subjects:
                st.caption(f"Status for Month {_dl_check_m} Week {_dl_check_w} {_dl_check_day}:")
                _dl_cols = st.columns(4)
                for _i, _sn in enumerate(sorted(_subjects)):
                    _has_lesson = _pc.tryGetLesson(selected, _sn, _dl_cal_month, _dl_check_w, _dl_check_day)
                    _mark = "✓" if _has_lesson else "✗"
                    _dl_cols[_i % 4].write(f"{_mark} {_sn}")

            with st.form("daily"):
                c1, c2, c3 = st.columns(3)
                dl_month = c1.number_input("Month (1–10)", min_value=1, max_value=10, value=_smart_dm, key="dl_m")
                dl_week = c2.number_input("Week (1–4)", min_value=1, max_value=4, value=_smart_dw, key="dl_w")
                dl_day = c3.selectbox("Day", _DAYS, index=_DAYS.index(_smart_dd), key="dl_day")
                if st.form_submit_button("Generate Daily Lessons"):
                    _cal_month = sy.school_month_to_calendar_month(int(dl_month))
                    _to_generate = [
                        _sn for _sn in _subjects
                        if not _pc.tryGetLesson(selected, _sn, _cal_month, int(dl_week), dl_day)
                    ]
                    if not _to_generate:
                        st.info("All subjects already have this day's lesson generated — nothing to do.")
                    else:
                        with st.spinner(f"Generating {len(_to_generate)} subject lesson(s)…"):
                            _dl_errors = []
                            for _sn in _to_generate:
                                try:
                                    _pc.generateLesson(selected, _sn, _cal_month, int(dl_week), dl_day)
                                except Exception as e:
                                    _dl_errors.append(f"{_sn}: {e}")
                        if _dl_errors:
                            st.warning(
                                f"Generated {len(_to_generate) - len(_dl_errors)}/{len(_to_generate)} "
                                f"— {len(_dl_errors)} error(s):"
                            )
                            for _e in _dl_errors:
                                st.caption(f"• {_e}")
                        else:
                            st.success(
                                f"Generated {len(_to_generate)} subject lesson(s) for **{dl_day}**, "
                                f"month {dl_month} week {dl_week}!"
                            )
                        # Refresh so the checklist/status above reflects whatever just
                        # succeeded, even on a partial failure.
                        st.rerun()

        # ── Bulk Generate all school weeks ────────────────────────────────
        with st.expander("Bulk Generate All School Weeks"):
            _bulk_cfg = sy.load_config()
            _school_weeks = sy.get_school_weeks(_bulk_cfg)
            _vac_count = 40 - len(_school_weeks)
            st.write(
                f"**{len(_school_weeks)}** school weeks · "
                f"**{_vac_count}** vacation weeks skipped."
            )

            with st.expander("Week-by-Week Status", expanded=False):
                st.caption(
                    "Checks every school week against what's actually generated, and whether "
                    "every current subject is covered - read-only, no OpenAI cost. Up to "
                    f"{len(_school_weeks)} quick requests, so it may take a moment."
                )
                if st.button("Check Week-by-Week Status", key="bulk_wk_status"):
                    _current_names = set(_subjects.keys())
                    _wk_rows = []
                    with st.spinner("Checking all weeks…"):
                        for _sm, _sw in _school_weeks:
                            _cal_m = sy.school_month_to_calendar_month(_sm)
                            _wk_data = _pc.tryGetWeeklyBreakdown(selected, _cal_m, _sw)
                            if not _wk_data:
                                _wk_rows.append((_sm, _sw, "not_generated", []))
                                continue
                            _covered = set()
                            for _d in _wk_data.get("days", []):
                                for _s in _d.get("subjects", []):
                                    _covered.add(
                                        id_cache.get_canonical_subject_name(
                                            _client, selected, _s.get("subject_name", "")
                                        )
                                    )
                            _missing = sorted(_current_names - _covered)
                            _wk_rows.append((_sm, _sw, "missing" if _missing else "complete", _missing))
                    st.session_state["_bulk_wk_rows"] = _wk_rows

                _wk_rows = st.session_state.get("_bulk_wk_rows")
                if _wk_rows:
                    _n_missing = sum(1 for r in _wk_rows if r[2] == "missing")
                    _n_not_gen = sum(1 for r in _wk_rows if r[2] == "not_generated")
                    _n_complete = sum(1 for r in _wk_rows if r[2] == "complete")
                    st.write(
                        f"✓ **{_n_complete}** complete · ⚠ **{_n_missing}** missing a subject · "
                        f"✗ **{_n_not_gen}** not generated"
                    )
                    for _sm, _sw, _status, _missing in _wk_rows:
                        if _status == "complete":
                            continue
                        _label = (
                            "✗ Not generated" if _status == "not_generated"
                            else f"⚠ Missing: {', '.join(_missing)}"
                        )
                        _wc1, _wc2 = st.columns([4, 1])
                        _wc1.caption(f"Month {_sm} Week {_sw} — {_label}")

                        if _status != "missing":
                            continue  # "not_generated" just needs normal generation, not a sync

                        _sync_key = f"_sync_confirm_{selected}_{_sm}_{_sw}"
                        if st.session_state.get(_sync_key):
                            st.warning(
                                f"This will **delete and regenerate** Month {_sm} Week {_sw}'s "
                                "entire topic plan, day-by-day breakdown, and quiz - for ALL "
                                "subjects, not just the missing one, since a week's content is "
                                "generated for every subject together in one call. Already-"
                                "completed lessons for this week are **not** deleted, but may no "
                                "longer match the refreshed topic text."
                            )
                            _cc1, _cc2 = st.columns(2)
                            if _cc1.button(
                                "Confirm: Delete & Regenerate", key=f"{_sync_key}_go", type="primary"
                            ):
                                _cal_m = sy.school_month_to_calendar_month(_sm)
                                try:
                                    with st.spinner(f"Regenerating Month {_sm} Week {_sw}…"):
                                        _client.delete_weekly_breakdown(
                                            _stu_id, _cal_m, _sw, _curr_school_year
                                        )
                                        _pc.createWeeklyBreakdown(selected, _cal_m, _sw)
                                    st.success(f"Month {_sm} Week {_sw} regenerated.")
                                    st.session_state.pop(_sync_key, None)
                                    st.session_state.pop("_bulk_wk_rows", None)
                                    st.rerun()
                                except EmpowerHSAError as _e:
                                    st.error(str(_e))
                            if _cc2.button("Cancel", key=f"{_sync_key}_cancel"):
                                st.session_state.pop(_sync_key, None)
                                st.rerun()
                        else:
                            if _wc2.button("Sync", key=f"{_sync_key}_btn"):
                                st.session_state[_sync_key] = True
                                st.rerun()

            _active_job = st.session_state.get("_bulk_job_id")
            if _active_job:
                # Auto-polling status panel (re-executes every 5 s via st.fragment)
                _bulk_status_panel()
            else:
                _bulk_status = id_cache.get_bulk_generation_status(selected, _curr_school_year)
                if _bulk_status:
                    _b_errors = _bulk_status.get("errors", 0)
                    if _b_errors:
                        _failed_weeks = _bulk_status.get("failed_weeks") or []
                        st.warning(
                            f"Bulk generation for **{selected}**'s {_curr_school_year}-{str(_curr_school_year + 1)[2:]} "
                            f"school year last ran on {_bulk_status.get('completed_at')} — "
                            f"{_bulk_status.get('completed')}/{_bulk_status.get('total')} weeks, "
                            f"**{_b_errors}** error(s)."
                        )
                        if _failed_weeks:
                            _fw_labels = ", ".join(f"month {m} week {w}" for m, w in _failed_weeks)
                            st.caption(f"Failed: {_fw_labels} (calendar month numbers)")
                            if st.button(f"Retry {len(_failed_weeks)} failed week(s)", key="bulk_retry"):
                                _stu_id_bulk = stu_obj.get("_id")
                                if not _stu_id_bulk:
                                    st.error("Could not resolve student ID.")
                                else:
                                    try:
                                        _jid = _client.start_bulk_breakdown(
                                            _stu_id_bulk, _failed_weeks, _curr_school_year,
                                        )
                                        st.session_state["_bulk_job_id"] = _jid
                                        st.session_state["_bulk_job_student"] = selected
                                        st.session_state["_bulk_job_school_year"] = _curr_school_year
                                        st.rerun()
                                    except EmpowerHSAError as _e:
                                        st.error(str(_e))
                    else:
                        st.info(
                            f"✓ Bulk generation for **{selected}**'s {_curr_school_year}-{str(_curr_school_year + 1)[2:]} "
                            f"school year already completed on {_bulk_status.get('completed_at')} "
                            f"({_bulk_status.get('completed')}/{_bulk_status.get('total')} weeks)."
                        )
                st.caption(
                    "Runs on the empowerHSA server in the background — page refreshes "
                    "and tab switches won't interrupt it. Save your School Year calendar first."
                )
                if st.button("Start Bulk Generation", key="bulk_gen", type="primary"):
                    _stu_id_bulk = stu_obj.get("_id")
                    if not _stu_id_bulk:
                        st.error("Could not resolve student ID — make sure this student has a yearly plan.")
                    else:
                        try:
                            _jid = _client.start_bulk_breakdown(
                                _stu_id_bulk,
                                [[sy.school_month_to_calendar_month(m), w] for m, w in _school_weeks],
                                sy.load_config().get("school_year_start"),
                            )
                            st.session_state["_bulk_job_id"] = _jid
                            st.session_state["_bulk_job_student"] = selected
                            st.session_state["_bulk_job_school_year"] = sy.load_config().get("school_year_start")
                            st.rerun()
                        except EmpowerHSAError as _e:
                            st.error(str(_e))


# ═══════════════════════════════════════════════════════════════════════════
# ASSESSMENTS
# ═══════════════════════════════════════════════════════════════════════════
with tab_assessments:
    students = _all_students()
    names = [s["name"] for s in students]

    if not names:
        st.info("Add a student in the **Students** tab first.")
    else:
        sel_a = st.selectbox("Student", names, key="asmnt_sel")
        stu_a = next((s for s in students if s["name"] == sel_a), {})
        default_age_a = int(stu_a.get("age", 10))

        st.divider()

        with st.expander("Generate Assessment Test", expanded=True):
            st.caption(
                "Creates one multi-choice assessment per subject. All subjects in one "
                "call share the same assessment_number."
            )
            with st.form("gen_assessment"):
                c1, c2 = st.columns(2)
                as_age = c1.number_input("Age", min_value=4, max_value=18, value=default_age_a, key="as_age")
                as_grade = c2.number_input("Grade level", min_value=1, max_value=12, value=5, key="as_grade")
                as_subjects = st.text_input(
                    "Subjects (comma-separated)",
                    value="Mathematics, Language Arts, Science, Social Studies",
                )
                if st.form_submit_button("Generate"):
                    subj_list = [s.strip() for s in as_subjects.split(",") if s.strip()]
                    if not subj_list:
                        st.warning("Enter at least one subject.")
                    else:
                        with st.spinner("Generating assessment…"):
                            try:
                                results = _pc.assessmentTest(
                                    sel_a, int(as_age), int(as_grade), tuple(subj_list)
                                )
                                if results:
                                    num = results[0].get("assessment_number")
                                    st.success(
                                        f"Assessment **#{num}** generated for {sel_a} "
                                        f"across {len(results)} subject(s)."
                                    )
                            except Exception as e:
                                st.error(str(e))

        with st.expander("View Assessment"):
            with st.form("view_assessment"):
                as_num = st.number_input("Assessment number", min_value=1, value=1)
                if st.form_submit_button("Fetch"):
                    try:
                        data = _pc.getAssessment(sel_a, int(as_num))
                        items = data if isinstance(data, list) else ([data] if data else [])
                        if not items:
                            st.info("No assessment found for that number.")
                        else:
                            for item in items:
                                st.subheader(item.get("subject", "Unknown Subject"))
                                for i, q in enumerate(item.get("questions", []), 1):
                                    st.markdown(f"**{i}. {q.get('question', '')}**")
                                    for opt in q.get("options", []):
                                        st.write(f"  - {opt}")
                                    st.caption(f"Answer: {q.get('answer', '')}")
                    except Exception as e:
                        st.error(str(e))

        with st.expander("Delete Assessment"):
            with st.form("del_assessment"):
                del_as_id = st.text_input("Assessment ID")
                if st.form_submit_button("Delete"):
                    aid = del_as_id.strip()
                    if not aid:
                        st.warning("Enter an assessment ID.")
                    else:
                        try:
                            _client.delete_assessment(aid)
                            st.success("Assessment deleted.")
                        except EmpowerHSAError as e:
                            st.error(str(e))

# ═══════════════════════════════════════════════════════════════════════════
# MANAGE
# ═══════════════════════════════════════════════════════════════════════════
with tab_manage:
    mtab_subj, mtab_grade, mtab_lesson, mtab_progress = st.tabs(
        ["Subjects", "Grades", "Lessons", "Progress"]
    )

    # ── Subjects ──────────────────────────────────────────────────────────
    with mtab_subj:
        with st.form("add_subject"):
            sub_name = st.text_input("Subject name")
            if st.form_submit_button("Create Subject"):
                s = sub_name.strip()
                if not s:
                    st.warning("Enter a subject name.")
                else:
                    try:
                        _client.create_or_update_subject(subject_name=s)
                        st.success(f"**{s}** created.")
                        st.rerun()
                    except EmpowerHSAError as e:
                        st.error(str(e))

        st.divider()
        st.subheader("All Subjects")
        subjects = _all_subjects()
        if not subjects:
            st.info("No subjects found.")
        else:
            for subj in subjects:
                c1, c2 = st.columns([5, 1])
                c1.write(subj.get("name", "—"))
                if c2.button("Delete", key=f"del_sub_{subj['_id']}"):
                    try:
                        _client.delete_subject(subj["_id"])
                        st.success("Deleted.")
                        st.rerun()
                    except EmpowerHSAError as e:
                        st.error(str(e))

    # ── Grades ────────────────────────────────────────────────────────────
    with mtab_grade:
        with st.form("add_grade"):
            gr_num = st.number_input("Grade number", min_value=1, max_value=12, value=5)
            if st.form_submit_button("Create Grade"):
                try:
                    _client.create_or_update_grade(grade=int(gr_num))
                    st.success(f"Grade {gr_num} created.")
                    st.rerun()
                except EmpowerHSAError as e:
                    st.error(str(e))

        st.divider()
        st.subheader("All Grades")
        grades = _all_grades()
        if not grades:
            st.info("No grades found.")
        else:
            for gr in grades:
                c1, c2 = st.columns([5, 1])
                c1.write(f"Grade {gr.get('grade', '?')}  ·  ID: {gr.get('_id', '?')}")
                if c2.button("Delete", key=f"del_gr_{gr['_id']}"):
                    try:
                        _client.delete_grade(gr["_id"])
                        st.success("Deleted.")
                        st.rerun()
                    except EmpowerHSAError as e:
                        st.error(str(e))

    # ── Lessons ───────────────────────────────────────────────────────────
    with mtab_lesson:
        st.caption("Delete a specific lesson by its MongoDB ID (visible in quiz / progress records).")
        with st.form("del_lesson"):
            les_id = st.text_input("Lesson ID")
            if st.form_submit_button("Delete Lesson"):
                lid = les_id.strip()
                if not lid:
                    st.warning("Enter a lesson ID.")
                else:
                    try:
                        _client.delete_lesson(lid)
                        st.success("Lesson deleted.")
                    except EmpowerHSAError as e:
                        st.error(str(e))

    # ── Progress ──────────────────────────────────────────────────────────
    with mtab_progress:
        students = _all_students()
        names = [s["name"] for s in students]
        if not names:
            st.info("No students found.")
        else:
            _pr_cfg = sy.load_config()
            _pr_school_year = _pr_cfg.get("school_year_start")

            c1, c2 = st.columns(2)
            pr_stu = c1.selectbox("Student", names, key="pr_stu")

            _today_coords = sy.date_to_school_coords(_pr_cfg, datetime.date.today())
            _default_month = _today_coords[0] if _today_coords else 1
            _month_options = list(range(1, 11))
            pr_month = c2.selectbox(
                "Month", _month_options,
                index=_month_options.index(_default_month),
                format_func=lambda m: sy.MONTH_NAMES[m],
                key="pr_month",
            )

            stu_id = id_cache.get_student_id(_client, pr_stu)
            if not stu_id:
                st.warning("Student ID not cached — generate a yearly plan for this student first.")
            else:
                try:
                    attempts = _client.get_progress_month(
                        stu_id, sy.school_month_to_calendar_month(int(pr_month)), _pr_school_year,
                    ) or []
                except EmpowerHSAError as e:
                    st.error(str(e))
                    attempts = []

                if not attempts:
                    st.info(f"No progress recorded yet for {pr_stu} in {sy.MONTH_NAMES[pr_month]}.")
                else:
                    # Collapse repeated attempts on the same day down to the latest one,
                    # so retries don't get double-counted in the overview.
                    _latest_by_day = {}
                    for a in attempts:
                        key = (a.get("subject_name"), a.get("week_of_the_month"), a.get("day_name"))
                        if key not in _latest_by_day or (a.get("attempt_number") or 0) > (_latest_by_day[key].get("attempt_number") or 0):
                            _latest_by_day[key] = a

                    _by_subject = defaultdict(list)
                    for a in _latest_by_day.values():
                        _by_subject[a["subject_name"]].append(a)
                    for entries in _by_subject.values():
                        entries.sort(key=lambda a: (a["week_of_the_month"], _DAYS.index(a["day_name"])))

                    _month_avg = mean(a["quiz_grade"] for a in _latest_by_day.values())
                    st.metric(f"{sy.MONTH_NAMES[pr_month]} Average", f"{_month_avg:.1f}%")

                    st.divider()
                    for subj_name in sorted(_by_subject):
                        entries = _by_subject[subj_name]
                        avg = mean(e["quiz_grade"] for e in entries)
                        latest = entries[-1]
                        with st.expander(
                            f"**{subj_name}** — {len(entries)} lesson(s) recorded · "
                            f"avg {avg:.1f}% · latest {latest['quiz_grade']}%"
                        ):
                            for e in entries:
                                ec1, ec2, ec3 = st.columns([2, 1, 1])
                                ec1.write(f"Week {e['week_of_the_month']} · {e['day_name']}")
                                ec2.write(f"{e['quiz_grade']}%")
                                if e.get("attempt_number", 1) > 1:
                                    ec3.caption(f"Attempt {e['attempt_number']}")

                                wrong = e.get("wrong_answers") or []
                                quiz = e.get("quiz") or []
                                if wrong:
                                    st.markdown("**Missed questions:**")
                                    for w in wrong:
                                        try:
                                            q = quiz[int(w)]
                                        except (ValueError, IndexError, TypeError):
                                            st.write(f"  - Question {w}")
                                            continue
                                        st.write(
                                            f"  - {q.get('question', '?')}  "
                                            f"(correct answer: {q.get('answer', '?')})"
                                        )
                                else:
                                    st.caption("No wrong answers on record.")
                                st.divider()

# ═══════════════════════════════════════════════════════════════════════════
# SCHOOL YEAR CALENDAR
# ═══════════════════════════════════════════════════════════════════════════
with tab_school_year:
    _current_cfg = sy.load_config()
    _current_sy = _current_cfg.get("school_year_start", 2026)
    _sy_label = f"{_current_sy}-{str(_current_sy + 1)[2:]}"

    st.subheader(f"School Year Calendar — {_sy_label}")
    st.caption(
        "Click a day to mark it off. Click a red event to remove it. Drag to select a range. "
        "Save when done — vacation weeks (3+ days off) are skipped during bulk generation."
    )

    with st.expander(f"Start New School Year (currently {_sy_label})"):
        st.caption(
            "Rolls the configured school year forward. Past years' generated content stays "
            "in empowerHSA untouched - new generation calls (yearly plans, weekly breakdowns, "
            "lessons) target whatever year is set here. Clears the vacation-day calendar below "
            "since specific dates don't carry over between years - reload defaults or re-add them."
        )
        with st.form("new_school_year"):
            _new_sy = st.number_input(
                "School year starts in", min_value=2020, max_value=2100,
                value=_current_sy + 1, key="new_sy_input",
            )
            if st.form_submit_button("Start New School Year", type="primary"):
                _new_sy_int = int(_new_sy)
                sy.save_config({
                    "school_year_start": _new_sy_int,
                    "first_day": f"{_new_sy_int}-08-17",
                    "last_day": f"{_new_sy_int + 1}-05-28",
                    "vacation_days": [],
                })
                st.session_state["vacation_days"] = []
                st.session_state.pop("_pending_date", None)
                st.session_state.pop("_cal_fp", None)
                st.success(
                    f"School year set to {_new_sy_int}-{str(_new_sy_int + 1)[2:]}. "
                    "Add vacation days below (or load Texas defaults) and Save."
                )
                st.rerun()

    # ── Action buttons ────────────────────────────────────────────────────
    _sy_c1, _sy_c2, _sy_c3, _sy_spacer = st.columns([1.5, 1.2, 1, 4])
    if _sy_c1.button("Load Texas 2026-27 Defaults", key="sy_load",
                      help="Specific holiday dates are only accurate for the 2026-27 calendar year."):
        st.session_state["vacation_days"] = list(sy.default_config()["vacation_days"])
        st.session_state.pop("_pending_date", None)
        st.session_state.pop("_cal_fp", None)
        st.rerun()

    if _sy_c2.button("Clear All", key="sy_clear"):
        st.session_state["vacation_days"] = []
        st.session_state.pop("_pending_date", None)
        st.session_state.pop("_cal_fp", None)
        st.rerun()

    if _sy_c3.button("Save Calendar", key="sy_save", type="primary"):
        _save_days = sorted(
            st.session_state["vacation_days"], key=lambda x: x["date"]
        )
        sy.save_config({
            "school_year_start": _current_sy,
            "first_day": _current_cfg.get("first_day", f"{_current_sy}-08-17"),
            "last_day": _current_cfg.get("last_day", f"{_current_sy + 1}-05-28"),
            "vacation_days": _save_days,
        })
        _temp_cfg = {"school_year_start": _current_sy, "vacation_days": _save_days}
        _sw = sy.get_school_weeks(_temp_cfg)
        st.success(
            f"Saved — **{len(_save_days)}** vacation days · "
            f"**{len(_sw)}** of 40 school weeks will be generated."
        )

    st.divider()

    # ── FullCalendar interactive component ────────────────────────────────
    _events = [
        {
            "title": _vd.get("label") or "Off",
            "color": "#EF4444",
            "start": _vd["date"],
            "end": _vd["date"],
        }
        for _vd in st.session_state["vacation_days"]
    ]
    _cal_options = {
        "initialView": "dayGridMonth",
        "initialDate": f"{_current_sy}-08-01",
        "selectable": True,
        "navLinks": True,
        "editable": False,
        "contentHeight": 600,
        "headerToolbar": {
            "left": "today prev,next",
            "center": "title",
            "right": "dayGridMonth",
        },
    }
    _cal_state = st_calendar(events=_events, options=_cal_options, key="school_year_cal")
    # streamlit-calendar only reports its height to Streamlit once, on mount (see its
    # bundled JS: `useEffect(() => Streamlit.setFrameHeight(), [])`). Since this tab isn't
    # the default-selected one, it first mounts while its panel is hidden and gets stuck
    # reporting 0 height forever - the iframe stays collapsed even after switching to this
    # tab. Force the iframe's actual size to match its real rendered content each time this
    # tab becomes visible.
    st.components.v1.html(
        """
        <script>
        function fixCalendarSize() {
            const doc = window.parent.document;
            const iframes = doc.querySelectorAll('iframe[title="streamlit_calendar.calendar"]');
            iframes.forEach((f) => {
                try {
                    const h = f.contentDocument && f.contentDocument.body
                        ? f.contentDocument.body.scrollHeight : 0;
                    if (h > 0 && f.style.height !== h + 'px') {
                        f.style.height = h + 'px';
                    }
                    if (f.style.width !== '100%') {
                        f.style.width = '100%';
                    }
                } catch (e) {}
            });
        }
        setInterval(fixCalendarSize, 300);
        </script>
        """,
        height=0,
    )

    # Process calendar interactions
    if _cal_state:
        _cb = _cal_state.get("callback")

        if _cb == "dateClick":
            _clicked_date = _cal_state["dateClick"]["date"][:10]
            _fp = f"dateClick:{_clicked_date}"
            if _fp != st.session_state.get("_cal_fp"):
                st.session_state["_cal_fp"] = _fp
                _vac_set = {vd["date"] for vd in st.session_state["vacation_days"]}
                if _clicked_date not in _vac_set:
                    st.session_state["_pending_date"] = _clicked_date

        elif _cb == "eventClick":
            _ev_start = _cal_state["eventClick"]["event"].get("start", "")[:10]
            _fp = f"eventClick:{_ev_start}"
            if _fp != st.session_state.get("_cal_fp"):
                st.session_state["_cal_fp"] = _fp
                st.session_state["vacation_days"] = [
                    vd for vd in st.session_state["vacation_days"]
                    if vd["date"] != _ev_start
                ]
                st.session_state.pop("_pending_date", None)
                st.rerun()

        elif _cb == "select":
            _start_s = _cal_state["select"]["start"][:10]
            _end_s = _cal_state["select"]["end"][:10]
            _fp = f"select:{_start_s}:{_end_s}"
            if _fp != st.session_state.get("_cal_fp"):
                st.session_state["_cal_fp"] = _fp
                _vac_set = {vd["date"] for vd in st.session_state["vacation_days"]}
                _sd = datetime.date.fromisoformat(_start_s)
                _ed = datetime.date.fromisoformat(_end_s)
                _new = []
                _cur = _sd
                while _cur < _ed:
                    if _cur.weekday() < 5 and _cur.isoformat() not in _vac_set:
                        _new.append({"date": _cur.isoformat(), "label": ""})
                    _cur += datetime.timedelta(days=1)
                if _new:
                    st.session_state["vacation_days"].extend(_new)
                    st.session_state.pop("_pending_date", None)
                    st.rerun()

    # Pending-add form: shown when user clicked an empty day
    if "_pending_date" in st.session_state:
        _pd = st.session_state["_pending_date"]
        with st.form("add_pending"):
            st.write(f"Add **{_pd}** as a vacation day?")
            _lbl = st.text_input("Label (optional)", placeholder="e.g. Labor Day")
            _c1p, _c2p = st.columns(2)
            if _c1p.form_submit_button("Add"):
                st.session_state["vacation_days"].append({"date": _pd, "label": _lbl.strip()})
                st.session_state.pop("_pending_date", None)
                st.rerun()
            if _c2p.form_submit_button("Cancel"):
                st.session_state.pop("_pending_date", None)
                st.rerun()

    st.divider()

    # ── Vacation day summary + interactive list ────────────────────────────
    _all_vdays = sorted(
        st.session_state["vacation_days"], key=lambda x: x["date"]
    )
    _temp_cfg2 = {"school_year_start": _current_sy, "vacation_days": _all_vdays}
    _school_wk_count = len(sy.get_school_weeks(_temp_cfg2))

    _mc1, _mc2 = st.columns(2)
    _mc1.metric("Vacation Days", len(_all_vdays))
    _mc2.metric("School Weeks", _school_wk_count, f"{40 - _school_wk_count} skipped")

    _remove_date = None
    if _all_vdays:
        with st.expander("Vacation Day Breakdown", expanded=True):
            _by_month: dict = {}
            for _vd in _all_vdays:
                _dobj = datetime.date.fromisoformat(_vd["date"])
                _mk = (_dobj.year, _dobj.month)
                _by_month.setdefault(_mk, []).append(_vd)
            for _mk, _mdays in sorted(_by_month.items()):
                _mname = datetime.date(1900, _mk[1], 1).strftime("%B")
                st.markdown(f"**{_mname} {_mk[0]}** — {len(_mdays)} day(s)")
                for _vd in _mdays:
                    _dobj = datetime.date.fromisoformat(_vd["date"])
                    _lbl = _vd.get("label", "")
                    _rc1, _rc2 = st.columns([6, 1])
                    _rc1.write(f"  · {_dobj.strftime('%a')} {_dobj.day}{': ' + _lbl if _lbl else ''}")
                    if _rc2.button("✕", key=f"rm_{_vd['date']}"):
                        _remove_date = _vd["date"]

    if _remove_date:
        st.session_state["vacation_days"] = [
            vd for vd in st.session_state["vacation_days"] if vd["date"] != _remove_date
        ]
        st.rerun()

# ═══════════════════════════════════════════════════════════════════════════
# HELP
# ═══════════════════════════════════════════════════════════════════════════
with tab_help:
    st.subheader("Getting Started with a New Student")
    st.markdown(
        "Follow these steps in order — each stage depends on the one before it "
        "(a subject needs a Yearly Plan before a week can be generated; a week "
        "needs a Weekly Breakdown before a day's lessons can be generated)."
    )

    with st.expander("1. Add the student", expanded=True):
        st.markdown(
            "**Students tab** → fill in name and age → **Add**.\n\n"
            "That's it for this step — grade level is set per-subject later, not here."
        )

    with st.expander("2. Set up the school year calendar", expanded=True):
        st.markdown(
            "**School Year tab** → either **Load Texas Defaults** (accurate only for the "
            "2026-27 calendar year) or click days on the calendar yourself to mark them off "
            "as vacation days → **Save Calendar**.\n\n"
            "A week is automatically skipped during bulk generation once 3 or more of its "
            "weekdays are marked off. If you're starting a brand-new school year (not just "
            "editing this one), use **Start New School Year** first — it rolls the active "
            "year forward and clears the vacation calendar so you can rebuild it for the new year."
        )

    with st.expander("3. Generate each subject's Yearly Plan", expanded=True):
        st.markdown(
            "**Curriculum tab** → select the student → **Add Subject** expander → enter a "
            "subject name, age, and grade level → **Generate Yearly Plan**.\n\n"
            "Repeat once per subject (Math, Science, English, etc.) — this is what actually "
            "creates the subject and its 10-month topic outline; nothing downstream works "
            "without it. Each click is a real OpenAI call and takes a little while.\n\n"
            "**Important:** only click this once per subject. There's no \"already generated\" "
            "check here — running it again on the same subject adds a second, likely "
            "overlapping topic outline on top of the first instead of replacing it. If a "
            "subject's plan looks wrong, use **Regen** on that subject's row instead of "
            "Add Subject again (same caveat applies to Regen too - re-running it repeatedly "
            "on a subject that's already correct just adds redundant topics)."
        )

    with st.expander("4. Generate the actual weekly/daily content", expanded=True):
        st.markdown(
            "Once every subject has a Yearly Plan, you have two ways to get lesson content "
            "in front of the student:\n\n"
            "- **Let it happen automatically** — do nothing here. When the student opens the "
            "main app and picks a day, it generates that week's breakdown and that subject's "
            "lesson the first time it's needed. This is the lowest-effort option and is fine "
            "for day-to-day use once the year is underway.\n"
            "- **Generate ahead of time from here** — useful for testing, or to avoid the "
            "student waiting on a generation call:\n"
            "  - **Weekly Breakdown** expander: generates one month/week's topic plan, "
            "day-by-day breakdown, and end-of-week quiz across every subject. Shows whether "
            "that week already exists, with a **View Weekly Breakdown** button if so.\n"
            "  - **Daily Lessons** expander: generates one day's actual lecture + quiz for "
            "every subject, but only for subjects that don't already have that day's lesson - "
            "shows a ✓/✗ checklist so you can see what's missing before generating.\n"
            "  - **Bulk Generate All School Weeks** expander: generates every non-vacation "
            "week for the whole year in one background job (progress bar, safe to leave "
            "running). This is the expensive one - real OpenAI cost across the full year, "
            "so make sure your subjects and calendar are correct first."
        )

    with st.expander("5. Check what's actually there", expanded=False):
        st.markdown(
            "- Each subject's **Check** button (Curriculum tab) tests *today's actual "
            "school day* — its tooltip tells you exactly which month/week/day it's testing.\n"
            "- The **Year Plan** number next to each subject is that subject's topic count "
            "for the *currently active school year only* — topics from a previous year (or "
            "generated before year-scoping existed) don't count toward it.\n"
            "- **Manage tab** lets you look up progress records, and delete individual grades/"
            "lessons if something was generated wrong and needs to be cleared out by hand."
        )

    st.divider()
    st.subheader("What each tab is for")
    st.markdown(
        "- **Students** — add/edit/delete students; this is the only place age/name live.\n"
        "- **Curriculum** — the main workspace: per-subject Yearly Plans, Weekly Breakdown, "
        "Daily Lessons, and Bulk Generate, all scoped to whichever student is selected.\n"
        "- **Assessments** — generates a separate multi-subject placement/assessment test "
        "(not tied to the weekly curriculum), and lets you view or delete past ones by number/ID.\n"
        "- **Manage** — cross-cutting lookups and cleanup: view/delete grade records, delete a "
        "lesson by ID, and look up a specific progress/quiz-grade record.\n"
        "- **School Year** — the vacation-day calendar that controls which weeks get generated "
        "and skipped, plus rolling forward into a new school year.\n"
        "- **Help** — this tab."
    )

    st.divider()
    st.caption(
        "Generation calls cost real OpenAI usage and can take a few minutes each, especially "
        "Bulk Generate and any student with many subjects — there's no need to re-run something "
        "that already succeeded."
    )