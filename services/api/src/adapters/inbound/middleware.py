import logging
import re

logger = logging.getLogger(__name__)

INJECTION_PATTERNS = [
    (r"ignore\s+(all\s+)?previous\s+instructions", "ignore_previous_instructions"),
    (r"you\s+are\s+now", "role_reassignment"),
    (r"^(system|assistant|user)\s*:", "role_switching"),
    (r"forget\s+everything", "forget_everything"),
    (r"disregard\s+.*instructions", "disregard_instructions"),
    (r"do\s+not\s+follow", "do_not_follow"),
    (r"new\s+instruction", "new_instruction"),
    (r"role\s*:\s*(system|assistant)", "role_declaration"),
]

_COMPILED_PATTERNS = [(re.compile(p, re.IGNORECASE | re.MULTILINE), label) for p, label in INJECTION_PATTERNS]

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_HTML_TAGS_RE = re.compile(r"<[^>]+>")
_EXCESS_WHITESPACE_RE = re.compile(r"[ \t]+")
_EXCESS_NEWLINES_RE = re.compile(r"\n{3,}")


def sanitize_text(text: str | None) -> str | None:
    if text is None:
        return None
    result = _HTML_TAGS_RE.sub("", text)
    result = _CONTROL_CHARS_RE.sub("", result)
    result = _EXCESS_WHITESPACE_RE.sub(" ", result)
    result = _EXCESS_NEWLINES_RE.sub("\n\n", result)
    result = result.strip()
    return result


def detect_prompt_injection(text: str | None) -> list[str]:
    if not text:
        return []
    detected: list[str] = []
    for pattern, label in _COMPILED_PATTERNS:
        if pattern.search(text):
            detected.append(label)
    return detected


def check_injection(fields: dict[str, str | None], incident_id: str) -> bool:
    all_detected: list[str] = []
    for field_name, value in fields.items():
        patterns = detect_prompt_injection(value)
        if patterns:
            all_detected.extend(patterns)
            for p in patterns:
                logger.warning(
                    '{"type":"prompt_injection_detected","pattern":"%s","field":"%s","incident_id":"%s"}',
                    p,
                    field_name,
                    incident_id,
                )
    return len(all_detected) > 0
