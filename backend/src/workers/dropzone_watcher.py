import os
import time
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

logger = logging.getLogger("dropzone_watcher")

class DropzoneHandler(FileSystemEventHandler):
    def __init__(self, dropzone_path):
        self.dropzone_path = dropzone_path
        self.processing_files = set()

    def on_created(self, event):
        if event.is_directory or not event.src_path.lower().endswith('.pdf'):
            return
            
        file_path = event.src_path
        logger.info(f"Dropzone detected new file: {file_path}")
        self._process_file(file_path)

    def _process_file(self, file_path):
        # Wait until the OS finishes copying the file to the dropzone
        historical_size = -1
        while True:
            try:
                current_size = os.path.getsize(file_path)
                if current_size == historical_size and current_size > 0:
                    break
                historical_size = current_size
                time.sleep(1)
            except OSError:
                # File might be temporarily locked or moved
                time.sleep(1)

        logger.info(f"File write complete for {file_path}. Registering in local database...")
        
        try:
            from src.infrastructure.database import SessionLocal
            from src.models.document_model import Document, ProcessingStatus
            from src.models.academic_model import CourseOffering, Course, Department
            import uuid
            
            db = SessionLocal()
            
            # Find any course offering to attach this to (or create a default "Local Dropzone" one)
            offering = db.query(CourseOffering).first()
            if not offering:
                logger.info("No courses found. Creating default 'Local Library' course...")
                dept = Department(id=uuid.uuid4(), code="LOCAL", name="Local Library")
                course = Course(id=uuid.uuid4(), department_id=dept.id, code="LOC101", title="Local Dropzone Files")
                offering = CourseOffering(id=uuid.uuid4(), course_id=course.id, year=2026, semester="AUTUMN")
                db.add(dept)
                db.add(course)
                db.add(offering)
                db.commit()
                db.refresh(offering)
                
            filename = os.path.basename(file_path)
            
            # Create the document record
            new_doc = Document(
                id=uuid.uuid4(),
                course_offering_id=offering.id,
                title=filename,
                description="Imported via Local Dropzone",
                doc_type="PDF",
                format="PDF",
                s3_key=file_path,  # Storing the local path here for offline mode
                file_size_bytes=os.path.getsize(file_path),
                status=ProcessingStatus.PENDING
            )
            db.add(new_doc)
            db.commit()
            
            doc_id = str(new_doc.id)
            db.close()
            
            logger.info(f"Registered document {doc_id}. Triggering offline ingestion...")
            
            # Import here to avoid circular imports at Celery worker boot time
            from src.workers.tasks.ingestion_tasks import process_document_task
            process_document_task.delay(document_id=doc_id, old_version=None)
            
        except Exception as e:
            logger.error(f"Failed to register dropzone file {file_path}: {e}")

def start_watcher():
    dropzone_path = os.path.expanduser("~/KgpOne_Dropzone")
    os.makedirs(dropzone_path, exist_ok=True)
    
    logger.info(f"Starting Dropzone Watcher on {dropzone_path}")
    
    event_handler = DropzoneHandler(dropzone_path)
    observer = Observer()
    observer.schedule(event_handler, dropzone_path, recursive=False)
    observer.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    start_watcher()
