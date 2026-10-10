from uuid import UUID
from fastapi import HTTPException
from src.repositories.postgres.document_repository import DocumentRepository
from src.schemas.document_schema import DocumentCreate, DocumentUpdate, PresignedUrlResponse
from src.models.document_model import Document, ProcessingStatus
from src.models.system_model import CleanupJob, DeletionStatus
from src.repositories.s3.storage_repository import S3Storage
from src.workers.tasks.ingestion_tasks import process_document_task
from src.workers.tasks.cleanup_tasks import cleanup_document_task
from src.models.academic_model import CourseOffering
import uuid

class DocumentService:
    def __init__(self, repository: DocumentRepository, s3_storage: S3Storage = None):
        self.repository = repository
        self.s3_storage = s3_storage or S3Storage()

    def generate_upload_url(self, user_id: UUID, filename: str, content_type: str, course_offering_id: UUID) -> PresignedUrlResponse:
        offering = self.repository.session.get(CourseOffering, course_offering_id)
        if not offering:
            raise HTTPException(status_code=404, detail="Course offering not found")
        
        dept_code = offering.course.department.code
        course_code = offering.course.code
        offering_str = f"{offering.year}_{offering.semester.value}"
        
        unique_file_key = f"documents/{dept_code}/{course_code}/{offering_str}/{uuid.uuid4()}_{filename}"
        presigned_data = self.s3_storage.generate_presigned_url(
            file_key=unique_file_key,
            content_type=content_type
        )
        return PresignedUrlResponse(
            upload_url=presigned_data["url"],
            file_key=presigned_data["file_key"]
        )

    def generate_download_url(self, document_id: UUID) -> str:
        doc = self.get_document(document_id)
        if not doc.s3_key:
            raise HTTPException(status_code=400, detail="Document has no associated file")
            
        presigned_data = self.s3_storage.generate_presigned_url(
            file_key=doc.s3_key,
            action="get_object"
        )
        return presigned_data["url"]

    def upload_document(self, doc_in: DocumentCreate) -> Document:
        # Save the record with PENDING status.
        doc = self.repository.create_document(doc_in)
        
        # Trigger the asynchronous Celery pipeline
        process_document_task.delay(str(doc.id))
        
        return doc

    def get_document(self, document_id: UUID) -> Document:
        doc = self.repository.get_document(document_id)
        if not doc or doc.is_deleted:
            raise HTTPException(status_code=404, detail="Document not found")
        return doc

    def delete_document(self, document_id: UUID):
        doc = self.repository.get_document(document_id)
        if not doc or doc.is_deleted:
            raise HTTPException(status_code=404, detail="Document not found")
            
        # Soft delete
        doc.is_deleted = True
        doc.deletion_status = DeletionStatus.PENDING
        self.repository.session.commit()
        
        # Create cleanup job
        job = CleanupJob(resource_type="DOCUMENT", resource_id=document_id)
        self.repository.session.add(job)
        self.repository.session.commit()
        self.repository.session.refresh(job)
        
        # Dispatch Celery Task
        cleanup_document_task.delay(str(document_id), str(job.id))
        
        return doc

    def get_documents_for_offering(self, offering_id: UUID) -> list[Document]:
        return self.repository.get_documents_by_offering(offering_id)

    def get_local_documents(self) -> list[Document]:
        return self.repository.get_local_documents()

    def update_document(self, document_id: UUID, doc_update: DocumentUpdate) -> Document:
        doc = self.get_document(document_id)
        return self.repository.update_document(doc, doc_update)

    def mark_processing_complete(self, document_id: UUID, qdrant_id: str) -> Document:
        doc = self.repository.update_status(document_id, ProcessingStatus.COMPLETED, qdrant_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        return doc
        return doc
