"""Embeddings module exports."""

from app.modules.embeddings.models import (
    APPROVED_MODELS,
    CandidateDocumentEmbedding,
    EmbeddingModel,
    JobEmbedding,
)
from app.modules.embeddings.service import (
    DeprecatedEmbeddingModelException,
    EmbeddingModelNotFoundException,
    InvalidEmbeddingDimensionException,
    InvalidSearchParameterException,
    get_embedding_model,
    search_similar_candidate_documents,
    store_candidate_document_embedding,
    store_job_embedding,
)

__all__ = [
    "APPROVED_MODELS",
    "CandidateDocumentEmbedding",
    "DeprecatedEmbeddingModelException",
    "EmbeddingModel",
    "EmbeddingModelNotFoundException",
    "InvalidEmbeddingDimensionException",
    "InvalidSearchParameterException",
    "JobEmbedding",
    "get_embedding_model",
    "search_similar_candidate_documents",
    "store_candidate_document_embedding",
    "store_job_embedding",
]
