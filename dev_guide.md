# HomeSchoolAI Developer Guide

## Overview

HomeSchoolAI is a personal homeschooling application that serves as a thin client for the empowerHSA curriculum API. It provides two interfaces for students to interact with curriculum content:
- A terminal-based menu for content generation and management
- A Streamlit UI for taking lectures and quizzes

All curriculum generation, storage, and management happens via the empowerHSA REST API. This repository focuses on the client-side experience and local utility functions (like vocabulary extraction).

## Quick Start

### Prerequisites

- Python 3.13 (a pre-populated virtualenv exists at `myenv/`)
- empowerHSA API server running locally (see below)
- Git

### Environment Setup

1. **Activate the virtual environment** (PowerShell):
   ```powershell
   myenv\Scripts\Activate.ps1
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements-dev.txt
   ```
   (includes pytest and all runtime dependencies)

3. **Configure environment variables** (create `.env` from `.env.example`):
   ```
   EMPOWER_HSA_BASE_URL=<empowerHSA API URL>
   EMPOWER_HSA_API_KEY=<API key matching empowerHSA's server>
   myGptKey=<OpenAI API key (optional, only used by dictionary builder)>
   ```

### Running the Application

**The empowerHSA API server must be running first.**

Start it in `D:\empowerHSA`:
```bash
python manage.py runserver
```
(with MongoDB running; see empowerHSA's README)

Then, in this repo:

**Terminal Menu** (for content generation):
```bash
python index.py
```

**Streamlit UI** (student-facing interface):
```bash
streamlit run main_page.py
```
Opens at `http://localhost:8501`

### Testing

Run the full test suite (pure-logic tests, no API calls):
```bash
pytest
```

Run a specific test file:
```bash
pytest tests/test_paths.py
```

Run a specific test:
```bash
pytest tests/test_paths.py::test_year_plan_file
```

## Project Structure

```
.
├── index.py                    # Terminal menu entry point
├── main_page.py               # Streamlit UI entry point
├── test.py                    # Scratch script (not part of test suite)
├── requirements.txt           # Production dependencies
├── requirements-dev.txt       # Dev dependencies (includes pytest)
├── controller/
│   ├── parent.py             # Main client class - thin wrapper over empowerHSA
│   └── data_manipulation.py   # Local vocabulary/dictionary builder
├── services/
│   ├── empower_client.py      # HTTP client for empowerHSA API
│   ├── id_cache.py            # Name ↔ ID mapping cache (data/empower_ids.json)
│   └── paths.py               # Path helpers for local archive (legacy)
├── ui/
│   ├── session.py             # Streamlit session state initialization
│   ├── lecture_view.py        # Lecture rendering component
│   ├── quiz_view.py           # Quiz rendering and grading
│   └── graph_lab.py           # Plotly-based algebra graph lab
├── pages/
│   └── assesment_test.py       # Assessment test multipage entry
├── tests/
│   └── *.py                   # Test suite (pytest)
├── data/
│   ├── dictionary.json        # Built by vocabulary builder (local)
│   ├── empower_ids.json       # Name → ID cache (populated by API calls)
│   ├── yearPlan/              # Legacy archive (not written by current code)
│   └── assessments/           # Legacy archive (not written by current code)
└── z_Data_stock/              # Old generated JSON (superseded formats)
```

## Architecture

### Parent Class (`controller/parent.py`)

The main client interface. Each public method:
1. Resolves student/subject names to IDs (via `id_cache.py`)
2. Calls the corresponding empowerHSA endpoint (via `empower_client.py`)
3. Returns structured data to the UI

**Key methods:**
- `createYearlyLessonPlanForSubject()` → `POST /api/yearly/breakdown/subject`
- `createWeeklyBreakdown()` / `createWeeklyQuiz()` → `POST /api/weekly/breakdown`
- `createDailyBreakDown()` / `generateLesson()` → `POST /api/lesson`
- `tryGetLesson()` → `GET /api/lesson` (status check, never generates)
- `markLessonComplete()` → `POST /api/lesson` (update)
- `recordProgress()` → `POST /api/progress`
- `assessmentTest()` / `getAssessment()` → `POST`/`GET /api/assessment`

See empowerHSA's `dev_guide.md` for the authoritative API contract.

### ID Resolution (`services/id_cache.py`, `services/empower_client.py`)

The empowerHSA API uses numeric IDs (`student_id`, `subject_id`), but this repo's UI works with names. 

`id_cache.py`:
- Maintains a local cache: `data/empower_ids.json` (name → ID)
- Populated on create operations
- Falls back to listing the API on cache miss
- Cache miss loads the full list once, finds the match, caches it

`empower_client.py`:
- Thin `requests` wrapper, one method per API endpoint
- Unwraps empowerHSA's `{"success": bool, "data"|"error"}` envelope
- Raises `EmpowerHSAError` on failure

### Calendar Model

The school year runs **10 months** (August–May) with exactly **4 weeks per month**.

- `week_of_the_month` is **1-based** (1-4) at the Parent/API boundary
- Streamlit UI uses zero-indexed weeks internally; conversion to 1-based happens at the Parent call site, not inside Parent

### Streamlit UI (`main_page.py`, `ui/`)

`main_page.py` is a thin entrypoint:
- Page config and sidebar day/subject picker
- Completion coloring via `Parent.tryGetLesson()` (never triggers generation)
- Routes to render functions in `ui/`

**Rendering modules** (`ui/`):
- `session.py` — `init_session_state()`, all session defaults in one place
- `lecture_view.py` — `render_lecture()`: renders lecture text (split on `[p]`) and lecture-check questions
- `quiz_view.py` — `render_quiz()`: gated 100%-lecture-questions pass, progress persistence, 3-attempts final-attempt flow
- `graph_lab.py` — Full-page Plotly algebra tool (Slope/intercept sliders, click-to-plot)

**Note:** `ui/` is a plain package, not Streamlit's `pages/` convention — helper modules must not live in `pages/` or they'll be auto-registered as sidebar pages. `pages/assesment_test.py` is the one exception (legitimate multipage entry for self-grading assessments).

### Local Archive (`data/`)

Historical archive of pre-empowerHSA-migration content:
- `yearPlan/`, `assessments/` — legacy JSON (imported into empowerHSA via its `import_legacy_json` command)
- `dictionary.json` — **still actively built** by `controller/data_manipulation.py` (local vocabulary extraction)
- `empower_ids.json` — **still actively used** as the name→ID cache

**No current code reads/writes the legacy archive** except the dictionary and ID cache. `services/paths.py` still defines archive path shapes for reference/tooling.

### Vocabulary Builder (`controller/data_manipulation.py`)

Fully local utility (no empowerHSA dependency):
1. Scans already-generated lecture text for "big words"
2. Looks up definitions via the free dictionaryapi.dev API
3. Builds `data/dictionary.json`

Runs independently of the main curriculum pipeline.

## Common Development Tasks

### Adding a New API Endpoint

1. Add the method to `services/empower_client.py` (thin wrapper around `requests`)
2. Add the corresponding method to `controller/parent.py` (ID resolution + call)
3. Add tests in `tests/`
4. Wire it into the UI where needed

### Testing an API Call

Use `pytest` with the pure-logic test suite (no live API required):
```bash
pytest tests/test_paths.py -v
```

For integration testing, ensure empowerHSA is running and add tests that call `Parent` directly.

### Debugging Streamlit

Run with verbose logging:
```bash
streamlit run main_page.py --logger.level=debug
```

Check `streamlit.config.toml` for additional logging options.

### Updating UI Components

All rendering is in `ui/`:
- `lecture_view.py` — Lecture + lecture-check rendering
- `quiz_view.py` — Quiz flow, grading, feedback
- `graph_lab.py` — Algebra graph tool

Call `Parent` methods to fetch data, then pass to render functions.

### Adding a New Subject or Feature

1. If it requires new empowerHSA endpoints, add them there first (see empowerHSA's dev_guide.md)
2. Add wrapper methods to `services/empower_client.py` and `controller/parent.py`
3. Add UI rendering in `ui/` (or `pages/` if it's a new multipage entry)
4. Test with the terminal menu (`index.py`) first, then Streamlit

## Dependencies

**Runtime** (`requirements.txt`):
- `requests` — HTTP client for empowerHSA
- `streamlit` — Web UI framework
- `plotly` — Interactive graphing for algebra
- `python-dotenv` — Environment variable loading

**Dev** (`requirements-dev.txt` adds):
- `pytest` — Test runner
- `pytest-cov` — Coverage reporting (optional)

## Environment Variables (`.env`)

```
EMPOWER_HSA_BASE_URL=http://localhost:8000    # empowerHSA API URL
EMPOWER_HSA_API_KEY=dev-key-123               # Must match empowerHSA's API_KEY
myGptKey=sk-...                               # Optional, only for vocabulary builder
```

## Troubleshooting

### "Connection refused" / API calls fail
- Ensure empowerHSA is running: `python manage.py runserver` in `D:\empowerHSA`
- Check `EMPOWER_HSA_BASE_URL` and `EMPOWER_HSA_API_KEY` in `.env`
- Verify MongoDB is running (required by empowerHSA)

### Streamlit not reloading after changes
- Force refresh: `Ctrl+R` in browser
- Restart the server: `Ctrl+C` and `streamlit run main_page.py` again

### ID cache out of sync
- Delete `data/empower_ids.json`
- The next API call will rebuild the cache by listing students/subjects

### Tests fail with "no such file or directory"
- Ensure you're running from the repo root: `cd D:\GenAI\HomeSchoolingAi`
- Ensure the virtualenv is activated

## Further Reading

- **empowerHSA dev guide** (`D:\empowerHSA\dev_guide.md`) — Authoritative API contract, field mappings, generation pipeline staging rules
- **CLAUDE.md** (this repo) — Project-specific guidance for Claude Code
- **Streamlit docs** — https://docs.streamlit.io
- **Plotly docs** — https://plotly.com/python

## Support

For questions about this repo's architecture or API integration, check CLAUDE.md.  
For questions about curriculum generation or empowerHSA endpoints, see empowerHSA's dev_guide.md.
