# HomeSchoolingAi

An AI-generated homeschool curriculum tool for a single student. It uses the OpenAI API to generate a full year of curriculum — yearly subject plans, weekly breakdowns, daily lectures, and quizzes — and a Streamlit app for the student to actually work through the lectures and be graded.

There are two entry points over the same generation logic:
- `index.py` — a terminal menu that drives content generation (creates year plans, weekly plans, daily lectures, quizzes, assessment tests).
- `main_page.py` — a Streamlit app where the student reads lectures, answers lecture-check questions, and takes quizzes.

## Setup

**1. Create and activate a virtual environment**

```
python -m venv myenv
myenv\Scripts\Activate.ps1
```

**2. Install dependencies**

```
pip install -r requirements.txt
```

For development (adds pytest):
```
pip install -r requirements-dev.txt
```

**3. Configure your OpenAI API key**

Create a `.env` file in the project root:

```
myGptKey=sk-...
```

## Usage

**Generate content** (year plans, weekly breakdowns, lectures, quizzes, assessments):

```
python index.py
```

Follow the menu prompts. Content generation must happen roughly in order: a yearly plan for a subject, then a weekly plan for the student, then a weekly breakdown for a given month/week, then daily lecture/quiz content — later stages read the JSON written by earlier ones.

**Run the student-facing app:**

```
streamlit run main_page.py
```

## Data

All generated content is written as plain JSON files under `data/yearPlan/<student_name>/`, organized by month (`08`–`05`, skipping summer) and week (`0`–`3`). See [CLAUDE.md](CLAUDE.md) for the full directory layout and generation pipeline if you're working on the code.

## Testing

```
pytest
```

Covers the pure-logic pieces (path building, data reshaping, word scanning) with no OpenAI calls and no network access, so it's free to run. `Parent`'s generation methods aren't covered — testing those would mean mocking the OpenAI client or spending real API credits.

## Notes

- Content generation calls the OpenAI API and incurs real cost per call.
