import os
import httpx
from fastapi import APIRouter
from sqlalchemy import text
from src.infrastructure.database import is_postgres_healthy, LocalSessionLocal
from src.infrastructure.qdrant import get_qdrant_client, get_local_qdrant_client
from src.workers.watcher_manager import watcher_manager
from src.models.document_model import Document
from src.schemas.response_schema import StandardResponse

router = APIRouter(prefix="/system", tags=["System & Diagnostics"])

@router.get("/diagnostics")
async def get_system_diagnostics():
    """
    Returns live health telemetry for all 7 subsystems across online and offline stacks.
    Provides actionable diagnostics for users and developers.
    """
    results = {}

    # 1. Cloud Postgres
    cloud_db_ok = is_postgres_healthy()
    results["cloud_database"] = {
        "status": "online" if cloud_db_ok else "unreachable",
        "description": "Neon PostgreSQL Serverless",
        "action": None if cloud_db_ok else "Operating in local SQLite mode."
    }

    # 2. Local SQLite
    local_doc_count = 0
    try:
        with LocalSessionLocal() as session:
            local_doc_count = session.query(Document).filter(Document.is_deleted == False).count()
        results["local_database"] = {
            "status": "ready",
            "active_documents": local_doc_count,
            "path": "./kgpone_offline.db"
        }
    except Exception as e:
        results["local_database"] = {
            "status": "error",
            "detail": str(e)
        }

    # 3. Cloud Qdrant
    cloud_qdrant = get_qdrant_client()
    results["cloud_vector_store"] = {
        "status": "online" if cloud_qdrant is not None else "unreachable",
        "description": "Cloud Qdrant Vector Cluster"
    }

    # 4. Local Qdrant
    local_qdrant = get_local_qdrant_client()
    results["local_vector_store"] = {
        "status": "ready" if local_qdrant is not None else "degraded",
        "description": "Local Disk Qdrant Storage"
    }

    # 5. Local Ollama LLM
    ollama_models = []
    ollama_status = "offline"
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get("http://127.0.0.1:11434/api/tags")
            if resp.status_code == 200:
                data = resp.json()
                ollama_models = [m.get("name") for m in data.get("models", [])]
                ollama_status = "ready" if ollama_models else "no_models"
    except Exception:
        ollama_status = "offline"

    results["local_llm_ollama"] = {
        "status": ollama_status,
        "models": ollama_models,
        "action": None if ollama_status == "ready" else "Start via 'ollama serve' or run grounded offline fallback."
    }

    # 6. Infinity Local Embeddings
    infinity_status = "offline"
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get("http://localhost:7997/models")
            if resp.status_code == 200:
                infinity_status = "ready"
    except Exception:
        infinity_status = "offline"

    results["local_embeddings_infinity"] = {
        "status": infinity_status,
        "endpoint": "http://localhost:7997",
        "action": None if infinity_status == "ready" else "Fallback to FastEmbed / deterministic embedding."
    }

    # 7. Dropzone Watcher
    dropzone_dir = os.path.expanduser("~/KgpOne_Dropzone")
    watcher_health = watcher_manager.health()
    file_count = 0
    if os.path.exists(dropzone_dir):
        file_count = len([f for f in os.listdir(dropzone_dir) if f.lower().endswith(".pdf")])

    results["dropzone_watcher"] = {
        "status": watcher_health.get("status", "stopped"),
        "directory": dropzone_dir,
        "pdf_files_in_folder": file_count,
        "crash_count": watcher_health.get("crash_count", 0),
        "last_error": watcher_health.get("last_error")
    }

    return StandardResponse(
        status="success",
        message="System diagnostics gathered successfully",
        data=results
    )
