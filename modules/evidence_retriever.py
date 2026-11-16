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
    def __init__(self, chunks: list[Chunk], embedder, statuses: set | None = config.GOVERNED_STATUSES):
        # TrustGuard indexes the whole governed repository (current AND superseded
        # versions). Which of them may be used as evidence is decided per search with
        # `allow` (see policy_validation.py): normally only versions in effect on the
        # question's date. statuses=None indexes everything.
        self.chunks = [c for c in chunks if statuses is None or c.status in statuses]
        self.excluded = len(chunks) - len(self.chunks)
        self.embedder = embedder
        texts = [c.embedding_text() for c in self.chunks]
        self.embedder.fit(texts)
        self.matrix = self.embedder.encode(texts)  # shape: (num_chunks, dim)
        self.min_relevance = config.MIN_RELEVANCE[embedder.kind]

    def search(self, query: str, k: int = config.TOP_K, allow=None) -> list[Evidence]:
        """Top-k sections by cosine similarity, highest first (relevance not yet filtered).
        allow(chunk) -> bool restricts the candidates, e.g. to policies in effect today."""
        q = self.embedder.encode([query])[0]
        scores = self.matrix @ q  # cosine similarity with every chunk at once
        order = [i for i in np.argsort(-scores) if allow is None or allow(self.chunks[i])]
        return [Evidence(chunk=self.chunks[i], score=float(scores[i])) for i in order[:k]]

    def search_many(self, queries: list[str], k: int = config.TOP_K, allow=None) -> list[Evidence]:
        """Search with several phrasings and keep each section's best score. TrustGuard
        searches with the claim AND with the employee's question, so a badly worded claim
        can't steer it away from the rule that actually applies."""
        best: dict[str, Evidence] = {}
        for query in queries:
            for e in self.search(query, k=k, allow=allow):
                if e.chunk.chunk_id not in best or e.score > best[e.chunk.chunk_id].score:
                    best[e.chunk.chunk_id] = e
        return sorted(best.values(), key=lambda e: -e.score)[:k]

    def relevant(self, evidence: list[Evidence]) -> list[Evidence]:
        return [e for e in evidence if e.score >= self.min_relevance]


def expand_siblings(evidence: list[Evidence], retriever: "EvidenceRetriever", allow=None,
                    limit: int = 5) -> list[Evidence]:
    """Add the sibling rules of the best match (same document, same parent section).

    Why: policies split one rule across sub-sections by amount band ("3.1 up to $20,000",
    "3.2 $20,000-$50,000", "3.3 above $50,000"). Similarity search can't compare numbers,
    so for "$80,000" it may rank the wrong band first. Reading the whole group lets the
    verifier pick the band that actually applies. This is one of TrustGuard's extra safety
    nets: Agent 1 reads only its top 2 passages."""
    if not evidence:
        return evidence
    top = evidence[0].chunk
    parent = top.section.split(".")[0]
    have = {e.chunk.chunk_id for e in evidence}
    out = list(evidence)
    for i, c in enumerate(retriever.chunks):
        if (c.document_id == top.document_id and c.section.split(".")[0] == parent and "." in c.section
                and c.chunk_id not in have and (allow is None or allow(c))):
            # Score siblings just below the top match so they stay "relevant" but rank after it.
            out.append(Evidence(chunk=c, score=evidence[0].score - 0.001))
            have.add(c.chunk_id)
    head, extra = out[:len(evidence)], out[len(evidence):]
    return (head + extra)[:max(limit, len(evidence))]
