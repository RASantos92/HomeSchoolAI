import streamlit as st

_DEFAULTS = {
    'close': False,
    'quiz_close': False,
    'selected_subject': None,
    'user_lecture_answers': {},
    'wrong_answer_indexes': {},
    'correct_answers': 0,
    'wrong_quiz_answer_indexes': {},
    'quiz_view': False,
    'quiz_grade': 0,
    'lecture_grade': 0,
    'quiz_attempts': 0,
    'final_attempt': False,
    'highest_grade': 0,
    'selected_video': None,
}


def init_session_state():
    for key, value in _DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = value
