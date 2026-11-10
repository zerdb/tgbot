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
    if best["score"] >= 0.90 and (len(ranked) == 1 or best["score"] - second_score >= 0.12):
        return {"status": "match", "contact": best, "candidates": ranked[:3]}
    if best["score"] >= 0.86 and (len(ranked) == 1 or best["score"] - second_score >= 0.12):
        return {"status": "match", "contact": best, "candidates": ranked[:3]}

    # Show only close candidates; never silently select among similar contacts.
    close = [item for item in ranked if item["score"] >= max(0.62, best["score"] - 0.12)]
    if best["score"] >= 0.68 and len(close) > 1:
        return {"status": "ambiguous", "contact": None, "candidates": close[:5]}
    if best["score"] >= 0.90:
        return {"status": "match", "contact": best, "candidates": ranked[:3]}
    return {"status": "not_found", "contact": None, "candidates": ranked[:3]}
