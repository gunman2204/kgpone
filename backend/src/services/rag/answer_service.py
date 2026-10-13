import logging
from typing import Any
from src.infrastructure.llm_factory import LLMFactory
from src.services.rag.base import BaseAnswerGenerator
from langchain_core.prompts import ChatPromptTemplate

logger = logging.getLogger("answer_service")

class AnswerService(BaseAnswerGenerator):
    def __init__(self, model_name: str | None = None):
        self.factory = LLMFactory()
        try:
            self.llm = self.factory.get_llm(model_name)
        except Exception as e:
            logger.error(f"Failed to configure LLM in AnswerService: {e}. Enabling fallback.")
            self.llm = None

        try:
            self.offline_llm = self.factory.get_offline_llm()
            logger.info("Configured offline Ollama LLM successfully.")
        except Exception as e:
            logger.warning(f"Failed to configure offline Ollama LLM: {e}. Will use grounded synthesizer.")
            self.offline_llm = None

        self.prompt_template = ChatPromptTemplate.from_messages([
            ("system", """You are the core intelligence of "KnowledgeOS", an advanced academic AI tutor designed for university students. 
Students use you to gain deep conceptual understanding, study for exams, and clarify complex academic topics.

UNDERSTANDING YOUR CONTEXT (THE RAG SYSTEM):
You will receive "Context" containing various "chunks" of data retrieved from the student's course materials (PDFs, lectures, notes, knowledge graphs). 
These chunks are RAW data blocks. They might include:
- Paragraphs of text
- Extracted LaTeX equations
- Tabular data 
- Metadata or Graph facts
- Links to images (e.g. `[Figure — image available at: SOME_URL]`)

YOUR BEHAVIOR & SYNTHESIS:
1. **Act as a Teacher**: Do NOT mechanically list out the chunks (e.g., never say "The course provides text on page 5" or "Here is an image at URL..."). Instead, WEAVE the information together into a natural, cohesive, and comprehensive explanation.
2. **Synthesize**: Combine facts from different chunks to form a complete narrative. Answer the user's question directly and thoughtfully.
3. **Citations**: Append inline citation links `[[CIT-N]](#CIT-N)` at the END of every sentence that draws from a source chunk. This tells the UI which document to highlight. Never bunch all citations at the end.
4. **Figures & Images**: If a chunk contains a figure URL (e.g., `[Figure — image available at: SOME_URL]`), EMBED it naturally in your explanation using markdown: `![Description](SOME_URL)`. Do NOT just say "an image is available at...". If no URL is present, explain the text without complaining about missing figures.
5. **Equations**: Wrap all LaTeX equations, variables, and math expressions in `$...$` for inline math and `$$...$$` for block equations. NEVER output raw LaTeX without dollar signs (e.g., write `$\text{{head}}_i$` instead of `\text{{head}}_i`).
6. **Tables**: If chunks contain tabular data, present it nicely in a Markdown table if it helps answer the query.
7. **Prerequisites**: If you use prerequisite graph context, explicitly explain WHY it connects to the current topic.
8. **Honesty**: Ground your answers in the context. If the context does not explicitly contain the direct answer, use the context to explain related concepts. IF the context is entirely irrelevant or lacks the answer, you MUST still answer the student's question using your own general knowledge. However, if you do this, you MUST add a disclaimer at the very bottom of your response stating exactly: "*(Note: This concept was not found in the current course materials.)*". Do NOT use any citations `[[CIT-N]]` for facts drawn from your general knowledge.
9. **Ambiguity**: If the query is conversational (e.g. "explain more deeply") or broad, do your best to explain the provided context chunks thoroughly.
10. **Document Links**: The UI handles document downloads automatically. If the user asks for download links, notes, or course materials, you MUST reply EXACTLY with: *"I have provided the relevant document download links below."* DO NOT apologize, and DO NOT claim you cannot provide links.
11. **Conversational Tone**: If the user is asking a follow-up or conversational question, address it naturally.

OUTPUT FORMAT:
- Start directly with your explanation. No robotic preamble (e.g., "Based on the provided context...").
- Use markdown headers (###), bullet points, and bold text to structure complex answers beautifully.
- Synthesize elegantly. You are an expert tutor, not a data parser."""),
            ("user", "Context:\n{context}\n\nStudent Query: {query}\n\nAnswer:")
        ])

        self.prompt_template_simple = ChatPromptTemplate.from_messages([
            ("system", """You are the core intelligence of "KnowledgeOS", an advanced academic AI tutor designed for university students. 
You will receive raw context chunks (text, equations, tables, image links).

YOUR BEHAVIOR & SYNTHESIS:
1. **Act as a Teacher**: Do NOT mechanically list out the chunks. WEAVE the information together into a natural, cohesive explanation.
2. **Figures & Images**: If a chunk contains a figure URL (e.g., `[Figure — image available at: SOME_URL]`), EMBED it naturally using markdown: `![Description](SOME_URL)`.
3. **Equations**: Wrap all LaTeX equations, variables, and math expressions in `$...$` for inline math and `$$...$$` for block equations.
4. **Structure**: Use headers and bullet lists for multi-part answers.
5. **Prerequisites**: Explicitly explain connections to prerequisite knowledge.
6. **Honesty**: Ground your answers in the context. If the context does not explicitly contain the direct answer, use the context to explain related concepts. IF the context is entirely irrelevant or lacks the answer, you MUST still answer the student's question using your own general knowledge. However, if you do this, you MUST add a disclaimer at the very bottom of your response stating exactly: "*(Note: This concept was not found in the current course materials.)*".
7. **Ambiguity**: If the query is conversational (e.g. "explain more deeply") or broad, do your best to explain the provided context chunks thoroughly.

Start directly with the explanation. No robotic preamble (e.g., "Based on the context...")."""),
            ("user", "Context:\n{context}\n\nStudent Query: {query}\n\nAnswer:")
        ])

        self.web_search_template = ChatPromptTemplate.from_messages([
            ("system", """You are a helpful AI assistant. Answer the user's query using the provided web search results.
Synthesize the information fluently, use markdown formatting, and cite sources inline.
If the results do not contain the answer, say: "I couldn't find a good answer in the web search results."
Do not generate code unless explicitly requested."""),
            ("user", "{context}\n\nQuery: {query}\nAnswer:")
        ])

        self.general_qa_template = ChatPromptTemplate.from_messages([
            ("system", """You are a helpful, intelligent assistant inside an academic app (KgpOne). 
The user is asking a general knowledge, conversational, or off-topic question that does NOT require course materials.
Answer their question directly and naturally using your own knowledge. 
If they ask for code, provide it. Use markdown formatting beautifully."""),
            ("user", "{query}")
        ])


    def _build_context_string(self, ranked_chunks: list[dict[str, Any]], use_citations: bool) -> str:
        context_blocks = []
        for idx, chunk in enumerate(ranked_chunks):
            payload = chunk["payload"]
            cit_id = f"CIT-{idx + 1}"
            course_code = payload.get("course_code", "Unknown Course")
            is_prereq = payload.get("is_prereq", False)
            prereq_str = " (Prerequisite Course Content)" if is_prereq else " (Active Course Content)"
            chunk_type = payload.get("chunk_type", "text")
            page_info = f", Page {payload.get('page_number')}" if payload.get('page_number') else ""

            # Use the richly-formatted text built by the retrieval service (includes equation labels,
            # figure S3 keys, and table headers). Fall back to raw content if not present.
            rich_content = payload.get("formatted_text") or payload.get("content") or payload.get("text", "")

            # For figure chunks: if we have a presigned image_url (injected by the route handler)
            # inject it directly into the context so the LLM can embed it.
            if chunk_type == "figure":
                image_url = payload.get("image_url")  # presigned URL injected by query_routes
                image_s3_key = payload.get("image_s3_key", "")
                if image_url:
                    rich_content = f"{rich_content}\n[Figure — image available at: {image_url}]"
                elif image_s3_key:
                    rich_content = f"{rich_content}\n[Figure — image S3 key: {image_s3_key}]"

            if use_citations:
                context_blocks.append(
                    f"Source: [{cit_id}] (Course: {course_code}{prereq_str}{page_info}, Type: {chunk_type})\n"
                    f"Content:\n{rich_content}\n---"
                )
            else:
                context_blocks.append(
                    f"Course: {course_code}{prereq_str}{page_info}\n"
                    f"Content:\n{rich_content}\n---"
                )

        return "\n\n".join(context_blocks)

    def generate_answer(self, query: str, ranked_chunks: list[dict[str, Any]], citations: list[dict[str, Any]], use_citations: bool = True) -> str:
        """
        Generates a grounded academic response. Highlight prerequisite sources.
        """
        top_score = ranked_chunks[0].get("final_score", ranked_chunks[0].get("score", 0.0)) if ranked_chunks else 0.0
        # Removing the 0.05 threshold so meta-queries can be handled by the LLM
        is_irrelevant = not ranked_chunks

        if is_irrelevant:
            try:
                from ddgs import DDGS
                with DDGS() as ddgs:
                    results = [r for r in ddgs.text(query, max_results=3)]
                if not results:
                    return "I couldn't find any relevant study materials or web results for your query."
                context_str = "Web Search Results:\n\n"
                for i, r in enumerate(results):
                    context_str += f"[{i+1}] {r.get('title', '')}\n{r.get('body', '')}\n---"
            except Exception as e:
                logger.error(f"Web search fallback failed: {e}")
                return "I couldn't find any relevant study materials in your workspace matching your query. Please upload notes or lecture materials first."
        else:
            context_str = self._build_context_string(ranked_chunks, use_citations)

        if not self.llm:
            return self._generate_offline_grounded_answer(query, ranked_chunks, citations)

        try:
            if is_irrelevant:
                template = self.web_search_template
            else:
                template = self.prompt_template if use_citations else self.prompt_template_simple
                
            messages = template.format_messages(context=context_str, query=query)
            
            # Inject image URLs into the user message for Vision support (Only for non-Groq providers since Groq decommissioned vision)
            from src.config.settings import Settings
            if Settings.AI_PROVIDER != "groq":
                image_urls = []
                if not is_irrelevant:
                    for c in ranked_chunks:
                        url = c.get("payload", {}).get("image_url")
                        if url and url not in image_urls:
                            image_urls.append(url)
                            
                if image_urls:
                    user_msg = messages[-1]
                    content = [{"type": "text", "text": user_msg.content}]
                    for url in image_urls:
                        content.append({"type": "image_url", "image_url": {"url": url}})
                    user_msg.content = content

            response = self.llm.invoke(messages)
            return response.content
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            return self._generate_offline_grounded_answer(query, ranked_chunks, citations)
    async def generate_general_answer_stream(self, query: str, chat_history: list[dict] = None, user_memories: list[str] = None):
        """
        Bypasses the RAG pipeline entirely and streams a direct response to a general query.
        """
        if not self.llm:
            yield "*(General QA unavailable. LLM not configured.)*\n\n"
            return
            
        try:
            messages = self.general_qa_template.format_messages(query=query)
            
            # Inject memory and history
            if user_memories:
                memory_str = "\n".join([f"- {m}" for m in user_memories])
                messages[0].content += f"\n\nUSER PROFILE (Keep this in mind):\n{memory_str}"
                
            from langchain_core.messages import AIMessage, HumanMessage
            if chat_history:
                history_msgs = []
                for msg in chat_history:
                    if msg["role"] == "user":
                        history_msgs.append(HumanMessage(content=msg["content"]))
                    elif msg["role"] == "assistant":
                        history_msgs.append(AIMessage(content=msg["content"]))
                messages = [messages[0]] + history_msgs + messages[1:]
                
            async for chunk in self.llm.astream(messages):
                if isinstance(chunk.content, str):
                    yield chunk.content
                elif isinstance(chunk.content, list):
                    text_parts = [c.get("text", "") if isinstance(c, dict) else str(c) for c in chunk.content]
                    yield "".join(text_parts)
                else:
                    yield str(chunk.content)
        except Exception as e:
            logger.error(f"LLM streaming failed for general QA: {e}")
            yield "\n\n*(Error streaming direct answer)*\n\n"

    async def generate_answer_stream(
        self, 
        query: str, 
        ranked_chunks: list[dict[str, Any]], 
        use_citations: bool = True,
        chat_history: list[dict] = None,
        user_memories: list[str] = None,
        is_offline: bool = False
    ):
        """
        Generates a streaming academic response.
        Routes to local Ollama if offline, otherwise primary cloud LLM,
        with instantaneous fallback to local grounded synthesis.
        """
        is_irrelevant = not ranked_chunks

        if is_irrelevant:
            if is_offline:
                yield "I couldn't find matching sections in your selected local library materials. Please ensure the document is selected in the local library panel.\n\n"
                return

            yield "*No local course materials found. Searching the web...*\n\n"
            try:
                from ddgs import DDGS
                with DDGS() as ddgs:
                    results = [r for r in ddgs.text(query, max_results=4)]
                if not results:
                    yield "I couldn't find any relevant study materials or web results for your query."
                    return
                context_str = "Web Search Results:\n\n"
                for i, r in enumerate(results):
                    context_str += f"[{i+1}] {r.get('title', '')}\n{r.get('body', '')}\n---"
            except Exception as e:
                logger.error(f"Web search fallback failed: {e}")
                yield "I couldn't find any relevant study materials in your workspace matching your query. Please upload notes or lecture materials first."
                return
        else:
            context_str = self._build_context_string(ranked_chunks, use_citations)

        # Select LLM engine
        active_llm = self.offline_llm if is_offline else self.llm
        if is_offline and not active_llm:
            active_llm = self.llm # try primary if offline_llm was None

        if not active_llm:
            yield self._generate_offline_grounded_answer(query, ranked_chunks, [])
            return

        try:
            if is_irrelevant:
                template = self.web_search_template
            else:
                template = self.prompt_template if use_citations else self.prompt_template_simple
                
            messages = template.format_messages(context=context_str, query=query)
            
            # Inject memory and history
            if user_memories:
                memory_str = "\n".join([f"- {m}" for m in user_memories])
                messages[0].content += f"\n\nUSER PROFILE (Keep this in mind):\n{memory_str}"
                
            from langchain_core.messages import AIMessage, HumanMessage
            if chat_history:
                history_msgs = []
                for msg in chat_history:
                    if msg["role"] == "user":
                        history_msgs.append(HumanMessage(content=msg["content"]))
                    elif msg["role"] == "assistant":
                        history_msgs.append(AIMessage(content=msg["content"]))
                messages = [messages[0]] + history_msgs + messages[1:]
            
            # Inject image URLs into the user message for Vision support (only when online)
            from src.config.settings import Settings
            if not is_offline and Settings.AI_PROVIDER != "groq":
                image_urls = []
                if not is_irrelevant:
                    for c in ranked_chunks:
                        url = c.get("payload", {}).get("image_url")
                        if url and url not in image_urls:
                            image_urls.append(url)
                            
                if image_urls:
                    user_msg = messages[-1]
                    content = [{"type": "text", "text": user_msg.content}]
                    for url in image_urls:
                        content.append({"type": "image_url", "image_url": {"url": url}})
                    user_msg.content = content

            async for chunk in active_llm.astream(messages):
                if isinstance(chunk.content, str):
                    yield chunk.content
                elif isinstance(chunk.content, list):
                    text_parts = [c.get("text", "") if isinstance(c, dict) else str(c) for c in chunk.content]
                    yield "".join(text_parts)
                else:
                    yield str(chunk.content)
        except Exception as e:
            logger.error(f"LLM streaming failed: {e}")
            if is_offline:
                yield "\n\n*(Local LLM offline or unreachable. Generating grounded answer from local notes:)*\n\n"
            else:
                yield "\n\n*(Network/API Error. Falling back to offline grounded generation)*\n\n"
            citations = []
            if use_citations:
                try:
                    from src.services.rag.citation_service import CitationService
                    citations = CitationService().format_citations(ranked_chunks)
                except Exception:
                    pass
            yield self._generate_offline_grounded_answer(query, ranked_chunks, citations)

    def _generate_offline_grounded_answer(self, query: str, ranked_chunks: list[dict[str, Any]], citations: list[dict[str, Any]]) -> str:
        """
        Synthesizes a grounded answer from chunk payloads locally without requiring an LLM.
        """
        answer_parts = []
        safe_citations = [c.model_dump() if hasattr(c, "model_dump") else c for c in citations]
        
        prereq_citations = [c for c in safe_citations if c.get("is_prerequisite")]
        active_citations = [c for c in safe_citations if not c.get("is_prerequisite")]

        if prereq_citations:
            p_cit = prereq_citations[0]
            concept = p_cit.get("prerequisite_concept", "foundational concept")
            course = p_cit.get("course_code", "previous course")
            answer_parts.append(
                f"**[Prerequisite Concept Reference]** Foundational concept **{concept}** "
                f"from course **{course}**:\n\n"
            )
            snippet = p_cit.get("text_snippet", "").replace("...", "")
            answer_parts.append(f"> *{snippet}* [[{p_cit['citation_id']}](#{p_cit['citation_id']})]\n\n")

        if active_citations:
            first_c = active_citations[0]
            header = f"in **{first_c['course_code']}**" if first_c.get("course_code") else f"from **{first_c.get('source_title', 'Document')}**"
            answer_parts.append(f"### Relevant Insights {header}:\n\n")
            for c in active_citations[:3]:
                snippet = c.get("text_snippet", "").replace("...", "")
                title = c.get("source_title", "Document")
                sec = f" (Section: {c['section']})" if c.get("section") else ""
                answer_parts.append(f"- **From {title}{sec}:** {snippet} [[{c['citation_id']}](#{c['citation_id']})]\n\n")
        elif ranked_chunks:
            answer_parts.append("### Relevant Information from Uploaded Materials:\n\n")
            for idx, ch in enumerate(ranked_chunks[:3]):
                p = ch.get("payload", {})
                txt = p.get("formatted_text") or p.get("content") or p.get("text", "")
                title = p.get("document_title", p.get("title", "Document"))
                page = p.get("page_number", "")
                page_str = f", Page {page}" if page else ""
                cit_id = f"CIT-{idx + 1}"
                answer_parts.append(f"- **From {title}{page_str}:** {txt[:280]}... [[{cit_id}](#{cit_id})]\n\n")
        else:
            answer_parts.append("No local notes or document chunks were found matching your query.")

        answer_parts.append("\n*(Note: Grounded local synthesis mode - Offline active)*")
        return "".join(answer_parts)
