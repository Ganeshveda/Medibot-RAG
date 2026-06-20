from __future__ import annotations

import logging
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from docling.chunking import HybridChunker
from docling.document_converter import DocumentConverter
from fastembed.sparse.sparse_text_embedding import SparseTextEmbedding
from qdrant_client import QdrantClient, models
from sentence_transformers import SentenceTransformer

import config


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".pdf", ".md"}
BATCH_SIZE = 32


@dataclass
class ChunkRecord:
    text: str
    source_document: str
    collection: str
    access_roles: list[str]
    section_title: str
    chunk_type: str
    metadata: dict


def get_document_paths(data_dir: Path) -> list[Path]:
    document_paths = []
    for path in sorted(data_dir.rglob("*")):
        if path.is_file() and path.suffix.lower() in ALLOWED_EXTENSIONS:
            if path.parent.name not in config.RBAC_MATRIX:
                raise ValueError(f"Unknown collection folder: {path.parent.name}")
            document_paths.append(path)
    return document_paths


def build_section_title(chunk) -> str:
    headings = getattr(chunk.meta, "headings", None) or []
    if not headings:
        return ""
    if isinstance(headings, str):
        return headings.strip()
    return " > ".join(str(h).strip() for h in headings if h)


def build_chunk_type(chunk, text: str) -> str:
    doc_items = getattr(chunk.meta, "doc_items", []) or []
    labels = [str(getattr(item, "label", "")).lower() for item in doc_items if getattr(item, "label", None)]
    if any("table" in label for label in labels):
        return "table"
    if any("code" in label for label in labels):
        return "code"
    if not text.strip() and getattr(chunk.meta, "headings", None):
        return "heading"
    return "text"


def build_chunk_text(chunk) -> str:
    prefix = build_section_title(chunk)
    body = (chunk.text or "").strip()
    if prefix and body:
        return f"{prefix}\n\n{body}"
    if prefix:
        return prefix
    return body


def chunk_document(path: Path, converter: DocumentConverter, chunker: HybridChunker) -> Iterable[ChunkRecord]:
    logger.info("Processing %s", path)
    result = converter.convert(path)
    document = result.document
    chunks = list(chunker.chunk(dl_doc=document))
    if not chunks:
        logger.warning("No chunks found for %s", path)
    collection = path.parent.name
    access_roles = config.RBAC_MATRIX[collection]
    for chunk in chunks:
        text = build_chunk_text(chunk)
        if not text.strip():
            continue
        section_title = build_section_title(chunk)
        chunk_type = build_chunk_type(chunk, text)
        metadata = {
            "source_document": path.name,
            "collection": collection,
            "access_roles": access_roles,
            "section_title": section_title,
            "chunk_type": chunk_type,
        }
        yield ChunkRecord(
            text=text,
            source_document=path.name,
            collection=collection,
            access_roles=access_roles,
            section_title=section_title,
            chunk_type=chunk_type,
            metadata=metadata,
        )


def create_qdrant_collection(client: QdrantClient, collection_name: str, embedding_dim: int) -> None:
    logger.info("Creating Qdrant collection %s", collection_name)
    if client.get_collection(collection_name):
        logger.info("Collection %s already exists; recreating", collection_name)
        client.delete_collection(collection_name)

    client.create_collection(
        collection_name=collection_name,
        vectors_config={
            "dense": models.VectorParams(size=embedding_dim, distance=models.Distance.COSINE),
        },
        sparse_vectors_config={
            "sparse": models.SparseVectorParams(index=models.SparseIndexParams(full_scan_threshold=100)),
        },
    )
    logger.info("Collection %s created", collection_name)


def chunks_to_points(chunks: list[ChunkRecord], dense_embeddings, sparse_embeddings) -> list[models.PointStruct]:
    points = []
    for idx, chunk in enumerate(chunks):
        dense_vector = dense_embeddings[idx].tolist() if hasattr(dense_embeddings[idx], "tolist") else list(dense_embeddings[idx])
        sparse_item = sparse_embeddings[idx]
        sparse_vector = models.SparseVector(indices=sparse_item.indices.tolist(), values=sparse_item.values.tolist())
        point = models.PointStruct(
            id=f"chunk-{idx}",
            vector={"dense": dense_vector, "sparse": sparse_vector},
            payload=chunk.metadata,
        )
        points.append(point)
    return points


def main() -> None:
    data_dir = config.DATA_DIR
    collection_name = config.COLLECTION_NAME

    if not data_dir.exists():
        raise FileNotFoundError(f"Data directory not found: {data_dir}")

    document_paths = get_document_paths(data_dir)
    if not document_paths:
        raise RuntimeError("No documents found for ingestion.")

    converter = DocumentConverter()
    chunker = HybridChunker(tokenizer=config.DENSE_MODEL_NAME, max_tokens=256, merge_peers=True)
    dense_model = SentenceTransformer(config.DENSE_MODEL_NAME)
    sparse_model = SparseTextEmbedding(config.SPARSE_MODEL_NAME, lazy_load=True)
    qdrant_client = QdrantClient(path=str(config.QDRANT_STORAGE_PATH))

    all_chunks: list[ChunkRecord] = []
    for path in document_paths:
        all_chunks.extend(chunk_document(path, converter, chunker))

    if not all_chunks:
        raise RuntimeError("No valid chunks were generated.")

    logger.info("Total chunks generated: %d", len(all_chunks))
    texts = [chunk.text for chunk in all_chunks]
    logger.info("Computing dense embeddings for %d chunks", len(texts))
    dense_embeddings = dense_model.encode(texts, convert_to_numpy=True, show_progress_bar=True)
    logger.info("Computing sparse embeddings for %d chunks", len(texts))
    sparse_results = list(sparse_model.embed(texts, batch_size=BATCH_SIZE))

    create_qdrant_collection(qdrant_client, collection_name, config.DENSE_DIMENSION)

    points = chunks_to_points(all_chunks, dense_embeddings, sparse_results)
    logger.info("Uploading %d points to Qdrant", len(points))
    qdrant_client.upsert(collection_name=collection_name, points=points)

    collection_counts = Counter(chunk.collection for chunk in all_chunks)
    type_counts = Counter(chunk.chunk_type for chunk in all_chunks)
    avg_size = sum(len(chunk.text) for chunk in all_chunks) / len(all_chunks)

    logger.info("Ingestion complete")
    logger.info("Chunks per collection: %s", dict(collection_counts))
    logger.info("Chunk type distribution: %s", dict(type_counts))
    logger.info("Average chunk text length: %.1f characters", avg_size)

    for collection, count in collection_counts.items():
        logger.info("  %s: %d chunks", collection, count)

    logger.info("Qdrant collection %s is ready at %s", collection_name, config.QDRANT_STORAGE_PATH)


if __name__ == "__main__":
    main()
