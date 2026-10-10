import asyncio
import os
import tempfile
import logging
from celery import shared_task
from sqlalchemy.orm import Session
from src.infrastructure.database import SessionLocal
from src.repositories.postgres.document_repository import DocumentRepository
from src.repositories.s3.storage_repository import S3Storage
from src.models.document_model import ProcessingStatus, Document
from src.models.academic_model import CourseOffering, Course
from src.models.user_model import User

from src.services.ingestion.parser.llama_parser import LlamaParserImpl
from src.services.ingestion.chunking.recursive_chunker import RecursiveChunker
from src.services.ingestion.embedding.llm_embedding import LLMEmbedder
from src.repositories.qdrant.vector_repository import QdrantRepository
from src.services.ingestion.pipeline import IngestionPipeline
from src.services.ingestion.metadata_builder import MetadataBuilder
from src.workers.tasks.cleanup_tasks import delete_old_vectors_task

logger = logging.getLogger("ingestion_tasks")

def run_document_ingestion(document_id: str, old_version: int = None):
    """
    Executes the ingestion pipeline for a given document.
    Safe to run inside synchronous background task threads.
    """
    logger.info(f"Starting ingestion process for document {document_id}")
    db: Session = SessionLocal()
    try:
        import uuid
        # 1. Fetch document metadata
        repo = DocumentRepository(db)
        # Ensure we pass a UUID object, not a string, as SQLite's SQLAlchemy dialect expects an object to call .hex on
        doc_uuid = uuid.UUID(document_id) if isinstance(document_id, str) else document_id
        doc = repo.get_document(doc_uuid)
        if not doc:
            logger.error(f"Document {document_id} not found in DB.")
            return

        # Update status to processing
        repo.update_status(doc.id, ProcessingStatus.PROCESSING, None)
        
        # We assume doc.s3_key holds the S3 object key or a local file path
        file_key = doc.s3_key 
        
        # 2. Prepare file path (Download from S3 if cloud, use directly if local dropzone)
        ext = os.path.splitext(file_key)[1] or ".pdf"
        is_local_file = os.path.isabs(file_key) and os.path.exists(file_key)
        s3_storage = None  # Will only be assigned in cloud mode
        
        if is_local_file:
            logger.info(f"Offline Mode: Using local file directly from {file_key}")
            temp_path = file_path = file_key
        else:
            s3_storage = S3Storage()
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                temp_path = tmp.name
            
            logger.info(f"Cloud Mode: Downloading {file_key} from S3 to {temp_path}")
            s3_storage.download_file(file_key, temp_path)
            file_path = temp_path
        
        # 3. Setup the pipeline
        from src.services.ingestion.parser.llama_parser import LlamaParserImpl
        from src.services.ingestion.chunking.dom_chunker import DOMChunker
        from src.services.ingestion.extraction.gliner_extractor import GLiNERExtractor
        from src.services.ingestion.extraction.entity_resolver import EntityResolver
        from src.services.ingestion.extraction.spacy_relation_extractor import SpacyRelationExtractor
        from src.services.graph.graph_builder_service import GraphBuilderService
        from src.infrastructure.model_factory import NLPModelFactory
        
        doc_id = str(doc.id)
        parser = LlamaParserImpl(
            document_id=doc_id,
            s3_storage=s3_storage if not is_local_file else None,
        )
        chunker = DOMChunker()
        embedder = LLMEmbedder()
        vector_store = QdrantRepository()
        
        entity_extractor = GLiNERExtractor()
        entity_resolver = EntityResolver()
        relation_extractor = SpacyRelationExtractor()
        graph_builder = GraphBuilderService()
        
        pipeline = IngestionPipeline(
            parser=parser,
            chunker=chunker,
            embedder=embedder,
            vector_store=vector_store,
            collection_name="documents",
            entity_extractor=entity_extractor,
            entity_resolver=entity_resolver,
            relation_extractor=relation_extractor,
            graph_builder=graph_builder
        )
        
        # Build metadata
        metadata_base = MetadataBuilder.build(doc)

        # Build dynamic parsing instructions (graceful for local/LOC101 files)
        try:
            course = doc.course_offering.course
            dynamic_instructions = (
                f"This document is titled '{doc.title}' and is classified as '{doc.doc_type}'. "
                f"It belongs to the university course '{course.code}: {course.title}' "
                f"offered in {doc.course_offering.semester.value} {doc.course_offering.year}. "
                "Use this specific course context to accurately extract and preserve domain-specific acronyms, "
                "formulas, variables, and technical tables."
            )
        except Exception:
            # Fallback for local dropzone files with no real course context
            dynamic_instructions = (
                f"This document is titled '{doc.title}'. "
                "Extract all text, equations, tables, and structural elements accurately."
            )
        if doc.parsing_instructions:
            dynamic_instructions += f"\n\nAdditional Uploader Instructions:\n{doc.parsing_instructions}"

        # 4. Execute pipeline
        logger.info(f"[Pipeline] Running ingestion pipeline for document {document_id}")
        try:
            asyncio.run(pipeline.process_document(
                file_path=temp_path,
                metadata_base=metadata_base,
                parsing_instructions=dynamic_instructions
            ))
        except RuntimeError:
            # Fallback if there's already a running event loop (e.g. in test environments)
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            if loop.is_running():
                future = asyncio.run_coroutine_threadsafe(
                    pipeline.process_document(
                        file_path=temp_path,
                        metadata_base=metadata_base,
                        parsing_instructions=dynamic_instructions
                    ),
                    loop
                )
                future.result()
            else:
                loop.run_until_complete(pipeline.process_document(
                    file_path=temp_path,
                    metadata_base=metadata_base,
                    parsing_instructions=dynamic_instructions
                ))

        # 5. Cleanup temp file (only for cloud-downloaded files)
        if not is_local_file and os.path.exists(temp_path):
            os.remove(temp_path)

        # 6. Update status to COMPLETED
        doc.status = ProcessingStatus.COMPLETED
        db.commit()
        logger.info(f"[Done] Successfully processed Document: {document_id}")

    except Exception as e:
        logger.error(f"Failed to process Document {document_id}: {str(e)}")
        repo.update_status(document_id, ProcessingStatus.FAILED, None)
        raise e
    finally:
        try:
            from src.infrastructure.model_factory import NLPModelFactory
            NLPModelFactory.unload_gliner()
        except Exception as e:
            logger.error(f"Failed to unload GLiNER: {e}")
        db.close()

@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def process_document_task(self, document_id: str, old_version: int = None):
    """
    Celery task that wraps the core ingestion process.
    """
    try:
        run_document_ingestion(document_id, old_version)
        # If this was a re-ingestion, trigger deletion of the old vectors safely
        if old_version is not None:
            delete_old_vectors_task.delay(document_id, old_version)
    except Exception as e:
        error_msg = str(e).lower()
        if "429" in error_msg or "quota" in error_msg:
            logger.error(f"Permanent API Error (Rate Limit/Quota). Stopping retries for Document {document_id}")
            return # Fail gracefully, DB is already marked as FAILED in run_document_ingestion
        # Re-raise to trigger celery retry logic
        raise self.retry(exc=e, countdown=60)
