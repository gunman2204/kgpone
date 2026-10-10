import uuid
from src.infrastructure.database import SessionLocal
from src.models.document_model import Document
from src.workers.dropzone_watcher import get_local_course_offering_id

db = SessionLocal()
try:
    loc_id = get_local_course_offering_id(db)
    docs = db.query(Document).filter(Document.course_offering_id != loc_id).all()
    count = 0
    for doc in docs:
        if doc.s3_key and doc.s3_key.startswith("/"): # it's a local file
            doc.course_offering_id = loc_id
            count += 1
    db.commit()
    print(f"Fixed {count} documents.")
finally:
    db.close()
