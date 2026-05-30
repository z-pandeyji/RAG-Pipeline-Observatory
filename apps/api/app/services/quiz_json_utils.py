import json
import re


SMART_QUOTES = {
    "\u201c": '"',
    "\u201d": '"',
    "\u2018": "'",
    "\u2019": "'",
}


def cleanup_json_text(raw: str) -> str:
    cleaned = raw.strip()
    for source, replacement in SMART_QUOTES.items():
        cleaned = cleaned.replace(source, replacement)
    cleaned = re.sub(r"```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.replace("```", "")
    cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)
    return cleaned.strip()


def extract_json_candidate(raw: str) -> str:
    cleaned = cleanup_json_text(raw)
    candidates = _balanced_json_values(cleaned)
    if not candidates:
        raise ValueError("No JSON object or array found in model response.")

    first_parse_error: Exception | None = None
    for candidate in candidates:
        if candidate.lstrip().startswith("["):
            continue
        normalized = _wrap_array(candidate)
        try:
            parsed = json.loads(normalized)
        except json.JSONDecodeError as exc:
            first_parse_error = first_parse_error or exc
            continue
        if isinstance(parsed, dict) and "questions" in parsed:
            return normalized

    for candidate in candidates:
        if candidate.lstrip().startswith("["):
            continue
        normalized = _wrap_array(candidate)
        try:
            json.loads(normalized)
            return normalized
        except json.JSONDecodeError as exc:
            first_parse_error = first_parse_error or exc

    for candidate in candidates:
        if not candidate.lstrip().startswith("["):
            continue
        normalized = _wrap_array(candidate)
        try:
            json.loads(normalized)
            return normalized
        except json.JSONDecodeError as exc:
            first_parse_error = first_parse_error or exc

    if first_parse_error:
        raise ValueError(str(first_parse_error)) from first_parse_error
    raise ValueError("No parseable JSON candidate found in model response.")


def _wrap_array(candidate: str) -> str:
    if candidate.lstrip().startswith("["):
        return f'{{"questions": {candidate}}}'
    return candidate


def _balanced_json_values(raw: str) -> list[str]:
    values: list[str] = []
    for start, char in enumerate(raw):
        if char not in "{[":
            continue
        value = _balanced_json_value_from(raw, start)
        if value is not None:
            values.append(cleanup_json_text(value))
    return values


def _balanced_json_value_from(raw: str, start: int) -> str | None:
    stack: list[str] = []
    in_string = False
    escape = False
    quote = ""
    for index in range(start, len(raw)):
        char = raw[index]
        if escape:
            escape = False
            continue
        if char == "\\" and in_string:
            escape = True
            continue
        if char in {'"', "'"}:
            if not in_string:
                in_string = True
                quote = char
            elif quote == char:
                in_string = False
                quote = ""
            continue
        if in_string:
            continue
        if char in "{[":
            stack.append("}" if char == "{" else "]")
        elif char in "}]":
            if not stack or stack[-1] != char:
                return None
            stack.pop()
            if not stack:
                return raw[start : index + 1].strip()
    return None
