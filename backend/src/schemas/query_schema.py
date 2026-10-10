from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Literal
from uuid import UUID
from datetime import datetime

class QueryPlan(BaseModel):
    intent: str
    course_code: Optional[str] = None
    course_offering_id: Optional[str] = None
    entities_mentioned: List[str] = []
    backends_needed: List[str] = []
    confidence_score: float = 1.0

class QueryRequest(BaseModel):
    query: str
    conversation_id: Optional[UUID] = None
    course_code: Optional[str] = None
    course_offering_id: Optional[str] = None
    document_ids: Optional[List[UUID]] = None # Phase 5 Dynamic Scoping
    use_citations: bool = True
    # Controls which pipeline is used: basic = fast NLP, advanced = tool-calling agent, general = direct LLM
    analysis_mode: Literal["basic", "advanced", "general"] = "basic"
    # BYOK — user supplies own key per-request; never persisted server-side
    byok_provider: Optional[Literal["openai", "gemini", "groq", "anthropic"]] = None
    byok_api_key: Optional[str] = Field(default=None, exclude=True)  # excluded from logs/responses
    byok_model: Optional[str] = None

class CitationRead(BaseModel):
    citation_id: str
    document_id: Optional[str] = None
    source_title: str = "Lecture Notes"
    course_code: str = "GEN101"
    academic_year: str = ""
    page_number: Optional[int] = None
    section: str = "General"
    section_number: Optional[str] = None
    confidence: str = "Supporting Evidence"
    score: float = 0.0
    is_prerequisite: bool = False
    prerequisite_concept: Optional[str] = None
    source_url: Optional[str] = None
    text_snippet: str = ""
    # Chunk-type enrichment for frontend rendering
    chunk_type: str = "text"
    equation_label: Optional[str] = None
    raw_latex: Optional[str] = None
    image_s3_key: Optional[str] = None
    image_url: Optional[str] = None

class SourceRead(BaseModel):
    document_id: str
    title: str
    course_code: str
    doc_type: str
    s3_key: str

class QueryResponse(BaseModel):
    answer: str
    citations: List[CitationRead]
    sources: List[SourceRead]
    graph_context: Optional[Dict[str, Any]] = None
    intent: str
    backends_used: List[str]
    cache_hit: bool = False
    confidence_score: float = 1.0

class SearchResult(BaseModel):
    document_id: str
    title: str
    course_code: str
    doc_type: str
    snippet: str
    score: float
    s3_key: str
