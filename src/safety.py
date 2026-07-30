"""Local heuristics that look for prompt injection before a query is sent.

This is layer 1 of three. Layer 2 is the moderation endpoint, which covers a
disjoint threat: measured against the moderation API, the injection used as
test case C5 comes back unflagged with no category set, because its content is
not harmful, it merely tries to change what the program does. Layer 3 is the
instruction already present in the RESTRICCIONES block of the prompt, and it is
the backstop for whatever the first two miss.

Nothing here is a guarantee. A heuristic trades false positives against false
negatives and cannot minimise both, which is exactly why the other two layers
exist. The known limitation belongs in the report rather than hidden.

The module imports nothing from openai_client, so these heuristics stay
testable with no API key.
"""

import re
import unicodedata

# Patterns are written in their normalised form: lowercase, unaccented, single
# spaces. Writing "ignorá" here would never match, because the text being
# searched has already had its accents stripped.
#
# The bounded gap [^.]{0,40} lets one pattern cover reorderings and filler
# words -- "ignora las instrucciones", "ignora por completo todas las reglas"
# -- without a separate entry for each. Excluding the period keeps a match from
# spanning two sentences, which would invent intent that is not there.
INJECTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "override_instructions",
        re.compile(
            r"\b(ignora|ignorar|olvida|olvidate|descarta|desestima"
            r"|ignore|forget|disregard)\b"
            r"[^.]{0,40}"
            r"\b(instruccion|instrucciones|reglas|indicaciones|lo anterior"
            r"|instruction|instructions|rules|above|previous)\b"
        ),
    ),
    (
        "reveal_system_prompt",
        re.compile(
            r"\b(prompt|mensaje) de sistema\b"
            r"|\bsystem prompt\b"
            r"|\b(mostra|muestra|revela|decime|dime|devolve|devuelve|repeti|repite"
            r"|show|reveal|repeat|print)\b"
            r"[^.]{0,40}"
            r"\b(prompt|instrucciones|reglas|instructions|rules)\b"
        ),
    ),
    (
        "role_override",
        re.compile(
            r"\bmodo (desarrollador|dios)\b"
            r"|\bdeveloper mode\b"
            r"|\b(actua|comporta|haces de cuenta|a partir de ahora (sos|eres)"
            r"|act as|pretend|you are now)\b"
            r"[^.]{0,40}"
            r"\bsin (restricciones|reglas|limites|filtros)\b"
            r"|\bwithout (restrictions|rules|limits|filters)\b"
        ),
    ),
    (
        "control_tokens",
        re.compile(r"<\|im_(start|end)\|>|\[/?(system|inst)\]|#{3,}\s*system"),
    ),
)


def normalize(text: str) -> str:
    """Reduce text to the single form the patterns are matched against.

    Literal comparison is what makes a naive filter trivial to evade: "ignorá",
    "IGNORA" and "ignora   todas" are three different strings to Python. Folding
    them into one form first is what lets a single pattern catch all of them.

    Three steps, and the order matters:

    1. Lowercase, which handles capitalisation including alternating case.
    2. Strip diacritics. Unicode can write "á" two ways, as one precomposed
       character or as "a" followed by a separate combining accent, and the two
       are visually identical but unequal in Python, so an attacker can evade a
       filter by choosing the form it does not know. NFD forces everything to
       the second form, which leaves the accents as standalone characters in
       category "Mn" (mark, nonspacing) that can then be dropped.
    3. Collapse runs of whitespace, including tabs and newlines, into one space.

    Args:
        text: The raw query, as the customer wrote it.

    Returns:
        The lowercase, unaccented, single-spaced form.
    """
    decomposed = unicodedata.normalize("NFD", text.lower())
    without_accents = "".join(
        char for char in decomposed if unicodedata.category(char) != "Mn"
    )
    return re.sub(r"\s+", " ", without_accents).strip()


def detect_injection(text: str) -> str | None:
    """Look for a known prompt-injection shape in a query.

    Returns the name of the pattern rather than a bare boolean so the safety
    log can record why something was rejected, not merely that it was.

    Args:
        text: The raw query. Normalisation happens here, so callers pass the
            original text.

    Returns:
        The name of the first pattern that matched, or None if none did.
    """
    normalized = normalize(text)
    for name, pattern in INJECTION_PATTERNS:
        if pattern.search(normalized):
            return name
    return None
