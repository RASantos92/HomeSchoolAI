"""Parent portal — password-gated admin panel for managing students,
curriculum generation, assessments, and data in empowerHSA."""

import datetime

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


# ── Main tabs ─────────────────────────────────────────────────────────────
tab_students, tab_curriculum, tab_assessments, tab_manage, tab_school_year = st.tabs(
    ["Students", "Curriculum", "Assessments", "Manage", "School Year"]
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
            c1, c2, c3 = st.columns([3, 2, 1])
            c1.write(f"**{s.get('name', '—')}**")
            c2.write(f"Age {s.get('age', '?')}")
            if c3.button("Delete", key=f"del_stu_{s['_id']}"):
                try:
                    _client.delete_student(s["_id"])
                    st.success("Student deleted.")
                    st.rerun()
                except EmpowerHSAError as e:
                    st.error(str(e))

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
        _month_count = len(stu_obj.get("year", []))

        st.subheader(f"{selected}'s Subjects")

        if not _existing_subjects:
            st.info("No subjects yet — add one below.")
        else:
            # Header row
            _hc = st.columns([3, 1, 2, 2, 1, 1])
            _hc[0].markdown("**Subject**")
            _hc[1].markdown("**Grade**")
            _hc[2].markdown("**Year Plan**")
            _hc[3].markdown("**Breakdowns**")
            st.divider()

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

                # Grade column: shows current grade as a button label; click = increment by 1
                _g_label = str(_cached_grade) if _cached_grade else "?"
                if _row[1].button(
                    f"{_g_label} ▲",
                    key=f"inc_{_sname}",
                    help="Click to increment grade by 1 (then Regen to apply)",
                ):
                    _new_grade = (_cached_grade or 0) + 1
                    id_cache.set_subject_grade(selected, _sname, _new_grade)
                    st.session_state[_grade_changed_key] = True
                    st.session_state.pop(_chk_key, None)
                    st.rerun()

                _row[2].caption(
                    f"✓ {_month_count}/10 months" if _month_count else "Not started"
                )

                # Breakdown spot-check
                _chk_status = st.session_state.get(_chk_key, "—")
                _row[3].caption(_chk_status)
                if _row[3].button("Check", key=f"chk_{_sname}", help="Test month 1 week 1"):
                    try:
                        _lesson = _client.try_get_lesson(
                            student_id=_stu_id,
                            subject_id=_sid,
                            month_number=1,
                            week_of_the_month=1,
                            day_name="Monday",
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
                    _default_grade = id_cache.get_subject_grade(selected, _sname) or 5
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
                yr_grade = c3.number_input("Grade level", min_value=1, max_value=12, value=5, key="yr_grade")
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
            if _subjects:
                _wk_check = _pc.tryGetLesson(selected, next(iter(_subjects)), _smart_m, _smart_w, "Monday")
                if _wk_check:
                    st.info("✓ This week has already been generated.")
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
                            _pc.createWeeklyBreakdown(selected, str(wk_month), int(wk_week))
                            st.success(f"Week {wk_week} of month {wk_month} generated!")
                        except Exception as e:
                            st.error(str(e))

        # ── Daily lessons ─────────────────────────────────────────────────
        with st.expander("Daily Lessons"):
            st.caption(
                "Generates all subject lessons for one day. "
                "Requires the weekly breakdown for this month/week to already exist."
            )
            _smart_day = sy.get_smart_day(_cfg)
            _smart_dm, _smart_dw, _smart_dd = _smart_day if _smart_day else (1, 1, "Monday")
            if _subjects:
                _dl_check = _pc.tryGetLesson(selected, next(iter(_subjects)), _smart_dm, _smart_dw, _smart_dd)
                if _dl_check:
                    st.info("✓ Lessons for this day have already been generated.")
            with st.form("daily"):
                c1, c2, c3 = st.columns(3)
                dl_month = c1.number_input("Month (1–10)", min_value=1, max_value=10, value=_smart_dm, key="dl_m")
                dl_week = c2.number_input("Week (1–4)", min_value=1, max_value=4, value=_smart_dw, key="dl_w")
                dl_day = c3.selectbox("Day", _DAYS, index=_DAYS.index(_smart_dd))
                if st.form_submit_button("Generate Daily Lessons"):
                    with st.spinner("Generating all subject lessons…"):
                        try:
                            _pc.createDailyBreakDown(selected, str(dl_month), int(dl_week), dl_day)
                            st.success(f"**{dl_day}** lessons for month {dl_month} week {dl_week} generated!")
                        except Exception as e:
                            st.error(str(e))

        # ── Bulk Generate all school weeks ────────────────────────────────
        with st.expander("Bulk Generate All School Weeks"):
            _bulk_cfg = sy.load_config()
            _school_weeks = sy.get_school_weeks(_bulk_cfg)
            _vac_count = 40 - len(_school_weeks)
            st.write(
                f"**{len(_school_weeks)}** school weeks · "
                f"**{_vac_count}** vacation weeks skipped."
            )

            _active_job = st.session_state.get("_bulk_job_id")
            if _active_job:
                # Auto-polling status panel (re-executes every 5 s via st.fragment)
                _bulk_status_panel()
            else:
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
                                [[m, w] for m, w in _school_weeks],
                            )
                            st.session_state["_bulk_job_id"] = _jid
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
            with st.form("view_progress"):
                c1, c2 = st.columns(2)
                pr_stu = c1.selectbox("Student", names, key="pr_stu")
                pr_subj = c2.text_input("Subject name")
                c3, c4, c5 = st.columns(3)
                pr_month = c3.number_input("Month (1–10)", min_value=1, max_value=10, value=1, key="pr_m")
                pr_week = c4.number_input("Week (1–4)", min_value=1, max_value=4, value=1, key="pr_w")
                pr_day = c5.selectbox("Day", _DAYS, key="pr_day")
                if st.form_submit_button("View Progress"):
                    stu_id = id_cache.get_student_id(_client, pr_stu)
                    if not stu_id:
                        st.warning("Student ID not cached — generate a yearly plan for this student first.")
                    elif not pr_subj.strip():
                        st.warning("Enter a subject name.")
                    else:
                        try:
                            data = _client.get_progress(
                                stu_id, pr_subj.strip(), int(pr_month), int(pr_week), pr_day
                            )
                            if data:
                                st.metric("Quiz Grade", f"{data.get('quiz_grade', '?')}%")
                                wrong = data.get("wrong_answers", [])
                                if wrong:
                                    st.markdown("**Incorrect answers:**")
                                    for w in wrong:
                                        st.write(f"  - {w}")
                                else:
                                    st.success("No wrong answers on record.")
                            else:
                                st.info("No progress record found for that combination.")
                        except EmpowerHSAError as e:
                            st.error(str(e))

# ═══════════════════════════════════════════════════════════════════════════
# SCHOOL YEAR CALENDAR
# ═══════════════════════════════════════════════════════════════════════════
with tab_school_year:
    st.subheader("School Year Calendar — 2026-27")
    st.caption(
        "Click a day to mark it off. Click a red event to remove it. Drag to select a range. "
        "Save when done — vacation weeks (3+ days off) are skipped during bulk generation."
    )

    # ── Action buttons ────────────────────────────────────────────────────
    _sy_c1, _sy_c2, _sy_c3, _sy_spacer = st.columns([1.5, 1.2, 1, 4])
    if _sy_c1.button("Load Texas 2026-27 Defaults", key="sy_load"):
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
        _existing_cfg = sy.load_config()
        _save_days = sorted(
            st.session_state["vacation_days"], key=lambda x: x["date"]
        )
        sy.save_config({
            "school_year_start": _existing_cfg.get("school_year_start", 2026),
            "first_day": _existing_cfg.get("first_day", "2026-08-17"),
            "last_day": _existing_cfg.get("last_day", "2027-05-28"),
            "vacation_days": _save_days,
        })
        _temp_cfg = {"school_year_start": 2026, "vacation_days": _save_days}
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
        "initialDate": "2026-08-01",
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
    _temp_cfg2 = {"school_year_start": 2026, "vacation_days": _all_vdays}
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