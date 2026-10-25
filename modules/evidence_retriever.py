"""Step 2 — find the policy sections most relevant to each claim.

How semantic search works: an embedding model turns any text into a vector (a list
of ~384 numbers) such that texts with similar MEANING end up pointing in similar
directions. "Maximum daily travel allowance" and "Employees may claim up to $150 per
day" share almost no words but get similar vectors. We embed every policy section
once at startup, embed each claim at query time, and rank sections by cosine
similarity (the cosine of the angle between two vectors: 1 = same direction).

Why no vector database? With ~30 sections, one matrix multiplication over all of them
takes microseconds. ChromaDB earns its keep at thousands of documents, not 30.

IMPORTANT: relevant ≠ supporting. A section about the $150 allowance is highly
relevant to the claim "the allowance is $200" — and it contradicts it. Retrieval
only decides what the verifier gets to read; the verifier decides what it means.

Fallback: if the embedding model can't be loaded (no internet on first run), we fall
back to TF-IDF keyword matching so the app still works. It's weaker — it matches
words, not meaning — and the UI says when it's in use.
"""
import math
import re
from collections import Counter

import numpy as np

import config
from modules.schemas import Chunk, Evidence


class SentenceTransformerEmbedder:
    kind = "sentence-transformers"

    def __init__(self, model_name: str = config.EMBEDDING_MODEL):
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(model_name)
        self.label = model_name

    def fit(self, texts: list[str]) -> None:
        pass  # pretrained; nothing to learn from our documents

    def encode(self, texts: list[str]) -> np.ndarray:
        # normalize_embeddings=True makes every vector length 1, so a plain dot
        # product equals cosine similarity.
        return self.model.encode(texts, normalize_embeddings=True, convert_to_numpy=True)


class TfidfEmbedder:
    """Keyword-based fallback. Words that are rare across the knowledge base
    (e.g. 'accommodation') get more weight than common ones (e.g. 'the')."""
    kind = "tfidf"
    label = "TF-IDF keyword fallback"
    STOP = set("the a an of to and or for in on is are be by with as at from this that it any all each".split())

    def _tokens(self, text: str) -> list[str]:
        return [t for t in re.findall(r"[a-z0-9$]+", text.lower()) if t not in self.STOP]

    def fit(self, texts: list[str]) -> None:
        docs = [set(self._tokens(t)) for t in texts]
        self.vocab = {w: i for i, w in enumerate(sorted(set().union(*docs)))}
        n = len(texts)
        self.idf = np.zeros(len(self.vocab))
        for w, i in self.vocab.items():
            df = sum(w in d for d in docs)
            self.idf[i] = math.log((1 + n) / (1 + df)) + 1

    def encode(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), len(self.vocab)))
        for row, text in enumerate(texts):
            for w, c in Counter(self._tokens(text)).items():
                if w in self.vocab:
                    out[row, self.vocab[w]] = c * self.idf[self.vocab[w]]
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        return out / np.where(norms == 0, 1, norms)


def make_embedder(prefer: str = "sentence-transformers"):
    """Returns (embedder, warning_or_None)."""
    if prefer == "sentence-transformers":
        try:
            return SentenceTransformerEmbedder(), None
        except Exception as e:  # no internet on first download, missing torch, etc.
            return TfidfEmbedder(), (f"Embedding model unavailable ({type(e).__name__}); "
                                     "using TF-IDF keyword fallback. Retrieval quality is reduced.")
    return TfidfEmbedder(), None


class EvidenceRetriever:
    def __init__(self, chunks: list[Chunk], embedder):
        # Only approved documents are searchable. Superseded versions stay on disk
        # but must never be used as evidence for what the policy says today.
        self.chunks = [c for c in chunks if c.status in config.SEARCHABLE_STATUSES]
        self.excluded = len(chunks) - len(self.chunks)
        self.embedder = embedder
        texts = [c.embedding_text() for c in self.chunks]
        self.embedder.fit(texts)
        self.matrix = self.embedder.encode(texts)  # shape: (num_chunks, dim)
        self.min_relevance = config.MIN_RELEVANCE[embedder.kind]

    def search(self, query: str, k: int = config.TOP_K) -> list[Evidence]:
        """Top-k sections by cosine similarity, highest first (relevance not yet filtered)."""
        q = self.embedder.encode([query])[0]
        scores = self.matrix @ q  # cosine similarity with every chunk at once
        top = np.argsort(-scores)[:k]
        return [Evidence(chunk=self.chunks[i], score=float(scores[i])) for i in top]

    def relevant(self, evidence: list[Evidence]) -> list[Evidence]:
        return [e for e in evidence if e.score >= self.min_relevance]
