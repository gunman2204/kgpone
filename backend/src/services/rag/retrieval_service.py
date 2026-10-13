"""
Hybrid Retrieval Service with parallel execution and Reciprocal Rank Fusion.

Executes Qdrant vector search and Neo4j graph traversal concurrently via
asyncio.gather(), then merges results using RRF for a unified ranking.
"""

import asyncio
import logging
from typing import Any, List, Dict

from src.services.rag.base import BaseRetriever
from src.services.ingestion.embedding.base import BaseEmbedder
from src.utils.interfaces import IVectorRepo
from src.repositories.neo4j.graph_repository import Neo4jRepo
from src.schemas.query_schema import QueryPlan
from src.services.rag.fusion import reciprocal_rank_fusion
from src.repositories.s3.storage_repository import S3Storage

logger = logging.getLogger("retrieval_service")


class RetrievalService(BaseRetriever):
    def __init__(
        self,
        embedder: BaseEmbedder,
        cloud_vector_store: IVectorRepo,
        local_vector_store: IVectorRepo,
        db=None,
        collection_name: str = "documents",
    ):
        self.embedder = embedder
        self.cloud_vector_store = cloud_vector_store
        self.local_vector_store = local_vector_store
        self.db = db
        self.collection_name = collection_name
        self.graph_repo = Neo4jRepo()

    async def retrieve_context(self, query: str, plan: QueryPlan, document_ids: list[str] | None = None) -> dict[str, Any]:
        """
        Coordinates hybrid vector + graph retrieval based on QueryPlan.
        Uses asyncio.gather() for parallel execution and RRF for fusion.
        """
        logger.info(f"Retrieving context for intent: '{plan.intent}' with backends: {plan.backends_needed}")

        # Build retrieval tasks for parallel execution
        tasks = []
        task_labels = []

        if "qdrant" in plan.backends_needed:
            tasks.append(self._retrieve_vector(query, plan, document_ids))
            task_labels.append("qdrant")

        if "neo4j" in plan.backends_needed:
            tasks.append(self._retrieve_graph(plan))
            task_labels.append("neo4j")

        if "postgresql" in plan.backends_needed:
            tasks.append(self._retrieve_postgres(plan))
            task_labels.append("postgresql")

        # Execute all retrievals in parallel
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
        else:
            results = []

        # Collect successful results for RRF
        result_lists = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Retrieval from {task_labels[i]} failed: {result}")
                continue
            if result:
                result_lists.append(result)

        # Merge via Reciprocal Rank Fusion
        if len(result_lists) > 1:
            merged_chunks = reciprocal_rank_fusion(result_lists)
        elif len(result_lists) == 1:
            merged_chunks = result_lists[0]
        else:
            merged_chunks = []

        return {
            "query": query,
            "course_code": plan.course_code,
            "retrieved_chunks": merged_chunks,
            "graph_visualization": {"nodes": [], "edges": []},
            "has_missing_prerequisites": plan.intent == "prerequisites",
        }

    async def _retrieve_vector(self, query: str, plan: QueryPlan, document_ids: list[str] | None = None) -> List[Dict[str, Any]]:
        """Qdrant vector search — fetches top candidates and formats DOM metadata."""
        chunks = []
        try:
            query_vector = await self.embedder.embed_query(query)
            if not query_vector:
                return chunks

            filters = {}
            if plan.course_code:
                filters["course_code"] = plan.course_code
            if getattr(plan, "course_offering_id", None):
                filters["course_offering_id"] = plan.course_offering_id
            vector_store = self.cloud_vector_store
            if document_ids:
                filters["document_id"] = document_ids # Qdrant supports matching against lists
                vector_store = self.local_vector_store

            # For figure searches fetch more candidates so we don't miss image chunks
            is_figure_query = plan.intent == "figure_search"
            limit = 50 if is_figure_query else 30

            try:
                search_results = await asyncio.to_thread(
                    vector_store.search,
                    collection_name=self.collection_name,
                    query_vector=query_vector,
                    limit=limit,
                    filters=filters if filters else None,
                )
            except Exception as search_err:
                if vector_store != self.local_vector_store:
                    logger.warning(f"Vector search against cloud store failed ({search_err}). Falling back to local vector store.")
                    vector_store = self.local_vector_store
                    search_results = await asyncio.to_thread(
                        vector_store.search,
                        collection_name=self.collection_name,
                        query_vector=query_vector,
                        limit=limit,
                        filters=filters if filters else None,
                    )
                else:
                    raise search_err

            for r in search_results:
                payload = r.payload or {}
                chunk_type = payload.get("chunk_type", "text")
                context_path = payload.get("context_path", [])

                # Build context breadcrumb
                breadcrumb = ""
                if context_path:
                    breadcrumb = f"[Context: {' › '.join(context_path)}]\n"

                # Build formatted_text based on chunk type
                if chunk_type == "equation":
                    eq_label = payload.get("equation_label")
                    label_str = f"Equation ({eq_label})" if eq_label else "Equation"
                    raw_text = payload.get("content", payload.get("text", ""))
                    # Strip the chunker's breadcrumb prefix to get just the equation
                    if "]\n[Eq" in raw_text:
                        eq_body = raw_text.split("]\n", 1)[-1]
                    else:
                        eq_body = raw_text
                    formatted_text = f"{breadcrumb}[{label_str}]:\n{eq_body}"

                elif chunk_type == "figure":
                    image_s3_key = payload.get("image_s3_key", "")
                    raw_text = payload.get("content", payload.get("text", ""))
                    # Only include the image reference line if we actually have an S3 key.
                    # The presigned URL will be injected later by _inject_presigned_image_urls.
                    if image_s3_key:
                        formatted_text = f"{breadcrumb}[Figure — image S3 key: {image_s3_key}]\n{raw_text}"
                    else:
                        formatted_text = f"{breadcrumb}[Figure]\n{raw_text}"

                elif chunk_type == "table_row":
                    headers = payload.get("headers", [])
                    table_title = payload.get("parent_table_title", "Table")
                    formatted_text = f"{breadcrumb}Table '{table_title}' Row:\n"
                    if headers:
                        formatted_text += f"Headers: | {' | '.join(headers)} |\n"
                    formatted_text += f"Row Data: {payload.get('content', payload.get('text', ''))}"

                else:
                    # Standard text/heading/list chunk
                    raw_text = payload.get("content", payload.get("text", ""))
                    formatted_text = breadcrumb + raw_text

                payload["formatted_text"] = formatted_text

                chunks.append({
                    "id": r.id,
                    "score": r.score,
                    "payload": payload,
                })

            # For figure queries: inject presigned image URLs into the payloads so both
            # the context builder and the LLM can embed the actual images.
            if is_figure_query:
                _inject_presigned_image_urls(chunks)

        except Exception as e:
            logger.exception("Vector retrieval failed")

        return chunks


    async def _retrieve_graph(self, plan: QueryPlan) -> List[Dict[str, Any]]:
        """Neo4j graph traversal — wrapped in asyncio.to_thread for async compat."""
        if self.graph_repo.use_fallback:
            return []

        chunks = []
        try:
            if plan.intent == "prerequisites" and plan.course_code:
                chunks.extend(await self._graph_prerequisites(plan.course_code))

            elif plan.intent in ["topic_explain", "compare", "relationship", "concept_search"]:
                for entity in plan.entities_mentioned:
                    chunks.extend(await self._graph_entity_search(entity))
        except Exception as e:
            logger.error(f"Graph retrieval failed: {e}")

        return chunks

    async def _graph_prerequisites(self, course_code: str) -> List[Dict[str, Any]]:
        """Fetches prerequisite chain from Neo4j."""
        cypher = """
        MATCH (c:Course {code: $code})-[:PREREQUISITE*]->(prereq:Course)
        MATCH (prereq)-[:HAS_OFFERING]->(o)-[:HAS_DOCUMENT]->(d)-[:COVERS|:MENTIONS]->(concept)
        RETURN prereq.code as course, concept.name as concept, concept.description as desc
        LIMIT 5
        """
        results = await asyncio.to_thread(
            self.graph_repo.execute_read_query, cypher, {"code": course_code}
        )

        chunks = []
        for r in results:
            chunks.append({
                "id": f"graph_prereq_{r['course']}_{r['concept']}",
                "score": 0.8,
                "payload": {
                    "text": f"Prerequisite Concept ({r['course']}): {r['concept']} - {r.get('desc', '')}",
                    "document_id": "GRAPH",
                    "course_code": r["course"],
                    "is_prerequisite": True,
                    "prerequisite_concept": r["concept"],
                },
            })
        return chunks

    async def _graph_entity_search(self, entity: str) -> List[Dict[str, Any]]:
        """Searches for related Entities, Topics, and Tables in the knowledge graph."""
        cypher = """
        MATCH (n) WHERE toLower(n.name) CONTAINS toLower($entity)
        OPTIONAL MATCH (n)-[r]-(related)
        RETURN labels(n)[0] as source_label, n.name as source, 
               type(r) as relation, 
               labels(related)[0] as target_label, related.name as target, 
               related.description as desc
        LIMIT 10
        """
        results = await asyncio.to_thread(
            self.graph_repo.execute_read_query, cypher, {"entity": entity}
        )

        chunks = []
        for r in results:
            source_label = r.get("source_label")
            if source_label == "Table":
                text_fact = f"Document contains Table: '{r['source']}'. Headers: {r.get('headers', 'N/A')}."
                if r['relation']:
                    text_fact += f" Relation: {r['relation']} {r['target_label']} ({r['target']})"
            elif source_label == "Topic":
                text_fact = f"Document covers Topic: '{r['source']}'."
                if r['relation']:
                    text_fact += f" Relation: {r['relation']} {r['target_label']} ({r['target']})"
            else:
                text_fact = f"Graph Fact: {r['source']} {r['relation']} {r['target_label']} ({r['target']}). {r.get('desc', '')}"
                
            chunks.append({
                "id": f"graph_fact_{r['source']}_{r.get('target', 'None')}",
                "score": 0.7,
                "payload": {
                    "text": text_fact,
                    "formatted_text": text_fact, # For RRF / downstream compatibility
                    "document_id": "GRAPH",
                },
            })
        return chunks

    async def _retrieve_postgres(self, plan: QueryPlan) -> List[Dict[str, Any]]:
        """PostgreSQL document listing for download/list_documents intents."""
        if not self.db:
            return []

        chunks = []
        try:
            if plan.intent in ["list_documents", "download"]:
                from src.repositories.postgres.document_repository import DocumentRepository
                doc_repo = DocumentRepository(self.db)

                if getattr(plan, "course_offering_id", None):
                    docs = await asyncio.to_thread(
                        doc_repo.get_documents_by_offering, plan.course_offering_id
                    )
                    for doc in docs:
                        if doc.status == "COMPLETED":
                            chunks.append({
                                "id": f"pg_doc_{doc.id}",
                                "score": 1.0,
                                "payload": {
                                    "text": f"Document available: {doc.title} (Type: {doc.doc_type}, Description: {doc.description or 'N/A'})",
                                    "document_id": str(doc.id),
                                    "title": doc.title,
                                    "course_code": plan.course_code or "Unknown",
                                    "document_type": doc.doc_type,
                                    "s3_key": doc.s3_key,
                                },
                            })
        except Exception as e:
            logger.error(f"PostgreSQL retrieval failed: {e}")

        return chunks


def _inject_presigned_image_urls(chunks: List[Dict[str, Any]], expiration: int = 3600) -> None:
    """
    For every figure chunk that has an `image_s3_key`, generate a presigned S3 GET URL
    (1-hour expiry by default) and inject it into payload['image_url'].
    Mutates the chunk payloads in place.
    """
    figure_chunks = [
        c for c in chunks
        if c.get("payload", {}).get("chunk_type") == "figure"
        and c.get("payload", {}).get("image_s3_key")
    ]
    if not figure_chunks:
        return
    try:
        s3 = S3Storage()
        for chunk in figure_chunks:
            payload = chunk["payload"]
            payload["image_url"] = s3.generate_presigned_get_url(
                payload["image_s3_key"], expiration=expiration
            )
            # Also update formatted_text to embed the live URL so it's visible in context
            existing_fmt = payload.get("formatted_text", "")
            if payload["image_url"] and "[Figure — image available at:" not in existing_fmt:
                payload["formatted_text"] = (
                    f"{existing_fmt}\n[Figure — image available at: {payload['image_url']}]"
                )
    except Exception as e:
        logger.warning(f"Failed to inject presigned image URLs into figure chunks: {e}")
