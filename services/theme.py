"""Local UI color-theme preference for the student-facing Streamlit app.

Saved to data/theme_preference.json so the student's chosen colors persist
across sessions/restarts. Purely a display setting - unrelated to empowerHSA
content, same pattern as the other small local JSON files in services/.
"""
import json

from services import paths

DEFAULT_THEME = "Dark"


def load_theme() -> str:
    path = paths.theme_file()
    if not path.exists():
        return DEFAULT_THEME
    with open(path, "r") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            return DEFAULT_THEME
    return data.get("theme", DEFAULT_THEME)


def save_theme(theme_name: str) -> None:
    path = paths.theme_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump({"theme": theme_name}, f, indent=4)
