from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Iterable, List

from qdrant_client import QdrantClient, models
from sentence_transformers import CrossEncoder
from sentence_transformers import SentenceTransformer

import config

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

DEFAULT_RETRIEVAL_K = 10
DEFAULT_RERANK_K = 3

_DENSE_QUERY_MODEL: SentenceTransformer | None = None


@dataclass
class RetrievalCandidate:
    id: str | int
    text: str
    metadata: dict[str, Any]
    score: float

    @property
    def source_document(self) -> str:
        return str(self.metadata.get("source_document", ""))

    @property
    def collection(self) -> str:
        return str(self.metadata.get("collection", ""))


def create_qdrant_client() -> QdrantClient:
    return QdrantClient(
        path=str(config.QDRANT_STORAGE_PATH),
        embedding_model_name=config.DENSE_MODEL_NAME,
        sparse_embedding_model_name=config.SPARSE_MODEL_NAME,
    )


def get_dense_query_model() -> SentenceTransformer:
    global _DENSE_QUERY_MODEL
    if _DENSE_QUERY_MODEL is None:
        _DENSE_QUERY_MODEL = SentenceTransformer(config.DENSE_MODEL_NAME)
    return _DENSE_QUERY_MODEL


def build_role_filter(role: str) -> models.Filter:
    if role not in config.ROLES:
        raise ValueError(f"Unknown role: {role}")

    return models.Filter(
        must=models.FieldCondition(
            key="access_roles",
            match=models.MatchAny(any=[role]),
        )
    )


def hybrid_search(query_text: str, role: str, limit: int = DEFAULT_RETRIEVAL_K) -> list[RetrievalCandidate]:
    logger.info("Running hybrid Qdrant retrieval for role=%s, limit=%d", role, limit)
    qdrant_client = create_qdrant_client()
    query_filter = build_role_filter(role)
    query_model = get_dense_query_model()
    query_vector = query_model.encode(query_text, convert_to_numpy=True).tolist()

    try:
        response = qdrant_client.query_points(
            collection_name=config.COLLECTION_NAME,
            query=query_vector,
            query_filter=query_filter,
            limit=limit,
            using="dense",
        )
    finally:
        qdrant_client.close()

    points = response.points
    candidates = [
        RetrievalCandidate(
            id=result.id,
            text=str((result.payload or {}).get("text", "")),
            metadata=dict(result.payload or {}),
            score=float(result.score),
        )
        for result in points
    ]

    _confirm_rbac_filter(candidates, role)
    logger.info("Retrieved %d candidate chunks for role=%s", len(candidates), role)
    return candidates


def rerank_candidates(query_text: str, candidates: Iterable[RetrievalCandidate], top_n: int = DEFAULT_RERANK_K) -> list[RetrievalCandidate]:
    candidates_list = list(candidates)
    if not candidates_list:
        return []

    logger.info("Reranking %d candidate chunks", len(candidates_list))
    reranker = CrossEncoder(config.RERANK_MODEL_NAME)
    pairs = [(query_text, candidate.text) for candidate in candidates_list]
    scores = reranker.predict(pairs, convert_to_numpy=True, batch_size=16)

    scored_candidates = sorted(
        zip(candidates_list, scores.tolist()), key=lambda pair: pair[1], reverse=True
    )

    reranked = [candidate for candidate, _score in scored_candidates[:top_n]]
    logger.info("Selected top %d reranked chunks", len(reranked))
    return reranked


def build_prompt(query_text: str, candidates: Iterable[RetrievalCandidate]) -> str:
    candidates_list = list(candidates)
    if not candidates_list:
        return f"Question: {query_text}\n\nNo relevant passages were found for the requested role."

    context_sections = []
    for idx, candidate in enumerate(candidates_list, start=1):
        source = f"{candidate.source_document} ({candidate.collection})"
        context_sections.append(
            f"Source {idx}: {source}\n{candidate.text.strip()}"
        )

    prompt = (
        "Use the passages below to answer the user question. Cite the source document and collection for every fact. "
        "If the answer cannot be found in the provided passages, say that you do not know.\n\n"
        "QUESTION:\n"
        f"{query_text}\n\n"
        "PASSAGES:\n"
        f"{chr(10).join(context_sections)}\n\n"
        "Answer:\n"
    )
    return prompt


def retrieve_and_prepare_prompt(
    query_text: str,
    role: str,
    retrieval_k: int = DEFAULT_RETRIEVAL_K,
    rerank_k: int = DEFAULT_RERANK_K,
) -> tuple[str, list[RetrievalCandidate]]:
    candidates = hybrid_search(query_text=query_text, role=role, limit=retrieval_k)
    reranked = rerank_candidates(query_text=query_text, candidates=candidates, top_n=rerank_k)
    prompt = build_prompt(query_text=query_text, candidates=reranked)
    return prompt, reranked


def _confirm_rbac_filter(candidates: list[RetrievalCandidate], role: str) -> None:
    for candidate in candidates:
        access_roles = candidate.metadata.get("access_roles", [])
        if role not in access_roles:
            raise RuntimeError(
                "RBAC filter failed: retrieved a candidate that the current role is not allowed to access"
            )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Run the hybrid retrieval + reranking pipeline against Qdrant.")
    parser.add_argument("query", type=str, help="Natural language query")
    parser.add_argument("--role", type=str, default="doctor", help="Requesting user role")
    parser.add_argument("--retrieval-k", type=int, default=DEFAULT_RETRIEVAL_K, help="Number of raw retrieval candidates")
    parser.add_argument("--rerank-k", type=int, default=DEFAULT_RERANK_K, help="Number of reranked candidates to keep")
    args = parser.parse_args()

    prompt, reranked = retrieve_and_prepare_prompt(
        query_text=args.query,
        role=args.role,
        retrieval_k=args.retrieval_k,
        rerank_k=args.rerank_k,
    )

    print("\n=== RERANKED CANDIDATES ===")
    for idx, candidate in enumerate(reranked, start=1):
        print(f"\n[{idx}] score={candidate.score:.4f} source={candidate.source_document} collection={candidate.collection}")
        print(candidate.text[:800])

    print("\n=== GENERATED PROMPT ===")
    print(prompt)


if __name__ == "__main__":
    main()
