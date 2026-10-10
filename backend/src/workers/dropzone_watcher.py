"""
dropzone_watcher.py — Robust Dropzone Folder Monitor
=====================================================
Watches ~/KgpOne_Dropzone for PDF files and ingests them into the local
pipeline via Celery. Handles:
  - Startup scan: registers any files already in the folder that are
    missing from the database.
  - Deduplication: first by file path (s3_key), then by SHA-256 hash.
  - File deletion: marks the DB record as deleted when the file is removed.
  - Stale duplicate cleanup: removes PENDING duplicate records that share
    the same file path but are older.
"""

import os
import time
import hashlib
import uuid
import logging
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Import all models at startup so SQLAlchemy can resolve all relationship strings
from src.infrastructure.database import SessionLocal  # noqa: F401 — registers Base
from src.models.document_model import Document, DocFormat, ProcessingStatus  # noqa: F401
from src.models.academic_model import CourseOffering, Course, Department, SemesterType  # noqa: F401

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("dropzone_watcher")

DROPZONE_DIR = os.path.expanduser("~/KgpOne_Dropzone")
SUPPORTED_EXTENSIONS = {".pdf"}
os.makedirs(DROPZONE_DIR, exist_ok=True)


# ── Helpers ────────────────────────────────────────────────────────────────

def get_file_hash(filepath: str) -> str | None:
    """Compute SHA-256 hash of a file efficiently. Returns None on failure."""
    try:
        hasher = hashlib.sha256()
        with open(filepath, "rb") as f:
            while chunk := f.read(65_536):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception as e:
        logger.error(f"[Hash] Failed to hash {filepath}: {e}")
        return None


def get_local_offering_id(db) -> uuid.UUID:
    """Returns (and lazily creates) the LOC101 course offering for Dropzone files."""
    from src.models.academic_model import Course, CourseOffering, Department, SemesterType

    course = db.query(Course).filter(Course.code == "LOC101").first()
    if course:
        offering = db.query(CourseOffering).filter(
            CourseOffering.course_id == course.id
        ).first()
        if offering:
            return offering.id

    logger.info("[Setup] Creating LOC / LOC101 department + course + offering …")
    dept = db.query(Department).filter(Department.code == "LOC").first()
    if not dept:
        dept = Department(code="LOC", name="Local System")
        db.add(dept)
        db.flush()

    if not course:
        course = Course(
            code="LOC101",
            title="Local Library",
            department_id=dept.id,
            credits=0,
        )
        db.add(course)
        db.flush()

    offering = CourseOffering(
        course_id=course.id,
        year=2026,
        semester=SemesterType.SUMMER,
    )
    db.add(offering)
    db.commit()
    logger.info(f"[Setup] Created local offering {offering.id}")
    return offering.id


def _cleanup_stale_duplicates(db, filepath: str) -> None:
    """
    Remove PENDING (never processed) records that share the same file path.
    This prevents leftover ghosts from previous watcher crashes.
    """
    from src.models.document_model import Document, ProcessingStatus

    stale = (
        db.query(Document)
        .filter(
            Document.s3_key == filepath,
            Document.status == ProcessingStatus.PENDING,
        )
        .all()
    )
    if stale:
        for d in stale:
            db.delete(d)
        db.commit()
        logger.info(
            f"[Cleanup] Removed {len(stale)} stale PENDING record(s) for {os.path.basename(filepath)}"
        )


def ingest_file(filepath: str) -> None:
    """
    Core ingestion logic — idempotent.
    Returns silently if the file is already processed/processing.
    """
    from src.infrastructure.database import SessionLocal
    from src.models.document_model import Document, DocFormat, ProcessingStatus
    from src.workers.tasks.ingestion_tasks import process_document_task

    filename = os.path.basename(filepath)
    ext = Path(filepath).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        logger.debug(f"[Skip] Unsupported extension: {filename}")
        return

    # Wait for the file write to finish (copy-in may still be in progress)
    time.sleep(1.5)
    if not os.path.exists(filepath):
        logger.warning(f"[Skip] File disappeared before ingestion: {filename}")
        return

    db = SessionLocal()
    try:
        # ── Step 1: path-based deduplication ──────────────────────────
        existing_by_path = (
            db.query(Document)
            .filter(Document.s3_key == filepath)
            .order_by(Document.status.desc())   # COMPLETED before PENDING
            .all()
        )
        if existing_by_path:
            completed = [d for d in existing_by_path if d.status == ProcessingStatus.COMPLETED]
            if completed:
                logger.info(
                    f"[Skip] '{filename}' is already COMPLETED in the DB "
                    f"(doc_id={completed[0].id}). Nothing to do."
                )
                return
            processing = [d for d in existing_by_path if d.status == ProcessingStatus.PROCESSING]
            if processing:
                logger.info(
                    f"[Skip] '{filename}' is currently PROCESSING (doc_id={processing[0].id})."
                )
                return
            # Only PENDING/FAILED left — clean them up and re-ingest
            logger.warning(
                f"[Retry] Found {len(existing_by_path)} PENDING/FAILED record(s) for "
                f"'{filename}'. Removing stale records and re-ingesting."
            )
            for d in existing_by_path:
                db.delete(d)
            db.commit()

        # ── Step 2: hash-based deduplication (catches renames / copies) ─
        file_hash = get_file_hash(filepath)
        if file_hash:
            existing_by_hash = (
                db.query(Document)
                .filter(
                    Document.file_hash == file_hash,
                    Document.status == ProcessingStatus.COMPLETED,
                )
                .first()
            )
            if existing_by_hash:
                logger.info(
                    f"[Skip] '{filename}' has the same content as "
                    f"'{existing_by_hash.title}' (hash match). Skipping duplicate."
                )
                return

        # ── Step 3: register & dispatch ───────────────────────────────
        offering_id = get_local_offering_id(db)
        new_doc = Document(
            id=uuid.uuid4(),
            course_offering_id=offering_id,
            title=filename,
            description="Imported from Local Dropzone",
            doc_type="NOTES",
            format=DocFormat.PDF,
            s3_key=filepath,
            file_size_bytes=os.path.getsize(filepath),
            file_hash=file_hash,
            status=ProcessingStatus.PENDING,
        )
        db.add(new_doc)
        db.commit()
        doc_id = str(new_doc.id)
        logger.info(
            f"[Registered] '{filename}' → doc_id={doc_id} | "
            f"hash={file_hash[:8] if file_hash else 'N/A'}…"
        )

        import threading
        from src.workers.tasks.ingestion_tasks import run_document_ingestion

        thread = threading.Thread(
            target=run_document_ingestion,
            args=(doc_id,),
            daemon=True,
            name=f"ingest-{doc_id[:8]}"
        )
        thread.start()
        logger.info(f"[Thread] Ingestion started in background thread for doc_id={doc_id}")

    except Exception as e:
        logger.error(f"[Error] Failed to ingest '{filename}': {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()


def handle_deletion(filepath: str) -> None:
    """
    When a file is deleted from the Dropzone, mark its DB record as deleted
    and clear its hash so the same content can be re-imported later.
    """
    from src.infrastructure.database import SessionLocal
    from src.models.document_model import Document

    filename = os.path.basename(filepath)
    db = SessionLocal()
    try:
        docs = db.query(Document).filter(Document.s3_key == filepath).all()
        if not docs:
            return
        for d in docs:
            d.is_deleted = True
            d.file_hash = None   # ← Clear hash so the file can be re-imported
        db.commit()
        logger.info(
            f"[Deleted] Marked {len(docs)} record(s) for '{filename}' as deleted "
            f"and cleared hash."
        )
    except Exception as e:
        logger.error(f"[Error] Failed to handle deletion of '{filename}': {e}")
        db.rollback()
    finally:
        db.close()


def startup_scan() -> None:
    """
    On startup, scan the Dropzone directory and ingest any PDF files that
    are not yet COMPLETED or PROCESSING in the database.
    """
    from src.infrastructure.database import SessionLocal
    from src.models.document_model import Document, ProcessingStatus

    logger.info(f"[Startup Scan] Scanning {DROPZONE_DIR} for unprocessed files …")
    db = SessionLocal()
    try:
        completed_paths = {
            d.s3_key
            for d in db.query(Document)
            .filter(
                Document.status.in_([ProcessingStatus.COMPLETED, ProcessingStatus.PROCESSING])
            )
            .all()
        }
    finally:
        db.close()

    all_files = [
        os.path.join(DROPZONE_DIR, f)
        for f in os.listdir(DROPZONE_DIR)
        if Path(f).suffix.lower() in SUPPORTED_EXTENSIONS
    ]

    to_ingest = [f for f in all_files if f not in completed_paths]
    logger.info(
        f"[Startup Scan] Found {len(all_files)} PDF(s); "
        f"{len(to_ingest)} need ingestion."
    )
    for filepath in to_ingest:
        logger.info(f"[Startup Scan] Ingesting: {os.path.basename(filepath)}")
        ingest_file(filepath)


# ── Watchdog handler ───────────────────────────────────────────────────────

class DropzoneHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return
        logger.info(f"[Event] File created: {event.src_path}")
        ingest_file(event.src_path)

    def on_moved(self, event):
        """Handles file-move-into-folder (e.g. via file manager drag-and-drop)."""
        if event.is_directory:
            return
        logger.info(f"[Event] File moved into dropzone: {event.dest_path}")
        ingest_file(event.dest_path)

    def on_deleted(self, event):
        if event.is_directory:
            return
        logger.info(f"[Event] File deleted: {event.src_path}")
        handle_deletion(event.src_path)


def reconciliation_loop(stop_event):
    """Re-queues PENDING documents whose files still exist on disk."""
    from src.infrastructure.database import SessionLocal
    from src.models.document_model import Document, ProcessingStatus
    import threading
    from src.workers.tasks.ingestion_tasks import run_document_ingestion

    while stop_event and not stop_event.is_set():
        # wait in chunks so it can exit quickly on stop
        for _ in range(60): 
            if stop_event.is_set():
                break
            time.sleep(5)
            
        if stop_event.is_set():
            break

        db = SessionLocal()
        try:
            stuck = (
                db.query(Document)
                .filter(
                    Document.status == ProcessingStatus.PENDING,
                    Document.is_deleted == False
                )
                .all()
            )
            if stuck:
                logger.info(f"[Reconciliation] Found {len(stuck)} stuck PENDING document(s). Re-queuing …")
                for doc in stuck:
                    if doc.s3_key and os.path.exists(doc.s3_key):
                        thread = threading.Thread(
                            target=run_document_ingestion,
                            args=(str(doc.id),),
                            daemon=True,
                            name=f"ingest-{str(doc.id)[:8]}"
                        )
                        thread.start()
                        logger.info(f"[Reconciliation] Re-queued doc {doc.id}: {doc.title}")
                    else:
                        doc.status = ProcessingStatus.FAILED
                db.commit()
        except Exception as e:
            logger.error(f"[Reconciliation] Error: {e}")
        finally:
            db.close()

# ── Entry point ────────────────────────────────────────────────────────────

def start_watcher(stop_event=None):
    logger.info(f"[Watcher] Starting Dropzone Watcher on: {DROPZONE_DIR}")

    import threading
    if stop_event is None:
        stop_event = threading.Event()

    startup_scan()

    event_handler = DropzoneHandler()
    observer = Observer()
    observer.schedule(event_handler, DROPZONE_DIR, recursive=False)
    observer.start()
    
    recon_thread = threading.Thread(target=reconciliation_loop, args=(stop_event,), daemon=True, name="reconciliation")
    recon_thread.start()
    
    logger.info("[Watcher] Watchdog observer is running. Press Ctrl+C to stop.")
    try:
        while not stop_event.is_set():
            time.sleep(2)
    except KeyboardInterrupt:
        logger.info("[Watcher] Shutting down …")
        stop_event.set()
    finally:
        observer.stop()
        observer.join()

if __name__ == "__main__":
    start_watcher()
