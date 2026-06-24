from __future__ import annotations

from decimal import Decimal


def _norm_text(x: object) -> str:
    if x is None:
        return ""
    s = str(x)
    if hasattr(s, "normalize"):
        try:
            s = s.normalize("NFKC")  # type: ignore[attr-defined]
        except Exception:
            pass
    return " ".join(s.strip().lower().split())


def _as_decimal(x: object) -> Decimal | None:
    if x is None or x == "":
        return None
    try:
        return Decimal(str(x).strip())
    except Exception:
        return None


def grade_answer(*, question_type: str, correct_answer: object, answer: object, config: dict) -> bool:
    """
    Pure grading function: returns True/False.

    Supported types:
    - multiple_choice: compares normalized choice id (string)
    - boolean: compares boolean-ish
    - numeric: Decimal compare with optional tolerance (config.tolerance)
    - short_text: exact match after normalization; accepts list of acceptable strings
    """
    qt = str(question_type or "").strip()
    if qt == "multiple_choice":
        return _norm_text(answer) == _norm_text(correct_answer)

    if qt == "boolean":
        def _to_bool(v: object) -> bool | None:
            if isinstance(v, bool):
                return v
            s = _norm_text(v)
            if s in ("true", "t", "1", "yes", "y"):
                return True
            if s in ("false", "f", "0", "no", "n"):
                return False
            return None

        return _to_bool(answer) is not None and _to_bool(answer) == _to_bool(correct_answer)

    if qt == "numeric":
        a = _as_decimal(answer)
        c = _as_decimal(correct_answer)
        if a is None or c is None:
            return False
        tol = _as_decimal((config or {}).get("tolerance"))
        if tol is None:
            return a == c
        return abs(a - c) <= tol

    # short_text (default)
    if isinstance(correct_answer, list):
        targets = [_norm_text(x) for x in correct_answer]
        return _norm_text(answer) in {t for t in targets if t}
    return _norm_text(answer) == _norm_text(correct_answer)

