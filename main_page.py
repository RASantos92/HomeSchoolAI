import datetime

import streamlit as st

from controller.parent import Parent
from services import school_year as sy
from ui.session import init_session_state
from ui.graph_lab import is_graph_popup_requested, render_graph_popup
from ui.lecture_view import render_lecture
from ui.quiz_view import render_lecture_grade_feedback, render_quiz, render_final_attempt

st.set_page_config(layout="wide")

# If launched as a graph-only window (via the Algebra fab's ?graph=1 link), render just that and stop.
if is_graph_popup_requested():
    render_graph_popup()
    st.stop()

pc = Parent()

STUDENT_NAME = "Hayden"

_cfg = sy.load_config()
_today = datetime.date.today()
_first_day = datetime.date.fromisoformat(_cfg.get("first_day", "2026-08-17"))
_last_day = datetime.date.fromisoformat(_cfg.get("last_day", "2027-05-28"))

if _today < _first_day:
    st.info(f"School hasn't started yet. Classes begin {_first_day.strftime('%B %d, %Y')}.")
    st.stop()
elif _today > _last_day:
    st.info("The school year has ended. See you next year!")
    st.stop()
elif not sy.is_school_day(_cfg, _today):
    _label = sy.vacation_label(_cfg, _today.isoformat())
    _reason = f" ({_label})" if _label else ""
    _next = sy.next_school_day(_cfg, _today + datetime.timedelta(days=1))
    _next_str = f" Next school day: {_next.strftime('%A, %B %d')}." if _next else ""
    st.info(f"Today is not a school day{_reason}.{_next_str} Enjoy your break!")
    st.stop()

_smart = sy.get_smart_day(_cfg)
school_month, school_week, today_day = _smart if _smart else (1, 1, "Monday")

# Define days of the week — default to today's day
days_of_week = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
selected_day = st.sidebar.selectbox("Choose a day", days_of_week, index=days_of_week.index(today_day))

# Idempotent re-fetch of the week's breakdown (no OpenAI call if already generated).
week_data = pc.createWeeklyBreakdown(STUDENT_NAME, school_month, school_week)
if not week_data:
    st.warning("Today's lessons haven't been generated yet. Ask a parent to generate them in the Parent Portal.")
    st.stop()

day_data = next((d for d in week_data.get("days", []) if d.get("day_name") == selected_day), None)
subject_names = [s["subject_name"] for s in day_data.get("subjects", [])] if day_data else []

if not subject_names:
    st.sidebar.write("No data available for the selected day.")

init_session_state()

# Function to update the selected video in the session state
def select_video(index):
    st.session_state['selected_video'] = index

daily_youtube_videos = {
        1: {
            "video_type": "Music",
            "link":'https://www.youtube.com/watch?v=ukZj1OdkMYI&list=RDukZj1OdkMYI&start_radio=1'
        },
        2: {
            "video_type": "Music",
            "link": 'https://www.youtube.com/watch?v=nLOuU1YrkgE'
        }
}

# Create a navigation bar with buttons for each video
st.sidebar.header("Daily youtube videos")

st.markdown("""
<style>
/* container for our floating button */
.fab-container {
  position: fixed;
  right: 24px;
  bottom: 24px;
  z-index: 1000;
}
.fab-container button {
  border-radius: 999px !important;
  padding: 0.6rem 1rem !important;
}
</style>
""", unsafe_allow_html=True)

for video_number, video_info in daily_youtube_videos.items():
    st.sidebar.button(f"{video_number} Video {video_info['video_type']}", on_click=select_video, args=(video_number,))

# Display the selected video using an iframe at the top of the page
if st.session_state['selected_video'] is not None:
    selected_video = daily_youtube_videos[st.session_state['selected_video']]
    st.video(selected_video['link'])


if subject_names:
    st.sidebar.write("Subjects:")
    for subject_name in subject_names:
        # try_get_lesson never triggers generation - just checks what's already there.
        lesson = pc.tryGetLesson(STUDENT_NAME, subject_name, school_month, school_week, selected_day)
        if lesson and lesson.get('complete'):
            # Green background for completed subjects
            st.sidebar.markdown(
                f"<div style='background-color: #90EE90; padding: 10px; margin-bottom: 5px;'>{subject_name}</div>",
                unsafe_allow_html=True
            )
        else:
            # Default background for incomplete subjects
            st.sidebar.markdown(
                f"<div style='background-color: #FFCCCB; padding: 10px; margin-bottom: 5px;'>{subject_name}</div>",
                unsafe_allow_html=True
            )
            if st.sidebar.button(f"Open {subject_name}"):
                st.session_state['selected_subject'] = subject_name
                del st.session_state['quiz_grade']
                del st.session_state['lecture_grade']
                st.session_state['quiz_view'] = False
                st.rerun()

if st.session_state['selected_subject']:
    subject_name = st.session_state['selected_subject']
    # generate_lesson fetches the existing lesson, or generates it if this is the first open.
    lesson = pc.generateLesson(STUDENT_NAME, subject_name, school_month, school_week, selected_day)

    if lesson is not None:
        lesson = render_lecture(subject_name, lesson)

        # This will inform the student about their grade on the lecture questions,
        if not st.session_state['quiz_view']:
            render_lecture_grade_feedback()

        # If the student has a passing grade for the lecture questions
        if st.session_state.get('quiz_view', False) and not st.session_state.get('final_attempt'):
            render_quiz(pc, STUDENT_NAME, subject_name, lesson, school_month, school_week, selected_day)

        if st.session_state['final_attempt']:
            render_final_attempt(lesson)
