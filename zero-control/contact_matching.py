"""Name matching for voice-selected address-book contacts."""
from __future__ import annotations
import re
from difflib import SequenceMatcher

_RUSSIAN_ENDINGS = ("иями", "ями", "ами", "ого", "ему", "ому", "ыми", "ими", "иях", "его", "ому", "ую", "юю", "ая", "яя", "ое", "ее", "ые", "ие", "ов", "ев", "ей", "ам", "ям", "ах", "ях", "ом", "ем", "ой", "ей", "ую", "ю", "а", "я", "у", "ю", "е", "ы", "и", "ом", "ем", "ь", "ъ")

def _tokens(value: str) -> list[str]:
    cleaned = re.sub(r"[^а-яa-z0-9 ]", " ", str(value or "").lower().replace("ё", "е"))
    result = []
    for token in cleaned.split():
        for ending in _RUSSIAN_ENDINGS:
            if len(token) - len(ending) >= 3 and token.endswith(ending):
                token = token[:-len(ending)]
                break
        if token:
            result.append(token)
    return result

def _similarity(left: str, right: str) -> float:
    if left == right:
        return 1.0
    if min(len(left), len(right)) < 5:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()

def best_contact_matches(spoken_name: str, contact_names: list[str], threshold: float = 0.82) -> list[str]:
    """Return only top-scoring contacts; keep ties ambiguous instead of guessing."""
    spoken = _tokens(spoken_name)
    if not spoken:
        return []
    scores = []
    for name in contact_names:
        saved = _tokens(name)
        if not saved:
            continue
        # A spoken first name or surname may identify a full saved contact.
        score = max((_similarity(query, candidate) for query in spoken for candidate in saved), default=0.0)
        if score >= threshold:
            scores.append((score, name))
    if not scores:
        return []
    best = max(score for score, _ in scores)
    # Keep near-equal alternatives visible to the user rather than auto-selecting.
    return [name for score, name in scores if best - score <= 0.04]
