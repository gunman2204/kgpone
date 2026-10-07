import os
import re
import uuid
import asyncio
import logging
from pathlib import Path
from typing import Optional, List, Dict, Tuple

from src.services.ingestion.parser.base import BaseParser
from src.schemas.dom_schema import DocumentDOM, DOMNode, DOMMetadata

logger = logging.getLogger("llama_parser")

# Matches trailing equation label like (2) or (3.1)
_EQ_LABEL_RE = re.compile(r'\((\d+(?:\.\d+)?)\)\s*$')
# Matches a numeric section prefix like "3.3 " or "3.3.1 "
_SECTION_NUM_RE = re.compile(r'^(\d+(?:\.\d+)*)\s+')
# Matches LlamaParse page-break markers
_PAGE_BREAK_RE = re.compile(r'^(?:---+|___+|\*\*\*+)$')


class LlamaParserImpl(BaseParser):
    """
    Primary parser: LlamaParse (cloud) with pypdf image extraction.
    Fallback: pypdf plain-text extraction when API key is absent or call fails.

    Pass `document_id` and `s3_storage` to enable image extraction and upload.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        document_id: Optional[str] = None,
        s3_storage=None,
    ):
        from src.config.settings import Settings
        self.api_key = api_key or os.environ.get("LLAMA_CLOUD_API_KEY")
        self.document_id = document_id
        self.s3_storage = s3_storage
        self.use_fallback = not bool(self.api_key) or Settings.OFFLINE_MODE
        if self.use_fallback:
            logger.warning(
                "Offline Mode or API Key missing — falling back to pypdf local parsing."
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def parse(
        self, file_path: str, parsing_instructions: Optional[str] = None
    ) -> DocumentDOM:
        if self.use_fallback:
            return await self._parse_local_dom(file_path)

        instructions = (
            "Extract all text, equations, tables, and structural elements from this document. "
            "Format display equations using $$...$$ blocks and inline math using $...$. "
            "Preserve section numbers exactly (e.g. '3.3 Position-wise Feed-Forward Networks'). "
            "Preserve equation labels like (2) at the end of the equation line. "
            "Keep all tables in standard markdown table format."
        )
        if parsing_instructions:
            instructions += f"\n\nAdditional context:\n{parsing_instructions}"

        try:
            from llama_parse import LlamaParse

            parser = LlamaParse(
                api_key=self.api_key,
                result_type="markdown",
                system_prompt=instructions,
                verbose=False,
            )
            documents = await asyncio.to_thread(parser.load_data, str(file_path))
            if not documents:
                raise RuntimeError("LlamaParse returned no content.")

            return await self._build_dom_from_llama_docs(documents, file_path)

        except Exception as exc:
            logger.warning(f"LlamaParse failed ({exc}). Falling back to pypdf.")
            return await self._parse_local_dom(file_path)

    # ------------------------------------------------------------------
    # DOM builder from LlamaParse documents
    # ------------------------------------------------------------------

    async def _build_dom_from_llama_docs(
        self, documents, file_path: str
    ) -> DocumentDOM:
        dom = DocumentDOM(document_id=self.document_id or str(uuid.uuid4()))

        # Extract and upload images in a thread (non-blocking)
        page_images: Dict[int, List[str]] = {}
        if self.s3_storage and self.document_id:
            page_images = await asyncio.to_thread(
                self._extract_and_upload_images, file_path
            )

        current_path: List[str] = []
        heading_stack: List[Tuple[int, str]] = []
        all_nodes: List[DOMNode] = []

        for doc_idx, doc in enumerate(documents):
            # Resolve page number -----------------------------------------
            page_no: Optional[int] = None
            meta = getattr(doc, "metadata", {}) or {}
            for key in ("page_number", "page_label", "page"):
                if key in meta:
                    try:
                        page_no = int(meta[key])
                    except (ValueError, TypeError):
                        pass
                    break
            # If LlamaParse returned one doc per page use index
            if page_no is None and len(documents) > 1:
                page_no = doc_idx + 1

            # Parse markdown page → DOM nodes
            page_nodes = self._parse_markdown_page(
                doc.text or "", page_no, current_path, heading_stack, dom
            )
            all_nodes.extend(page_nodes)

            # Attach extracted images for this page
            if page_no and page_no in page_images:
                for s3_key in page_images[page_no]:
                    all_nodes.append(
                        DOMNode(
                            node_id=str(uuid.uuid4()),
                            node_type="figure",
                            text_content=f"[IMAGE: {s3_key}]",
                            page_number=page_no,
                            metadata=DOMMetadata(
                                context_path=list(current_path),
                                image_s3_key=s3_key,
                            ),
                        )
                    )

        dom.nodes = all_nodes
        return dom

    # ------------------------------------------------------------------
    # Markdown → DOM node list (per page)
    # ------------------------------------------------------------------

    def _parse_markdown_page(
        self,
        text: str,
        page_no: Optional[int],
        current_path: List[str],
        heading_stack: List[Tuple[int, str]],
        dom: DocumentDOM,
    ) -> List[DOMNode]:
        nodes: List[DOMNode] = []
        lines = text.splitlines()
        buffer: List[str] = []
        in_table = False
        in_block_eq = False
        eq_lines: List[str] = []

        def flush_paragraph() -> None:
            if not buffer:
                return
            content = "\n".join(buffer).strip()
            buffer.clear()
            if content:
                nodes.append(
                    DOMNode(
                        node_id=str(uuid.uuid4()),
                        node_type="paragraph",
                        text_content=content,
                        page_number=page_no,
                        metadata=DOMMetadata(context_path=list(current_path)),
                    )
                )

        def flush_table() -> None:
            if not buffer:
                return
            content = "\n".join(buffer).strip()
            buffer.clear()
            if content:
                nodes.append(
                    DOMNode(
                        node_id=str(uuid.uuid4()),
                        node_type="table",
                        text_content=content,
                        page_number=page_no,
                        metadata=DOMMetadata(context_path=list(current_path)),
                    )
                )

        def emit_equation(eq_text: str) -> None:
            eq_text = eq_text.strip()
            if not eq_text:
                return
            label = _EQ_LABEL_RE.search(eq_text)
            eq_label = label.group(1) if label else None
            nodes.append(
                DOMNode(
                    node_id=str(uuid.uuid4()),
                    node_type="equation",
                    text_content=eq_text,
                    raw_latex=eq_text,
                    equation_label=eq_label,
                    page_number=page_no,
                    metadata=DOMMetadata(context_path=list(current_path)),
                )
            )

        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            # ── Block equation ────────────────────────────────────────
            if stripped.startswith("$$"):
                if in_block_eq:
                    # closing $$
                    emit_equation("\n".join(eq_lines))
                    eq_lines = []
                    in_block_eq = False
                else:
                    flush_paragraph()
                    inner = stripped[2:].rstrip("$").strip()
                    # Single-line $$..$$
                    if stripped.endswith("$$") and len(stripped) > 4:
                        emit_equation(inner)
                    else:
                        in_block_eq = True
                        if inner:
                            eq_lines.append(inner)
                i += 1
                continue

            if in_block_eq:
                if stripped.endswith("$$"):
                    eq_lines.append(stripped[:-2].strip())
                    emit_equation("\n".join(eq_lines))
                    eq_lines = []
                    in_block_eq = False
                else:
                    eq_lines.append(line)
                i += 1
                continue

            # ── Page-break marker ─────────────────────────────────────
            if _PAGE_BREAK_RE.match(stripped) and not in_table:
                flush_paragraph()
                i += 1
                continue

            # ── Heading ───────────────────────────────────────────────
            if line.startswith("#") and not in_table:
                flush_paragraph()
                raw_level = len(line) - len(line.lstrip("#"))
                title = line.lstrip("# ").strip()

                # Override level using numeric prefix depth
                section_num: Optional[str] = None
                m = _SECTION_NUM_RE.match(title)
                if m:
                    section_num = m.group(1)
                    dot_count = section_num.count(".")
                    # "3" → level 2, "3.3" → level 3, "3.3.1" → level 4
                    raw_level = dot_count + 2

                # Pop stack until we find a parent
                while heading_stack and heading_stack[-1][0] >= raw_level:
                    heading_stack.pop()
                    if current_path:
                        current_path.pop()

                heading_stack.append((raw_level, title))
                current_path.append(title)
                dom.toc.append({"level": raw_level, "title": title, "page": page_no})

                meta = DOMMetadata(
                    context_path=list(current_path),
                    section_number=section_num,
                )
                nodes.append(
                    DOMNode(
                        node_id=str(uuid.uuid4()),
                        node_type="heading",
                        text_content=title,
                        page_number=page_no,
                        metadata=meta,
                    )
                )
                i += 1
                continue

            # ── Table ─────────────────────────────────────────────────
            if stripped.startswith("|") and stripped.endswith("|"):
                if not in_table:
                    flush_paragraph()
                    in_table = True
                buffer.append(line)
                i += 1
                continue
            elif in_table:
                if not stripped:
                    flush_table()
                    in_table = False
                else:
                    buffer.append(line)
                i += 1
                continue

            # ── Paragraph ─────────────────────────────────────────────
            if not stripped:
                flush_paragraph()
            else:
                buffer.append(line)
            i += 1

        # Flush any remaining buffers
        flush_paragraph()
        if in_table:
            flush_table()
        if in_block_eq and eq_lines:
            emit_equation("\n".join(eq_lines))

        return nodes

    # ------------------------------------------------------------------
    # Image extraction via pypdf
    # ------------------------------------------------------------------

    def _extract_and_upload_images(self, file_path: str) -> Dict[int, List[str]]:
        """
        Extracts embedded images from each PDF page using pypdf and
        uploads them to S3 under images/{document_id}/page_{n}_img_{i}.ext
        Returns a dict mapping page_number → list of s3_keys.
        """
        page_images: Dict[int, List[str]] = {}
        try:
            import pypdf

            reader = pypdf.PdfReader(file_path)
            for page_num, page in enumerate(reader.pages, start=1):
                page_images[page_num] = []
                try:
                    for img_idx, image_obj in enumerate(page.images):
                        try:
                            img_bytes = image_obj.data
                            # Skip tiny decorative images (< 5 KB)
                            if len(img_bytes) < 5_000:
                                continue
                            ext = Path(image_obj.name).suffix.lower() or ".png"
                            s3_key = (
                                f"images/{self.document_id}/"
                                f"page_{page_num}_img_{img_idx}{ext}"
                            )
                            self.s3_storage.upload(s3_key, img_bytes)
                            page_images[page_num].append(s3_key)
                            logger.info(f"Uploaded image → {s3_key}")
                        except Exception as img_err:
                            logger.warning(
                                f"Skipping image {img_idx} on page {page_num}: {img_err}"
                            )
                except Exception as page_err:
                    logger.warning(f"Could not iterate images on page {page_num}: {page_err}")

        except Exception as exc:
            logger.error(f"Image extraction failed entirely: {exc}")

        return page_images

    # ------------------------------------------------------------------
    # Offline fallback: pypdf plain text
    # ------------------------------------------------------------------

    async def _parse_local_dom(self, file_path: str) -> DocumentDOM:
        """Pure pypdf fallback — no LlamaParse dependency required."""
        dom = DocumentDOM(document_id=self.document_id or str(uuid.uuid4()))
        nodes: List[DOMNode] = []

        # Extract and upload embedded images even in the fallback path
        page_images: Dict[int, List[str]] = {}
        if self.s3_storage and self.document_id:
            try:
                page_images = await asyncio.to_thread(
                    self._extract_and_upload_images, file_path
                )
                logger.info(f"Fallback path: extracted images for {len(page_images)} pages")
            except Exception as img_exc:
                logger.warning(f"Fallback image extraction failed: {img_exc}")

        try:
            import pypdf

            def _extract() -> List[Tuple[int, str]]:
                pages_text = []
                reader = pypdf.PdfReader(file_path)
                for page_num, page in enumerate(reader.pages, start=1):
                    text = page.extract_text() or ""
                    if text.strip():
                        pages_text.append((page_num, text.strip()))
                return pages_text

            pages = await asyncio.to_thread(_extract)

            current_path: List[str] = []
            heading_stack: List[Tuple[int, str]] = []

            for page_no, text in pages:
                page_nodes = self._parse_markdown_page(
                    text, page_no, current_path, heading_stack, dom
                )
                nodes.extend(page_nodes)

                # Attach figure nodes for images extracted from this page
                if page_no in page_images:
                    for s3_key in page_images[page_no]:
                        nodes.append(
                            DOMNode(
                                node_id=str(uuid.uuid4()),
                                node_type="figure",
                                text_content=f"[IMAGE: {s3_key}]",
                                page_number=page_no,
                                metadata=DOMMetadata(
                                    context_path=list(current_path),
                                    image_s3_key=s3_key,
                                ),
                            )
                        )

        except Exception as exc:
            logger.error(f"pypdf local fallback failed: {exc}")
            # Last resort: raw text node
            try:
                raw = open(file_path, "r", encoding="utf-8", errors="ignore").read()
                nodes.append(
                    DOMNode(
                        node_id=str(uuid.uuid4()),
                        node_type="paragraph",
                        text_content=raw[:50_000],
                        metadata=DOMMetadata(),
                    )
                )
            except Exception:
                pass

        dom.nodes = nodes
        return dom
