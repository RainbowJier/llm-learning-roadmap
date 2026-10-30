import importlib

rag = importlib.import_module("stage_02_rag_engineering.code_examples.01_toy_rag")


def test_bm25_ranks_matching_document_first() -> None:
    docs = [
        rag.Document("fastapi", "FastAPI supports typed request validation."),
        rag.Document("asyncio", "Asyncio schedules coroutines on an event loop."),
    ]
    chunks = [chunk for doc in docs for chunk in rag.chunk_document(doc, size=20)]
    results = rag.BM25Retriever(chunks).search("typed request validation")
    assert results[0][0].doc_id == "fastapi"
    assert results[0][1] > 0


def test_unknown_question_is_refused() -> None:
    docs = [rag.Document("doc", "Only known facts are indexed.")]
    chunks = rag.chunk_document(docs[0], size=20)
    result = rag.answer("quantum mechanics", rag.BM25Retriever(chunks))
    assert result["sources"] == []
    assert "无法回答" in result["answer"]
