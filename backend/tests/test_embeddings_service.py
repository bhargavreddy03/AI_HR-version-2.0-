"""Unit tests for the vector embedding service: model registry, dimension checks, vector validation, and similarity search."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.modules.embeddings.models import (
    CandidateDocumentEmbedding,
    EmbeddingModel,
)
from app.modules.embeddings.service import (
    DeprecatedEmbeddingModelException,
    EmbeddingModelNotFoundException,
    InvalidEmbeddingDimensionException,
    InvalidSearchParameterException,
    _validate_vector_elements,
    get_embedding_model,
    search_similar_candidate_documents,
    store_candidate_document_embedding,
    store_job_embedding,
)


def test_validate_vector_elements_valid() -> None:
    """Finite positive and negative floats/ints are accepted."""
    _validate_vector_elements([0.1, -0.5, 1.0, 0.0, 42])
    # With non-zero magnitude check
    _validate_vector_elements([0.0, 0.1], check_zero_magnitude=True)


def test_validate_vector_elements_empty_rejected() -> None:
    """Empty vector is rejected with InvalidSearchParameterException."""
    with pytest.raises(InvalidSearchParameterException, match="cannot be empty"):
        _validate_vector_elements([])


def test_validate_vector_elements_non_list_rejected() -> None:
    """Non-list input is rejected."""
    with pytest.raises(InvalidSearchParameterException, match="cannot be empty"):
        _validate_vector_elements("not a list")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "bad_element",
    [float("nan"), float("inf"), float("-inf"), True, False, "0.5", None],
)
def test_validate_vector_elements_invalid_values_rejected(bad_element: object) -> None:
    """Non-finite, boolean, or non-numeric elements are rejected."""
    with pytest.raises(InvalidSearchParameterException, match="contains invalid non-finite value"):
        _validate_vector_elements([0.1, bad_element, 0.3])  # type: ignore[list-item]


def test_validate_vector_elements_zero_magnitude_rejected() -> None:
    """All-zero vectors are rejected when check_zero_magnitude=True."""
    with pytest.raises(InvalidSearchParameterException, match="zero magnitude"):
        _validate_vector_elements([0.0, 0.0, 0.0], check_zero_magnitude=True)


@pytest.mark.asyncio
async def test_get_embedding_model_success() -> None:
    """Registered active model is retrieved successfully."""
    mock_session = AsyncMock()
    mock_model = EmbeddingModel(
        model_identifier="text-embedding-3-small",
        provider="openai",
        expected_dimensions=1536,
        is_active=True,
    )
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_model
    mock_session.execute.return_value = mock_result

    model = await get_embedding_model(mock_session, "text-embedding-3-small")
    assert model.model_identifier == "text-embedding-3-small"
    assert model.expected_dimensions == 1536


@pytest.mark.asyncio
async def test_get_embedding_model_not_found() -> None:
    """Unregistered model raises EmbeddingModelNotFoundException (404)."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result

    with pytest.raises(EmbeddingModelNotFoundException) as exc_info:
        await get_embedding_model(mock_session, "non-existent-model")
    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "EMBEDDING_MODEL_NOT_FOUND"


@pytest.mark.asyncio
async def test_store_candidate_document_embedding_success() -> None:
    """Active model with matching dimension correctly populates candidate document record."""
    mock_session = AsyncMock()
    mock_model = EmbeddingModel(
        model_identifier="text-embedding-3-small",
        provider="openai",
        expected_dimensions=1536,
        is_active=True,
    )
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_model
    mock_session.execute.return_value = mock_result

    tenant_id = uuid4()
    doc_id = uuid4()
    vector = [0.01] * 1536

    record = await store_candidate_document_embedding(
        session=mock_session,
        tenant_id=tenant_id,
        document_id=doc_id,
        model_identifier="text-embedding-3-small",
        model_version="1.0",
        embedding=vector,
    )
    assert record.tenant_id == tenant_id
    assert record.document_id == doc_id
    assert record.vector_dimensions == 1536
    assert record.embedding_1536 == vector
    assert record.embedding_1024 is None
    assert record.embedding_768 is None
    mock_session.add.assert_called_once_with(record)
    mock_session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_store_candidate_document_embedding_inactive_rejected() -> None:
    """Deprecated or inactive model raises DeprecatedEmbeddingModelException."""
    mock_session = AsyncMock()
    mock_model = EmbeddingModel(
        model_identifier="old-model",
        provider="openai",
        expected_dimensions=1536,
        is_active=False,
    )
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_model
    mock_session.execute.return_value = mock_result

    with pytest.raises(DeprecatedEmbeddingModelException) as exc_info:
        await store_candidate_document_embedding(
            session=mock_session,
            tenant_id=uuid4(),
            document_id=uuid4(),
            model_identifier="old-model",
            model_version="1.0",
            embedding=[0.1] * 1536,
        )
    assert exc_info.value.code == "EMBEDDING_MODEL_INACTIVE"


@pytest.mark.asyncio
async def test_store_candidate_document_embedding_dimension_mismatch() -> None:
    """Supplying wrong vector dimension raises InvalidEmbeddingDimensionException."""
    mock_session = AsyncMock()
    mock_model = EmbeddingModel(
        model_identifier="text-embedding-3-small",
        provider="openai",
        expected_dimensions=1536,
        is_active=True,
    )
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_model
    mock_session.execute.return_value = mock_result

    with pytest.raises(InvalidEmbeddingDimensionException) as exc_info:
        await store_candidate_document_embedding(
            session=mock_session,
            tenant_id=uuid4(),
            document_id=uuid4(),
            model_identifier="text-embedding-3-small",
            model_version="1.0",
            embedding=[0.1] * 768,  # Mismatch: 768 != 1536
        )
    assert exc_info.value.code == "INVALID_EMBEDDING_DIMENSION"


@pytest.mark.asyncio
async def test_store_job_embedding_success() -> None:
    """Job embedding storage verifies model dimension and populates correct column."""
    mock_session = AsyncMock()
    mock_model = EmbeddingModel(
        model_identifier="bge-base-en-v1.5",
        provider="baai",
        expected_dimensions=768,
        is_active=True,
    )
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_model
    mock_session.execute.return_value = mock_result

    tenant_id = uuid4()
    job_id = uuid4()
    vector = [0.05] * 768

    record = await store_job_embedding(
        session=mock_session,
        tenant_id=tenant_id,
        job_id=job_id,
        model_identifier="bge-base-en-v1.5",
        model_version="1.5",
        embedding=vector,
    )
    assert record.tenant_id == tenant_id
    assert record.job_id == job_id
    assert record.vector_dimensions == 768
    assert record.embedding_768 == vector
    assert record.embedding_1536 is None
    assert record.embedding_1024 is None
    mock_session.add.assert_called_once_with(record)
    mock_session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_store_job_embedding_dimension_mismatch() -> None:
    """Supplying vector dimension not matching job embedding model raises exception."""
    mock_session = AsyncMock()
    mock_model = EmbeddingModel(
        model_identifier="bge-base-en-v1.5",
        provider="baai",
        expected_dimensions=768,
        is_active=True,
    )
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_model
    mock_session.execute.return_value = mock_result

    with pytest.raises(InvalidEmbeddingDimensionException):
        await store_job_embedding(
            session=mock_session,
            tenant_id=uuid4(),
            job_id=uuid4(),
            model_identifier="bge-base-en-v1.5",
            model_version="1.5",
            embedding=[0.1] * 512,
        )


@pytest.mark.parametrize("bad_limit", [0, -1, 101, "10", True, False, None])
@pytest.mark.asyncio
async def test_search_similar_candidate_documents_invalid_limit(bad_limit: object) -> None:
    """Invalid limit raises InvalidSearchParameterException."""
    mock_session = AsyncMock()
    with pytest.raises(InvalidSearchParameterException, match="limit must be a positive integer"):
        await search_similar_candidate_documents(
            session=mock_session,
            tenant_id=uuid4(),
            query_vector=[0.1] * 768,
            model_identifier="bge-base-en-v1.5",
            limit=bad_limit,  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_search_similar_candidate_documents_dimension_mismatch() -> None:
    """Search query vector dimension mismatch raises InvalidEmbeddingDimensionException."""
    mock_session = AsyncMock()
    mock_model = EmbeddingModel(
        model_identifier="cohere.embed-english-v3",
        provider="cohere",
        expected_dimensions=1024,
        is_active=True,
    )
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_model
    mock_session.execute.return_value = mock_result

    with pytest.raises(InvalidEmbeddingDimensionException) as exc_info:
        await search_similar_candidate_documents(
            session=mock_session,
            tenant_id=uuid4(),
            query_vector=[0.1] * 768,  # Mismatch: 768 != 1024
            model_identifier="cohere.embed-english-v3",
            limit=10,
        )
    assert exc_info.value.code == "INVALID_EMBEDDING_DIMENSION"


@pytest.mark.asyncio
async def test_search_similar_candidate_documents_success() -> None:
    """Similarity search maps cosine distance into similarity score (1 - distance)."""
    mock_session = AsyncMock()
    mock_model = EmbeddingModel(
        model_identifier="cohere.embed-english-v3",
        provider="cohere",
        expected_dimensions=1024,
        is_active=True,
    )
    mock_doc = CandidateDocumentEmbedding(
        id=uuid4(),
        tenant_id=uuid4(),
        document_id=uuid4(),
        model_identifier="cohere.embed-english-v3",
        vector_dimensions=1024,
    )
    # Cosine distance = 0.15 -> Cosine similarity = 0.85
    mock_row = (mock_doc, 0.15)
    mock_db_res = MagicMock()
    mock_db_res.all.return_value = [mock_row]

    mock_model_res = MagicMock()
    mock_model_res.scalar_one_or_none.return_value = mock_model

    mock_session.execute.side_effect = [mock_model_res, mock_db_res]

    results = await search_similar_candidate_documents(
        session=mock_session,
        tenant_id=uuid4(),
        query_vector=[0.05] * 1024,
        model_identifier="cohere.embed-english-v3",
        limit=5,
    )
    assert len(results) == 1
    doc, similarity = results[0]
    assert doc == mock_doc
    assert round(similarity, 2) == 0.85
