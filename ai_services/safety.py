"""
Red-flag symptom screening.

This is a deterministic guardrail that runs before (and independently of)
the embedding model. Its only job is to make sure that a patient who
describes an emergency sign is told to seek urgent help instead of just
being shown reading material. It never diagnoses anything.

Rules are deliberately explicit regular expressions so that the behaviour
is predictable, auditable and does not depend on the model being
available.
"""

import re
from dataclasses import dataclass


EMERGENCY = "emergency"
CRISIS = "crisis"


@dataclass(frozen=True)
class SafetyAlert:
    level: str
    category: str
    message: str


_EMERGENCY_MESSAGE = (
    "Some of what you described can be a sign of a medical emergency. "
    "If you are experiencing this now, call 911 or go to the nearest "
    "emergency room. Do not wait for your scheduled appointment."
)

_CRISIS_MESSAGE = (
    "You mentioned thoughts of harming yourself or ending your life. "
    "You don't have to go through this alone. Call or text 988 (Suicide "
    "& Crisis Lifeline, U.S.) to talk to someone right now, or call 911 "
    "if you are in immediate danger."
)


def _rx(pattern):
    return re.compile(pattern, re.IGNORECASE)


# (category, level, patterns). A rule fires if ANY pattern matches.
# Tuples inside the pattern list mean "all of these must match".
RULES = [
    ("self_harm", CRISIS, [
        _rx(r"suicid"),
        _rx(r"\bkill(ing)? myself\b"),
        _rx(r"\bend(ing)? (my|it all|my own) ?life\b|\bend(ing)? it all\b"),
        _rx(r"\b(hurt|harm)(ing)? myself\b|\bself[- ]?harm"),
        _rx(r"\b(don'?t|do not) want to (live|be alive)\b|\bwant to die\b"),
    ]),
    ("cardiac", EMERGENCY, [
        _rx(r"\bheart attack\b"),
        _rx(r"\bcrushing\b.*\bchest\b|\bchest\b.*\bcrushing\b"),
        (
            _rx(r"\bchest (pain|pressure|tightness|discomfort)\b|\bpressure in (my|the) chest\b"),
            _rx(r"\b(left )?arm\b|\bjaw\b|\bsweat|\bshort(ness)? of breath\b"),
        ),
    ]),
    ("breathing", EMERGENCY, [
        _rx(r"\b(can'?t|cannot|unable to|struggling to|hard to) (catch my )?breathe?\b"),
        _rx(r"\blips? (look|looks|are|is|turning|turned) (blue|grey|gray)\b|\bblue lips\b"),
        _rx(r"\bchoking\b"),
        _rx(r"\bthroat (is )?(closing|swelling)\b|\bswollen tongue\b|\banaphyla"),
    ]),
    ("stroke", EMERGENCY, [
        _rx(r"\bface (is )?droop|\bdrooping face\b"),
        _rx(r"\bslurred speech\b|\bslurring (my )?words\b"),
        _rx(r"\b(numb(ness)?|weak(ness)?) on one side\b"),
        _rx(r"\bstroke\b"),
    ]),
    ("severe_headache", EMERGENCY, [
        _rx(r"\bworst headache\b|\bthunderclap\b"),
    ]),
    ("bleeding", EMERGENCY, [
        _rx(r"\b(coughing|vomiting|throwing) up blood\b|\bblood in (my )?vomit\b"),
        _rx(r"\bblack,? tarry stool"),
    ]),
    ("consciousness", EMERGENCY, [
        _rx(r"\bpassed out\b|\bfainted\b|\blost consciousness\b|\bunconscious\b"),
        _rx(r"\bseizure\b"),
    ]),
]


def concern_text_for_screening(concern):
    fields = [
        concern.symptom,
        concern.description,
        concern.triggers,
        concern.question_for_doctor,
    ]
    return " ".join(str(f) for f in fields if f)


def _matches(rule_pattern, text):
    if isinstance(rule_pattern, tuple):
        return all(p.search(text) for p in rule_pattern)
    return bool(rule_pattern.search(text))


def screen_text(text):
    """
    Return a SafetyAlert for the most serious rule that matches, or None.
    Crisis (self-harm) rules are checked first because they need a
    different response (988) from physical emergencies (911).
    """
    if not text:
        return None

    for category, level, patterns in RULES:
        if any(_matches(p, text) for p in patterns):
            message = _CRISIS_MESSAGE if level == CRISIS else _EMERGENCY_MESSAGE
            return SafetyAlert(level=level, category=category, message=message)

    return None


def screen_concern(concern):
    return screen_text(concern_text_for_screening(concern))
