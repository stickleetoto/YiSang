from __future__ import annotations

import re

_TOKEN_RE = re.compile(r"[A-Za-z0-9_가-힣]+")
_CAMEL_BOUNDARY_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_DOTTED_ACRONYM_RE = re.compile(r"\b(?:[A-Za-z]\.){2,}[A-Za-z]?\.?\b")

# Conservative aliases for high-value English forms that commonly appear in
# YiSang memory text. This is intentionally small and deterministic: lexical
# retrieval should not pretend to be a full NLP stemmer.
_CANONICAL_ALIASES = {
    "rebuilt": "rebuild",
    "indexes": "index",
    "indices": "index",
    "capabilities": "capability",
    "tools": "tool",
    "quarantined": "quarantine",
}


def lexical_terms(text: str) -> frozenset[str]:
    """Return deterministic canonical terms for lightweight lexical retrieval.

    The normalizer handles:
    - dotted acronyms such as E.G.O. -> ego
    - camel/pascal identifiers such as MemoryGovernor -> memory, governor
    - a deliberately small alias table for common morphology

    It avoids broad stemming so unrelated words are not collapsed together.
    """
    normalized = _collapse_dotted_acronyms(text)
    normalized = _CAMEL_BOUNDARY_RE.sub(" ", normalized)

    terms: set[str] = set()
    for match in _TOKEN_RE.finditer(normalized):
        token = match.group(0).lower()
        terms.add(_CANONICAL_ALIASES.get(token, token))
    return frozenset(terms)


def _collapse_dotted_acronyms(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        return match.group(0).replace(".", "")

    return _DOTTED_ACRONYM_RE.sub(repl, text)
