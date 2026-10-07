from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import select
from src.models.document_model import Document, DocumentMetadata, ProcessingStatus
from src.schemas.document_schema import DocumentCreate, DocumentUpdate

class DocumentRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_document(self, document_id: UUID | str) -> Document | None:
        import uuid
        if isinstance(document_id, str):
            document_id = uuid.UUID(document_id)
        return self.session.get(Document, document_id)

    def get_documents_by_offering(self, offering_id: UUID) -> list[Document]:
        stmt = select(Document).where(Document.course_offering_id == offering_id)
        return list(self.session.scalars(stmt).all())

    def create_document(self, doc_in: DocumentCreate) -> Document:
        doc = Document(
            course_offering_id=doc_in.course_offering_id,
            uploader_id=doc_in.uploader_id,
            title=doc_in.title,
            description=doc_in.description,
            doc_type=doc_in.doc_type,
            format=doc_in.format,
            s3_key=doc_in.s3_key,
            file_size_bytes=doc_in.file_size_bytes
        )
        self.session.add(doc)
        
        # Add metadata
        for meta_in in doc_in.metadata_entries:
            meta = DocumentMetadata(
                document=doc,
                key=meta_in.key,
                value=meta_in.value
            )
            self.session.add(meta)
            
        self.session.commit()
        self.session.refresh(doc)
        return doc

    def update_document(self, document: Document, doc_update: DocumentUpdate) -> Document:
        update_data = doc_update.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(document, field, value)
        self.session.add(document)
        self.session.commit()
        self.session.refresh(document)
        return document

    def update_status(self, document_id: UUID, status: ProcessingStatus, qdrant_id: str | None = None) -> Document | None:
        doc = self.get_document(document_id)
        if doc:
            doc.status = status
            if qdrant_id:
                doc.qdrant_collection_id = qdrant_id
            self.session.add(doc)
            self.session.commit()
            self.session.refresh(doc)
        return doc
