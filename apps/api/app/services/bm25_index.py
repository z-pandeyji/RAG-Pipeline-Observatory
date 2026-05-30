"""Post-retrieval: BM25 lexical index for hybrid search.

Builds an in-memory BM25 index from a list of text chunks and returns
BM25 scores for a query.  Used alongside vector search to produce hybrid
Reciprocal Rank Fusion (RRF) scores.

No external dependency required — implements Okapi BM25 directly.

Usage::

    index = BM25Index(texts)
    scores = index.score(query)          # list[float], one per chunk

RRF fusion::

    fused = BM25Index.rrf_fuse(bm25_scores, vector_scores, k=60)
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field


def _tokenise(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


@dataclass
class BM25Index:
    """Okapi BM25 index over a corpus of text strings."""

    texts: list[str]
    k1: float = 1.5
    b: float = 0.75
    _idf: dict[str, float] = field(default_factory=dict, init=False, repr=False)
    _tf: list[dict[str, float]] = field(default_factory=list, init=False, repr=False)
    _avgdl: float = field(default=0.0, init=False, repr=False)

    def __post_init__(self) -> None:
        corpus = [_tokenise(text) for text in self.texts]
        n = len(corpus)
        self._avgdl = sum(len(doc) for doc in corpus) / max(n, 1)

        # Document frequency per term
        df: dict[str, int] = {}
        for doc in corpus:
            for term in set(doc):
                df[term] = df.get(term, 0) + 1

        # IDF: log((N - df + 0.5) / (df + 0.5) + 1)  [Robertson-Sparck-Jones]
        self._idf = {
            term: math.log((n - freq + 0.5) / (freq + 0.5) + 1.0)
            for term, freq in df.items()
        }

        # TF per document
        self._tf = []
        for doc in corpus:
            counts: dict[str, int] = {}
            for token in doc:
                counts[token] = counts.get(token, 0) + 1
            length = len(doc)
            tf_norm = {
                term: (
                    count * (self.k1 + 1)
                    / (count + self.k1 * (1 - self.b + self.b * length / max(self._avgdl, 1)))
                )
                for term, count in counts.items()
            }
            self._tf.append(tf_norm)

    def score(self, query: str) -> list[float]:
        """Return a BM25 score for each document in the corpus."""
        query_terms = _tokenise(query)
        scores = [0.0] * len(self.texts)
        for term in set(query_terms):
            idf = self._idf.get(term, 0.0)
            for doc_idx, tf_map in enumerate(self._tf):
                tf = tf_map.get(term, 0.0)
                scores[doc_idx] += idf * tf
        return scores

    @staticmethod
    def rrf_fuse(
        bm25_scores: list[float],
        vector_scores: list[float],
        k: int = 60,
    ) -> list[float]:
        """Reciprocal Rank Fusion of BM25 and vector score lists.

        Returns a fused score list of the same length.  Higher is better.
        ``k`` is the RRF constant (default 60).
        """
        assert len(bm25_scores) == len(vector_scores), (
            "BM25 and vector score lists must have the same length"
        )
        n = len(bm25_scores)
        if n == 0:
            return []

        # Build rank arrays (0-based, lower rank = better)
        bm25_order = sorted(range(n), key=lambda i: bm25_scores[i], reverse=True)
        vec_order = sorted(range(n), key=lambda i: vector_scores[i], reverse=True)
        bm25_rank = [0] * n
        vec_rank = [0] * n
        for rank, idx in enumerate(bm25_order):
            bm25_rank[idx] = rank
        for rank, idx in enumerate(vec_order):
            vec_rank[idx] = rank

        return [
            1.0 / (k + bm25_rank[i]) + 1.0 / (k + vec_rank[i])
            for i in range(n)
        ]
