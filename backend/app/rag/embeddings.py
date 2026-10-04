"""Deterministic text embedding for the agricultural knowledge index.

The project must run with no external embedding-service credentials, so the
embedding function is built from scikit-learn vectorisers fitted on the curated
corpus:

* a word-level TF-IDF vectoriser (1-2 grams, sublinear term frequency), and
* a character ``char_wb`` 3-5 gram vectoriser, which gives partial-word and
  morphological tolerance for terms such as "irrigation"/"irrigations".

The two sparse vectors are L2-normalised, weighted, concatenated into a single
dense vector and L2-normalised again so that an inner product equals cosine
similarity - which is what the FAISS inner-product index optimises.

This is a genuine, reproducible lexical-semantic retrieval stage, not a neural
embedding model; the limitation is documented in the README.
"""

from __future__ import annotations

import numpy as np
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer

WORD_WEIGHT = 0.7
CHAR_WEIGHT = 0.3


class CorpusEmbedder:
    """Fit on the corpus and used to embed both documents and queries."""

    def __init__(self) -> None:
        self._word_vectorizer = TfidfVectorizer(
            lowercase=True,
            stop_words="english",
            ngram_range=(1, 2),
            sublinear_tf=True,
            min_df=1,
            norm="l2",
        )
        self._char_vectorizer = TfidfVectorizer(
            lowercase=True,
            analyzer="char_wb",
            ngram_range=(3, 5),
            sublinear_tf=True,
            min_df=1,
            norm="l2",
        )
        self.is_fitted = False
        self._dimension = 0

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def name(self) -> str:
        return "tfidf(word 1-2gram) + char_wb(3-5gram), cosine"

    def fit(self, texts: list[str]) -> CorpusEmbedder:
        if not texts:
            msg = "Cannot fit an embedder on an empty corpus"
            raise ValueError(msg)
        self._word_vectorizer.fit(texts)
        self._char_vectorizer.fit(texts)
        self._dimension = len(self._word_vectorizer.vocabulary_) + len(self._char_vectorizer.vocabulary_)
        self.is_fitted = True
        return self

    def transform(self, texts: list[str]) -> np.ndarray:
        if not self.is_fitted:
            msg = "CorpusEmbedder must be fitted before use"
            raise RuntimeError(msg)
        if not texts:
            return np.zeros((0, self._dimension), dtype="float32")

        word = self._word_vectorizer.transform(texts)
        char = self._char_vectorizer.transform(texts)

        word_norm = _sparse_l2(word)
        char_norm = _sparse_l2(char)

        blocks: list[sparse.spmatrix] = []
        if word_norm.shape[1] > 0:
            blocks.append(sparse.csr_matrix(word_norm * WORD_WEIGHT))
        if char_norm.shape[1] > 0:
            blocks.append(sparse.csr_matrix(char_norm * CHAR_WEIGHT))

        matrix = sparse.hstack(blocks, format="csr")
        return _sparse_l2(matrix).astype("float32").toarray()


def _sparse_l2(matrix: sparse.spmatrix) -> sparse.spmatrix:
    """Row-wise L2 normalisation that also tolerates all-zero rows."""
    matrix = sparse.csr_matrix(matrix)
    norms = np.sqrt(matrix.multiply(matrix).sum(axis=1)).A.ravel()
    norms[norms == 0] = 1.0
    inverse = sparse.diags(1.0 / norms)
    return sparse.csr_matrix(inverse @ matrix)
