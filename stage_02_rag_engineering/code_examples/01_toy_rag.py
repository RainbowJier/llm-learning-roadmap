"""Small, dependency-free RAG baseline.

This is intentionally transparent rather than state-of-the-art: whitespace/
Unicode tokenization, chunking, BM25-style lexical retrieval, and a simple
extractive answer. It gives the course a reproducible baseline before adding
embeddings or a vector database.
"""
from dataclasses import dataclass
import math
import re
from collections import Counter


@dataclass(frozen=True)
class Document:
    doc_id: str
    text: str


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    doc_id: str
    text: str


def tokenize(text: str) -> list[str]:
    return re.findall(r"[\w]+", text.lower(), flags=re.UNICODE)


def chunk_document(document: Document, size: int = 40, overlap: int = 8) -> list[Chunk]:
    if size <= 0 or overlap < 0 or overlap >= size:
        raise ValueError("size must be positive and overlap must be in [0, size)")
    words = document.text.split()
    chunks: list[Chunk] = []
    step = size - overlap
    for index, start in enumerate(range(0, len(words), step)):
        text = " ".join(words[start : start + size])
        if not text:
            break
        chunks.append(Chunk(f"{document.doc_id}:{index}", document.doc_id, text))
        if start + size >= len(words):
            break
    return chunks


class BM25Retriever:
    def __init__(self, chunks: list[Chunk], k1: float = 1.5, b: float = 0.75) -> None:
        if not chunks:
            raise ValueError("at least one chunk is required")
        self.chunks = chunks
        self.k1 = k1
        self.b = b
        self.term_frequencies = [Counter(tokenize(c.text)) for c in chunks]
        self.doc_lengths = [sum(freq.values()) for freq in self.term_frequencies]
        self.avgdl = sum(self.doc_lengths) / len(self.doc_lengths)
        self.document_frequency: Counter[str] = Counter()
        for frequencies in self.term_frequencies:
            self.document_frequency.update(frequencies.keys())

    def search(self, query: str, top_k: int = 3) -> list[tuple[Chunk, float]]:
        query_terms = set(tokenize(query))
        total = len(self.chunks)
        scored: list[tuple[Chunk, float]] = []
        for chunk, frequencies, length in zip(self.chunks, self.term_frequencies, self.doc_lengths):
            score = 0.0
            for term in query_terms:
                frequency = frequencies.get(term, 0)
                if not frequency:
                    continue
                df = self.document_frequency[term]
                idf = math.log(1 + (total - df + 0.5) / (df + 0.5))
                numerator = frequency * (self.k1 + 1)
                denominator = frequency + self.k1 * (1 - self.b + self.b * length / self.avgdl)
                score += idf * numerator / denominator
            scored.append((chunk, score))
        return sorted(scored, key=lambda item: item[1], reverse=True)[:top_k]


def answer(query: str, retriever: BM25Retriever, top_k: int = 2) -> dict[str, object]:
    results = retriever.search(query, top_k=top_k)
    if not results or results[0][1] <= 0:
        return {"answer": "根据现有文档无法回答该问题。", "sources": [], "results": results}
    best = results[0][0]
    return {"answer": best.text, "sources": [chunk.doc_id for chunk, _ in results], "results": results}


if __name__ == "__main__":
    docs = [Document("demo", "FastAPI supports typed request validation and async endpoints.")]
    chunks = [chunk for doc in docs for chunk in chunk_document(doc)]
    print(answer("async endpoints", BM25Retriever(chunks)))
