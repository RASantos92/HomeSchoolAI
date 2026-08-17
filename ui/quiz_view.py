import streamlit as st


def inject_scroll_script():
    scroll_script = """
    <script>
        function scrollToTop() {
            var body = window.parent.document.querySelector('.main');
            if (body) {
                body.scrollTo(0, 0);
            }
        };
        scrollToTop();
    </script>
    """
    st.components.v1.html(scroll_script, height=0)


def toggle_start_quiz():
    st.session_state['quiz_view'] = not st.session_state['quiz_view']
    inject_scroll_script()


def toggle_final_attempt(pc, lesson):
    pc.markLessonComplete(lesson['_id'])
    st.session_state['final_attempt'] = True


def render_lecture_grade_feedback():
    """Messaging shown once the student has submitted the lecture questions, gating access to the quiz."""
    if st.session_state['lecture_grade'] == 100:
        if st.session_state.get('quiz_view', False):
            st.write("Good Luck on the test!!")
            st.button("Review Lecture", on_click=toggle_start_quiz)
        else:
            st.write("Awesome job. 100% correct!")
            st.button("Attempt Quiz", on_click=toggle_start_quiz)
    elif st.session_state['lecture_grade'] >= 70:
        st.write("You are close to 100%! You need 100% to take the quiz and move on.")
        st.session_state['close'] = True
    elif st.session_state['lecture_grade'] > 0:
        st.write("You are far from 100%. You need 100% to take the quiz and move on.")
        st.session_state['close'] = False


def render_quiz(pc, student_name, subject_name, lesson, month, week_number, day):
    st.subheader("Quiz Time")
    user_quiz_answers = {}
    st.session_state['correct_answers'] = 0
    st.session_state["total_questions_quiz_questions"] = len(lesson['quiz'])
    st.header("Quiz:")
    for index, question in enumerate(lesson['quiz']):
        st.write(f"Question {index}: \n {question['question']}")
        if index in st.session_state['wrong_quiz_answer_indexes'] and st.session_state['quiz_close']:
            st.markdown(f'<p style="color:red;">{st.session_state["wrong_quiz_answer_indexes"][index]}<p>', unsafe_allow_html=True)
        user_quiz_answers[index] = st.radio(
            f"Select answer for question {index}:",
            options=question['options'],
            key=f"quiz_question_{index}"
        )

    if st.button("Submit Quiz"):
        correct_answers = 0
        wrong_answers_quiz_questions = []
        for index, question in enumerate(lesson['quiz']):
            if user_quiz_answers[index][0] == question['answer'][0]:
                if index in st.session_state['wrong_quiz_answer_indexes']:
                    del st.session_state['wrong_quiz_answer_indexes'][index]
                correct_answers += 1
            else:
                st.session_state['wrong_quiz_answer_indexes'][index] = "This answer is incorrect"
                wrong_answers_quiz_questions.append(index)
        st.session_state['quiz_submitted'] = True
        st.session_state['correct_answers'] = correct_answers
        grade = round((correct_answers / st.session_state['total_questions_quiz_questions']) * 100, 2)
        st.session_state['quiz_grade'] = grade
        st.session_state['wrong_answers_quiz_questions'] = (st.session_state.get("wrong_answers_quiz_questions", 0) + len(wrong_answers_quiz_questions))
        st.session_state['quiz_attempts'] += 1
        st.session_state['highest_grade'] = max(grade, st.session_state['highest_grade'])
        pc.recordProgress(
            student_name, subject_name, month, week_number, day,
            quiz_grade=grade,
            wrong_answers=[str(i) for i in wrong_answers_quiz_questions],
            quiz=lesson['quiz'],
        )
        if (st.session_state['quiz_attempts'] + 1) > 3:
            toggle_final_attempt(pc, lesson)

    if st.session_state.get('quiz_submitted'):
        if st.session_state['quiz_grade'] == 100:
            pc.markLessonComplete(lesson['_id'])

            st.write("Marked as complete!")
            st.write('Awesome job. You finished the quiz with a 100%')
            st.subheader("Summary")
            st.write(lesson.get("summary", "No summary available"))
        elif st.session_state['quiz_grade'] >= 70:
            st.write("You are close to 100%, keep going!")
            st.session_state['quiz_close'] = True
        else:
            st.write("You are far off from 100%")
            st.session_state['quiz_close'] = False


def render_final_attempt(lesson):
    st.title("That was your final attempt at the quiz")
    st.subheader(f"Your best quiz score was a {st.session_state['quiz_grade']}%")
    st.button("Review Lecture", on_click=toggle_start_quiz)

    st.subheader("Wikipedia References")
    for reference in lesson.get("wikipedia_references", []):
        st.write(f"- ({reference})")
