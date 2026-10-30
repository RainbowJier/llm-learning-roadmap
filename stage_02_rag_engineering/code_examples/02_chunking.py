import importlib

_base = importlib.import_module("stage_02_rag_engineering.code_examples.01_toy_rag")
Document = _base.Document
Chunk = _base.Chunk
chunk_document = _base.chunk_document

__all__ = ["Document", "Chunk", "chunk_document"]
