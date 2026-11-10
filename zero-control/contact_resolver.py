"""Local, deterministic matching of spoken Russian names to address-book contacts."""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", str(value or "")).casefold().replace("ё", "е")
    value = re.sub(r"[^а-яa-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _token_forms(token: str) -> set[str]:
    """Return conservative Russian inflection variants without external NLP packages."""
    forms = {token}
    suffixes = (
        "иями", "ями", "ами", "иях", "ах", "ях",
        "ого", "его", "ому", "ему", "ыми", "ими",
        "ов", "ев", "ей", "ой", "ам", "ям", "ом", "ем",
        "ую", "юю", "ая", "яя", "ое", "ее",
        "а", "я", "у", "ю", "е", "и", "ы", "ь", "ъ",
    )
    for suffix in suffixes:
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            stem = token[:-len(suffix)]
            forms.add(stem)
            if suffix in ("ю", "я", "е", "и") and len(stem) >= 3:
                forms.add(stem + "ь")
    return forms


def _consonant_skeleton(token: str) -> str:
    """A lightweight phonetic key resilient to vowel substitutions by speech recognition."""
    return re.sub(r"[аеёиоуыэюяaeiouy]", "", token)


def _damerau_similarity(left: str, right: str) -> float:
    """Normalized edit similarity with support for adjacent transpositions."""
    if not left or not right:
        return 0.0
    rows, cols = len(left) + 1, len(right) + 1
    distance = [[0] * cols for _ in range(rows)]
    for i in range(rows):
        distance[i][0] = i
    for j in range(cols):
        distance[0][j] = j
    for i in range(1, rows):
        for j in range(1, cols):
            cost = 0 if left[i - 1] == right[j - 1] else 1
            distance[i][j] = min(
                distance[i - 1][j] + 1,
                distance[i][j - 1] + 1,
                distance[i - 1][j - 1] + cost,
            )
            if (
                i > 1 and j > 1
                and left[i - 1] == right[j - 2]
                and left[i - 2] == right[j - 1]
            ):
                distance[i][j] = min(distance[i][j], distance[i - 2][j - 2] + 1)
    return 1.0 - distance[-1][-1] / max(len(left), len(right))


def _token_similarity(query: str, candidate: str) -> float:
    query_forms = _token_forms(query)
    candidate_forms = _token_forms(candidate)
    if query_forms.intersection(candidate_forms):
        return 1.0

    best = 0.0
    for left in query_forms:
        for right in candidate_forms:
            ratio = SequenceMatcher(None, left, right).ratio()
            best = max(best, ratio)
            shorter = min(len(left), len(right))
            if shorter >= 4 and (left.startswith(right) or right.startswith(left)):
                best = max(best, 0.86 + 0.10 * shorter / max(len(left), len(right)))

            # Speech recognition often changes vowels and occasionally swaps
            # adjacent consonants. Compare consonant skeletons as a second,
            # lower-confidence signal rather than treating them as exact names.
            left_key = _consonant_skeleton(left)
            right_key = _consonant_skeleton(right)
            if min(len(left_key), len(right_key)) >= 3:
                best = max(best, _damerau_similarity(left_key, right_key))
    return best


def _score_name(spoken_tokens: list[str], contact_name: str) -> float:
    contact_tokens = _normalize(contact_name).split()
    if not spoken_tokens or not contact_tokens:
        return 0.0

    scores = [
        max((_token_similarity(token, candidate) for candidate in contact_tokens), default=0.0)
        for token in spoken_tokens
    ]
    # A candidate must account for every spoken name token; one matching fragment
    # must not outweigh another token that points to a different person.
    if any(score < 0.62 for score in scores):
        return 0.0
    return sum(scores) / len(scores)


def resolve_contact(spoken_name: str, address_book: dict) -> dict:
    """Return match, ambiguous, or not_found using only local contact names."""
    spoken_tokens = _normalize(spoken_name).split()
    if not spoken_tokens or not isinstance(address_book, dict):
        return {"status": "not_found", "contact": None, "candidates": []}

    ranked = []
    for name, details in address_book.items():
        if not isinstance(details, dict) or not str(details.get("email") or "").strip():
            continue
        score = _score_name(spoken_tokens, str(name))
        if score >= 0.62:
            ranked.append({
                "name": str(name),
                "email": str(details["email"]).strip(),
                "score": round(score, 4),
            })

    ranked.sort(key=lambda item: (-item["score"], item["name"].casefold()))
    if not ranked:
        return {"status": "not_found", "contact": None, "candidates": []}

    best = ranked[0]
    second_score = ranked[1]["score"] if len(ranked) > 1 else 0.0
    if best["score"] >= 0.86 and (len(ranked) == 1 or best["score"] - second_score >= 0.12):
        return {"status": "match", "contact": best, "candidates": ranked[:3]}

    # Medium-confidence phonetic matches are presented for explicit confirmation,
    # even when there is only one plausible contact. Never silently guess.
    close = [item for item in ranked if item["score"] >= max(0.62, best["score"] - 0.12)]
    if best["score"] >= 0.68 and close:
        return {"status": "ambiguous", "contact": None, "candidates": close[:5]}
    return {"status": "not_found", "contact": None, "candidates": ranked[:3]}
