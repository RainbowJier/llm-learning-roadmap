import importlib

rag = importlib.import_module("stage_02_rag_engineering.code_examples.01_toy_rag")


def test_chunking_respects_size_and_overlap() -> None:
    document = rag.Document("doc", "one two three four five six seven")
    chunks = rag.chunk_document(document, size=4, overlap=1)
    assert [chunk.text for chunk in chunks] == [
        "one two three four",
        "four five six seven",
    ]


def test_invalid_chunk_parameters() -> None:
    document = rag.Document("doc", "one two")
    try:
        rag.chunk_document(document, size=0)
    except ValueError as exc:
        assert "size" in str(exc)
    else:
        raise AssertionError("expected ValueError")
