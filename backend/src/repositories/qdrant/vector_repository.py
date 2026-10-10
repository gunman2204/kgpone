import uuid
import logging
import asyncio
from qdrant_client.models import VectorParams, Distance, PointStruct, Filter, FieldCondition, MatchValue, PayloadSchemaType
from src.infrastructure.qdrant import get_qdrant_client
from src.utils.interfaces import IVectorRepo

from src.config.settings import Settings

logger = logging.getLogger("qdrant_repository")

class QdrantRepository(IVectorRepo):
    # In-memory storage fallback for offline mode
    _fallback_storage: list[dict] = []

    def __init__(self, vector_size: int = None):
        self.client = get_qdrant_client()
        self.vector_size = vector_size or Settings.EMBEDDING_DIMENSION
        self.use_fallback = False
        if self.client is None:
            logger.warning("[Qdrant Fallback] Qdrant service not connected. Enabling offline in-memory mock search.")
            self.use_fallback = True

    def search(self, collection_name: str, query_vector: list[float], filters: dict | None = None, limit: int = 5):
        if self.use_fallback:
            import math
            def dot_product(v1, v2):
                return sum(x * y for x, y in zip(v1, v2))
            def magnitude(v):
                return math.sqrt(sum(x * x for x in v))

            scored_results = []
            for point in self._fallback_storage:
                # Filter check
                if filters:
                    match = True
                    for k, v in filters.items():
                        if isinstance(v, list):
                            str_v = [str(x) for x in v]
                            if str(point["payload"].get(k)) not in str_v:
                                match = False
                                break
                        elif point["payload"].get(k) != v:
                            match = False
                            break
                    if not match:
                        continue

                # Cosine similarity
                vec = point["vector"]
                mag1 = magnitude(query_vector)
                mag2 = magnitude(vec)
                if mag1 == 0 or mag2 == 0:
                    sim = 0.5 # Neutral baseline
                else:
                    sim = dot_product(query_vector, vec) / (mag1 * mag2)

                # Mock ScoredPoint structure matching qdrant return type attributes
                class MockScoredPoint:
                    def __init__(self, point_id, score, payload):
                        self.id = point_id
                        self.score = score
                        self.payload = payload

                scored_results.append(MockScoredPoint(point["id"], sim, point["payload"]))

            scored_results.sort(key=lambda x: x.score, reverse=True)
            return scored_results[:limit]

        query_filter = None
        if filters:
            from qdrant_client.models import MatchAny
            conditions = []
            for k, v in filters.items():
                if isinstance(v, list):
                    # For Qdrant >= 1.9, use MatchAny to filter by a list of values
                    # If UUIDs, they should be stringified first
                    str_v = [str(x) for x in v]
                    conditions.append(FieldCondition(key=k, match=MatchAny(any=str_v)))
                else:
                    conditions.append(FieldCondition(key=k, match=MatchValue(value=v)))
            query_filter = Filter(must=conditions)
            
        return self.client.query_points(
            collection_name=collection_name,
            query=query_vector,
            query_filter=query_filter,
            limit=limit
        ).points

    def delete_by_filter(self, collection_name: str, filters: dict):
        if self.use_fallback:
            self._fallback_storage = [
                p for p in self._fallback_storage
                if not all(p["payload"].get(k) == v for k, v in filters.items())
            ]
            return

        if not filters:
            return
            
        conditions = [
            FieldCondition(key=k, match=MatchValue(value=v))
            for k, v in filters.items()
        ]
        
        try:
            self.client.delete(
                collection_name=collection_name,
                points_selector=Filter(must=conditions)
            )
        except Exception as e:
            # Qdrant throws error if collection doesn't exist, we treat it as idempotent success
            pass

    def _ensure_collection_exists(self, collection_name: str):
        if self.use_fallback:
            return
        collections_response = self.client.get_collections()
        collection_names = [col.name for col in collections_response.collections]
        
        if collection_name not in collection_names:
            self.client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=self.vector_size, distance=Distance.COSINE),
            )
            
            # Create payload indexes for frequently filtered fields
            self.client.create_payload_index(collection_name, "course_code", field_schema=PayloadSchemaType.KEYWORD)
            self.client.create_payload_index(collection_name, "course_offering_id", field_schema=PayloadSchemaType.KEYWORD)
            self.client.create_payload_index(collection_name, "document_type", field_schema=PayloadSchemaType.KEYWORD)
            self.client.create_payload_index(collection_name, "semester", field_schema=PayloadSchemaType.KEYWORD)
            self.client.create_payload_index(collection_name, "year", field_schema=PayloadSchemaType.INTEGER)

    async def upsert(self, collection_name: str, vectors: list[list[float]], metadata: list[dict]):
        if len(vectors) != len(metadata):
            raise ValueError("The number of vectors must match the number of metadata entries.")
            
        if self.use_fallback:
            for vec, meta in zip(vectors, metadata):
                self._fallback_storage.append({
                    "id": str(uuid.uuid4()),
                    "vector": vec,
                    "payload": meta
                })
            logger.info(f"[Qdrant Fallback] Saved {len(vectors)} points in-memory.")
            return

        # Ensure the collection exists before inserting (blocking call wrapped in thread)
        await asyncio.to_thread(self._ensure_collection_exists, collection_name)

        points = []
        for vec, meta in zip(vectors, metadata):
            points.append(
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector=vec,
                    payload=meta
                )
            )

        # Upsert in batches of 100 to avoid request size limits
        batch_size = 100
        for i in range(0, len(points), batch_size):
            batch = points[i:i + batch_size]
            await asyncio.to_thread(
                self.client.upsert,
                collection_name=collection_name,
                points=batch
            )
