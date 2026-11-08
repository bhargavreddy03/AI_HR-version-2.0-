"""Vector embedding service: dimension validation, tenant-scoped storage, and cosine similarity search."""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppException
from app.modules.embeddings.models import (
    CandidateDocumentEmbedding,
    EmbeddingModel,
    JobEmbedding,
)

logger = logging.getLogger(__name__)


class InvalidEmbeddingDimensionException(AppException):
    """Raised when supplied vector dimension does not match the registered model specifications."""

    def __init__(self, message: str = "Invalid vector dimension for embedding model") -> None:
        super().__init__(
            message=message,
            status_code=400,
            code="INVALID_EMBEDDING_DIMENSION",
        )


class DeprecatedEmbeddingModelException(AppException):
    """Raised when an embedding is generated using an inactive or deprecated model."""

    def __init__(self, message: str = "Embedding model is inactive or deprecated") -> None:
        super().__init__(
            message=message,
            status_code=400,
            code="EMBEDDING_MODEL_INACTIVE",
        )


class EmbeddingModelNotFoundException(AppException):
    """Raised when the specified embedding model is not registered."""

    def __init__(self, message: str = "Embedding model is not registered") -> None:
        super().__init__(
            message=message,
            status_code=404,
            code="EMBEDDING_MODEL_NOT_FOUND",
        )


async def get_embedding_model(
    session: AsyncSession,
    model_identifier: str,
) -> EmbeddingModel:
    """Retrieve and validate the registered embedding model."""
    stmt = select(EmbeddingModel).where(EmbeddingModel.model_identifier == model_identifier)
    result = await session.execute(stmt)
    model = result.scalar_one_or_none()
    if not model:
        raise EmbeddingModelNotFoundException(
            f"Embedding model '{model_identifier}' is not registered in the platform registry"
        )
    return model


async def store_candidate_document_embedding(
    session: AsyncSession,
    tenant_id: UUID,
    document_id: UUID,
    model_identifier: str,
    model_version: str,
    embedding: list[float],
) -> CandidateDocumentEmbedding:
    """Store a tenant-scoped document embedding with model dimension verification.

    Validates that:
    1. The model is registered and active.
    2. The vector length strictly matches expected_dimensions.
    3. Populates exactly the matching typed vector column (1536, 1024, or 768).
    """
    model = await get_embedding_model(session, model_identifier)
    if not model.is_active:
        raise DeprecatedEmbeddingModelException(
            f"Embedding model '{model_identifier}' is deprecated or inactive"
        )

    dimensions = len(embedding)
    if dimensions != model.expected_dimensions:
        raise InvalidEmbeddingDimensionException(
            f"Vector dimension {dimensions} does not match model '{model_identifier}' expected {model.expected_dimensions}"
        )

    emb_1536 = embedding if dimensions == 1536 else None
    emb_1024 = embedding if dimensions == 1024 else None
    emb_768 = embedding if dimensions == 768 else None

    record = CandidateDocumentEmbedding(
        tenant_id=tenant_id,
        document_id=document_id,
        model_identifier=model_identifier,
        model_version=model_version,
        vector_dimensions=dimensions,
        embedding_1536=emb_1536,
        embedding_1024=emb_1024,
        embedding_768=emb_768,
    )
    session.add(record)
    await session.flush()
    return record


async def store_job_embedding(
    session: AsyncSession,
    tenant_id: UUID,
    job_id: UUID,
    model_identifier: str,
    model_version: str,
    embedding: list[float],
) -> JobEmbedding:
    """Store a tenant-scoped job embedding with model dimension verification."""
    model = await get_embedding_model(session, model_identifier)
    if not model.is_active:
        raise DeprecatedEmbeddingModelException(
            f"Embedding model '{model_identifier}' is deprecated or inactive"
        )

    dimensions = len(embedding)
    if dimensions != model.expected_dimensions:
        raise InvalidEmbeddingDimensionException(
            f"Vector dimension {dimensions} does not match model '{model_identifier}' expected {model.expected_dimensions}"
        )

    emb_1536 = embedding if dimensions == 1536 else None
    emb_1024 = embedding if dimensions == 1024 else None
    emb_768 = embedding if dimensions == 768 else None

    record = JobEmbedding(
        tenant_id=tenant_id,
        job_id=job_id,
        model_identifier=model_identifier,
        model_version=model_version,
        vector_dimensions=dimensions,
        embedding_1536=emb_1536,
        embedding_1024=emb_1024,
        embedding_768=emb_768,
    )
    session.add(record)
    await session.flush()
    return record


async def search_similar_candidate_documents(
    session: AsyncSession,
    tenant_id: UUID,
    query_vector: list[float],
    model_identifier: str,
    limit: int = 10,
) -> list[tuple[CandidateDocumentEmbedding, float]]:
    """Execute tenant-scoped cosine similarity search across candidate document vectors.

    Uses pgvector's cosine distance operator (<=>).
    Returns list of (CandidateDocumentEmbedding, cosine_similarity) tuples sorted by highest similarity.
    Cosine similarity = 1 - cosine_distance.
    """
    dimensions = len(query_vector)

    if dimensions == 1536:
        vector_col = CandidateDocumentEmbedding.embedding_1536
    elif dimensions == 1024:
        vector_col = CandidateDocumentEmbedding.embedding_1024
    elif dimensions == 768:
        vector_col = CandidateDocumentEmbedding.embedding_768
    else:
        raise InvalidEmbeddingDimensionException(
            f"Unsupported query vector dimension: {dimensions}"
        )

    distance_expr = vector_col.cosine_distance(query_vector)
    stmt = (
        select(CandidateDocumentEmbedding, distance_expr.label("distance"))
        .where(
            CandidateDocumentEmbedding.tenant_id == tenant_id,
            CandidateDocumentEmbedding.model_identifier == model_identifier,
            vector_col.is_not(None),
        )
        .order_by(distance_expr.asc())
        .limit(limit)
    )

    results = await session.execute(stmt)
    items: list[tuple[CandidateDocumentEmbedding, float]] = []
    for row in results.all():
        doc_emb, dist = row[0], row[1]
        similarity = 1.0 - float(dist) if dist is not None else 0.0
        items.append((doc_emb, similarity))

    return items
