lecture =  "Today, we will dive into basic algebraic principles. This will include understanding variables, constants, and the importance of operations in algebraic expressions. Let's start with **variables and constants**. \n\nA variable is a letter or symbol that represents a number that can change. For instance, in the expression x + 3 = 5, the letter x is a variable. It can take on different values. A constant, on the other hand, is a fixed value. In the same expression, the numbers 3 and 5 are constants; they do not change. Understanding the difference is crucial because variables allow us to create general expressions that can describe many situations.\n\nThink of variables as placeholders that can be replaced by numbers. In equations, they serve as unknowns that we are trying to solve for. Now, let's pause for a moment here to reflect on the definitions of variables and constants. [p] \n\nLet\u2019s now move on to the **order of operations**. This is a critical concept in all areas of mathematics, including algebra. Order of operations tells us the sequence in which we should perform operations to get the correct answer. A common acronym to remember this order is PEMDAS: \n\n- P stands for Parentheses. \n- E stands for Exponents. \n- MD stands for Multiplication and Division (from left to right). \n- AS stands for Addition and Subtraction (from left to right). \n\nFor example, consider the expression 3 + 6 \u00d7 (5 + 4) \u00f7 3 - 7. According to PEMDAS, we first calculate the expression in the parentheses: (5 + 4) gives us 9. Then we do multiplication and division from left to right: 6 \u00d7 9 = 54, and then 54 \u00f7 3 = 18. Now we add 3 to 18 to get 21, and finally, we subtract 7 to arrive at our final answer: 14. Keeping the order of operations in mind ensures we don\u2019t make mistakes while solving equations. [p] \n\nMoving on to our final subtopic: **simple equations**. A simple equation is an equation that has one equal sign and can be solved for a variable. For example, in the equation x + 2 = 5, we can isolate the variable x by subtracting 2 from both sides; thus, we find x = 3. Solving equations is about keeping the equation balanced\u2014what we do to one side must be done to the other, maintaining the equality. \n\nThis process of solving equations is fundamental in algebra, and mastering it will allow you to tackle more complex algebraic problems in the future. Let\u2019s take another pause to absorb this material. [p] \n\nNow that we have discussed each of the subtopics, let\u2019s briefly summarize. You learned about **variables** as symbols that represent numbers, **constants** as fixed values, the importance of maintaining the *order of operations* through PEMDAS, and how to solve **simple equations** by using basic arithmetic operations while keeping the balance of equations in mind. Understanding these basic principles provides a strong foundation for further algebra studies.\n\nAs you practice these concepts, keep referring back to these definitions and procedures, and don\u2019t hesitate to reach out if you have questions. Overall, mastering these ideas will enhance your confidence and competence in algebra. \n \nReferences:\n1. Variables and Constants: https://en.wikipedia.org/wiki/Variable_(mathematics)\n2. Order of Operations: https://en.wikipedia.org/wiki/Order_of_operations\n3. Simple Equations: https://en.wikipedia.org/wiki/Equation\n\nMain Topic: Review of Basic Algebraic Principles\nSub Topics: Variables and Constants, Order of Operations, Simple Equations"

import time
import requests
import re
import os

from collections import defaultdict

from pathlib import Path
import json
from datetime import datetime
from services import paths

class DataManipulation:
    def __init__(self):
        pass

    def scan_subject_lectures(self, lecture, letter_count: int = 8):
        # \b\w+\b finds word tokens; adjust if you want to exclude digits/underscores
        tokens = re.findall(r"\b[A-Za-z']+\b", lecture)
        groups = defaultdict(set)
        for w in tokens:
            if len(w) >= letter_count:
                groups[len(w)].add(w)
        return dict(groups)
    
    @staticmethod    
    def _flatten_words_by_length_map(words_by_len: dict[int, set[str] | list[str]]):
        """Turn {length: {words}} into a sorted, unique list of lowercase words."""
        bag = set()
        for _, words in words_by_len.items():
            for w in words:
                w_clean = (w or "").strip().strip(",.;:!?()[]{}'\"").lower()
                if w_clean:
                    bag.add(w_clean)
        return sorted(bag)
    
    @staticmethod
    def _fetch_definition(word: str, timeout=8):
        """
        Use the free Dictionary API (https://dictionaryapi.dev).
        Returns (definition, part_of_speech) or (None, None) if not found.
        """
        url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}"
        try:
            r = requests.get(url, timeout=timeout)
            if r.status_code != 200:
                return None, None
            data = r.json()
            # Structure: [{word, meanings:[{partOfSpeech, definitions:[{definition, example,...}], ...}], ...}]
            if not isinstance(data, list) or not data:
                return None, None

            for meaning in data[0].get("meanings", []):
                defs = meaning.get("definitions", [])
                if defs:
                    # Take the first concise definition available
                    d = defs[0].get("definition")
                    pos = meaning.get("partOfSpeech")
                    if d:
                        return d, pos
            return None, None
        except Exception:
            return None, None

    def build_dictionary(self,
                            words_by_len: dict[int, set[str] | list[str]],
                            json_path: str = str(paths.dictionary_file()),
                            sleep_between: float = 0.25,
                            include_pos: bool = True,
                            overwrite: bool = False) -> dict:
        """
        Update data/dictionary.json with definitions for the given words.

        Returns a small stats dict for convenience: {"added": ..., "updated": ..., "skipped": ..., "total": ...}
        """
        # --- load existing file (if any) ---
        p = Path(json_path)
        p.parent.mkdir(parents=True, exist_ok=True)

        existing: dict[str, dict] = {}
        if p.exists():
            try:
                with p.open("r", encoding="utf-8") as f:
                    raw = json.load(f) or {}
            except Exception:
                raw = {}

            # normalize: allow {"word":"def"} or {"word":{"definition":...,"pos":...}}
            for k, v in raw.items():
                if isinstance(v, str):
                    existing[k.lower()] = {"definition": v, "pos": None}
                elif isinstance(v, dict):
                    existing[k.lower()] = {
                        "definition": v.get("definition"),
                        "pos": v.get("pos")
                    }
                else:
                    existing[k.lower()] = {"definition": None, "pos": None}

        # --- collect new/updated entries ---
        words = self._flatten_words_by_length_map(words_by_len)
        added = updated = skipped = 0

        for w in words:
            # skip if we already have a definition and we're not overwriting
            if not overwrite and (w in existing and existing[w].get("definition")):
                skipped += 1
                continue

            definition, pos = self._fetch_definition(w)
            if definition:
                payload = {"definition": definition}
                if include_pos:
                    payload["pos"] = pos
                payload["last_updated"] = datetime.utcnow().isoformat() + "Z"
                payload["source"] = "dictionaryapi.dev"

                if w in existing and existing[w].get("definition"):
                    existing[w].update(payload)
                    updated += 1
                else:
                    existing[w] = payload
                    added += 1
            else:
                # keep placeholder if word has no definition (optional)
                if w not in existing:
                    existing[w] = {"definition": None, "pos": None}
                skipped += 1

            time.sleep(sleep_between)

        # --- atomic write ---
        tmp = p.with_suffix(p.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(tmp, p)

        return {"added": added, "updated": updated, "skipped": skipped, "total": len(existing)}

    def collect_lectures(self, student_name: str, base_dir: str = None):
        """
        Traverse data/yearPlan/<student_name>/weeklyBreakdown/** and pull out all lesson['lecture'] strings.
        Returns a list of dicts: {student, month, week, day, subject, lecture}.
        """
        
        EXCLUDE_FILES = {paths.PROGRESS_FILENAME, paths.BREAKDOWN_FILENAME}

        weekly = (Path(base_dir) / student_name / "weeklyBreakdown") if base_dir else paths.weekly_breakdown_root(student_name)
        if not weekly.exists():
            raise FileNotFoundError(f"Not found: {weekly}")

        results = []

        # months like 08, 09, 10, 11, 12, 01, 02, 03, 04, 05 — but we just iterate whatever exists
        for month_dir in sorted([p for p in weekly.iterdir() if p.is_dir() and p.name.isdigit()]):
            # weeks 0-3 (again, iterate what exists)
            for week_dir in sorted([p for p in month_dir.iterdir() if p.is_dir() and p.name.isdigit()]):
                # days (Monday…Friday folders)
                for day_dir in sorted([p for p in week_dir.iterdir() if p.is_dir()]):
                    for json_path in day_dir.glob("*.json"):
                        if json_path.name in EXCLUDE_FILES:
                            continue
                        try:
                            with json_path.open(encoding="utf-8") as f:
                                data = json.load(f)
                        except Exception:
                            # skip malformed JSON but keep going
                            continue

                        # Normalize to a list of lesson dicts and collect lecture text(s)
                        lessons = []
                        if isinstance(data, dict):
                            lessons = data.get("lessons") or []
                        elif isinstance(data, list):
                            # Common pattern in your files: top-level list with one item that has "lessons"
                            if data and isinstance(data[0], dict) and "lessons" in data[0]:
                                lessons = data[0]["lessons"]
                            else:
                                # In case each item IS a lesson
                                lessons = [x for x in data if isinstance(x, dict)]

                        for lesson in lessons:
                            lecture = lesson.get("lecture")
                            if lecture:
                                results.append({
                                    # "student": student_name,
                                    # "month": month_dir.name,     # e.g., "08"
                                    # "week": week_dir.name,       # "0".."3"
                                    # "day": day_dir.name,         # "Monday".."Friday"
                                    # "subject": json_path.stem,   # e.g., "Astronomy"
                                    "lecture": lecture,
                                })

        return results