from fastapi import APIRouter, Depends, status, Request
from fastapi.responses import StreamingResponse
from typing import List
import json
import time
import logging
from src.utils.logger import setup_logger
from src.repositories.s3.storage_repository import S3Storage

logger = setup_logger("query_routes")
from src.schemas.query_schema import QueryRequest, QueryResponse, SearchResult
from src.schemas.response_schema import StandardResponse
from src.services.rag.nlp_planner_service import NLPPlannerService
from src.services.rag.retrieval_service import RetrievalService, _inject_presigned_image_urls
from src.services.rag.cross_encoder_rerank_service import CrossEncoderRerankService
from src.services.rag.citation_service import CitationService
from src.services.rag.answer_service import AnswerService
from src.services.rag.semantic_cache_service import SemanticCacheService
from src.services.ingestion.embedding.llm_embedding import LLMEmbedder
from src.repositories.qdrant.vector_repository import QdrantRepository
from src.infrastructure.database import get_db
from sqlalchemy.orm import Session
from src.infrastructure.llm_factory import LLMFactory
from src.api.middleware.auth_middleware import get_current_user
from src.models.user_model import User
from src.repositories.postgres.chat_repository import ChatRepository
from src.models.chat_model import MessageRole

router = APIRouter(prefix="/query", tags=["Query & RAG"])

def get_rag_services(db: Session = Depends(get_db)):
    planner = NLPPlannerService()
    embedder = LLMEmbedder()
    vector_repo = QdrantRepository()
    retriever = RetrievalService(embedder=embedder, vector_store=vector_repo, db=db)
    reranker = CrossEncoderRerankService()
    citation_formatter = CitationService()
    answer_generator = AnswerService()
    semantic_cache = SemanticCacheService()
    llm_factory = LLMFactory()

    return {
        "planner": planner,
        "retriever": retriever,
        "reranker": reranker,
        "citation_formatter": citation_formatter,
        "answer_generator": answer_generator,
        "embedder": embedder,
        "semantic_cache": semantic_cache,
        "llm_factory": llm_factory,
    }

@router.post("/ask", response_model=StandardResponse[QueryResponse])
async def ask_question(req: QueryRequest, services: dict = Depends(get_rag_services)):
    """Full hybrid RAG pipeline: Cache Check -> Plan -> Retrieve -> Rerank -> Answer"""
    query = req.query
    course_code = req.course_code
    course_offering_id = req.course_offering_id
    
    # 0. Semantic Cache Check
    cache_hit = False
    semantic_cache = services["semantic_cache"]
    embedder = services["embedder"]
    
    # Generate embedding for cache lookup (reused later for retrieval)
    try:
        query_embedding = await embedder.embed_query(query)
    except Exception as e:
        logger.error(f"Error embedding query: {e}")
        query_embedding = []
    
    if query_embedding:
        scope_key = course_offering_id if course_offering_id else None
        cached = await semantic_cache.get(query, query_embedding, scope_key=scope_key)
        if cached:
            # Return cached response directly
            cached["cache_hit"] = True
            return StandardResponse(
                status="success",
                message="Query answered from cache",
                data=QueryResponse(**cached),
            )
    
    # 1. Plan
    plan = await services["planner"].detect_intent(query, course_code, course_offering_id)
    
    # 2. Retrieve
    context = await services["retriever"].retrieve_context(query, plan, document_ids=req.document_ids)

    # 2b. Inject presigned image URLs into ALL figure chunks now so the answer
    #     service context builder can pass live URLs to the LLM.
    _inject_presigned_image_urls(context["retrieved_chunks"])

    # 3. Rerank
    reranked_chunks = await services["reranker"].rerank_chunks(query, context["retrieved_chunks"], top_n=10)
    
    # 4. Format Citations if requested
    citations = []
    if req.use_citations:
        citations = services["citation_formatter"].format_citations(reranked_chunks)
        # Enrich figure citations with presigned GET URLs
        _enrich_citations_with_image_urls(citations)
        _enrich_citations_with_document_urls(citations)

    # 5. Generate Answer
    answer = services["answer_generator"].generate_answer(query, reranked_chunks, citations, use_citations=req.use_citations)
    
    # Build Sources (unique documents)
    sources = []
    seen_docs = set()
    for chunk in reranked_chunks:
        payload = chunk.get("payload", {})
        doc_id = payload.get("document_id")
        if doc_id and doc_id != "GRAPH" and doc_id not in seen_docs:
            seen_docs.add(doc_id)
            sources.append({
                "document_id": doc_id,
                "title": payload.get("document_title", payload.get("title", "Unknown")),
                "course_code": payload.get("course_code", ""),
                "doc_type": payload.get("document_type", "Notes"),
                "s3_key": payload.get("s3_key", "")
            })
            
    response_data = QueryResponse(
        answer=answer,
        citations=citations,
        sources=sources,
        graph_context=context.get("graph_visualization"),
        intent=plan.intent,
        backends_used=plan.backends_needed,
        cache_hit=False,
        confidence_score=plan.confidence_score,
    )
    
    # 6. Cache the response for future identical queries
    if query_embedding:
        scope_key = course_offering_id if course_offering_id else None
        try:
            await semantic_cache.set(
                query,
                query_embedding,
                response_data.model_dump(),
                scope_key=scope_key,
            )
        except Exception:
            pass  # Cache write failure is non-critical
    
    return StandardResponse(
        status="success",
        message="Query answered successfully",
        data=response_data
    )

@router.post("/ask_stream")
async def ask_question_stream(
    req: QueryRequest, 
    services: dict = Depends(get_rag_services),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """SSE endpoint for streaming the RAG answer.

    Supports two modes controlled by `analysis_mode` in the request body:
      - 'basic'    : fast NLP planner (~3ms) → deterministic retrieval pipeline.
      - 'advanced' : tool-calling agent → autonomously fetches context via tools
                     before handing off to the generator.

    Also supports BYOK via `byok_provider`, `byok_api_key`, `byok_model` fields.
    BYOK keys are used only for this request and are never stored.
    """
    query = req.query
    course_code = req.course_code
    course_offering_id = req.course_offering_id
    t0 = time.time()
    
    chat_repo = ChatRepository(db)
    
    chat_history_dicts = []
    user_memories_strs = []
    
    # Load user memories
    memories = chat_repo.get_user_memories(user.id)
    user_memories_strs = [m.fact for m in memories]
    
    # ── Handle Conversation State ──
    if req.conversation_id:
        conversation = chat_repo.get_conversation(req.conversation_id, load_messages=True)
        if not conversation or conversation.user_id != user.id:
            req.conversation_id = None # Fallback to new if invalid
        else:
            if conversation.summary:
                summary_text = f"Previous Conversation Summary: {conversation.summary}"
                if conversation.keywords:
                    summary_text += f"\nKeywords: {conversation.keywords}"
                chat_history_dicts.append({"role": "system", "content": summary_text})
                
            # Only keep the last 5 messages to avoid huge context sizes
            for msg in conversation.messages[-5:]:
                chat_history_dicts.append({"role": msg.role.value, "content": msg.content})
    
    if not req.conversation_id:
        # Title can be generated later async, just use query snippet for now
        conversation = chat_repo.create_conversation(user.id, title=req.query[:50] + "..." if len(req.query) > 50 else req.query)
        req.conversation_id = conversation.id
        
    # Add user message
    chat_repo.add_message(req.conversation_id, MessageRole.USER, query)

    # ── Planner: Basic (NLP) or Advanced (Tool-Calling Agent) ──
    if req.analysis_mode == "advanced":
        from src.services.rag.agentic_planner_service import AgenticPlannerService
        llm_factory = services["llm_factory"]
        agent_llm = llm_factory.get_llm_for_request(
            byok_provider=req.byok_provider,
            byok_api_key=req.byok_api_key,
            byok_model=req.byok_model,
        )
        planner = AgenticPlannerService(llm=agent_llm)
        logger.info(f"[Mode] Advanced Agent (BYOK={bool(req.byok_api_key)})")
    else:
        planner = services["planner"]
        logger.info("[Mode] Basic NLP planner")

    if req.analysis_mode == "general":
        from src.schemas.query_schema import QueryPlan
        plan = QueryPlan(intent="general_qa", backends_needed=[])
        logger.info("[Mode] General bypass requested")
    else:
        plan = await planner.detect_intent(query, course_code, course_offering_id)
    t1 = time.time()
    logger.info(f"[PERF] Planner took: {t1 - t0:.4f}s")

    if plan.intent == "general_qa":
        logger.info("[Bypass] General QA detected. Bypassing RAG pipeline.")
        async def general_event_generator():
            full_response = ""
            async for text_chunk in services["answer_generator"].generate_general_answer_stream(query, chat_history=chat_history_dicts, user_memories=user_memories_strs):
                full_response += text_chunk
                yield f"data: {json.dumps({'type': 'chunk', 'content': text_chunk})}\n\n"
            metadata = {
                "type": "metadata",
                "citations": [],
                "sources": [],
                "intent": plan.intent,
                "backends_used": [],
                "conversation_id": str(req.conversation_id)
            }
            chat_repo.add_message(req.conversation_id, MessageRole.ASSISTANT, full_response, metadata)
            
            import asyncio
            from src.workers.tasks.memory_tasks import extract_user_memory_task
            asyncio.create_task(extract_user_memory_task(req.conversation_id))
            
            yield f"data: {json.dumps(metadata)}\n\n"
        return StreamingResponse(general_event_generator(), media_type="text/event-stream")

    # Agent pre-fetched chunks (only present in advanced mode)
    agent_chunks = getattr(plan, "_agent_chunks", [])

    context = await services["retriever"].retrieve_context(query, plan, document_ids=req.document_ids)
    t2 = time.time()
    logger.info(f"[PERF] Retriever took: {t2 - t1:.4f}s")

    # Merge agent tool results with retriever results (agent chunks get priority)
    if agent_chunks:
        context["retrieved_chunks"] = agent_chunks + context["retrieved_chunks"]
        logger.info(f"[Agent] Injected {len(agent_chunks)} pre-fetched tool chunks")

    # Inject presigned image URLs into all figure chunks so the LLM context includes them
    _inject_presigned_image_urls(context["retrieved_chunks"])

    reranked_chunks = await services["reranker"].rerank_chunks(query, context["retrieved_chunks"], top_n=10)
    t3 = time.time()
    logger.info(f"[PERF] Reranker took: {t3 - t2:.4f}s")
    
    citations = services["citation_formatter"].format_citations(reranked_chunks)
    # Enrich figure citations with presigned GET URLs
    _enrich_citations_with_image_urls(citations)
    _enrich_citations_with_document_urls(citations)
    t4 = time.time()
    logger.info(f"[PERF] Citations took: {t4 - t3:.4f}s")
        
    sources = []
    seen_docs = set()
    for chunk in reranked_chunks:
        payload = chunk.get("payload", {})
        doc_id = payload.get("document_id")
        if doc_id and doc_id != "GRAPH" and doc_id not in seen_docs:
            seen_docs.add(doc_id)
            sources.append({
                "document_id": doc_id,
                "title": payload.get("document_title", payload.get("title", "Unknown")),
                "course_code": payload.get("course_code", ""),
                "doc_type": payload.get("document_type", "Notes"),
                "s3_key": payload.get("s3_key", "")
            })
            
    async def event_generator():
        # Stream the text chunks
        t_gen_start = time.time()
        first_chunk = True
        full_response = ""
        async for text_chunk in services["answer_generator"].generate_answer_stream(query, reranked_chunks, req.use_citations, chat_history=chat_history_dicts, user_memories=user_memories_strs):
            full_response += text_chunk
            if first_chunk:
                t_first = time.time()
                logger.info(f"[PERF] Generator TTFT (Time to First Token) took: {t_first - t_gen_start:.4f}s")
                first_chunk = False
            yield f"data: {json.dumps({'type': 'chunk', 'content': text_chunk})}\n\n"
            
        t_gen_end = time.time()
        logger.info(f"[PERF] Generator Total LLM Stream took: {t_gen_end - t_gen_start:.4f}s")
        
        # Filter citations: Only include citations that the LLM actually emitted in the response
        active_citations = []
        used_doc_ids = set()
        
        raw_citations = [c.model_dump() for c in citations] if citations and hasattr(citations[0], "model_dump") else citations
        
        if req.use_citations:
            for cit in raw_citations:
                cit_id = cit.get("citation_id")
                # Check if e.g. "CIT-1" appears anywhere in the full text response
                if cit_id and cit_id in full_response:
                    active_citations.append(cit)
                    doc_id = cit.get("document_id")
                    if doc_id and doc_id != "GRAPH":
                        used_doc_ids.add(doc_id)
        else:
            active_citations = raw_citations
            
        # Filter sources based on used citations
        active_sources = [s for s in sources if s.get("document_id") in used_doc_ids]

        # Stream the final metadata block
        metadata = {
            "type": "metadata",
            "citations": active_citations,
            "sources": active_sources,
            "intent": plan.intent,
            "backends_used": plan.backends_needed,
            "graph_context": context.get("graph_visualization"),
            "conversation_id": str(req.conversation_id)
        }
        
        # Save assistant message to DB
        chat_repo.add_message(req.conversation_id, MessageRole.ASSISTANT, full_response, metadata)
        
        # Trigger background memory extraction (fire and forget)
        import asyncio
        from src.workers.tasks.memory_tasks import extract_user_memory_task
        asyncio.create_task(extract_user_memory_task(req.conversation_id))
        
        yield f"data: {json.dumps(metadata)}\n\n"
        
    return StreamingResponse(event_generator(), media_type="text/event-stream")


def _enrich_citations_with_image_urls(citations: list) -> None:
    """
    For figure citations that have an image_s3_key, generate a presigned GET URL
    (1-hour expiry) and attach it as image_url. Mutates citations in place.
    """
    figure_cits = [c for c in citations if c.get("chunk_type") == "figure" and c.get("image_s3_key")]
    if not figure_cits:
        return
    try:
        s3 = S3Storage()
        for cit in figure_cits:
            cit["image_url"] = s3.generate_presigned_get_url(
                cit["image_s3_key"], expiration=3600
            )
    except Exception as e:
        logger.warning(f"Failed to generate presigned image URLs: {e}")

def _enrich_citations_with_document_urls(citations: list) -> None:
    """
    For all citations that have a document_s3_key, generate a presigned GET URL
    (1-hour expiry) and attach it as document_download_url. Mutates citations in place.
    """
    doc_cits = [c for c in citations if c.get("document_s3_key")]
    if not doc_cits:
        return
    try:
        s3 = S3Storage()
        # Cache presigned URLs per document to avoid redundant S3 calls
        cache = {}
        for cit in doc_cits:
            key = cit["document_s3_key"]
            if key not in cache:
                cache[key] = s3.generate_presigned_get_url(key, expiration=3600)
            cit["document_download_url"] = cache[key]
    except Exception as e:
        logger.warning(f"Failed to generate presigned document URLs: {e}")

@router.post("/search", response_model=StandardResponse[List[SearchResult]])
async def semantic_search(req: QueryRequest, services: dict = Depends(get_rag_services)):
    """Vector-only search returning ranked document chunks"""
    query = req.query
    course_code = req.course_code
    course_offering_id = req.course_offering_id
    
    plan = await services["planner"].detect_intent(query, course_code, course_offering_id)
    # Force semantic search
    plan.backends_needed = ["qdrant"]
    
    context = await services["retriever"].retrieve_context(query, plan, document_ids=req.document_ids)
    reranked_chunks = await services["reranker"].rerank_chunks(query, context["retrieved_chunks"], top_n=10)
    
    results = []
    for chunk in reranked_chunks:
        payload = chunk.get("payload", {})
        if payload.get("document_id") and payload.get("document_id") != "GRAPH":
            results.append(SearchResult(
                document_id=payload.get("document_id"),
                title=payload.get("document_title", payload.get("title", "Unknown")),
                course_code=payload.get("course_code", ""),
                doc_type=payload.get("document_type", "Notes"),
                snippet=payload.get("content", payload.get("text", ""))[:300],
                score=chunk.get("final_score", chunk.get("score", 0.0)),
                s3_key=payload.get("s3_key", "")
            ))
            
    return StandardResponse(
        status="success",
        message="Search completed successfully",
        data=results
    )
