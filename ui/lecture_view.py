import streamlit as st
from ui.graph_lab import render_graph_fab


def render_lecture(subject_name, lesson):
    """Render one lesson's lecture content and lecture-question grading.

    `lesson` is expected to already have `quiz`/`lecture_questions` filled in -
    the API's generate_lesson call returns both in one shot, so there's no
    separate lazy-generation step here anymore.
    """
    st.title(subject_name)
    lecture_chapters = lesson['lecture'].split("[p]")
    st.session_state['total_lecture_questions'] = len(lesson['lecture_questions'])

    if not st.session_state.get('quiz_view', False):
        st.subheader("Lecture")
        for chapter in lecture_chapters:
            st.markdown(rf"""
                        <p>{chapter}<p>
                        """, unsafe_allow_html=True)

        lecture_questions = lesson['lecture_questions']
        user_lecture_answers = {}
        st.write("Lecture Questions:")
        for index, question in enumerate(lecture_questions):
            st.write(question['question'])
            # This checks if the question has been answered wrong, if the student is close then we display that this is the question that was wrong.
            if index in st.session_state['wrong_answer_indexes'] and st.session_state['close']:
                st.markdown(f'<p style="color:red;">{st.session_state["wrong_answer_indexes"][index]}<p>', unsafe_allow_html=True)
            user_lecture_answers[index] = st.radio(
                "Select answer for the question:",
                options=question['options'],
                key=f"question_{index}"
            )

        if st.button("Submit Lecture Questions"):
            correct_answers = 0
            wrong_answers_lecture_questions = []
            for index, question in enumerate(lesson['lecture_questions']):
                if user_lecture_answers[index][0] == question['answer'][0]:
                    if index in st.session_state['wrong_answer_indexes']:
                        del st.session_state['wrong_answer_indexes'][index]
                    correct_answers += 1
                else:
                    st.session_state['wrong_answer_indexes'][index] = "The answer to this questions is wrong."
                    wrong_answers_lecture_questions.append(index)
            st.session_state['lecture_submitted'] = True
            st.session_state['correct_answers'] = correct_answers
            st.session_state['lecture_grade'] = round((correct_answers / st.session_state['total_lecture_questions']) * 100, 2)
            st.session_state['number_of_wrong_answers_lecture_questions'] = len(wrong_answers_lecture_questions)

    # --- only for Algebra subjects ---
    if subject_name.lower() == "algebra":
        render_graph_fab()

    return lesson
