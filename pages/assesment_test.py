import streamlit as st

from controller.parent import Parent

pc = Parent()

STUDENT_NAME = "Hayden"
ASSESSMENT_NUMBER = 18

data = pc.getAssessment(STUDENT_NAME, ASSESSMENT_NUMBER) or []

main_subjects = [d.get("subject") for d in data]

subject_selection = st.sidebar.selectbox("Choose a subject", main_subjects)

selected_subject = None
for entry in data:
    if entry.get("subject") == subject_selection:
        selected_subject = entry.get("questions", [])
        break

# Dictionary to hold user's answers
user_answers = {}
# Flag to check if the test has been submitted
submitted = st.session_state.get('submitted', False)
wrong_answers = []
if "correct_answers" not in st.session_state and "total_questions" not in st.session_state:
    st.session_state['correct_answers'] = 0
    st.session_state['total_questions'] = 10
if selected_subject:
    st.title(f"Test for {subject_selection}")

    # Only render questions if the test has not been submitted yet
    if not submitted:
        for index, question_data in enumerate(selected_subject):
            st.write(f"Question {index + 1}: {question_data['question']}")

            # Use the question index as the unique key for each set of radio buttons
            user_answers[index] = st.radio(
                f"Select answer for question {index + 1}:",
                options=question_data['options'],
                key=f"question_{index}"
            )

        # Submit button
    if st.button("Submit"):
            correct_answers = 0
            total_questions = len(selected_subject)

            for index, question_data in enumerate(selected_subject):
                # Compare user's answer with the correct answer
                if user_answers[index][0] == question_data['answer'][0]:
                    correct_answers += 1
                else:
                    wrong_answers.append(question_data.get('topic'))

            # Store submission state in session_state
            st.session_state['submitted'] = True
            st.session_state['correct_answers'] = correct_answers
            st.session_state['total_questions'] = total_questions
            st.write(f"You got {correct_answers} out of {total_questions} correct!")
    elif submitted:
        # If already submitted, show score
        correct_answers = st.session_state['correct_answers']
        total_questions = st.session_state['total_questions']
        st.write(f"You got {correct_answers} out of {total_questions} correct!")
        st.write(f"Your score: {(correct_answers / total_questions) * 100:.2f}%")

# Custom CSS to reduce the padding between the radio buttons
st.markdown("""
    <style>
    .stRadio > div {
        gap: 10px;  /* Decrease this to reduce the spacing */
    }
    </style>
""", unsafe_allow_html=True)
