import json
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

REQUIRED = {
    "id", "difficulty", "family", "feasible", "document",
    "instruction", "expected_answer", "why_hard",
}


def validate_record(record: object) -> list[str]:
    if not isinstance(record, dict):
        return ["record must be a JSON object"]
    errors = []
    missing = REQUIRED - record.keys()
    if missing:
        errors.append(f"missing fields: {', '.join(sorted(missing))}")
    answer = record.get("expected_answer")
    if not isinstance(answer, dict):
        return errors + ["expected_answer must be an object"]
    status, items = answer.get("status"), answer.get("items")
    if status not in ("ok", "cannot_complete"):
        errors.append("expected_answer.status must be ok or cannot_complete")
    if not isinstance(items, list):
        return errors + ["expected_answer.items must be a list"]
    if status == "cannot_complete" and items:
        errors.append("cannot_complete requires empty items")
    for index, item in enumerate(items, 1):
        if not isinstance(item, dict):
            errors.append(f"item {index} must be an object")
            continue
        deadline = item.get("deadline")
        if deadline in (None, ""):
            continue
        try:
            if not isinstance(deadline, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", deadline):
                raise ValueError("expected YYYY-MM-DD")
            date.fromisoformat(deadline)
        except ValueError:
            errors.append(f"item {index}: invalid deadline {deadline!r}")
    return errors


def reject_constant(value: str) -> None:
    raise ValueError(f"invalid JSON constant: {value}")


def main(path: Path) -> int:
    errors, counts = [], Counter()
    expected = {"easy": 4, "hard": 2, "adversarial": 2}
    try:
        with path.open(encoding="utf-8") as lines:
            for number, line in enumerate(lines, 1):
                try:
                    record = json.loads(line, parse_constant=reject_constant)
                except ValueError as exc:
                    errors.append(f"line {number}: invalid JSON: {exc}")
                    continue
                errors.extend(f"line {number}: {error}" for error in validate_record(record))
                if isinstance(record, dict):
                    difficulty = record.get("difficulty")
                    if isinstance(difficulty, str):
                        counts[difficulty] += 1
                    else:
                        errors.append(f"line {number}: difficulty must be a string")
    except (OSError, UnicodeError) as exc:
        errors.append(f"cannot read {path}: {exc}")
    if counts != expected:
        errors.append(f"difficulty distribution: {dict(counts)}; expected {expected}")
    for error in errors:
        print(f"FAIL: {error}")
    if errors:
        return 1
    print(f"PASS: {sum(counts.values())} tasks; difficulty={dict(counts)}")
    return 0


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "data/tasks.jsonl"
    raise SystemExit(main(path))
