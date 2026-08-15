# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A personal homeschooling tool for a single student. All curriculum generation and storage (yearly
subject plans → weekly breakdowns → daily lectures + quizzes, plus assessment tests) now happens in
a separate app, **empowerHSA** (`D:\empowerHSA`, a Django + MongoDB REST API) — this repo is a thin
client over that API plus two front ends for the student: a terminal menu (`index.py`) and a
Streamlit UI (`main_page.py`) for actually taking lectures/quizzes. See empowerHSA's own
`dev_guide.md` for the authoritative API contract (endpoints, request/response shapes, the
generation pipeline's staging rules).

The one piece that stays fully local: `controller/data_manipulation.py`'s vocabulary/dictionary
builder, which scans already-generated lecture text for big words and looks up definitions via the
free dictionaryapi.dev API — unrelated to empowerHSA.

## Commands

A pre-populated virtualenv already exists at `myenv/` (Python 3.13).

Activate the env (PowerShell):
```
myenv\Scripts\Activate.ps1
```

Install dependencies (`requirements-dev.txt` adds pytest on top of `requirements.txt`):
```
pip install -r requirements-dev.txt
```

**The empowerHSA API server must be running** (`python manage.py runserver` in `D:\empowerHSA`,
with a reachable MongoDB — see that repo's README) for anything in this repo that generates or
fetches curriculum content to work.

Run the terminal content-generation menu (calls the empowerHSA API):
```
python index.py
```

Run the student-facing Streamlit app:
```
streamlit run main_page.py
```

Run the test suite (pure-logic tests only — no OpenAI calls, no network, no cost):
```
pytest
```
Run a single test file or case with `pytest tests/test_paths.py` or `pytest tests/test_paths.py::test_year_plan_file`.

`test.py` is a scratch script (string-splitting experiment), not part of the automated test suite.

Requires a `.env` file (copy `.env.example`) with:
- `EMPOWER_HSA_BASE_URL` / `EMPOWER_HSA_API_KEY` — the empowerHSA server this repo talks to;
  `EMPOWER_HSA_API_KEY` must match the `API_KEY` empowerHSA's own `.env` was started with.
- `myGptKey` — only used by the local dictionary-builder feature, not curriculum generation.

## Architecture

**Thin client (`controller/parent.py`, class `Parent`)**
`Parent` no longer calls OpenAI or writes local JSON — every method resolves the student/subject
names this repo's UI and CLI work with into the ids empowerHSA's API needs, then calls through
`services/empower_client.py`. Method-to-endpoint mapping: `createYearlyLessonPlanForSubject` →
`POST /api/yearly/breakdown/subject`; `createWeeklyBreakdown`/`createWeeklyQuiz` →
`POST /api/weekly/breakdown` (one call now covers the topic plan, day-by-day breakdown, *and*
end-of-week quiz — the API stages all three behind this one endpoint); `createDailyBreakDown`/
`generateLesson` → `POST /api/lesson` per subject (returns quiz + lecture_questions in one shot, no
separate lazy-generation step); `tryGetLesson` → `GET /api/lesson` (never triggers generation, used
for UI status checks); `markLessonComplete` → the lesson-update path of `POST /api/lesson`;
`recordProgress` → `POST /api/progress`; `assessmentTest`/`getAssessment` →
`POST`/`GET /api/assessment`; `updateWeeklylessonPlanWithNewSubject` (mid-year subject addition) →
`generate_yearly_breakdown` called with the student's existing id, which merges into their existing
months server-side.

**id resolution (`services/id_cache.py`, `services/empower_client.py`)** — the API is id-keyed
(`student_id`/`subject_id`) but this repo's UI/CLI operate on names. `id_cache.py` keeps a small
local cache (`data/empower_ids.json`, name → id) populated on create, falling back to listing the
API and matching by name on a cache miss — it's just a lookup cache, not a second source of truth;
all actual content lives in empowerHSA. `empower_client.py`'s `EmpowerHSAClient` is a thin
`requests` wrapper, one method per endpoint, unwrapping the `{"success": bool, "data"|"error"}`
envelope and raising `EmpowerHSAError` on failure.

**Calendar model** — the school year runs 10 months, August–May, with exactly 4 weeks per month.
`week_of_the_month` is 1-based (1-4) at the `Parent`/API boundary; the Streamlit UI's own
zero-indexed week convention is converted to 1-based right where it calls into `Parent`, not inside
`Parent` itself.

**Local archive (`data/`)** — `data/yearPlan/...` and `data/assessments/...` still exist on disk as
a historical archive of content generated before the empowerHSA migration (imported into empowerHSA
via that repo's `import_legacy_json` management command — see its dev_guide.md and CLAUDE.md for the
field-mapping). Nothing in this repo reads or writes that archive anymore except
`data/dictionary.json` (built by `controller/data_manipulation.py`, still fully local) and
`data/empower_ids.json` (the id cache above). `services/paths.py` still defines the archive's path
shapes for reference/tooling, even though `Parent` no longer builds paths through it.

**Services (`services/`)**
- `empower_client.py` (see above)
- `id_cache.py` (see above)
- `paths.py` — path shapes for the local archive and the dictionary/id-cache files (no longer used
  for reading/writing curriculum content)

**Streamlit UI (`main_page.py`, `ui/`, `pages/assesment_test.py`)**
`main_page.py` is a thin entrypoint: page config, the `?graph=1` popup route, the sidebar day/subject
picker with completion coloring (via `Parent.tryGetLesson`, which never triggers generation), and
dispatch into the extracted render functions. The actual rendering lives in `ui/`:
- `ui/session.py` — `init_session_state()`, all default `st.session_state` keys in one place
- `ui/graph_lab.py` — the "Graph Lab" (Plotly, slope/intercept sliders + click-to-plot), rendered
  full-page when opened via the Algebra subject's fab button (`?graph=1`, opens in a new tab)
- `ui/lecture_view.py` — `render_lecture()`: renders one lesson's lecture text (split on `[p]`) and
  lecture-check questions; the lesson passed in already has `quiz`/`lecture_questions` filled in by
  `Parent.generateLesson`, so there's no lazy-generation step here anymore
- `ui/quiz_view.py` — `render_quiz()`, `render_lecture_grade_feedback()`, `render_final_attempt()`:
  the quiz gated behind a 100%-on-lecture-questions pass, progress persistence via
  `Parent.recordProgress`, completion via `Parent.markLessonComplete`, and the 3-attempts
  final-attempt flow

Note `ui/` is a plain sibling package, not Streamlit's `pages/` convention — anything dropped into
`pages/` is auto-registered as a navigable sidebar page, so helper modules must not live there.
`pages/assesment_test.py` is the one legitimate use of that convention: a separate Streamlit
multipage entry that fetches one assessment (`Parent.getAssessment`) for self-grading.

**`z_Data_stock/`** is a dump of older/superseded generated JSON (mixed ad hoc formats from earlier
iterations of the data layout) — not read by any current code path.
