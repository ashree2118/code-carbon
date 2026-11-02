"""BM25 keyword retrieval over the practices.

Used as the fallback when the embedding model or vector store is unavailable
(for example offline, before the model has been downloaded once).
"""

import math
import re
from collections import Counter

from app.services.knowledge_base import Practice

_TOKEN_RE = re.compile(r"[a-z0-9_]+")
_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "do", "does", "each",
    "for", "from", "has", "if", "in", "instead", "into", "is", "it", "its", "of",
    "on", "one", "or", "same", "so", "such", "than", "that", "the", "then", "this",
    "to", "use", "used", "when", "which", "while", "with", "you", "your",
}


def tokenize(text: str) -> list[str]:
    tokens = []
    for token in _TOKEN_RE.findall(text.lower()):
        if token in _STOP_WORDS:
            continue
        # Light stemming so "loops" matches "loop" and "files" matches "file".
        if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
            token = token[:-1]
        tokens.append(token)
    return tokens


class BM25Index:
    """Okapi BM25 over a fixed list of tokenized documents."""

    def __init__(self, documents: list[list[str]], k1: float = 1.5, b: float = 0.75) -> None:
        self._k1 = k1
        self._b = b
        self._term_counts = [Counter(doc) for doc in documents]
        self._lengths = [len(doc) for doc in documents]
        self._avg_length = sum(self._lengths) / max(len(documents), 1)
        doc_freq = Counter(term for doc in documents for term in set(doc))
        n = len(documents)
        self._idf = {
            term: math.log(1 + (n - freq + 0.5) / (freq + 0.5)) for term, freq in doc_freq.items()
        }

    def scores(self, query: list[str]) -> list[float]:
        results = []
        for counts, length in zip(self._term_counts, self._lengths):
            score = 0.0
            for term in query:
                tf = counts.get(term, 0)
                if tf:
                    norm = self._k1 * (1 - self._b + self._b * length / self._avg_length)
                    score += self._idf[term] * tf * (self._k1 + 1) / (tf + norm)
            results.append(score)
        return results


class KeywordRetriever:
    name = "keyword"

    def __init__(self, practices: list[Practice]) -> None:
        self._practices = practices
        # The title is repeated so title words weigh more than body words.
        self._index = BM25Index(
            [tokenize(f"{p.title} {p.title} {p.category} {p.content}") for p in practices]
        )

    def search(self, query: str, k: int) -> list[tuple[Practice, float]]:
        """Best first. Scores are relative to the best match (1.0)."""
        terms = tokenize(query)
        if not terms:
            return []
        ranked = sorted(
            ((score, p) for score, p in zip(self._index.scores(terms), self._practices) if score > 0),
            key=lambda pair: pair[0],
            reverse=True,
        )[:k]
        if not ranked:
            return []
        best = ranked[0][0]
        return [(p, score / best) for score, p in ranked]
