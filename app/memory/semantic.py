"""
Qdrant SemanticICPStore — vector store for semantic ICP matching.

Collection : ``companies``
Vector size: 1536  (OpenAI text-embedding-3-small)

Payload fields stored per point
────────────────────────────────
  domain         : str   (used as stable point ID via UUID5)
  name           : str
  headcount      : int
  funding_stage  : str
  description    : str

Hybrid search = cosine-similarity OVER dense vector
              + Qdrant payload filter (funding_stage in [...] etc.)
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Any

import openai
import structlog
from qdrant_client import AsyncQdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchAny,
    PointIdsList,
    PointStruct,
    VectorParams,
)

logger = structlog.get_logger(__name__)


def _domain_to_uuid(domain: str) -> str:
    """
    Derive a stable Qdrant point UUID from a company domain.
    Uses UUID5 with a fixed namespace so the same domain always maps
    to the same UUID — enabling idempotent upserts.
    """
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, domain))


class SemanticICPStore:
    """
    Async Qdrant store for semantic ICP matching via dense embeddings.

    Parameters
    ----------
    host, port, grpc_port:
        Qdrant server coordinates.
    api_key:
        Optional Qdrant Cloud API key.
    collection_name:
        Target collection (created on connect if absent).
    vector_size:
        Must match the embedding model output (1536 for text-embedding-3-small).
    openai_api_key:
        OpenAI key used to generate embeddings.
    embedding_model:
        OpenAI embedding model name.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6333,
        grpc_port: int = 6334,
        api_key: str | None = None,
        collection_name: str = "companies",
        vector_size: int = 1536,
        openai_api_key: str = "",
        embedding_model: str = "text-embedding-3-small",
    ) -> None:
        self._host = host
        self._port = port
        self._grpc_port = grpc_port
        self._api_key = api_key
        self._collection = collection_name
        self._vector_size = vector_size
        self._embedding_model = embedding_model

        self._client: AsyncQdrantClient | None = None
        self._openai = openai.AsyncOpenAI(api_key=openai_api_key)

    # ── lifecycle ─────────────────────────────────────────────────────────────

    async def connect(self) -> None:
        kwargs: dict[str, Any] = {
            "host": self._host,
            "port": self._port,
            "grpc_port": self._grpc_port,
            "prefer_grpc": True,
        }
        if self._api_key:
            kwargs["api_key"] = self._api_key

        self._client = AsyncQdrantClient(**kwargs)
        await self._ensure_collection()
        logger.info(
            "semantic_store_connected",
            host=self._host,
            collection=self._collection,
        )

    async def _ensure_collection(self) -> None:
        """Create the collection if it does not already exist."""
        exists = await self._client.collection_exists(self._collection)  # type: ignore[union-attr]
        if not exists:
            await self._client.create_collection(  # type: ignore[union-attr]
                collection_name=self._collection,
                vectors_config=VectorParams(
                    size=self._vector_size,
                    distance=Distance.COSINE,
                ),
            )
            logger.info("qdrant_collection_created", collection=self._collection)
        else:
            logger.debug("qdrant_collection_exists", collection=self._collection)

    @property
    def client(self) -> AsyncQdrantClient:
        if self._client is None:
            raise RuntimeError("SemanticICPStore not connected — call connect() first")
        return self._client

    # ── embedding helper ──────────────────────────────────────────────────────

    async def _embed(self, text: str) -> list[float]:
        """Call OpenAI embedding API and return the float vector."""
        response = await self._openai.embeddings.create(
            model=self._embedding_model,
            input=text,
        )
        return response.data[0].embedding

    # ── public API ────────────────────────────────────────────────────────────

    async def upsert_company_embedding(
        self,
        domain: str,
        description: str,
        metadata: dict[str, Any],
    ) -> None:
        """
        Embed *description* and upsert the point into Qdrant.

        The point ID is derived deterministically from *domain* so repeated
        calls update the existing point (idempotent).

        Payload
        -------
        domain, name, headcount, funding_stage, description
        """
        log = logger.bind(domain=domain)
        vector = await self._embed(description)
        point_id = _domain_to_uuid(domain)

        payload: dict[str, Any] = {
            "domain": domain,
            "description": description,
            "name": metadata.get("name", ""),
            "headcount": metadata.get("headcount", 0),
            "funding_stage": metadata.get("funding_stage", ""),
        }
        # Forward any extra scalar metadata
        for k, v in metadata.items():
            if k not in payload and isinstance(v, (str, int, float, bool)):
                payload[k] = v

        await self.client.upsert(
            collection_name=self._collection,
            points=[PointStruct(id=point_id, vector=vector, payload=payload)],
        )
        log.info("company_embedding_upserted", point_id=point_id)

    async def find_similar_companies(
        self,
        icp_description: str,
        top_k: int = 20,
        funding_stage_filter: list[str] | None = None,
        min_headcount: int | None = None,
        max_headcount: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Hybrid search: cosine similarity + optional payload filters.

        Parameters
        ----------
        icp_description:
            Natural-language description of the ideal customer profile.
        top_k:
            Maximum number of results to return.
        funding_stage_filter:
            If provided, only return companies whose ``funding_stage``
            is in this list (e.g. ``["Series A", "Series B"]``).
        min_headcount / max_headcount:
            Optional headcount range filter.

        Returns
        -------
        list of dicts with keys: domain, name, headcount, funding_stage,
        description, score.
        """
        log = logger.bind(top_k=top_k)
        query_vector = await self._embed(icp_description)

        # Build Qdrant filter
        conditions = []
        if funding_stage_filter:
            conditions.append(
                FieldCondition(
                    key="funding_stage",
                    match=MatchAny(any=funding_stage_filter),
                )
            )
        if min_headcount is not None:
            from qdrant_client.models import Range

            conditions.append(
                FieldCondition(
                    key="headcount",
                    range=Range(gte=min_headcount),
                )
            )
        if max_headcount is not None:
            from qdrant_client.models import Range

            conditions.append(
                FieldCondition(
                    key="headcount",
                    range=Range(lte=max_headcount),
                )
            )

        qdrant_filter = Filter(must=conditions) if conditions else None

        results = await self.client.search(
            collection_name=self._collection,
            query_vector=query_vector,
            limit=top_k,
            query_filter=qdrant_filter,
            with_payload=True,
        )

        candidates = []
        for hit in results:
            payload = hit.payload or {}
            candidates.append(
                {
                    "domain": payload.get("domain"),
                    "name": payload.get("name"),
                    "headcount": payload.get("headcount"),
                    "funding_stage": payload.get("funding_stage"),
                    "description": payload.get("description"),
                    "score": hit.score,
                }
            )

        log.info("semantic_search_complete", returned=len(candidates))
        return candidates

    async def delete_company(self, domain: str) -> None:
        """Remove the point for *domain* from the collection."""
        point_id = _domain_to_uuid(domain)
        await self.client.delete(
            collection_name=self._collection,
            points_selector=PointIdsList(points=[point_id]),
        )
        logger.info("company_embedding_deleted", domain=domain, point_id=point_id)

    # ── health ─────────────────────────────────────────────────────────────────

    async def ping(self) -> bool:
        """Return True if Qdrant is reachable."""
        try:
            await self.client.get_collections()
            return True
        except Exception:
            return False
