from uuid import UUID
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from src.infrastructure.database import get_db
from src.schemas.document_schema import (
    DocumentCreate, DocumentRead, DocumentUpdate,
    PresignedUrlRequest, PresignedUrlResponse
)
from src.repositories.postgres.document_repository import DocumentRepository
from src.services.ingestion.upload_manager.document_service import DocumentService
from src.models.user_model import User, UserRole
from src.api.middleware.auth_middleware import get_current_user, require_role
from src.schemas.response_schema import StandardResponse

router = APIRouter(prefix="/documents", tags=["Documents"])

def get_document_service(db: Session = Depends(get_db)) -> DocumentService:
    repo = DocumentRepository(db)
    return DocumentService(repo)

@router.post("/presigned-url", response_model=StandardResponse[PresignedUrlResponse], status_code=status.HTTP_201_CREATED)
def get_presigned_url(req: PresignedUrlRequest, service: DocumentService = Depends(get_document_service), user: User = Depends(require_role([UserRole.ADMIN, UserRole.PUBLISHER]))):
    data = service.generate_upload_url(user.id, req.filename, req.content_type, req.course_offering_id)
    return StandardResponse(status="success", message="Presigned URL generated successfully", data=data)

@router.post("/", response_model=StandardResponse[DocumentRead], status_code=status.HTTP_201_CREATED)
def upload_document(doc_in: DocumentCreate, service: DocumentService = Depends(get_document_service), user: User = Depends(require_role([UserRole.ADMIN, UserRole.PUBLISHER]))):
    data = service.upload_document(doc_in)
    return StandardResponse(status="success", message="Document metadata saved successfully", data=data)

@router.get("/offering/{offering_id}", response_model=StandardResponse[list[DocumentRead]])
def list_documents_for_offering(offering_id: UUID, service: DocumentService = Depends(get_document_service), user: User = Depends(get_current_user)):
    data = service.get_documents_for_offering(offering_id)
    return StandardResponse(status="success", message="Documents retrieved successfully", data=data)

@router.get("/watcher-health", response_model=StandardResponse[dict])
def watcher_health():
    from src.workers.watcher_manager import watcher_manager
    data = watcher_manager.health()
    return StandardResponse(status="success", message="Watcher health retrieved", data=data)

@router.get("/local", response_model=StandardResponse[list[DocumentRead]])
def get_local_documents(service: DocumentService = Depends(get_document_service), user: User = Depends(get_current_user)):
    data = service.get_local_documents()
    return StandardResponse(status="success", message="Local documents retrieved successfully", data=data)

@router.get("/{document_id}", response_model=StandardResponse[DocumentRead])
def get_document(document_id: UUID, service: DocumentService = Depends(get_document_service), user: User = Depends(get_current_user)):
    data = service.get_document(document_id)
    return StandardResponse(status="success", message="Document retrieved successfully", data=data)

@router.get("/{document_id}/download", response_model=StandardResponse[str])
def download_document(document_id: UUID, service: DocumentService = Depends(get_document_service), user: User = Depends(get_current_user)):
    url = service.generate_download_url(document_id)
    return StandardResponse(status="success", message="Download URL generated", data=url)

@router.patch("/{document_id}", response_model=StandardResponse[DocumentRead])
def update_document(document_id: UUID, doc_update: DocumentUpdate, service: DocumentService = Depends(get_document_service), user: User = Depends(require_role([UserRole.ADMIN, UserRole.PUBLISHER]))):
    data = service.update_document(document_id, doc_update)
    return StandardResponse(status="success", message="Document updated successfully. Re-ingestion started.", data=data)

@router.delete("/{document_id}", response_model=StandardResponse[DocumentRead])
def delete_document(document_id: UUID, service: DocumentService = Depends(get_document_service), user: User = Depends(require_role([UserRole.ADMIN, UserRole.PUBLISHER]))):
    data = service.delete_document(document_id)
    return StandardResponse(status="success", message="Document soft-deleted. Cleanup job dispatched successfully.", data=data)
